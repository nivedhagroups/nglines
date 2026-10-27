import asyncio
from email.message import EmailMessage
from email.utils import formataddr
import smtplib

from app.core.config import settings


class SMTPEmailDelivery:
    def __init__(self) -> None:
        if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
            raise RuntimeError("Configure SMTP_HOST, SMTP_USERNAME, and SMTP_PASSWORD")
        self.from_email = settings.smtp_from_email or settings.smtp_username

    async def send_invitation(self, destination: str, name: str, temporary_password: str) -> None:
        message = self._message(
            destination,
            "Your Nivedha Groups account is ready",
            f"Hello {name},\n\nYour Nivedha Groups account is ready. Sign in with this email address and temporary password:\n\n{temporary_password}\n\nYou will be required to set a new password before accessing the app. Do not share this email or password.",
        )
        await asyncio.to_thread(self._send_sync, message)

    def _message(self, destination: str, subject: str, body: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((settings.smtp_from_name, self.from_email))
        message["To"] = destination
        message.set_content(body)
        return message

    @staticmethod
    def _send_sync(message: EmailMessage) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.ehlo()
            if settings.smtp_starttls:
                server.starttls()
                server.ehlo()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)