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


def load_participants(path=None):
    path = Path(path) if path else ROOT / 'participants.csv'
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    participants = []
    for row in rows:
        first = row.get('first_name', '').strip()
        last = row.get('last_name', '').strip()
        if not first or not last:
            raise ValueError('Every participant must have a first and last name.')
        role = row.get('line_of_work', '').strip()
        chickens = row.get('chicken_count', '').strip()
        farms = row.get('farm_count', '').strip()
        experience = row.get('recordkeeping_experience', '').strip()
        experience_choice = {'less than a year': 'less than a year', '1 year': '1 year',
            '2 years': '2-4 years', '3 years': '2-4 years', '4 years': '2-4 years',
            '2-4 years': '2-4 years', '5 years or more': '5 years or more'}.get(experience, '')
        methods = [value.strip() for value in row.get('recordkeeping_methods', '').split(';') if value.strip()]
        review_frequency = row.get('review_frequency', '').strip()
        chicken_choice = {'150 - 200': '150 - 200', '200+': '201 or more', '201 or more': '201 or more', '50 - 100': '50 - 100'}.get(chickens, '')
        farm_choice = {'1': '1', '2': '2-5', '3': '2-5', '4': '2-5', '5': '2-5', '2-5': '2-5', 'More': 'More'}.get(farms, '')
        participants.append({'name': first + ' ' + last, 'first_name': first, 'last_name': last,
            'line_of_work': role, 'chicken_count': chickens, 'farm_count': farms,
            'recordkeeping_experience': experience, 'recordkeeping_methods': methods,
            'review_frequency': review_frequency,
            'answers': {'FIRST NAME': first, 'LAST NAME': last,
                'Choose the option that describes your line of work.': role,
                'How many chickens do you currently have?': chicken_choice,
                'Number of poultry farm owned': farm_choice,
                'How many years of experience does the person responsible for recordkeeping have?': experience_choice,
                'What method do you primarily use to maintain farm records?': methods,
                'How often are your financial records reviewed or checked?': review_frequency}})
    return participants


def create_preview(schema, questions, counts):
    participants = load_participants()
    data = json.dumps({'url': FORM_URL, 'questions': questions, 'participants': participants}, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    title = html.escape(str(schema['title']))
    template = (ROOT / 'survey_template.html').read_text(encoding='utf-8')
    preview = template.replace('__TITLE__', title).replace('__DATA__', data)
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
