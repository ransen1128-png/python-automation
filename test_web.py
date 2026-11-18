import json
import unittest
from unittest.mock import patch
from app import app


class WebDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.client=app.test_client()

    def test_web_root_renders_without_reading_private_participants(self):
        with patch('survey_automation.load_participants',side_effect=AssertionError('Must not publish private CSV')):
            response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'participantFile',response.data)
        self.assertIn(b'"participants": []',response.data)
        self.assertNotIn(b'Rafael Miguel Perez',response.data)
        self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_health_check_and_preview_link(self):
        self.assertEqual(self.client.get('/health').json,{'status':'ok'})
        self.assertEqual(self.client.get('/survey_preview.html').status_code,302)

    def test_private_files_and_submission_routes_are_not_exposed(self):
        for path in ('/participants.csv','/.env','/.git/config','/draft_answers.json','/survey_automation.py'):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.client.post('/').status_code,405)


if __name__=='__main__':unittest.main()
