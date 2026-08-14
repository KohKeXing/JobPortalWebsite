# JobPortal Acceptance Tests

This suite covers the current job seeker and employer acceptance criteria:

- Job seeker and employer signup, login, forgot password, and reset password
- Job seeker profile viewing, editing, and field validation
- Employer profile viewing, immutable registered company name, and logo validation
- Employer company background editing and public viewing
- Interview scheduling after an application enters `Interview` status
- Job posting lifecycle: `draft`, `published`, `closed`, and `archived`
- Job seeker visibility: only `published` jobs are shown

## Install test packages

```powershell
pip install pytest pytest-html
```

## Folder placement

Copy the entire `acceptance_tests` folder into the root of the JobPortal
project, beside `seeker_main.py` and `employer_main.py`.

## Run

From PowerShell, the easiest method is:

```powershell
.\acceptance_tests\run_acceptance_tests.ps1
```

Or run the commands manually:

```powershell
pip install -r acceptance_tests/requirements.txt
pytest -c acceptance_tests/pytest.ini acceptance_tests
```

The HTML result is created as `acceptance_report.html` in the project root.

## Test isolation

The tests call the real Flask routes and validation code, but replace external
Supabase/Auth/email operations with in-memory fakes. They do not create real
accounts, send password-reset emails, upload real files, or modify production
data.

The actual delivery of confirmation and password-reset emails should still be
checked once manually in the deployed environment because that depends on the
Supabase email configuration and redirect URLs.
