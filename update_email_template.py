import requests
import os
from dotenv import load_dotenv

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECRET_KEY")

# The template you want to set
template_html = """
<h2>Reset Your Password</h2>

<p>Hello,</p>

<p>You requested to reset your password for JobPortal.</p>

<p>Click the link below to reset your password:</p>

<p>
  <a href="http://127.0.0.1:3000/reset-password#access_token={{ .Token }}" 
     style="background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; display: inline-block;">
    Reset Password
  </a>
</p>

<p>Or copy and paste this link into your browser:</p>
<p>http://127.0.0.1:3000/reset-password#access_token={{ .Token }}</p>

<p>This link will expire in 24 hours.</p>

<p>If you didn't request this, please ignore this email.</p>

<p>Regards,<br>JobPortal Team</p>
"""

# API endpoint for recovery (reset password) template
url = f"{supabase_url}/auth/v1/admin/templates/recovery"

headers = {
    "Authorization": f"Bearer {service_role_key}",
    "Content-Type": "application/json"
}

payload = {
    "subject": "Reset Your Password - JobPortal",
    "html": template_html,
    "text": "Reset your password for JobPortal. Click the link: http://127.0.0.1:3000/reset-password#access_token={{ .Token }}"
}

try:
    response = requests.put(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        print("✅ Email template updated successfully!")
        print(f"Response: {response.json()}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(f"Response: {response.text}")
except Exception as e:
    print(f"❌ Exception: {e}")