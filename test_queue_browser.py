"""Offline browser fixtures. All Google requests are intercepted, never sent."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse
from participant_queue import FORM_URL,process_participant,make_queue,read_state,watch_manual_submission
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


if __name__=='__main__':unittest.main()
