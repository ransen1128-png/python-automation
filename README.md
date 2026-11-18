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

## Automatic desktop participant queue

Double-click **Start Survey.cmd**. It installs the desktop Playwright dependency
on its first run, then opens Chrome (or Edge) with the first ready, pending
participant. It clicks **Next** through the prefilled pages and stops at the
final **Submit** button. Review the answers and click **Submit yourself**.
After Google's confirmation message appears, the queue saves progress and opens
the next participant automatically. It never clicks Submit. Once the final page
is reached, Back remains available for reviewing earlier pages without being
automatically moved forward again. Suggested ratings still require review.

If Next cannot advance because of a validation error, the helper does not keep
clicking an unchanged page. Correct the missing/invalid answers; it can then
continue. Use `--manual-next` to turn automatic page navigation off entirely.

Only participants with all required supplied details are queued; missing ages,
poultry types or other fields are not invented. Each participant uses a fresh
browser context to avoid carrying another person's draft or login forward.
Google access restrictions still apply. Sign in manually if Google asks.

Close the browser or press Ctrl+C to stop. Launch Start Survey again to resume;
confirmed participants are skipped. Closing a form before confirmation does not
mark it done. Local `.survey_queue_state.json` and its lock/backup files are kept
out of GitHub. Changes to an already-completed person's details do not silently
cause another submission. Use an explicit reset only if a repeat is intended.

```powershell
& '.\Start Survey.cmd' --plan-only
& '.\Start Survey.cmd' --limit 5
& '.\Start Survey.cmd' --manual-next
& '.\Start Survey.cmd' --reset-progress
```

The default recognises Google's English/Filipino recorded-response message. If
the owner has replaced it with custom text, provide the full actual confirmation
using `--confirmation-text "Your exact custom confirmation message"`.
No completion is assumed from elapsed time or from a page error.

This queue runs on your **desktop**, where it can observe the browser you control.
The Render web helper still uses manual participant selection; it cannot read
Google's cross-origin submission result. The Render service does not install or
run Playwright. See [Playwright's browser documentation](https://playwright.dev/python/docs/browsers).

## Desktop preview

Double-click **Open Preview.cmd**. It prepares and opens `survey_preview.html`.
No pip installation or additional Python packages are needed.

Choose a name in **Choose a participant**. The helper now reads `participants.csv`
and fills that person's first name, last name, role and supplied farm details.
Switching participants clears the previous person's unspecified information.
Age, poultry type and other unanswered questions remain blank. Ratings remain
proposed drafts until reviewed; they are not collected participant responses.
An optional `age` column now fills the Google Form's Age field using only the
supplied age in whole years. Blank ages stay blank; switching people clears the
previous person's age.
The optional `poultry_types` column fills the poultry-type checkboxes. Use the
exact listed choices, separated by semicolons for multiple types, e.g. `Layers`
or `Layers;Broiler`. Missing types stay blank.
Re-run Open Preview after editing the CSV to refresh the participant list.
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
