"""Pytest fixtures + session-wide hermetic guards.

`_hermetic_secret_manager` (autouse) is the systematic defence against
the 2026-05-29 CI failure mode: when the Cloud Build worker SA has
`roles/secretmanager.secretAccessor`, `resolve_sync_dsn()` falls through
to Google Secret Manager and returns the REAL production DSN whenever a
test calls `monkeypatch.delenv` on both `DATABASE_URL_SYNC` and
`DATABASE_URL`. The test asserts `is None`; the resolver returns the
prod DSN. Result: stage 1 backend-tests in Cloud Build fails (and the
prod DSN leaks into the assertion error output).

Two earlier per-test fixes (test_drive_feedback.py:483-497,
test_audit_2026_05_29_p0_patches.py) handled this one test at a time,
but every NEW test that delenvs both DSN vars carries the same risk.
The autouse fixture closes that hole at the suite level:
  - Sets `DMA_DISABLE_SECRET_DSN_FALLBACK=1` for every test.
  - Clears the module-level cache before and after each test so a test
    that opts back in (by delenv-ing the guard) cannot pollute later
    tests.

Tests that legitimately want to exercise the Secret Manager fallback
opt out via `monkeypatch.delenv("DMA_DISABLE_SECRET_DSN_FALLBACK")` —
the current resolver tests cover that branch by mocking
`_try_secret_manager` directly rather than relying on real ADC.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add backend root to sys.path so `app.*` imports work in tests.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _hermetic_secret_manager(monkeypatch):
    """Default-deny the Secret Manager fallback in `resolve_sync_dsn`.

    Cloud Build identity has secretAccessor; without this fixture any
    test that calls `monkeypatch.delenv("DATABASE_URL"); delenv(SYNC)`
    silently fetches the prod DSN and asserts fail with the secret
    pasted into stderr.

    The fixture is autouse so EVERY test inherits the safe default.
    Tests that exercise the fallback path opt in explicitly:

        monkeypatch.delenv("DMA_DISABLE_SECRET_DSN_FALLBACK")
        monkeypatch.setattr(sync_dsn, "_try_secret_manager",
                            lambda: "postgresql+psycopg://...")
    """
    monkeypatch.setenv("DMA_DISABLE_SECRET_DSN_FALLBACK", "1")
    # Reset module-level cache so a previously-cached prod DSN from
    # a same-session opt-in test cannot leak into this one.
    from app.services import sync_dsn as _sd
    _sd._CACHED_SECRET_DSN = None
    _sd._SECRET_LOOKUP_ATTEMPTED = False
    yield
    # Reset again on teardown — same reasoning, opposite direction.
    _sd._CACHED_SECRET_DSN = None
    _sd._SECRET_LOOKUP_ATTEMPTED = False
