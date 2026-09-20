"""Poker-tracker statistics with confidence intervals.

Variance in poker is large. Every rate carries a 95% Wilson interval and
bb/100 carries a normal-approximation interval so a leaderboard cannot be
read as a ranking when the sample does not support one.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping

Z = 1.96


def wilson(successes: int, n: int) -> tuple[float, float, float]:
    """Return (rate, low, high) as fractions."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = successes / n
    denom = 1 + Z * Z / n
    centre = (p + Z * Z / (2 * n)) / denom
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def bb100(net_bb: list[float]) -> tuple[float, float, float]:
    n = len(net_bb)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(net_bb) / n
    if n < 2:
        return mean * 100, float("nan"), float("nan")
    var = sum((x - mean) ** 2 for x in net_bb) / (n - 1)
    se = math.sqrt(var / n)
    return mean * 100, (mean - Z * se) * 100, (mean + Z * se) * 100


def _pct(t: tuple[float, float, float]) -> dict[str, float]:
    return {"value": round(t[0] * 100, 1), "low": round(t[1] * 100, 1), "high": round(t[2] * 100, 1)}


def player_stats(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate hand_results rows into per-identity statistics."""
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[r["identity_id"]].append(r)
    out: dict[str, dict[str, Any]] = {}
    for ident, rs in groups.items():
        n = len(rs)
        net = sum(r["net"] for r in rs)
        net_bb = [r["net"] / r["big_blind"] for r in rs]
        b, lo, hi = bb100(net_bb)
        wts = sum(r["went_to_showdown"] for r in rs)
        bets = sum(r["bets_raises"] for r in rs)
        calls = sum(r["calls"] for r in rs)
        out[ident] = {
            "identity_id": ident,
            "name": rs[-1]["name"],
            "hands": n,
            "net_chips": net,
            "bb_per_100": {"value": round(b, 1), "low": None if math.isnan(lo) else round(lo, 1), "high": None if math.isnan(hi) else round(hi, 1)},
            "vpip": _pct(wilson(sum(r["vpip"] for r in rs), n)),
            "pfr": _pct(wilson(sum(r["pfr"] for r in rs), n)),
            "af": round(bets / calls, 2) if calls else (float(bets) if bets else 0.0),
            "wtsd": _pct(wilson(wts, n)),
            "wsd": _pct(wilson(sum(r["won_at_showdown"] for r in rs), wts)),
            "timeouts": sum(r["timed_out"] for r in rs),
            "sample_warning": n < 1000,
        }
    return out


def format_table(stats: Mapping[str, Mapping[str, Any]]) -> str:
    cols = ["name", "hands", "net", "bb/100 (95% CI)", "VPIP", "PFR", "AF", "WTSD", "W$SD", "timeouts"]
    lines = [" | ".join(cols)]
    for s in sorted(stats.values(), key=lambda x: -x["net_chips"]):
        b = s["bb_per_100"]
        ci = f"{b['value']:+.1f} ({b['low']:+.1f} .. {b['high']:+.1f})" if b["low"] is not None else f"{b['value']:+.1f}"
        lines.append(" | ".join(str(x) for x in [
            s["name"], s["hands"], f"{s['net_chips']:+d}", ci, f"{s['vpip']['value']}%", f"{s['pfr']['value']}%", s["af"],
            f"{s['wtsd']['value']}%", f"{s['wsd']['value']}%", s["timeouts"],
        ]))
    return "\n".join(lines)
