# JobPortal Acceptance Test Plan

| ID | Area | Acceptance scenario | Expected result |
|---|---|---|---|
| AT-AUTH-01 | Seeker signup | Register with valid name, unique email, and strong password | Account registration returns success |
| AT-AUTH-02 | Seeker signup | Register with an existing email or weak password | Request is rejected with a clear error |
| AT-AUTH-03 | Seeker login | Login with registered email and correct password | Seeker session is created and dashboard redirect is returned |
| AT-AUTH-04 | Seeker forgot/reset | Request reset for a registered email and submit valid recovery tokens | Reset request is sent and new password is accepted |
| AT-AUTH-05 | Employer signup | Register company with unique email and strong password | Employer record and sequential `EMP` ID are created |
| AT-AUTH-06 | Employer login | Login with valid employer credentials | Employer session is created |
| AT-AUTH-07 | Employer forgot/reset | Request reset and submit valid recovery tokens | Reset request is sent and password is updated |
| AT-PRO-01 | Seeker profile | Authenticated seeker opens profile | Registered profile and email are displayed |
| AT-PRO-02 | Seeker profile | Submit valid name, headline, phone, bio, and skills | Profile is saved and normalized |
| AT-PRO-03 | Seeker validation | Submit numbers in name, invalid phone, short bio, or empty skills | Field-level errors are returned before saving |
| AT-PRO-04 | Employer profile | Authenticated employer opens profile | Employer ID, company name, email, and logo are displayed |
| AT-PRO-05 | Employer validation | Attempt to edit registered company name or upload a non-image logo | Company name change and invalid logo are rejected |
| AT-COMP-01 | Company background | Save valid background, industry, size, location, URL, year, and benefits | Company page is updated |
| AT-COMP-02 | Company validation | Enter URL without `http://`/`https://`, future year, or unsupported size | Save is rejected with a validation error |
| AT-COMP-03 | Public company page | Job seeker opens the company page | Company background is visible without private storage paths |
| AT-INT-01 | Interview prerequisite | Schedule while application is Pending | Scheduling is blocked |
| AT-INT-02 | Interview schedule | Change status to Interview and enter future meeting details | Interview is saved and shown to employer and job seeker |
| AT-INT-03 | Interview validation | Enter a past date/time | Scheduling is rejected immediately |
| AT-JOB-01 | Draft | Set posting to Draft | Saved for employer but hidden from job seekers |
| AT-JOB-02 | Published | Set posting to Published | Visible to job seekers and accepts applications |
| AT-JOB-03 | Closed | Set posting to Closed | Hidden from job seekers and no longer accepts applications |
| AT-JOB-04 | Archived | Set posting to Archived | Hidden from job seekers and retained in employer history |

## Manual email verification

The automated tests safely verify request handling without sending real email.
Before final acceptance, manually verify both roles using test email accounts:

1. Complete signup and open the confirmation email.
2. Confirm that the seeker link returns to the seeker application.
3. Confirm that the employer link returns to the employer application.
4. Request Forgot Password for each role.
5. Open each reset link and set a password that satisfies the password policy.
6. Confirm the old password fails and the new password succeeds.
