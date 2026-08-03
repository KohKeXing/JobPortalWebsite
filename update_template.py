import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECRET_KEY")

# Create Supabase client
client = create_client(supabase_url, service_role_key)

# New template
template_html = """
<h2>Reset Your Password</h2>

<p>Hello,</p>

<p>You requested to reset your password for JobPortal.</p>

<p>Click the link below to reset your password:</p>

<p>
  <a href="http://localhost:3000/reset-password#access_token={{ .Token }}" 
     style="background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; display: inline-block;">
    Reset Password
  </a>
</p>

<p>Or copy and paste this link into your browser:</p>
<p>http://localhost:3000/reset-password#access_token={{ .Token }}</p>

<p>This link will expire in 24 hours.</p>

<p>If you didn't request this, please ignore this email.</p>

<p>Regards,<br>JobPortal Team</p>
"""

try:
    # Update the reset password template
    response = client.auth.admin.update_template(
        "recovery",  # recovery = reset password
        {
            "subject": "Reset Your Password - JobPortal",
            "html": template_html,
            "text": "Reset your password: http://localhost:3000/reset-password#access_token={{ .Token }}"
        }
    )
    print("✅ Email template updated successfully!")
    print(response)
except Exception as e:
    print(f"❌ Error: {e}")