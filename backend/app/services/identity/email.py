"""Email sender interface — console stub or SMTP when configured."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import get_settings
from app.services.monitoring.logger import get_logger

log = get_logger("veritas.email")


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    """Dev/default: log invitation emails instead of sending."""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        log.info("email.console", to=to, subject=subject, body=body)
        print(f"\n[Veritas email → {to}] {subject}\n{body}\n")


class SMTPEmailSender:
    """Real SMTP delivery when smtp_host is configured."""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        settings = get_settings()

        def _send() -> None:
            msg = EmailMessage()
            msg["From"] = settings.smtp_from
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(msg)

        await asyncio.to_thread(_send)
        log.info("email.smtp", to=to, subject=subject)


_default_sender: EmailSender | None = None


def get_email_sender() -> EmailSender:
    global _default_sender
    if _default_sender is not None:
        return _default_sender
    settings = get_settings()
    if settings.smtp_host:
        return SMTPEmailSender()
    return ConsoleEmailSender()


def set_email_sender(sender: EmailSender) -> None:
    global _default_sender
    _default_sender = sender
