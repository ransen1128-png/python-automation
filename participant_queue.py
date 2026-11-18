"""Desktop queue: prepare one response, await manual submission, then advance."""
import argparse
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from survey_automation import ROOT, FORM_URL, load_participants, questions_from_schema, draft_ratings

DEFAULT_STATE = ROOT / '.survey_queue_state.json'
CONFIRMATIONS = ('your response has been recorded', 'naitala na ang iyong tugon', 'naitala na ang iyong sagot')


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def participant_id(person):
    return hashlib.sha256((normalized(person['first_name'])+'\0'+normalized(person['last_name'])).encode()).hexdigest()


def person_answers(questions, person):
    supplied = {normalized(key): value for key, value in person['answers'].items()}
    result, missing = [], []
    for question in questions:
        answer = question['draft'] if question['kind']=='rating' else supplied.get(normalized(question['question']), '')
        values = answer if isinstance(answer, list) else [answer] if answer else []
        valid = bool(values) and (not question['options'] or all(value in question['options'] for value in values))
        if question['required'] and not valid:
            missing.append(question['question'])
        if valid:
            result.extend(('entry.'+question['entry'], str(value)) for value in values)
    return result, missing


def prefilled_url(questions, person):
    answers, missing = person_answers(questions, person)
    if missing:
        raise ValueError('Participant details are incomplete: '+', '.join(missing))
    return FORM_URL+'?'+urlencode([('usp','pp_url'),('hl','en'),*answers])


def read_state(path):
    if not path.exists():
        return {'version':1, 'form':FORM_URL, 'completed':{}}
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('version')!=1 or value.get('form')!=FORM_URL or not isinstance(value.get('completed'),dict):
        raise ValueError('Progress file is invalid or belongs to another survey. It was not reset.')
    return value


def save_state(path, state):
    temporary = path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w',encoding='utf-8') as handle:
        json.dump(state,handle,indent=2)
        handle.flush();os.fsync(handle.fileno())
    temporary.replace(path)


class QueueLock:
    def __init__(self,path):self.path=path
    def __enter__(self):
        self.handle=self.path.open('a+b');self.handle.write(b'0');self.handle.flush();self.handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise ValueError('A participant queue is already running. Use its existing browser window.')
        return self
    def __exit__(self,*args):self.handle.close()


def confirmed_response(url, text, has_form, status, custom_text=None):
    current, expected = urlparse(url), urlparse(FORM_URL)
    if (current.hostname!=expected.hostname or current.path!=expected.path.replace('/viewform','/formResponse')
        or status!=200 or has_form):
        return False
    choices = (*CONFIRMATIONS, custom_text) if custom_text else CONFIRMATIONS
    return any(normalized(marker) in normalized(text) for marker in choices)


class AutoNextNavigator:
    """Click only an exact Next button; permanently stop auto-navigation at Submit."""
    def __init__(self):
        self.at_submit=False
        self.last_key=None
        self.stable_polls=0
        self.attempted=set()

    @staticmethod
    def visible_button(page,labels):
        buttons=page.get_by_role('button',name=re.compile(r'^\s*(?:'+labels+r')\s*$',re.IGNORECASE))
        for index in range(buttons.count()):
            button=buttons.nth(index)
            if button.is_visible():return button
        return None

    def step(self,page,status):
        if self.at_submit or status!=200:return
        current,expected=urlparse(page.url),urlparse(FORM_URL)
        if current.hostname!=expected.hostname or current.path not in (expected.path,expected.path.replace('/viewform','/formResponse')):return
        if not page.locator('form[action*="formResponse"]').count():return
        if self.visible_button(page,'Submit|Isumite') is not None:
            self.at_submit=True
            print('Reached Submit. Review the response and click Submit yourself. You can use Back to review earlier pages.',flush=True)
            return
        button=self.visible_button(page,'Next|Susunod')
        if button is None or not button.is_enabled():return
        snapshot=page.evaluate('''() => ({
            ready:document.readyState,
            url:location.href,
            history:document.querySelector('input[name="pageHistory"]')?.value || '',
            headings:[...document.querySelectorAll('[role="heading"]')].map(e=>e.textContent),
            inputs:[...document.querySelectorAll('input:not([type="hidden"]),textarea,select')].map(e=>[e.type,e.value,e.checked]),
            choices:[...document.querySelectorAll('[role="radio"],[role="checkbox"]')].map(e=>[e.getAttribute('aria-label'),e.getAttribute('aria-checked')])
        })''')
        if snapshot['ready']!='complete':return
        key=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()
        if key!=self.last_key:
            self.last_key=key;self.stable_polls=0
            return
        self.stable_polls+=1
        if self.stable_polls<2 or key in self.attempted:return
        # Store before clicking so a timeout cannot trigger repeat clicks on an unchanged page.
        self.attempted.add(key)
        print('Advancing to the next form page...',flush=True)
        button.click(timeout=4000)


def watch_manual_submission(page, *, custom_text=None, status_getter, stopped=lambda: False, auto_next=True):
    """Navigate Next pages if enabled, then observe final manual submission only."""
    from playwright.sync_api import Error
    navigator=AutoNextNavigator() if auto_next else None
    while not page.is_closed() and not stopped():
        try:
            if urlparse(page.url).path.endswith('/formResponse'):
                has_form = page.locator('form[action*="formResponse"]').count()>0
                if not has_form:
                    text = page.locator('body').inner_text(timeout=2000)
                    if confirmed_response(page.url,text,has_form,status_getter(),custom_text):
                        return True
            if navigator:navigator.step(page,status_getter())
            page.wait_for_timeout(350)
        except Error:
            if page.is_closed() or stopped():return False
            # A page transition can briefly destroy the document being inspected.
            page.wait_for_timeout(350)
    return False


def process_participant(page, person, questions, state, state_path, custom_text=None, manual_next=False):
    status = {'code':None}
    def navigated(response):
        try:
            if response.request.is_navigation_request() and response.frame==page.main_frame:
                status['code']=response.status
        except Exception:
            pass
    page.on('response',navigated)
    try:
        response=page.goto(prefilled_url(questions,person),wait_until='domcontentloaded',timeout=60000)
        status['code']=response.status if response else None
        if not watch_manual_submission(page,custom_text=custom_text,status_getter=lambda:status['code'],auto_next=not manual_next):
            return False
        entry={'confirmed_utc':datetime.now(timezone.utc).isoformat(),
            'details_sha256':hashlib.sha256(json.dumps(person['answers'],sort_keys=True).encode()).hexdigest()}
        state['completed'][participant_id(person)]=entry
        save_state(state_path,state)
        return True
    finally:
        page.remove_listener('response',navigated)


def make_queue(people,questions,state):
    pending,incomplete,seen=[],[],set()
    for person in people:
        key=participant_id(person)
        if key in seen:raise ValueError('Duplicate participant names found. Resolve them before starting the queue.')
        seen.add(key)
        if key in state['completed']:continue
        _,missing=person_answers(questions,person)
        if missing:incomplete.append((person,missing))
        else:pending.append(person)
    return pending,incomplete


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-only',action='store_true',help='Show counts without opening a browser or submitting anything.')
    parser.add_argument('--reset-progress',action='store_true',help='Start over explicitly; preserves a private backup of the previous progress file.')
    parser.add_argument('--limit',type=int,help='Stop after this many manually confirmed responses in this run.')
    parser.add_argument('--manual-next',action='store_true',help='Disable automatic Next clicks and review each page manually.')
    parser.add_argument('--confirmation-text',help='Exact custom Google confirmation text if the form owner changed the default.')
    args=parser.parse_args()
    if args.limit is not None and args.limit<1:parser.error('--limit must be positive')
    if args.confirmation_text and len(args.confirmation_text.strip())<12:parser.error('Provide the full custom confirmation message, at least 12 characters.')
    try:
        with QueueLock(ROOT/'.survey_queue.lock'):
            state=read_state(DEFAULT_STATE)
            if args.reset_progress:
                if DEFAULT_STATE.exists():
                    backup=ROOT/('.survey_queue_state.'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.backup.json')
                    backup.write_bytes(DEFAULT_STATE.read_bytes())
                state={'version':1,'form':FORM_URL,'completed':{}}
                if not args.plan_only:save_state(DEFAULT_STATE,state)
            schema=json.loads((ROOT/'form_schema.json').read_text(encoding='utf-8'))
            questions=questions_from_schema(schema);draft_ratings(questions)
            people=load_participants();pending,incomplete=make_queue(people,questions,state)
            print(f'Participants: {len(people)} | Pending and ready: {len(pending)} | Completed: {len(state["completed"])} | Incomplete: {len(incomplete)}',flush=True)
            if incomplete:
                print('Incomplete participants are skipped until their actual missing details are added to participants.csv.',flush=True)
            if args.plan_only or not pending:return 0
            print('Next pages advance automatically unless --manual-next is selected. The final Submit button is always manual.',flush=True)
            print('Review the response before you submit. After Google confirms it, the next participant opens automatically.',flush=True)
            print('Closing the browser stops the queue. Completed participants are remembered; unconfirmed responses remain pending.',flush=True)
            from playwright.sync_api import sync_playwright,Error
            with sync_playwright() as playwright:
                browser=None
                for channel in ('chrome','msedge'):
                    try:
                        browser=playwright.chromium.launch(channel=channel,headless=False)
                        break
                    except Error:pass
                if browser is None:
                    raise ValueError('Install Google Chrome or Microsoft Edge, then run Start Survey again.')
                try:
                    for number,person in enumerate(pending[:args.limit],1):
                        if not browser.is_connected():break
                        context=browser.new_context(locale='en-US',viewport={'width':1200,'height':900})
                        page=context.new_page()
                        print(f'[{number}/{min(len(pending),args.limit or len(pending))}] {person["name"]} - waiting for your review and manual submission.',flush=True)
                        if not process_participant(page,person,questions,state,DEFAULT_STATE,args.confirmation_text,args.manual_next):
                            print('Stopped. The current participant was not marked completed.',flush=True)
                            break
                        print('Google confirmed the response. Progress saved.',flush=True)
                        context.close()
                    else:print('This queue run is finished.',flush=True)
                finally:
                    if browser.is_connected():browser.close()
            return 0
    except KeyboardInterrupt:
        print('\nStopped. Confirmed progress is saved. Run Start Survey to resume.')
        return 130
    except Exception as error:
        print(f'Queue stopped: {error}\nConfirmed progress is retained. The current response was not assumed submitted.')
        return 1


if __name__=='__main__':raise SystemExit(main())
