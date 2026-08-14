from supabase_client import get_supabase_client


def create_test_user():
    supabase = get_supabase_client()

    email = "meganyx@example.com"
    password = "Test123456!"
    full_name = "Megan Test"

    try:
        response = supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": full_name
            }
        })

        if not response.user:
            print("Failed to create Authentication user.")
            return

        user_id = response.user.id

        supabase.table("profiles").upsert({
            "id": user_id,
            "full_name": full_name,
            "role": "employer",
            "headline": "",
            "phone": "",
            "bio": "",
            "skills": [],
            "avatar": None
        }, on_conflict="id").execute()

        print("Test account created successfully.")
        print(f"Email: {email}")
        print(f"Password: {password}")
        print(f"User ID: {user_id}")

    except Exception as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    create_test_user()