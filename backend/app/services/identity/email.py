"""Email sender interface — console stub in development."""

from __future__ import annotations

from typing import Protocol

from app.services.monitoring.logger import get_logger

log = get_logger("veritas.email")


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    """Dev/default: log invitation emails instead of sending."""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        log.info("email.console", to=to, subject=subject, body=body)
        print(f"\n[Veritas email → {to}] {subject}\n{body}\n")


_default_sender: EmailSender = ConsoleEmailSender()


def get_email_sender() -> EmailSender:
    return _default_sender


def set_email_sender(sender: EmailSender) -> None:
    global _default_sender
    _default_sender = sender
