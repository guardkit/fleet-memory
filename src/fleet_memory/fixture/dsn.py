"""Credential-hygiene helpers for DSN handling in the fixture package.

Exceptions and log lines must name ``host:port/db`` only — never a full DSN
and never a password (TASK-ABL5-002 hard requirement).
"""

from __future__ import annotations

__all__ = ["sanitize_target", "scrub_secrets"]


def _parse_conninfo(dsn: str) -> dict[str, str]:
    """Parse a libpq DSN (URL or keyword form) into a dict; empty on failure."""
    try:
        from psycopg.conninfo import conninfo_to_dict

        return {k: str(v) for k, v in conninfo_to_dict(dsn).items() if v is not None}
    except Exception:
        return {}


def sanitize_target(dsn: str) -> str:
    """Return a credential-free ``host:port/db`` label for ``dsn``.

    Safe to embed in exception messages, log lines, and the fixture manifest's
    ``source_target`` field.
    """
    info = _parse_conninfo(dsn)
    host = info.get("host") or "localhost"
    port = info.get("port") or "5432"
    dbname = info.get("dbname") or ""
    return f"{host}:{port}/{dbname}"


def scrub_secrets(text: str, dsn: str) -> str:
    """Remove the raw DSN and its password from ``text`` before it reaches an error."""
    if not text:
        return ""
    scrubbed = text.replace(dsn, "<dsn>")
    password = _parse_conninfo(dsn).get("password")
    if password:
        scrubbed = scrubbed.replace(password, "***")
    return scrubbed
