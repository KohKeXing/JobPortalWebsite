# my_auth.py
from supabase_client import get_supabase_client

class SupabaseAuth:
    def __init__(self):
        self.client = get_supabase_client()
    
    def register_user(self, email, password, full_name, role='job_seeker'):
        try:
            auth_response = self.client.auth.sign_up({
                "email": email,
                "password": password,
            })
            
            if not auth_response.user:
                return None, "Failed to create user"
            
            user_id = auth_response.user.id
            
            profile_data = {
                "id": user_id,
                "full_name": full_name,
                "role": "job_seeker",
            }
            
            self.client.table("profiles").insert(profile_data).execute()
            
            response = self.client.table("profiles").select("*").eq("id", user_id).execute()
            
            return response.data[0] if response.data else None, None
            
        except Exception as e:
            return None, str(e)
    
    def login_user(self, email, password):
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })
            
            if not response.user:
                return None, "Invalid credentials"
            
            profile = self.client.table("profiles").select("*").eq("id", response.user.id).execute()
            
            if not profile.data:
                return None, "User profile not found"
            
            user_data = profile.data[0]
            user_data["email"] = response.user.email
            user_data["access_token"] = response.session.access_token
            
            return user_data, None
            
        except Exception as e:
            return None, str(e)
    
    def logout_user(self):
        try:
            self.client.auth.sign_out()
            return True
        except:
            return False
    
    def get_user_by_id(self, user_id):
        try:
            response = self.client.table("profiles").select("*").eq("id", user_id).execute()
            return response.data[0] if response.data else None
        except:
            return None