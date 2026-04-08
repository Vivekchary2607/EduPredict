import smtplib
from email.message import EmailMessage

EMAIL_ADDRESS = "guduruvivekcharyg34pythonml@gmail.com"
EMAIL_PASSWORD = "kyhodmjrxpaixvit"

def send_invite_email(to_email, invite_code, expiry):
    msg = EmailMessage()
    msg["Subject"] = "EduPredict – Invitation to Join"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email

    msg.set_content(f"""
Hello,

You have been invited to access the EduPredict system.

Invite Code: {invite_code}
Expires at: {expiry}

Please open the application and register using this invite code.

Regards,
EduPredict Admin
""".strip())

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)


def send_org_code_email(email, org_name, org_code):
    msg=EmailMessage()
    msg["Subject"]="Your Organization Access Code"
    msg["From"]=EMAIL_ADDRESS
    msg["To"]=email
    msg.set_content(f"""
Hello {org_name},

Your organization has been successfully registered.

Organization Code: {org_code}

Use this code during admin registration.
Do NOT share this code publicly.

Regards,
Student Performance Platform
""".strip())
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)


# Sending deactivation email for organization

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def send_deactivation_email(to_email, org_name):
    subject = "Organization Deactivated - Student Performance System"

    body = f"""
    Dear {org_name},

    Your organization account has been successfully deactivated 
    from the Student Performance & Analytics Platform.

    If this was a mistake, please contact the platform administrator.

    Regards,
    Platform Admin
    """

    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
    server.quit()