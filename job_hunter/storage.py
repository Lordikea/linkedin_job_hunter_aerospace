"""Remember which postings were already sent, so only new ones notify."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


class SeenStore:
    def __init__(self, path: str | Path, forget_after_days: int = 30):
        self.path = Path(path)
        self.forget_after_days = forget_after_days
        self._seen: dict[str, dict] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(data, dict):
            self._seen = data.get("jobs", {}) if "jobs" in data else data

    def __contains__(self, job_id: str) -> bool:
        return job_id in self._seen

    def __len__(self) -> int:
        return len(self._seen)

    def mark(self, job_id: str, title: str = "") -> None:
        self._dirty = True
        self._seen[job_id] = {
            "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "title": title,
        }

    def prune(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.forget_after_days)
        stale = []
        for job_id, meta in self._seen.items():
            raw = (meta or {}).get("first_seen", "")
            try:
                first_seen = datetime.fromisoformat(raw)
            except (TypeError, ValueError):
                continue
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=timezone.utc)
            if first_seen < cutoff:
                stale.append(job_id)
        for job_id in stale:
            del self._seen[job_id]
        if stale:
            self._dirty = True
        return len(stale)

    def save(self) -> bool:
        """Write the file only when its contents have changed."""
        if not self._dirty and self.path.exists():
            return False

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "jobs": self._seen,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(self.path)
        self._dirty = False
        return True


def merge_seen(mine: dict, theirs: dict) -> dict:
    """Combine two seen-job maps, keeping the earliest sighting of each job."""
    merged = dict(theirs)
    for job_id, meta in mine.items():
        existing = merged.get(job_id)
        if existing is None:
            merged[job_id] = meta
            continue
        if str(meta.get("first_seen", "")) < str(existing.get("first_seen", "")):
            merged[job_id] = meta
    return merged


def merge_state_files(
    mine: Path | str,
    theirs: Path | str,
    out: Path | str,
    forget_after_days: int = 30,
) -> int:
    """Merge concurrent job histories and discard entries past their retention period."""

    def load(path: Path | str) -> dict:
        path = Path(path)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data.get("jobs", {}) if isinstance(data, dict) else {}

    merged = merge_seen(load(mine), load(theirs))
    cutoff = datetime.now(timezone.utc) - timedelta(days=forget_after_days)
    retained = {}
    for job_id, meta in merged.items():
        try:
            first_seen = datetime.fromisoformat((meta or {}).get("first_seen", ""))
        except (TypeError, ValueError):
            # Keep records with unknown timestamps rather than accidentally
            # forgetting jobs that may not have been notified successfully.
            retained[job_id] = meta
            continue
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        if first_seen >= cutoff:
            retained[job_id] = meta

    out_path = Path(out)
    current = load(out_path)
    if retained == current:
        return len(retained)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "jobs": retained,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return len(retained)

