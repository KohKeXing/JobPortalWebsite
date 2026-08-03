from supabase_client import get_supabase_client


def reset_test_password():
    supabase = get_supabase_client()

    user_id = "79990ad8-9a79-43c0-8a31-c74d55c28260"
    new_password = "Test123456!"

    try:
        response = supabase.auth.admin.update_user_by_id(
            user_id,
            {
                "password": new_password,
                "email_confirm": True,
            },
        )

        if not response.user:
            print("Password update failed.")
            return

        print("Password updated successfully.")
        print("Email: megan.test@example.com")
        print("Password: Test123456!")

    except Exception as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    reset_test_password()