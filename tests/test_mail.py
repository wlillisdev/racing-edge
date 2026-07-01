"""Tests for the email adapter — it must NEVER crash the run, and must not try to send
when the SMTP env vars aren't configured."""

from __future__ import annotations

import sys

from racing_edge.report import mail


def test_not_configured_returns_false_and_never_raises(monkeypatch) -> None:
    for k in ("EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECIPIENT"):
        monkeypatch.delenv(k, raising=False)
    assert mail.configured() is False
    # send must return False (not attempt SMTP, not raise) when unconfigured
    assert mail.send("subj", "body") is False


def test_configured_true_only_when_all_present(monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_SENDER", "a@b.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "x")
    monkeypatch.delenv("EMAIL_RECIPIENT", raising=False)
    assert mail.configured() is False            # one missing -> not configured
    monkeypatch.setenv("EMAIL_RECIPIENT", "c@d.com")
    assert mail.configured() is True


def _main() -> int:
    # lightweight manual run (pytest provides monkeypatch; here we fake it)
    class _MP:
        def delenv(self, k, raising=False):
            import os
            os.environ.pop(k, None)
        def setenv(self, k, v):
            import os
            os.environ[k] = v
    test_not_configured_returns_false_and_never_raises(_MP())
    test_configured_true_only_when_all_present(_MP())
    print("PASS  test_mail")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
