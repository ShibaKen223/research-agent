"""Tiny on-disk JSON cache so re-running the same query/analysis doesn't re-pay.

The expensive parts of a run — the Claude analysis (Sonnet) and the Haiku
relevance gate — are deterministic (temperature=0), so an identical input always
yields an identical output. Caching them keyed on their inputs makes a re-run of
the same keyword instant and free; the network search is cached too, so re-runs
also stop hammering the (rate-limited) free APIs.

Entries live under `.research_agent_cache/` in the working directory (override
with `RESEARCH_AGENT_CACHE_DIR`). Caching is on by default; disable it for a run
with the CLI `--no-cache` flag or by setting `RESEARCH_AGENT_NO_CACHE=1`. A
`VERSION` tag is folded into every key, so bumping it (or changing a prompt that
feeds into a key) transparently invalidates stale entries instead of serving them.
"""

import hashlib
import json
import os
from pathlib import Path

# Bump to invalidate every cached entry at once (e.g. if a cached shape changes).
VERSION = "1"

_DISABLE_VALUES = {"1", "true", "yes", "on"}
_enabled = os.environ.get("RESEARCH_AGENT_NO_CACHE", "").strip().lower() not in _DISABLE_VALUES


def disable() -> None:
    """Turn the cache off for the rest of the process (used by `--no-cache`)."""
    global _enabled
    _enabled = False


def enabled() -> bool:
    return _enabled


def _dir() -> Path:
    override = os.environ.get("RESEARCH_AGENT_CACHE_DIR")
    return Path(override) if override else Path.cwd() / ".research_agent_cache"


def key(*parts) -> str:
    """Hash the inputs that determine an output into a stable filename-safe key.

    `default=str` lets non-JSON parts (e.g. a Path) still hash deterministically.
    """
    raw = json.dumps([VERSION, *parts], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _path(namespace: str, k: str) -> Path:
    return _dir() / namespace / f"{k}.json"


def get(namespace: str, k: str):
    """Return the cached value, or None on a miss / disabled cache / unreadable file."""
    if not _enabled:
        return None
    path = _path(namespace, k)
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return None


def set(namespace: str, k: str, value) -> None:
    """Best-effort write; a cache that can't be written must never break the run."""
    if not _enabled:
        return
    path = _path(namespace, k)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
