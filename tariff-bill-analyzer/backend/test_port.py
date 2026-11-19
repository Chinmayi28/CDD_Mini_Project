import smtplib, ssl

ctx = ssl.create_default_context()
for label, port, ssl_first in [("587 STARTTLS", 587, False), ("465 SSL", 465, True)]:
    try:
        if ssl_first:
            s = smtplib.SMTP_SSL("smtp.gmail.com", port, timeout=15, context=ctx)
        else:
            s = smtplib.SMTP("smtp.gmail.com", port, timeout=15)
            s.ehlo(); s.starttls(context=ctx); s.ehlo()
        print(label, "-> CONNECTED OK")
        s.quit()
    except Exception as e:
        print(label, "-> FAILED:", type(e).__name__, e)