import smtplib
from email.mime.text import MIMEText

# Your Resend credentials
SMTP_HOST = "smtp.resend.com"
SMTP_PORT = 587
SMTP_USER = "resend"
resend.api_key = os.getenv("RESEND_API_KEY")
FROM_EMAIL = "onboarding@resend.dev"
TO_EMAIL = "megantyx1110@gmail.com"

try:
    # Create message
    msg = MIMEText("Test email from Resend SMTP")
    msg["Subject"] = "SMTP Test"
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL

    # Send email
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    server.starttls()
    server.login(SMTP_USER, SMTP_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("✅ Email sent successfully!")
except Exception as e:
    print(f"❌ Error: {e}")