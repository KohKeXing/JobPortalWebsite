"""Job-seeker registration and login through Supabase Auth."""

from __future__ import annotations

from typing import Any

from supabase_client import (
    create_supabase_auth_client,
    get_supabase_admin_client,
)


JOB_SEEKER_ROLE = "job_seeker"


class AuthService:
    """Authentication helper for job-seeker accounts."""

    def __init__(self, admin_client: Any | None = None):
        self.admin = admin_client or get_supabase_admin_client()

    def register_user(
        self,
        email: str,
        password: str,
        full_name: str,
    ):
        """Create an Auth user.

        The SQL trigger in profiles_auth_setup.sql creates the matching
        public.profiles row. A server-side upsert is retained as a safe
        fallback in case the trigger has not been installed yet.
        """
        email = email.strip().lower()
        full_name = full_name.strip()

        try:
            auth_client = create_supabase_auth_client()
            response = auth_client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "full_name": full_name,
                        "role": JOB_SEEKER_ROLE,
                    }
                },
            })

            if not response.user:
                return None, "Failed to create the authentication account."

            user_id = response.user.id

            profile = self.get_profile(user_id)
            if not profile:
                # This uses the admin/service-role client and therefore should
                # bypass RLS. If it does not, the .env contains the wrong key.
                profile_row = {
                    "id": user_id,
                    "full_name": full_name,
                    "role": JOB_SEEKER_ROLE,
                }
                self.admin.table("profiles").upsert(
                    profile_row,
                    on_conflict="id",
                ).execute()
                profile = self.get_profile(user_id)

            if not profile:
                return None, (
                    "The Auth account was created, but the profile row could "
                    "not be created. Run profiles_auth_setup.sql and verify "
                    "SUPABASE_SERVICE_ROLE_KEY in .env."
                )

            profile["email"] = response.user.email
            return profile, None

        except Exception as exc:
            message = str(exc)
            if "row-level security" in message.lower():
                return None, (
                    "Profile creation was blocked by Row Level Security. "
                    "Run profiles_auth_setup.sql and make sure .env contains "
                    "the service_role/secret key, not the anon key."
                )
            return None, message

    def login_user(self, email: str, password: str):
        email = email.strip().lower()

        try:
            auth_client = create_supabase_auth_client()
            response = auth_client.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })

            if not response.user or not response.session:
                return None, "Invalid email or password."

            profile = self.get_profile(response.user.id)
            if not profile:
                # Repair accounts that were created before the trigger existed.
                metadata = response.user.user_metadata or {}
                profile_row = {
                    "id": response.user.id,
                    "full_name": (
                        metadata.get("full_name")
                        or response.user.email.split("@")[0]
                    ),
                    "role": JOB_SEEKER_ROLE,
                }
                self.admin.table("profiles").upsert(
                    profile_row,
                    on_conflict="id",
                ).execute()
                profile = self.get_profile(response.user.id)

            if not profile:
                return None, "User profile was not found."

            if profile.get("role") != JOB_SEEKER_ROLE:
                return None, "Please use the employer login system."

            profile["email"] = response.user.email
            profile["access_token"] = response.session.access_token
            profile["refresh_token"] = response.session.refresh_token
            return profile, None

        except Exception as exc:
            print("SUPABASE LOGIN ERROR:", repr(exc))
            return None, "Invalid email or password."

    def get_profile(self, user_id: str):
        try:
            response = (
                self.admin.table("profiles")
                .select("*")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as exc:
            print("PROFILE LOOKUP ERROR:", repr(exc))
            return None

    def update_profile(self, user_id: str, updates: dict):
        allowed = {
            "full_name",
            "headline",
            "phone",
            "bio",
            "skills",
            "avatar",
        }
        safe_updates = {
            key: value for key, value in updates.items() if key in allowed
        }

        if not safe_updates:
            return self.get_profile(user_id)

        response = (
            self.admin.table("profiles")
            .update(safe_updates)
            .eq("id", user_id)
            .execute()
        )
        return response.data[0] if response.data else None
