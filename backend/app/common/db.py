#!/usr/bin/env python3
"""Database URL resolution (fail-fast, no hardcoded credentials)."""

import os


def get_postgres_url() -> str:
    """Return PostgreSQL connection URL from POSTGRES_URL or DATABASE_URL.

    Raises RuntimeError if neither environment variable is configured.
    """
    url = (os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "POSTGRES_URL (or DATABASE_URL) environment variable is required"
        )
    return url
