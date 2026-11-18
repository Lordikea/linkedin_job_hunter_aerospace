"""Send the new-postings digest over SMTP."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from ..config import EmailConfig
from ..linkedin import Job
from . import render

log = logging.getLogger(__name__)


class EmailError(Exception):
    pass


def _validate(config: EmailConfig, recipients: list[str]) -> None:
    missing = [
        name
        for name, value in (
            ("SMTP_HOST", config.host),
            ("SMTP_USERNAME", config.username),
            ("SMTP_PASSWORD", config.password),
        )
        if not value
    ]
    if missing:
        raise EmailError(
            "Could not send email; missing configuration: "
            + ", ".join(missing)
            + ". Configure these as GitHub Actions secrets (or locally in a .env file)."
        )
    if not recipients:
        raise EmailError("Could not send email: the recipient list is empty.")


def send_email(config: EmailConfig, recipients: list[str], jobs: list[Job]) -> None:
    if not jobs:
        return
    _validate(config, recipients)

    message = EmailMessage()
    message["Subject"] = render.subject(jobs, config.subject_prefix)
    message["From"] = formataddr(("LinkedIn Job Hunter", config.sender or config.username))
    message["To"] = ", ".join(recipients)
    message.set_content(render.as_text(jobs))
    message.add_alternative(render.as_html(jobs), subtype="html")

    try:
        if config.use_ssl or config.port == 465:
            server = smtplib.SMTP_SSL(config.host, config.port, timeout=30)
        else:
            server = smtplib.SMTP(config.host, config.port, timeout=30)
        with server:
            if not (config.use_ssl or config.port == 465):
                server.starttls()
            server.login(config.username, config.password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailError(
            "SMTP authentication was rejected. If you use Gmail, do not use your regular password; "
            "use an 'app password' generated while two-step verification is enabled."
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"SMTP error: {exc}") from exc

    log.info("Emailed %d job listing(s) to %s", len(jobs), ", ".join(recipients))

