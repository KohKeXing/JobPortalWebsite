1. Copy these files into your JobPortalWebsite project.
2. Put login.html, register.html, seeker.html and resumes.html inside templates/.
3. Run profiles_setup.sql in Supabase SQL Editor.
4. Copy .env.example to .env and fill in the real keys.
5. Install dependencies: python -m pip install -r requirements.txt
6. Run: python seeker_main.py
7. Open: http://127.0.0.1:3000/register

Keep your other files such as application_tracking.py, bookmark.py, job.py,
resume_builder.py and file_encryption.py unchanged.

Important: login and profiles are connected. Full per-user privacy for resumes,
applications and bookmarks still requires owner_id filtering in those storage classes.
