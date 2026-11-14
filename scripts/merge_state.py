"""Merge two seen-job state files into one.

Used by the workflow when concurrent runs have both discovered postings.
The union is correct for concurrently notified jobs, but old records must
still obey the retention period configured in config.yaml.

    python scripts/merge_state.py MINE THEIRS OUT
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_hunter.storage import merge_state_files  # noqa: E402


def configured_retention_days() -> int:
    config_path = Path("config.yaml")
    if not config_path.exists():
        return 30
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return int((config.get("settings") or {}).get("forget_after_days", 30))
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return 30


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    count = merge_state_files(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
        forget_after_days=configured_retention_days(),
    )
    print(f"{count} job history record(s) retained.")
