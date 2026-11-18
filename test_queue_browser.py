"""Offline browser fixtures. All Google requests are intercepted, never sent."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse
from participant_queue import FORM_URL,process_participant,make_queue,read_state,watch_manual_submission,AutoNextNavigator,AutoSubmitter,participant_id
from survey_automation import ROOT,questions_from_schema,draft_ratings
from test_participant_queue import example_person


@unittest.skipUnless(importlib.util.find_spec('playwright'),'Desktop Playwright dependency not installed')
class OfflineQueueBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright,Error
        cls.playwright=sync_playwright().start()
        try:cls.browser=cls.playwright.chromium.launch(channel='chrome',headless=True)
        except Error as error:
            cls.playwright.stop();raise unittest.SkipTest(str(error))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.playwright.stop()

    def setUp(self):
        self.context=self.browser.new_context();self.page=self.context.new_page();self.requests=[]
        self.questions=questions_from_schema(json.loads((ROOT/'form_schema.json').read_text(encoding='utf-8')))
        draft_ratings(self.questions)

    def tearDown(self):self.context.close()

    def test_manual_confirmation_advances_queue_and_resume_skips_completed(self):
        def route(request):
            self.requests.append(request.request.method)
            if urlparse(request.request.url).path.endswith('/viewform'):
                # Simulate the tester manually clicking Submit in this offline fixture.
                request.fulfill(content_type='text/html',body='''<html><body>
                <form action="formResponse"><button type="button" id="manual">Fixture manual submit</button></form>
                <script>document.getElementById('manual').onclick=()=>location.href=location.pathname.replace('/viewform','/formResponse');
                setTimeout(()=>document.getElementById('manual').click(),150);</script></body></html>''')
            else:request.fulfill(content_type='text/html',body='<html><body>Your response has been recorded.</body></html>')
        self.context.route('**/*',route)
        people=[example_person('Test','Alpha'),example_person('Test','Beta')]
        state={'version':1,'form':FORM_URL,'completed':{}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            for count,person in enumerate(people,1):
                self.assertTrue(process_participant(self.page,person,self.questions,state,path))
                self.assertEqual(len(read_state(path)['completed']),count)
                pending,_=make_queue(people,self.questions,read_state(path))
                self.assertEqual(len(pending),len(people)-count)
            self.assertEqual(make_queue(people,self.questions,read_state(path))[0],[])
        self.assertTrue(self.requests)
        self.assertTrue(all(method=='GET' for method in self.requests))

    def test_server_error_never_counts_as_recorded(self):
        self.context.route('**/*',lambda route:route.fulfill(status=500,content_type='text/html',body='Your response has been recorded.'))
        self.page.goto(FORM_URL.replace('/viewform','/formResponse'))
        checks={'count':0}
        def stopped():
            checks['count']+=1
            return checks['count']>3
        self.assertFalse(watch_manual_submission(self.page,status_getter=lambda:500,stopped=stopped))

    def test_automatic_queue_submits_once_leaves_suggestions_blank_and_resumes(self):
        submissions=[]
        fixture='''<html><body><script>
        window.showStage=n=>{
          document.body.innerHTML='<form action="formResponse"><h1 role="heading">Section '+n+'</h1>'+
          (n<5?'<button type="button" onclick="showStage('+(n+1)+')">Next</button>':
          '<div role="listitem">Your recommendations:<textarea>Old draft suggestion</textarea></div><button type="button" onclick="sendResponse()">Submit</button>')+'</form>';
        };
        window.sendResponse=()=>location.href=location.pathname.replace('/viewform','/formResponse')+'?suggestion='+encodeURIComponent(document.querySelector('textarea').value);
        showStage(0);
        </script></body></html>'''
        def route(request):
            if urlparse(request.request.url).path.endswith('/viewform'):
                request.fulfill(content_type='text/html',body=fixture)
            else:
                # The intent must already be on disk before the Submit click.
                self.assertEqual(len(read_state(path).get('in_flight',{})),1)
                submissions.append(request.request.url)
                request.fulfill(content_type='text/html',body='Your response has been recorded.')
        self.context.route('**/*',route)
        people=[example_person('Automatic','Alpha'),example_person('Automatic','Beta')]
        state={'version':1,'form':FORM_URL,'completed':{}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            for count,person in enumerate(people,1):
                self.assertTrue(process_participant(self.page,person,self.questions,state,path))
                saved=read_state(path)
                self.assertEqual(len(saved['completed']),count)
                self.assertEqual(saved['in_flight'],{})
                self.assertEqual(len(make_queue(people,self.questions,saved)[0]),len(people)-count)
        self.assertEqual(len(submissions),2)
        self.assertTrue(all(url.endswith('?suggestion=') for url in submissions))

    def test_uncertain_submit_is_not_repeated_or_marked_completed(self):
        fixture='''<form action="formResponse"><div role="listitem">Your recommendations:<textarea></textarea></div>
        <button type="button" onclick="window.clicks=(window.clicks||0)+1">Submit</button></form>'''
        self.context.route('**/*',lambda route:route.fulfill(content_type='text/html',body=fixture))
        self.page.goto(FORM_URL)
        state={'version':1,'form':FORM_URL,'completed':{}}
        person=example_person()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            def intent():
                state['in_flight']={participant_id(person):{'started_utc':'fixture'}}
                from participant_queue import save_state
                save_state(path,state)
            submitter=AutoSubmitter(intent)
            for _ in range(15):submitter.step(self.page,200)
            self.assertEqual(self.page.evaluate('window.clicks'),1)
            saved=read_state(path)
            self.assertEqual(saved['completed'],{})
            self.assertEqual(make_queue([person],self.questions,saved)[0],[])

    def test_auto_next_reaches_final_page_and_never_clicks_submit(self):
        fixture='''<html><body><script>
        window.nextClicks=0;window.submitClicks=0;
        window.showStage=n=>{
          window.stage=n;
          document.body.innerHTML='<form action="formResponse"><h1 role="heading">Section '+(n+1)+'</h1>'+
            (n<5?'<div role="button" tabindex="0" onclick="window.nextClicks++;showStage(window.stage+1)">Next</div>':
             '<button type="button" onclick="window.submitClicks++">Submit</button>')+
            (n>0?'<button type="button" onclick="showStage(window.stage-1)">Back</button>':'')+'</form>';
        };showStage(0);
        </script></body></html>'''
        self.context.route('**/*',lambda route:route.fulfill(content_type='text/html',body=fixture))
        self.page.goto(FORM_URL);navigator=AutoNextNavigator()
        for _ in range(30):navigator.step(self.page,200)
        self.assertTrue(navigator.at_submit)
        self.assertEqual(self.page.evaluate('window.nextClicks'),5)
        self.assertEqual(self.page.evaluate('window.submitClicks'),0)
        self.page.get_by_role('button',name='Back',exact=True).click()
        for _ in range(8):navigator.step(self.page,200)
        self.assertEqual(self.page.evaluate('window.stage'),4)
        self.assertEqual(self.page.evaluate('window.nextClicks'),5)

    def test_validation_pause_retries_only_after_answers_change(self):
        fixture='''<html><body><form action="formResponse"><h1 role="heading">Age</h1>
        <input id="age" value=""><p role="alert" id="error"></p>
        <div role="button" tabindex="0" onclick="window.nextStep()">Next</div>
        </form><script>window.clicks=0;window.nextStep=()=>{
          window.clicks++;
          if(!document.getElementById('age').value){document.getElementById('error').textContent='Required';}
          else{document.body.innerHTML='<form action="formResponse"><button type="button">Submit</button></form>';}
        };</script></body></html>'''
        self.context.route('**/*',lambda route:route.fulfill(content_type='text/html',body=fixture))
        self.page.goto(FORM_URL);navigator=AutoNextNavigator()
        for _ in range(12):navigator.step(self.page,200)
        self.assertEqual(self.page.evaluate('window.clicks'),1)
        self.page.locator('#age').fill('30')
        for _ in range(8):navigator.step(self.page,200)
        self.assertEqual(self.page.evaluate('window.clicks'),2)
        self.assertTrue(navigator.at_submit)

    def test_visible_submit_takes_priority_over_next(self):
        fixture='<form action="formResponse"><button type="button" onclick="window.clicked=true">Next</button><button type="button" onclick="window.clicked=true">Submit</button></form>'
        self.context.route('**/*',lambda route:route.fulfill(content_type='text/html',body=fixture))
        self.page.goto(FORM_URL);navigator=AutoNextNavigator()
        for _ in range(8):navigator.step(self.page,200)
        self.assertTrue(navigator.at_submit);self.assertIsNone(self.page.evaluate('window.clicked'))


if __name__=='__main__':unittest.main()
