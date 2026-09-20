"""Turn a model reply into a Decision. Tolerates fences, prose, and trailing commentary."""

from __future__ import annotations

import json
import re

from .base import Decision

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_OBJ = re.compile(r"\{.*\}", re.S)
_WORD = re.compile(r"\b(fold|check|call|bet|raise|all[- ]?in)\b", re.I)
_AMT = re.compile(r"(?:to|amount)\D{0,10}(\d+)", re.I)


class ParseError(ValueError):
    pass


def parse_decision(text: str) -> Decision:
    text = (text or "").strip()
    m = _FENCE.search(text) or _OBJ.search(text)
    if m:
        try:
            data = json.loads(m.group(1) if m.re is _FENCE else m.group(0))
            action = str(data.get("action", "")).lower().strip()
            if action:
                amt = data.get("amount")
                return Decision(action, int(amt) if amt not in (None, "") else None, data.get("say"), data.get("reasoning"))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    w = _WORD.search(text)
    if not w:
        raise ParseError(f"no action found in reply: {text[:120]!r}")
    action = w.group(1).lower().replace(" ", "").replace("-", "")
    if action == "allin":
        return Decision("raise", 10**9)
    a = _AMT.search(text)
    return Decision(action, int(a.group(1)) if a else None)
