"""Tie search, matching, de-duplication and notification together."""

from __future__ import annotations

import logging

from .config import Config, Search
from .freshness import is_recent
from .linkedin import Job, LinkedInClient, RateLimited, build_query
from .matching import matches
from .text import tokenize
from .notifiers.email_notifier import EmailError, send_email
from .notifiers.ntfy_notifier import send_ntfy
from .storage import SeenStore

log = logging.getLogger(__name__)


def collect_new_jobs(config: Config, store: SeenStore) -> list[Job]:
    """Search every configured query and return the postings not seen before."""
    client = LinkedInClient(
        user_agent=config.settings.user_agent,
        delay_seconds=config.settings.request_delay_seconds,
    )
    new_jobs: list[Job] = []
    seen_this_run: set[str] = set()
    counts = {
        "retrieved": 0,
        "already_seen": 0,
        "duplicate": 0,
        "too_old": 0,
        "excluded_location": 0,
        "no_keyword_match": 0,
    }

    for search in config.active_searches():
        search_retrieved = 0
        search_matches = 0
        for query in build_query(search.keywords, search.match_mode):
            try:
                results = client.search(
                    keywords=query,
                    location=search.location,
                    hours=config.settings.hours,
                    max_results=search.max_results,
                    remote_only=search.remote_only,
                )
            except RateLimited as exc:
                log.warning("%s: %s", search.name, exc)
                break
            except Exception as exc:
                log.error("%s / '%s' search failed: %s", search.name, query, exc)
                continue

            for job in results:
                counts["retrieved"] += 1
                search_retrieved += 1

                if job.id in store:
                    counts["already_seen"] += 1
                    continue
                if job.id in seen_this_run:
                    counts["duplicate"] += 1
                    continue
                if not is_recent(job.posted_at, job.posted_label, config.settings.hours):
                    counts["too_old"] += 1
                    continue
                if is_excluded_location(job.location, search.exclude_locations):
                    counts["excluded_location"] += 1
                    continue

                # Match both the role title and employer. This matters for
                # company-specific searches such as ATR, where the employer
                # name may not appear in the job title.
                searchable_text = f"{job.title} {job.company}"
                hits = matches(
                    searchable_text,
                    search.keywords,
                    mode=search.match_mode,
                    exclude=search.exclude,
                )
                if not hits:
                    counts["no_keyword_match"] += 1
                    continue

                job.search_name = search.name
                job.matched_keywords = hits
                seen_this_run.add(job.id)
                new_jobs.append(job)
                search_matches += 1

        log.info(
            "%s: retrieved %d listings; %d matched",
            search.name,
            search_retrieved,
            search_matches,
        )

    log.info(
        "Search summary: %(retrieved)d retrieved, %(already_seen)d already seen, "
        "%(duplicate)d duplicates, %(too_old)d outside date window, "
        "%(excluded_location)d excluded by location, %(no_keyword_match)d "
        "without a keyword match; %(matched)d new matches.",
        {**counts, "matched": len(new_jobs)},
    )
    return new_jobs


def is_excluded_location(location: str, terms: list[str]) -> bool:
    """True when the posting's location contains one of the excluded terms."""
    if not location or not terms:
        return False
    haystack = tokenize(location)
    return any(tokenize(term).strip() in haystack for term in terms if term.strip())


def notify(config: Config, jobs: list[Job]) -> list[str]:
    """Send the new-postings digest through every enabled channel."""
    errors: list[str] = []

    if config.email.enabled:
        per_recipient: dict[str, list[Job]] = {}
        by_name = {s.name: s for s in config.searches}
        for job in jobs:
            search = by_name.get(job.search_name)
            if search is None:
                continue
            for address in config.recipients_for(search):
                per_recipient.setdefault(address, []).append(job)

        for address, address_jobs in per_recipient.items():
            log.info(
                "Sending %d matching job(s) to %s",
                len(address_jobs),
                address,
            )
            try:
                send_email(config.email, [address], address_jobs)
                log.info("SMTP accepted the notification for %s", address)
            except EmailError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"Email delivery to {address} failed: {exc!r}")

    if config.ntfy.enabled:
        try:
            send_ntfy(config.ntfy, jobs)
        except Exception as exc:
            errors.append(f"ntfy notification failed: {exc}")

    return errors


def run(config: Config, dry_run: bool = False) -> int:
    """Run one hunt. Returns the process exit code."""
    store = SeenStore(config.settings.state_file, config.settings.forget_after_days)
    log.info("Loaded %d previously seen job(s).", len(store))

    jobs = collect_new_jobs(config, store)
    if not jobs:
        log.info("No new matching jobs. No notification email will be sent.")
        store.prune()
        store.save()
        return 0

    log.info("Found %d new matching job(s).", len(jobs))
    for job in jobs:
        log.info("  • %s — %s (%s)", job.title, job.company, job.url)

    if dry_run:
        log.info("Dry run: notifications were not sent and job history was not updated.")
        return 0

    errors = notify(config, jobs)
    if errors:
        for message in errors:
            log.error("%s", message)
        return 1

    for job in jobs:
        store.mark(job.id, job.title)
    store.prune()
    store.save()
    log.info("Successfully processed and recorded %d job(s).", len(jobs))
    return 0
