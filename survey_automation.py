"""Prepare one editable survey draft and open Google's prefilled form.

Standard library only. Never submits responses or creates participant identities.
"""
import argparse
import csv
import html
import json
import random
import re
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSdOu8okSs6Ng35TVR4bbkM5gqkbtWArAUkctDUZ3a4GA0ldyQ/viewform'
RATINGS = ('Strongly Agree', 'Agree', 'Neutral')


def refresh_schema():
    request = urllib.request.Request(FORM_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        source = response.read().decode('utf-8')
    match = re.search(r'FB_PUBLIC_LOAD_DATA_\s*=\s*', source)
    if not match:
        raise ValueError('Google did not provide the public form schema. Open the form manually to check access.')
    data, _ = json.JSONDecoder().raw_decode(source[match.end():])
    schema = {'title': data[1][8], 'url': FORM_URL, 'items': data[1][1]}
    (ROOT / 'form_schema.json').write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding='utf-8')
    return schema


def questions_from_schema(schema):
    questions = []
    section = 'Participant information'
    for item in schema['items']:
        kind = item[3]
        if kind == 8:
            section = item[1]
            continue
        if kind not in (0, 1, 2, 3, 4, 7):
            continue
        for entry in item[4] or []:
            options = [option[0] for option in entry[1] or []] if len(entry) > 1 else []
            question = entry[3][0] if kind == 7 else item[1]
            questions.append({
                'entry': str(entry[0]), 'section': section, 'question': question,
                'kind': 'rating' if kind == 7 else 'checkbox' if kind == 4 else 'select' if kind in (2, 3) else 'text',
                'required': bool(entry[2]), 'options': [value for value in options if value],
                'draft': '' if kind != 4 else [],
            })
    return questions


def draft_ratings(questions, seed=2026, weights=(55, 35, 10)):
    indices = [i for i, question in enumerate(questions) if question['kind'] == 'rating']
    total = sum(weights)
    if total <= 0 or any(weight < 0 for weight in weights):
        raise ValueError('Rating weights must be nonnegative and add up to more than zero.')
    exact = [len(indices) * weight / total for weight in weights]
    counts = [int(value) for value in exact]
    remainder = len(indices) - sum(counts)
    order = sorted(range(3), key=lambda i: exact[i] - counts[i], reverse=True)
    for i in order[:remainder]:
        counts[i] += 1
    choices = [rating for rating, count in zip(RATINGS, counts) for _ in range(count)]
    random.Random(seed).shuffle(choices)
    for index, choice in zip(indices, choices):
        if choice not in questions[index]['options']:
            raise ValueError('The rating choices changed; refresh and review the form schema.')
        questions[index]['draft'] = choice
    return dict(zip(RATINGS, counts))


PARTICIPANT_CONFIG = {
    'chicken_choices': {'150 - 200': '150 - 200', '200+': '201 or more', '201 or more': '201 or more', '50 - 100': '50 - 100'},
    'farm_choices': {'1': '1', '2': '2-5', '3': '2-5', '4': '2-5', '5': '2-5', '2-5': '2-5', 'More': 'More'},
    'experience_choices': {'less than a year': 'less than a year', '1 year': '1 year', '2 years': '2-4 years', '3 years': '2-4 years', '4 years': '2-4 years', '2-4 years': '2-4 years', '5 years or more': '5 years or more'},
    'labels': {'first_name': 'FIRST NAME', 'last_name': 'LAST NAME', 'age': 'AGE',
        'line_of_work': 'Choose the option that describes your line of work.',
        'poultry_types': 'What type of poultry farming do you operate?',
        'chicken_count': 'How many chickens do you currently have?',
        'farm_count': 'Number of poultry farm owned',
        'recordkeeping_experience': 'How many years of experience does the person responsible for recordkeeping have?',
        'recordkeeping_methods': 'What method do you primarily use to maintain farm records?',
        'review_frequency': 'How often are your financial records reviewed or checked?'}
}


def participant_from_row(row):
    values = {field: str(row.get(field) or '').strip() for field in PARTICIPANT_CONFIG['labels']}
    if not values['first_name'] or not values['last_name']:
        raise ValueError('Every participant must have a first and last name.')
    if values['age'] and (not re.fullmatch(r'[0-9]{1,3}', values['age']) or not 1 <= int(values['age']) <= 120):
        raise ValueError('Supplied ages must be whole years from 1 to 120, or blank if not provided.')
    values['name'] = values['first_name'] + ' ' + values['last_name']
    for field in ('recordkeeping_methods', 'poultry_types'):
        values[field] = [value.strip() for value in values[field].split(';') if value.strip()]
    answers = {label: values[field] for field, label in PARTICIPANT_CONFIG['labels'].items()}
    for field, mapping in (('chicken_count', 'chicken_choices'), ('farm_count', 'farm_choices'), ('recordkeeping_experience', 'experience_choices')):
        answers[PARTICIPANT_CONFIG['labels'][field]] = PARTICIPANT_CONFIG[mapping].get(values[field], '')
    return {**values, 'answers': answers}


def load_participants(path=None):
    path = Path(path) if path else ROOT / 'participants.csv'
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return [participant_from_row(row) for row in csv.DictReader(handle)]


def render_preview(schema, questions, participants):
    data = json.dumps({'url': FORM_URL, 'questions': questions, 'participants': participants,
        'participant_config': PARTICIPANT_CONFIG}, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    title = html.escape(str(schema['title']))
    template = (ROOT / 'survey_template.html').read_text(encoding='utf-8')
    return template.replace('__TITLE__', title).replace('__DATA__', data)


def create_preview(schema, questions, counts):
    participants = load_participants()
    preview = render_preview(schema, questions, participants)
    path = ROOT / 'survey_preview.html'
    path.write_text(preview, encoding='utf-8')
    plan = {'status': 'editable draft; not submitted', 'form': FORM_URL,
            'suggested_rating_counts': counts, 'questions': questions}
    (ROOT / 'draft_answers.json').write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Read the latest public question list from Google.')
    parser.add_argument('--seed', type=int, default=2026, help='Reproducible arrangement of suggested rating answers.')
    parser.add_argument('--no-open', action='store_true', help='Generate files without opening a browser.')
    parser.add_argument('--answers', type=Path, help='Optional JSON object mapping entry IDs to your own answers.')
    args = parser.parse_args()
    try:
        schema = refresh_schema() if args.refresh or not (ROOT / 'form_schema.json').exists() else json.loads((ROOT / 'form_schema.json').read_text(encoding='utf-8'))
        questions = questions_from_schema(schema)
        counts = draft_ratings(questions, args.seed)
        if args.answers:
            provided = json.loads(args.answers.read_text(encoding='utf-8'))
            if not isinstance(provided, dict):
                raise ValueError('Your answer file must be a JSON object keyed by entry ID.')
            for question in questions:
                if question['entry'] in provided:
                    value = provided[question['entry']]
                    if question['kind'] == 'checkbox':
                        if not isinstance(value, list) or any(v not in question['options'] for v in value):
                            raise ValueError('Checkbox answers must be lists containing the listed options.')
                    elif not isinstance(value, str) or (question['options'] and value not in question['options']):
                        raise ValueError('Each supplied answer must match its question type and listed options.')
                    question['draft'] = value
        path = create_preview(schema, questions, counts)
        print(f'Created {path}')
        print('Suggested ratings: ' + ', '.join(f'{name}: {count}' for name, count in counts.items()))
        print('Personal and farm details are not invented. Review and edit the draft before opening the Google Form.')
        print('The script never clicks Submit.')
        if not args.no_open:
            webbrowser.open(path.as_uri())
        return 0
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        print(f'Unable to prepare the survey: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
