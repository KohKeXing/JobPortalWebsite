# Login/Register RLS Fix

## Why the error happened

Registration created a Supabase Auth user, then the application attempted to
insert the profile using a client that was subject to Row Level Security.
Supabase rejected that insert.

This package fixes it in three ways:

1. A database trigger creates `public.profiles` automatically when a new
   `auth.users` row is created.
2. Public Auth operations use a fresh anon client.
3. Trusted profile/database operations use the service-role/secret client.

## Replace these files

- `supabase_client.py`
- `auth_service.py`
- `login_required.py`
- `seeker_main.py`
- `templates/login.html`
- `templates/register.html`

Delete or stop importing:

- `my_auth.py`
- `supabase.auth.py`
- any local file named `supabase_auth.py` (that name conflicts with the
  installed Supabase package)

## Supabase setup

1. Open Supabase > SQL Editor.
2. Run `profiles_auth_setup.sql`.
3. Copy `.env.example` to `.env` and enter the correct keys.
4. The project URL must look like:
   `https://PROJECT_ID.supabase.co`
   and must not include `/rest/v1/`.

## Run

```powershell
python -m pip install -r requirements.txt
python seeker_main.py
```

Open:

- `http://127.0.0.1:3000/register`
- `http://127.0.0.1:3000/login`

## Important

The uploaded `seeker_main.py` was used as the base. If you edited that file
after uploading it, compare your newer local copy before replacing it.
