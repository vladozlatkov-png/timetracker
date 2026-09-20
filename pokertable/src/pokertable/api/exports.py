"""Hand history exports: JSON (lossless), CSV (per seat per hand), text (PokerStars-style)."""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Mapping


def results_csv(rows: Iterable[Mapping[str, Any]]) -> str:
    buf = io.StringIO()
    cols = ["game_id", "hand_number", "seat", "identity_id", "name", "big_blind", "net", "vpip", "pfr", "bets_raises", "calls", "went_to_showdown", "won_at_showdown", "timed_out"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: r[c] for c in cols})
    return buf.getvalue()


def hand_text(game_name: str, record: dict[str, Any]) -> str:
    started = next(e for e in record["events"] if e["type"] == "hand_started")
    names = {s["seat"]: s["name"] for s in started["seats"]}
    out = [f"PokerTable Hand #{record['hand_id']}: No Limit Hold'em ({record['small_blind']}/{record['big_blind']})"]
    out.append(f"Table '{game_name}' Seat #{record['button_seat']} is the button")
    for s in started["seats"]:
        out.append(f"Seat {s['seat']}: {s['name']} ({s['stack']} in chips)")
    phase = "preflop"
    for e in record["events"]:
        t = e["type"]
        if t == "blind":
            out.append(f"{names[e['seat']]}: posts blind {e['amount']}")
        elif t == "deal_hole":
            out.append(f"Dealt to {names[e['seat']]} [{' '.join(e['cards'])}]")
        elif t == "action":
            a = e["action"]
            if a in ("bet", "raise"):
                out.append(f"{names[e['seat']]}: {a}s to {e['amount']}")
            elif a == "call":
                out.append(f"{names[e['seat']]}: calls {e['amount']}")
            else:
                out.append(f"{names[e['seat']]}: {a}s")
        elif t == "timeout":
            out.append(f"{names[e['seat']]}: timed out, {e['fallback']}s")
        elif t == "street":
            phase = e["phase"]
            out.append(f"*** {phase.upper()} *** [{' '.join(e['board'])}]")
        elif t == "showdown":
            out.append(f"{names[e['seat']]}: shows [{' '.join(e['cards'])}]")
        elif t == "settlement":
            out.append("*** SUMMARY ***")
            for seat, net in e["payoffs"].items():
                out.append(f"Seat {seat}: {names[int(seat)]} {'won' if int(net) > 0 else 'lost'} {abs(int(net))}")
    return "\n".join(out) + "\n"
