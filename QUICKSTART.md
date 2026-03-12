# Quick Start

This is the short version for starting the app and checking stored data without rereading the full README.

## Start The App

```bash
cd /Users/miros/Developer/sbi-midterm-interview
./run-local.sh
```

Open one of these URLs:

```text
http://localhost:8501/?name=Miros&recipient_email=miros@example.com&interview_config=midterm_interview
http://localhost:8501/?name=Miros&recipient_email=miros@example.com&interview_config=industry_org_survey
http://localhost:8501/?name=Miros&recipient_email=miros@example.com&interview_config=end_reflection_interview
```

## Run Local Checks

```bash
cd /Users/miros/Developer/sbi-midterm-interview
./test-local.sh
```

This runs:
- `pytest`
- `python -m compileall code`

## Best Local Smoke Test

1. Start without `student_number` first.
2. Send one text reply and confirm the assistant responds.
3. Test the mic button if you want voice input.
4. Test the speaker toggle if you want TTS playback.
5. Click `Quit` to exercise transcript save, summary generation, remote DB write, and optional email sending.

## Open LIACS In VS Code

Fastest path:

```bash
cd /Users/miros/Developer/sbi-midterm-interview
./open-liacs-vscode.sh
```

That opens:

```text
/home/zohrehvanda/BS-Interviews
```

To open the database folder directly:

```bash
./open-liacs-vscode.sh liacs /home/zohrehvanda/BS-Interviews/Database
```

## Inspect Remote Interview Data

The remote SQLite file is stored at:

```text
/home/zohrehvanda/BS-Interviews/Database/interviews.db
```

Use the helper script:

```bash
cd /Users/miros/Developer/sbi-midterm-interview
.venv/bin/python code/inspect_remote_data.py --table interviews --limit 20
.venv/bin/python code/inspect_remote_data.py --table progress --limit 20
.venv/bin/python code/inspect_remote_data.py --table interviews --student-id s1234567 --show-summary
```

## Local Files Written By The App

The app also writes local files to:
- [data/transcripts](/Users/miros/Developer/sbi-midterm-interview/data/transcripts)
- [data/times](/Users/miros/Developer/sbi-midterm-interview/data/times)

## If Something Stops Working

1. Re-run `./test-local.sh`.
2. Confirm [code/.streamlit/secrets.toml](/Users/miros/Developer/sbi-midterm-interview/code/.streamlit/secrets.toml) still has the required keys.
3. If LIACS access fails in VS Code, try the data helper script first. It is usually the quickest way to tell whether the issue is your local setup or a temporary server-side SSH/session problem.
