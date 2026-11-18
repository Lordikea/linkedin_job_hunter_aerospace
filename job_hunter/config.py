"""Configuration loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MAX_KEYWORDS = 10
VALID_MODES = {"any", "all"}


class ConfigError(Exception):
    """Raised when config.yaml is missing something or asks for the impossible."""


@dataclass
class Search:
    name: str
    keywords: list[str]
    location: str = ""
    match_mode: str = "any"
    exclude: list[str] = field(default_factory=list)
    remote_only: bool = False
    recipients: list[str] = field(default_factory=list)
    max_results: int = 25
    enabled: bool = True
    exclude_locations: list[str] = field(default_factory=list)
    company_include: list[str] = field(default_factory=list)


@dataclass
class EmailConfig:
    enabled: bool = True
    recipients: list[str] = field(default_factory=list)
    subject_prefix: str = "[Job Alert]"
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    sender: str = ""
    use_ssl: bool = False


@dataclass
class NtfyConfig:
    enabled: bool = False
    server: str = "https://ntfy.sh"
    topic: str = ""
    priority: str = "default"


@dataclass
class Settings:
    hours: int = 24
    request_delay_seconds: float = 3.0
    state_file: str = "state/seen_jobs.json"
    forget_after_days: int = 30
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )


@dataclass
class Config:
    searches: list[Search]
    email: EmailConfig
    ntfy: NtfyConfig
    settings: Settings

    def active_searches(self) -> list[Search]:
        return [search for search in self.searches if search.enabled]

    def recipients_for(self, search: Search) -> list[str]:
        """Who gets this search's results.

        A search with its own recipients goes only to them — so one person's
        alerts never land in another's inbox. Searches without their own list
        fall back to the global recipients.
        """
        return search.recipients or self.email.recipients


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _load_search(raw: dict[str, Any], index: int) -> Search:
    name = str(raw.get("name") or f"Search {index + 1}")
    keywords = [kw.strip() for kw in _as_list(raw.get("keywords")) if kw.strip()]
    if not keywords:
        raise ConfigError(f"Search '{name}' must contain at least one keyword.")
    if len(keywords) > MAX_KEYWORDS:
        raise ConfigError(
            f"Search '{name}' has {len(keywords)} keywords; "
            f"the maximum is {MAX_KEYWORDS}."
        )

    mode = str(raw.get("match_mode", "any")).lower()
    if mode not in VALID_MODES:
        raise ConfigError(
            f"Search '{name}' has an invalid match_mode. Expected one of {sorted(VALID_MODES)}, "
            f"not '{mode}'."
        )

    # A search can name a secret holding its recipients, so a public repo
    # never has to carry anyone's address.
    recipients = _as_list(raw.get("recipients"))
    enabled = bool(raw.get("enabled", True))

    secret_name = str(raw.get("recipients_secret") or "").strip()
    if secret_name:
        from_secret = _env_list(secret_name)
        # A disabled search never sends anything, so its secret need not exist
        # yet — that is how a search is staged before its secret is created.
        if enabled and not from_secret and not recipients:
            # Falling back to the global list here would quietly send this
            # search's alerts to the wrong person.
            raise ConfigError(
                f"Search '{name}' reads recipients from secret '{secret_name}', "
                f"but no value was provided. Check both: (1) whether the secret "
                f"is configured in GitHub (Settings > Secrets and variables > "
                f"Actions), and (2) whether .github/workflows/job-hunt.yml includes an env "
                f"entry '{secret_name}: ${{{{ secrets.{secret_name} }}}}' "
                f". Alternatively, temporarily disable the search "
                f"by setting 'enabled: false'."
            )
        for address in from_secret:
            if address not in recipients:
                recipients.append(address)

    return Search(
        name=name,
        keywords=keywords,
        location=str(raw.get("location") or "").strip(),
        match_mode=mode,
        exclude=[term.strip() for term in _as_list(raw.get("exclude")) if term.strip()],
        remote_only=bool(raw.get("remote_only", False)),
        recipients=recipients,
        max_results=int(raw.get("max_results", 25)),
        enabled=enabled,
        exclude_locations=[
            term.strip() for term in _as_list(raw.get("exclude_locations")) if term.strip()
        ],
        company_include=[
            term.strip() for term in _as_list(raw.get("company_include")) if term.strip()
        ],
    )


def _env(name: str, fallback: str = "") -> str:
    """Read an env var, treating an empty value as absent.

    A workflow passes every declared secret through, so an unset secret still
    arrives as an empty string; without this the config-file default would be
    overwritten by "".
    """
    return os.environ.get(name, "").strip() or fallback


def _env_list(name: str) -> list[str]:
    """Read a comma-separated env var, e.g. EMAIL_RECIPIENTS."""
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    raw_searches = raw.get("searches") or []
    if not raw_searches:
        raise ConfigError("config.yaml must contain at least one 'searches' entry.")
    searches = [_load_search(item or {}, i) for i, item in enumerate(raw_searches)]

    raw_notify = raw.get("notifications") or {}
    raw_email = raw_notify.get("email") or {}
    # Credentials come from the environment (GitHub Actions secrets), never
    # from the committed config file.
    # Recipients may live in EMAIL_RECIPIENTS so a public repo need not carry
    # anyone's address; both sources are merged, config order first.
    recipients = _as_list(raw_email.get("recipients"))
    for address in _env_list("EMAIL_RECIPIENTS"):
        if address not in recipients:
            recipients.append(address)

    email = EmailConfig(
        enabled=bool(raw_email.get("enabled", True)),
        recipients=recipients,
        subject_prefix=str(raw_email.get("subject_prefix", "[Job Alert]")),
        host=_env("SMTP_HOST", str(raw_email.get("host", "smtp.gmail.com"))),
        port=int(_env("SMTP_PORT", str(raw_email.get("port", 587)))),
        username=_env("SMTP_USERNAME"),
        password=_env("SMTP_PASSWORD"),
        sender=_env("SMTP_FROM") or _env("SMTP_USERNAME"),
        use_ssl=bool(raw_email.get("use_ssl", False)),
    )

    raw_ntfy = raw_notify.get("ntfy") or {}
    ntfy = NtfyConfig(
        enabled=bool(raw_ntfy.get("enabled", False)),
        server=str(raw_ntfy.get("server", "https://ntfy.sh")).rstrip("/"),
        topic=_env("NTFY_TOPIC", str(raw_ntfy.get("topic", ""))),
        priority=str(raw_ntfy.get("priority", "default")),
    )

    raw_settings = raw.get("settings") or {}
    settings = Settings(
        hours=int(raw_settings.get("hours", 24)),
        request_delay_seconds=float(raw_settings.get("request_delay_seconds", 3.0)),
        state_file=str(raw_settings.get("state_file", "state/seen_jobs.json")),
        forget_after_days=int(raw_settings.get("forget_after_days", 30)),
    )

    config = Config(searches=searches, email=email, ntfy=ntfy, settings=settings)

    if email.enabled:
        orphans = [s.name for s in config.active_searches() if not config.recipients_for(s)]
        if orphans:
            raise ConfigError(
                "No recipients configured for these searches: "
                + ", ".join(orphans)
                + ". Add 'recipients' (or 'recipients_secret') to the search, "
                "or add a global address under notifications.email.recipients."
            )
    if ntfy.enabled and not ntfy.topic:
        raise ConfigError("ntfy is enabled, but 'topic' is empty.")

    return config

