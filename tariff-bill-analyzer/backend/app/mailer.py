import smtplib, ssl
from email.message import EmailMessage
from . import config


def email_configured() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORD)


def send_reset_email(to: str, link: str):
    """Send the reset link by email only. The link is never printed to logs."""
    if not email_configured():
        print("ERROR: email is not configured. Set SMTP_HOST, SMTP_USER and SMTP_PASSWORD in backend/.env", flush=True)
        return
    msg = EmailMessage()
    msg["Subject"] = "Reset your Unit Ledger password"
    msg["From"] = config.SMTP_FROM or config.SMTP_USER
    msg["To"] = to
    msg.set_content(
        f"We received a request to reset your Unit Ledger password.\n\n"
        f"Open this link to choose a new password (valid for {config.RESET_MINUTES} minutes, works once):\n{link}\n\n"
        f"If you did not ask for this, you can ignore this email."
    )
    msg.add_alternative(
        f"""<p>We received a request to reset your Unit Ledger password.</p>
<p><a href="{link}" style="background:#0f4c4f;color:#fff;padding:10px 18px;border-radius:4px;text-decoration:none">Reset password</a></p>
<p>The link is valid for {config.RESET_MINUTES} minutes and works once.</p>
<p style="color:#666">If you did not ask for this, ignore this email.</p>""",
        subtype="html")
    print(f"Sending via {config.SMTP_HOST}:{config.SMTP_PORT} as {config.SMTP_USER}", flush=True)
    try:
        if config.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(config.SMTP_HOST, 465, timeout=20, context=ssl.create_default_context()) as s:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        print(f"Reset email sent to {to}", flush=True)
    except Exception as e:
        print(f"ERROR sending reset email to {to}: {type(e).__name__}: {e}", flush=True)
        if config.DEV_SHOW_RESET_LINK:
            print(f"DEV ONLY - reset link: {link}", flush=True)