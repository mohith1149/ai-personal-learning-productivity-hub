"""Outgoing e-mail. One provider today: SMTP (Gmail works with an App Password).

Security: the password lives only in backend settings. It is never logged, never put in an error message and never
returned by the API. Error text is written here; raw SMTP server replies (which can echo addresses) are not passed on.
"""
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr


class MailError(Exception):
    pass


@dataclass
class Mailer:
    host: str
    port: int
    username: str
    password: str
    sender: str
    provider: str = "smtp"

    def send(self, to: str, subject: str, html: str, text: str) -> str:
        """Returns a provider message id. Raises MailError; returns only after the server accepted the message."""
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, formataddr(("AI Learning Hub", self.sender)), to
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        ctx = ssl.create_default_context()
        try:
            if self.port == 465:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=20, context=ctx) as s:
                    s.login(self.username, self.password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=20) as s:
                    s.starttls(context=ctx)
                    s.login(self.username, self.password)
                    s.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            raise MailError("The mail server rejected the username or password. For Gmail use an App Password") from None
        except smtplib.SMTPRecipientsRefused:
            raise MailError("The mail server refused the recipient address") from None
        except (smtplib.SMTPException, OSError):
            raise MailError("Couldn't send through the mail server. Check SMTP_HOST, SMTP_PORT and your connection") from None
        return msg.get("Message-ID", "")


def build_mailer(settings) -> Mailer | None:
    """None when e-mail isn't configured (provider 'none' or missing credentials)."""
    if settings.email_provider != "smtp" or not (settings.smtp_username and settings.smtp_password):
        return None
    return Mailer(settings.smtp_host, settings.smtp_port, settings.smtp_username, settings.smtp_password, settings.email_from or settings.smtp_username)
