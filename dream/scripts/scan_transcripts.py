#!/usr/bin/env python3
"""
Scan Claude Code transcripts and emit a compact digest for the dream pass.

Raw transcripts are far too large to feed to a model directly — a single day of
agent work runs to tens of megabytes, most of it tool output that is worthless
the moment it is read. This extracts only the signal that a memory-consolidation
pass can act on: what the user actually said, what the agent concluded, and
where things went wrong.

Usage:
    scan_transcripts.py [--hours 24] [--projects-dir PATH] [--out PATH]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Per-item truncation. Generous enough to preserve meaning, tight enough that a
# runaway tool result can't blow up the digest.
MAX_USER_MSG = 2000
MAX_ASSISTANT_TEXT = 900
MAX_ERROR = 700
MAX_ITEMS_PER_SESSION = 120
MAX_DIGEST_BYTES = 400_000

# Wrapper text Claude Code injects into the user role. None of it was typed by
# the human, so none of it is evidence of a preference or a correction.
NOISE_PREFIXES = (
    "<local-command-caveat>",
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<system-reminder>",
    "<task-notification>",
    "<github-webhook-activity>",
    "Base directory for this skill:",
    "Caveat: The messages below were generated",
)

# Phrases that mark the user pushing back on something the agent did. These are
# the highest-value lines in any transcript: each one is a mistake with a
# correction attached, which is exactly what memory should absorb.
# Patterns are deliberately anchored to a second-person subject or an
# imperative. Bare keywords like "instead", "again" and "stop" fire constantly
# inside pasted articles and quoted material, which drowns the real signal.
CORRECTION_PATTERNS = [
    r"\bno[,.]?\s+(that|that's|thats|it|i|you|don't|dont)\b",
    r"\bthat'?s\s+(wrong|not right|incorrect|not what)\b",
    r"\bnot what i\b",
    r"\bi (said|told you|asked (you )?(for|to))\b",
    r"\byou (broke|missed|forgot|misunderstood|ignored|didn'?t)\b",
    r"\b(revert|undo|roll ?back)\b",
    r"(^|[.!?]\s*)(just |please )?stop\b",
    r"\bwhy did you\b",
    r"\b(try|do|read|run|check|say) (that |it |this )?again\b",
    r"\b(that|this|it|you)('?re| are| is| was)?\s+wrong\b",
    r"\bdoesn'?t work\b",
    r"\bstill (broken|failing|wrong|not)\b",
    r"(^|[.!?]\s*)actually[,.]?\s",
    r"\b(do|use|try|write|say|make|run|put) [^.!?]{0,40} instead\b",
    r"\binstead of (that|this|what you|doing that)\b",
]

# Phrases that mark a standing instruction rather than a one-off request.
PREFERENCE_PATTERNS = [
    r"\bi prefer\b",
    r"\bfrom now on\b",
    r"\bgoing forward\b",
    r"\bin (the )?future\b",
    r"\balways\b",
    r"\bnever\b",
    r"\bremember (that|to)\b",
    r"\bmake sure (you|to)\b",
    r"\bi (want|need) you to\b",
    r"\bdon'?t ever\b",
    r"\bplease (stop|don'?t|use|avoid)\b",
    r"\bmy (preference|convention|setup|workflow) is\b",
]

CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.I)
PREFERENCE_RE = re.compile("|".join(PREFERENCE_PATTERNS), re.I)

# A real correction leads with the pushback — "no, I meant…", "that's wrong…".
# A match buried 4kB into a pasted article is almost always quoted prose, so
# only the opening window of a long message counts.
LEAD_WINDOW = 400
SHORT_MSG = 600


def flag_match(regex, text):
    """Match anywhere in a short message, but only up front in a long paste."""
    if len(text) <= SHORT_MSG:
        return bool(regex.search(text))
    return bool(regex.search(text[:LEAD_WINDOW]))


def parse_ts(value):
    """Parse an ISO-8601 timestamp, tolerating the trailing Z and missing tz."""
    if not value or not isinstance(value, str):
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def truncate(text, limit):
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[+{len(text) - limit} chars truncated]"


def is_noise(text):
    """True for harness-injected wrapper text that the human never typed."""
    if not isinstance(text, str):
        return True
    stripped = text.lstrip()
    if not stripped:
        return True
    return any(stripped.startswith(prefix) for prefix in NOISE_PREFIXES)


def blocks_of(message):
    """Normalise message.content to a list of block dicts.

    Plain user turns arrive as a bare string; everything else is a list of
    typed blocks. Callers should not have to care which.
    """
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def flatten_tool_result(content):
    """Tool results are a string, or a list of blocks. Reduce both to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def scan_file(path, cutoff):
    """Extract one session's worth of signal from a transcript file."""
    session = {
        "file": str(path),
        "session_id": None,
        "cwd": None,
        "git_branch": None,
        "first_ts": None,
        "last_ts": None,
        "user_messages": [],
        "assistant_notes": [],
        "tool_errors": [],
        "tool_counts": {},
        "subagent_turns": 0,
        "corrections": [],
        "preferences": [],
        "truncated": False,
    }

    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"warn: cannot read {path}: {exc}", file=sys.stderr)
        return None

    item_count = 0
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue

            entry_type = entry.get("type")
            if entry_type not in ("user", "assistant"):
                continue

            ts = parse_ts(entry.get("timestamp"))
            if ts is None or ts < cutoff:
                continue

            # Metadata — last writer wins, which is fine since it is stable
            # across a session.
            session["session_id"] = entry.get("sessionId") or session["session_id"]
            session["cwd"] = entry.get("cwd") or session["cwd"]
            session["git_branch"] = entry.get("gitBranch") or session["git_branch"]
            if session["first_ts"] is None:
                session["first_ts"] = ts.isoformat()
            session["last_ts"] = ts.isoformat()

            is_sidechain = bool(entry.get("isSidechain"))
            if is_sidechain:
                session["subagent_turns"] += 1

            if item_count >= MAX_ITEMS_PER_SESSION:
                session["truncated"] = True
                continue

            message = entry.get("message")
            if not isinstance(message, dict):
                continue

            for block in blocks_of(message):
                btype = block.get("type")

                if btype == "text" and entry_type == "user":
                    text = block.get("text", "")
                    if is_noise(text):
                        continue
                    record = {
                        "ts": ts.isoformat(),
                        "text": truncate(text, MAX_USER_MSG),
                        "sidechain": is_sidechain,
                    }
                    session["user_messages"].append(record)
                    item_count += 1
                    # A line can be both a correction and a standing preference.
                    if flag_match(CORRECTION_RE, text):
                        session["corrections"].append(record)
                    if flag_match(PREFERENCE_RE, text):
                        session["preferences"].append(record)

                elif btype == "text" and entry_type == "assistant":
                    text = block.get("text", "")
                    if not text.strip():
                        continue
                    session["assistant_notes"].append(
                        {
                            "ts": ts.isoformat(),
                            "text": truncate(text, MAX_ASSISTANT_TEXT),
                            "sidechain": is_sidechain,
                        }
                    )
                    item_count += 1

                elif btype == "tool_use":
                    name = block.get("name", "unknown")
                    session["tool_counts"][name] = session["tool_counts"].get(name, 0) + 1

                elif btype == "tool_result" and block.get("is_error"):
                    body = flatten_tool_result(block.get("content"))
                    if body.strip():
                        session["tool_errors"].append(
                            {
                                "ts": ts.isoformat(),
                                "text": truncate(body, MAX_ERROR),
                                "sidechain": is_sidechain,
                            }
                        )
                        item_count += 1

                # thinking blocks are deliberately skipped: they are the agent's
                # scratch reasoning, not evidence of what the user wants.

    has_content = (
        session["user_messages"] or session["assistant_notes"] or session["tool_errors"]
    )
    return session if has_content else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument(
        "--projects-dir",
        default=str(Path.home() / ".claude" / "projects"),
        help="Root of Claude Code project transcripts.",
    )
    parser.add_argument("--out", default="-", help="Output path, or - for stdout.")
    args = parser.parse_args()

    projects_dir = Path(args.projects_dir).expanduser()
    if not projects_dir.is_dir():
        print(f"error: no transcripts directory at {projects_dir}", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.hours)
    # mtime is a cheap pre-filter; entry timestamps are the real gate. The pad
    # avoids skipping a file whose clock or flush lags slightly behind.
    mtime_floor = (cutoff - timedelta(hours=2)).timestamp()

    sessions = []
    scanned = skipped = 0
    for path in sorted(projects_dir.glob("*/*.jsonl")):
        try:
            if path.stat().st_mtime < mtime_floor:
                skipped += 1
                continue
        except OSError:
            continue
        scanned += 1
        result = scan_file(path, cutoff)
        if result:
            sessions.append(result)

    sessions.sort(key=lambda s: s.get("first_ts") or "")

    digest = {
        "generated_at": now.isoformat(),
        "window_hours": args.hours,
        "cutoff": cutoff.isoformat(),
        "projects_dir": str(projects_dir),
        "files_scanned": scanned,
        "files_skipped_by_mtime": skipped,
        "session_count": len(sessions),
        "totals": {
            "user_messages": sum(len(s["user_messages"]) for s in sessions),
            "corrections": sum(len(s["corrections"]) for s in sessions),
            "preferences": sum(len(s["preferences"]) for s in sessions),
            "tool_errors": sum(len(s["tool_errors"]) for s in sessions),
            "subagent_turns": sum(s["subagent_turns"] for s in sessions),
        },
        "sessions": sessions,
    }

    payload = json.dumps(digest, indent=2, ensure_ascii=False)

    # Last-resort cap. Drop assistant prose first — it is the most reconstructable
    # signal — then trim whole sessions oldest-first, so the newest work always
    # survives.
    if len(payload.encode("utf-8")) > MAX_DIGEST_BYTES:
        for session in digest["sessions"]:
            session["assistant_notes"] = session["assistant_notes"][:3]
            session["truncated"] = True
        payload = json.dumps(digest, indent=2, ensure_ascii=False)
        while len(payload.encode("utf-8")) > MAX_DIGEST_BYTES and len(digest["sessions"]) > 1:
            digest["sessions"].pop(0)
            digest["digest_trimmed"] = True
            payload = json.dumps(digest, indent=2, ensure_ascii=False)

    if args.out == "-":
        print(payload)
    else:
        out_path = Path(args.out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(f"wrote {out_path} ({len(payload):,} bytes, {len(sessions)} sessions)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
