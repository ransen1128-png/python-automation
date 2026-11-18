import json
import unittest
from copy import deepcopy
from survey_automation import ROOT, RATINGS, questions_from_schema, draft_ratings, load_participants


class SurveyDraftTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads((ROOT / 'form_schema.json').read_text(encoding='utf-8'))
        self.questions = questions_from_schema(self.schema)

    def test_real_question_count_and_unique_entries(self):
        self.assertEqual(len(self.questions), 40)
        self.assertEqual(sum(q['kind'] == 'rating' for q in self.questions), 29)
        self.assertEqual(len({q['entry'] for q in self.questions}), 40)

    def test_rating_mix_and_valid_google_options(self):
        counts = draft_ratings(self.questions)
        self.assertEqual(counts, {'Strongly Agree': 16, 'Agree': 10, 'Neutral': 3})
        for question in self.questions:
            if question['kind'] == 'rating':
                self.assertIn(question['draft'], question['options'])
                self.assertIn(question['draft'], RATINGS)

    def test_does_not_invent_personal_or_farm_information(self):
        draft_ratings(self.questions)
        for question in self.questions:
            if question['kind'] != 'rating':
                self.assertIn(question['draft'], ('', []))

    def test_reproducible_draft_and_changed_arrangement(self):
        second = deepcopy(self.questions)
        draft_ratings(self.questions, seed=2026)
        draft_ratings(second, seed=2026)
        self.assertEqual(self.questions, second)
        draft_ratings(second, seed=42)
        self.assertNotEqual(self.questions, second)

    def test_invalid_mix_rejected(self):
        for weights in ((0, 0, 0), (1, -1, 2)):
            with self.assertRaises(ValueError):
                draft_ratings(self.questions, weights=weights)

    def test_participant_list_and_supplied_farm_details(self):
        people=load_participants()
        self.assertEqual(len(people),93)
        by_name={person['name']:person for person in people}
        first=by_name['Rafael Miguel Perez']
        self.assertEqual(first['answers']['Choose the option that describes your line of work.'],'Poultry Farm Owner')
        self.assertEqual(first['answers']['How many chickens do you currently have?'],'150 - 200')
        self.assertEqual(first['answers']['Number of poultry farm owned'],'2-5')
        self.assertEqual(first['recordkeeping_experience'],'1 year')
        self.assertEqual(first['recordkeeping_methods'],['Handwritten notebook','Excel/spreadsheets'])
        self.assertEqual(first['review_frequency'],'Daily')
        second=by_name['Mary Ann Cordero']
        self.assertEqual(second['answers']['How many chickens do you currently have?'],'201 or more')
        self.assertEqual(second['farm_count'],'3')
        self.assertEqual(second['recordkeeping_experience'],'2 years')
        self.assertEqual(second['answers']['How many years of experience does the person responsible for recordkeeping have?'],'2-4 years')
        self.assertEqual(second['recordkeeping_methods'],['Handwritten notebook','Excel/spreadsheets'])
        self.assertEqual(second['review_frequency'],'Daily')
        self.assertEqual(by_name['Jericho Mark Dela Peña']['answers']['Choose the option that describes your line of work.'],'')


if __name__ == '__main__':
    unittest.main()
