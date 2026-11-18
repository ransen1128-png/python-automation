import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from participant_queue import (FORM_URL,confirmed_response,participant_id,read_state,save_state,
    make_queue,prefilled_url,process_participant)
from survey_automation import ROOT,questions_from_schema,draft_ratings,participant_from_row


def example_person(first='Test',last='Participant'):
    return participant_from_row({'first_name':first,'last_name':last,'age':'30',
        'line_of_work':'Poultry Farm Owner','poultry_types':'Layers','chicken_count':'50 - 100',
        'farm_count':'1','recordkeeping_experience':'1 year',
        'recordkeeping_methods':'Handwritten notebook;Excel/spreadsheets','review_frequency':'Daily'})


class ParticipantQueueTests(unittest.TestCase):
    def setUp(self):
        self.questions=questions_from_schema(json.loads((ROOT/'form_schema.json').read_text(encoding='utf-8')))
        draft_ratings(self.questions)
        self.state={'version':1,'form':FORM_URL,'completed':{}}
        self.response_url=FORM_URL.replace('/viewform','/formResponse')

    def test_confirmation_requires_recorded_message_correct_page_and_success(self):
        self.assertTrue(confirmed_response(self.response_url,'Your response has been recorded.',False,200))
        for url,text,form,status in ((FORM_URL,'Your response has been recorded.',False,200),
            (self.response_url,'Your response has been recorded.',True,200),
            (self.response_url,'Your response has been recorded.',False,500),
            (self.response_url,'You have already responded.',False,200),
            (self.response_url,'Please sign in to continue',False,200),
            (self.response_url.replace('docs.google.com','example.com'),'Your response has been recorded.',False,200)):
            self.assertFalse(confirmed_response(url,text,form,status))

    def test_custom_confirmation_and_filipino_confirmation(self):
        self.assertTrue(confirmed_response(self.response_url,'Naitala na ang iyong tugon.',False,200))
        self.assertTrue(confirmed_response(self.response_url,'Custom acceptance message.',False,200,'Custom acceptance message.'))
        self.assertFalse(confirmed_response(self.response_url,'Custom acceptance message.',False,200))

    def test_incomplete_participants_are_not_given_invented_answers(self):
        ready=example_person();incomplete=example_person('Missing','Information');incomplete['answers']['AGE']=''
        pending,missing=make_queue([ready,incomplete],self.questions,self.state)
        self.assertEqual(pending,[ready]);self.assertEqual(missing[0][1],['AGE'])
        with self.assertRaises(ValueError):prefilled_url(self.questions,incomplete)

    def test_completed_participants_skipped_even_if_details_change(self):
        person=example_person();self.state['completed'][participant_id(person)]={'confirmed_utc':'fixture'}
        changed=copy.deepcopy(person);changed['answers']['AGE']='31'
        pending,missing=make_queue([changed],self.questions,self.state)
        self.assertEqual(pending,[]);self.assertEqual(missing,[])

    def test_duplicate_names_block_queue(self):
        with self.assertRaises(ValueError):make_queue([example_person(),example_person()],self.questions,self.state)

    def test_progress_roundtrip_and_corruption_does_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'progress.json';save_state(path,self.state);self.assertEqual(read_state(path),self.state)
            path.write_text('{broken')
            with self.assertRaises(ValueError):read_state(path)
            self.assertEqual(path.read_text(),'{broken')

    def test_unconfirmed_browser_close_does_not_mark_complete(self):
        page=MagicMock();page.goto.return_value.status=200
        with tempfile.TemporaryDirectory() as directory,patch('participant_queue.watch_manual_submission',return_value=False):
            path=Path(directory)/'progress.json'
            self.assertFalse(process_participant(page,example_person(),self.questions,self.state,path))
            self.assertEqual(self.state['completed'],{});self.assertFalse(path.exists())

    def test_manual_next_option_disables_auto_page_navigation(self):
        page=MagicMock();page.goto.return_value.status=200
        with tempfile.TemporaryDirectory() as directory,patch('participant_queue.watch_manual_submission',return_value=False) as watcher:
            process_participant(page,example_person(),self.questions,self.state,Path(directory)/'state.json',manual_next=True)
            self.assertFalse(watcher.call_args.kwargs['auto_next'])

    def test_success_saves_once_and_resume_skips_person(self):
        page=MagicMock();page.goto.return_value.status=200
        with tempfile.TemporaryDirectory() as directory,patch('participant_queue.watch_manual_submission',return_value=True):
            path=Path(directory)/'progress.json';person=example_person()
            self.assertTrue(process_participant(page,person,self.questions,self.state,path))
            loaded=read_state(path);self.assertIn(participant_id(person),loaded['completed'])
            self.assertEqual(make_queue([person],self.questions,loaded)[0],[])


if __name__=='__main__':unittest.main()
