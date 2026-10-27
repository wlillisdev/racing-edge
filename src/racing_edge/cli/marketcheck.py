"""The pre-off market check: what the Betfair money has done since the morning read.

    python -m racing_edge.cli.marketcheck NOW.json --morning MORNING.json [--min-minutes 15]
    python -m racing_edge.cli.marketcheck betfair.json            # morning read: price v forecast only

His word, 27 Oct: "why don't you do your initial selection, and then before the
first race read Betfair odds again, and then update your selection based on
that." This prints, race by race, each runner's bookmaker forecast (Betfair's
card), his exchange price in the morning file and his price now, with the move.
It FLAGS; it never picks. Every flag is a question to put to the form ("what in
the snapshot explains this money?"), never a gate.

Exchange and forecast are compared as SHARES OF THEIR OWN BOOK (each race's
prices normalised to 100%), so a forecast with a big or small overround does not
fake a move. What one day said (27 Oct, every GB runner with a tight market): no
band of SUPPORTED horses was steadily profitable (+5.0, -6.1, -7.3 for 2x and up
at 08:05, 11:05, 12:05), so money alone is not a pick. The FRIENDLESS ones (the
exchange well longer than the forecast) were the steady losers: 6 of 48 won,
-23.8 at 11:05; 7 of 65, -30.1 at 12:05. Drifters, morning to SP, won 4 of 82.
One day: reading aids, re-measured by the night grade, never thresholds that
pick or rule out a horse.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

TIGHT = 1.25      # lay / back at or under this: the mid price is trusted
FIRMED = 1.2      # morning price / price now
SUPPORT = 1.2     # exchange share of the book / forecast share (1/SUPPORT: friendless)
DRIFT = 1.5       # price now / morning price
TOP = 4           # the market leaders always shown


def price(r: dict) -> tuple[float | None, bool]:
    """(price, trusted). Mid of back and lay when the spread is tight, else the
    last traded price (or the back) marked untrusted."""
    b, l = r.get("back"), r.get("lay_best")
    if b and l and l / b <= TIGHT:
        return round((b + l) / 2, 2), True
    p = r.get("ltp") or b
    return (p, False) if p else (None, False)


def forecast(r: dict) -> float | None:
    m = r.get("meta") or {}
    try:
        return float(m["FORECASTPRICE_NUMERATOR"]) / float(m["FORECASTPRICE_DENOMINATOR"]) + 1
    except (KeyError, ValueError, ZeroDivisionError):
        return None


def flags(share: float | None, morning: float | None, now: float | None, trusted: bool) -> list[str]:
    """share: his exchange share of the book over his forecast share (1.0 = as forecast)."""
    if now is None or not trusted:
        return []
    out = []
    if share and share >= SUPPORT:
        out.append(f"SUPPORTED x{share:.1f} v forecast")
    elif share and share <= 1 / SUPPORT:
        out.append(f"FRIENDLESS x{share:.1f} v forecast")
    if morning and morning / now >= FIRMED:
        out.append(f"FIRMED {morning:g}->{now:g}")
    if morning and now / morning >= DRIFT:
        out.append(f"DRIFT {morning:g}->{now:g}")
    return out


def check(now_file: list, morning_file: list | None = None,
          utc_now: datetime | None = None, min_minutes: int = 0) -> list[dict]:
    """One dict per race, in off-time order: venue, start, too_late, rows."""
    morning = {}
    for m in morning_file or []:
        for r in m.get("runners", []):
            morning[(m.get("market_id"), r.get("selection_id"))] = price(r)[0]
            morning.setdefault(("name", r.get("name", "").lower()), price(r)[0])
    races = []
    for m in sorted(now_file, key=lambda m: m.get("start", "")):
        start = datetime.fromisoformat(m["start"].replace("Z", "+00:00"))
        too_late = bool(utc_now) and start < utc_now + timedelta(minutes=min_minutes)
        runners = [(r, price(r), forecast(r)) for r in m.get("runners", [])]
        fbook = sum(1 / fc for _, _, fc in runners if fc)
        xbook = sum(1 / p for _, (p, _), _ in runners if p)
        rows = []
        for r, (p, ok), fc in runners:
            mp = morning.get((m.get("market_id"), r.get("selection_id")),
                             morning.get(("name", r.get("name", "").lower())))
            share = (fc * fbook) / (p * xbook) if fc and p and fbook and xbook else None
            rows.append({"name": r.get("name"), "forecast": fc, "morning": mp,
                         "now": p, "trusted": ok, "flags": flags(share, mp, p, ok)})
        rows.sort(key=lambda x: x["now"] or 9999)
        races.append({"venue": m.get("venue"), "start": start, "too_late": too_late,
                      "name": m.get("market_name"), "rows": rows})
    return races


def render(races: list[dict]) -> str:
    def f(x):
        return "-" if x is None else f"{x:g}"
    out = []
    for race in races:
        head = f"### {race['venue']} ({race['name']})"
        if race["too_late"]:
            out.append(f"{head}: TOO LATE, the morning pick stands")
            continue
        shown = [r for i, r in enumerate(race["rows"]) if i < TOP or r["flags"]]
        out.append(head)
        out.append("| horse | forecast | morning | now | flags |")
        out.append("|---|---|---|---|---|")
        for r in shown:
            now = f(r["now"]) + ("" if r["trusted"] else " (thin)")
            fc = "-" if r["forecast"] is None else f"{r['forecast']:.1f}"
            out.append(f"| {r['name']} | {fc} | {f(r['morning'])} | {now} | {'; '.join(r['flags'])} |")
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("now", help="the newest data/odds/<day>-HHMM-betfair-horses.json")
    ap.add_argument("--morning", help="the morning snapshot's betfair.json")
    ap.add_argument("--min-minutes", type=int, default=15,
                    help="races off sooner than this are TOO LATE")
    ap.add_argument("--at", help="the check's UTC time, YYYY-MM-DDTHH:MM (a replay); default now")
    a = ap.parse_args(argv)
    at = (datetime.fromisoformat(a.at).replace(tzinfo=timezone.utc) if a.at
          else datetime.now(timezone.utc))
    with open(a.now) as fh:
        now_file = json.load(fh)
    morning_file = None
    if a.morning:
        with open(a.morning) as fh:
            morning_file = json.load(fh)
    print(render(check(now_file, morning_file, at, a.min_minutes)))


if __name__ == "__main__":
    main()
