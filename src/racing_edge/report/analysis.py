"""Render the optimisation analysis — honest, sample-gated, CLV-led."""

from __future__ import annotations

from racing_edge.measurement.analyse import by_conviction, by_signal, walk_forward
from racing_edge.measurement.metrics import Summary
from racing_edge.measurement.record import SettledPick

_RULE = "=" * 66
_MIN_ACT = 100   # protocol: act floor
_MIN_DIR = 30    # below this, not even a direction


def _line(label: str, s: Summary) -> str:
    clv = f"{s.mean_clv_pct:+.1f}%" if s.mean_clv_pct is not None else "  —"
    beat = f"{s.pct_positive_clv:.0f}%" if s.pct_positive_clv is not None else " —"
    flag = "" if s.n >= _MIN_ACT else ("  (thin)" if s.n >= _MIN_DIR else "  (noise)")
    return f"  {label:<26}{s.n:>5}{s.win_pct:>6.0f}%{s.roi_pct:>8.1f}%{clv:>9}{beat:>7}{flag}"


def render_analysis(picks: list[SettledPick]) -> str:
    method = [p for p in picks if p.system == "method"]
    if not method:
        return "No method picks in the ledger yet — run the backtest first."
    head = f"  {'':<26}{'n':>5}{'win%':>7}{'ROI%':>8}{'CLV':>9}{'beat':>7}"
    lines = [_RULE, "  OPTIMISATION ANALYSIS — where (if anywhere) the edge lives", _RULE]

    lines.append("\n  by CONVICTION (does the edge concentrate in strong picks?)")
    lines.append(head)
    for label, s in by_conviction(picks):
        lines.append(_line(label, s))

    lines.append("\n  WALK-FORWARD (does it hold on the later half, or front-load?)")
    lines.append(head)
    for label, s in walk_forward(picks):
        lines.append(_line(label, s))

    lines.append("\n  by SIGNAL — CLV where it fired vs where it didn't (ΔCLV, sorted)")
    lines.append(f"  {'signal':<22}{'n_fired':>8}{'CLV_fired':>11}{'CLV_not':>9}{'Δ':>8}")
    rows = []
    for name, fired, notf in by_signal(picks):
        if fired.mean_clv_pct is None or notf.mean_clv_pct is None:
            continue
        rows.append((name, fired, notf, fired.mean_clv_pct - notf.mean_clv_pct))
    for name, fired, notf, delta in sorted(rows, key=lambda r: -r[3]):
        flag = "" if fired.n >= _MIN_ACT else ("  (thin)" if fired.n >= _MIN_DIR else "  (noise)")
        lines.append(f"  {name:<22}{fired.n:>8}{fired.mean_clv_pct:>10.1f}%"
                     f"{notf.mean_clv_pct:>8.1f}%{delta:>+7.1f}%{flag}")

    lines.append("\n" + _RULE)
    lines.append("  READ: CLV leads. A signal/threshold only earns a change if it helps on the")
    lines.append("  LATER half too and clears the sample gate (>=100 to act). Anything in a")
    lines.append("  small cell is a hypothesis for next winter, NOT a finding. Don't mine.")
    return "\n".join(lines)
