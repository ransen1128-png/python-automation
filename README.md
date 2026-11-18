# SmartPoultry survey draft helper

## Render web deployment

The repository now includes a web entry point (`app.py`), `requirements.txt`,
`.python-version` and `render.yaml`. For your existing Render **Web Service**:

- Root Directory: leave blank (the files are in the repository root).
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 60`
- Health Check Path: `/health`

Save the settings and deploy the latest commit. The desktop `.cmd` launcher
is not a web server and must not be used as Render's start command.

On the hosted page, click **Load your participants.csv** and choose the existing
CSV from your computer, then select a participant. The file is parsed only in
your browser. Participant files are not committed, uploaded, stored on Render,
or embedded in the public HTML. Reloading the hosted page clears its imported
list; choose the CSV again. Google receives the selected person's prefilled
answers only when you click **Open filled Google Form for review**.

For local web testing, install `requirements.txt`, then run `python app.py` and
open `http://127.0.0.1:10000`. Gunicorn runs on Render's Linux environment.
The website is a draft helper; no response is submitted automatically.

Deployment reference: [Render's Flask guide](https://render.com/docs/deploy-flask).

## Desktop use

Double-click **Start Survey.cmd**. It prepares and opens `survey_preview.html`.
No pip installation or additional Python packages are needed.

Choose a name in **Choose a participant**. The helper now reads `participants.csv`
and fills that person's first name, last name, role and supplied farm details.
Switching participants clears the previous person's unspecified information.
Age, poultry type and other unanswered questions remain blank. Ratings remain
proposed drafts until reviewed; they are not collected participant responses.
Re-run Start Survey after editing the CSV to refresh the participant list.
The form groups 2 or 3 farms as **2-5**, and the supplied **200+** category maps to
its **201 or more** choice. Exact supplied counts are shown beside the selector.
Likewise, the supplied **2 years** of experience maps to the form's **2-4 years** choice.

The helper proposes answers for the form's 29 rating statements:

- 16 Strongly Agree
- 10 Agree
- 3 Neutral

Review every statement and change any selection that does not match your own
experience. Personal and farm information is left blank rather than invented.
Click **Open filled Google Form for review**. Google opens a prefilled copy:
complete the required information, review the six pages, and submit it yourself.
The helper never clicks Submit, submits multiple responses, or invents respondents.

You can also open `survey_preview.html` directly without running Python.
Personal information typed into this local preview is not saved by the helper;
it is included in Google's prefilled URL when you choose to open that form.

## Commands

```powershell
python survey_automation.py
python survey_automation.py --seed 42
python survey_automation.py --refresh
python survey_automation.py --no-open
```

`--seed` changes the arrangement, keeping the same proportions. `--refresh`
reads the latest public question list; stop and review if the form changes.

`form_schema.json` contains the survey's public questions and Google entry IDs.
`draft_answers.json` contains an editable draft, labelled as not submitted.
For your own saved answers, create a private JSON object mapping entry IDs to
text values or lists for checkbox questions, and run:

```powershell
python survey_automation.py --answers my_answers.json
```

Opening another draft overwrites `survey_preview.html` and `draft_answers.json`.
The actual form URL is fixed in `survey_automation.py`. No Google password or
API key is needed. Google may require you to sign in or review required fields.
"# python-automation" 
