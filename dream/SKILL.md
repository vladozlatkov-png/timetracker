---
name: dream
description: >
  Overnight memory consolidation. Reads Claude Code session transcripts from the last 24 hours
  across every project, compares them against current memory (~/.claude/CLAUDE.md and the Obsidian
  vault), and proposes corrections, preferences, new facts, duplicate merges, and stale-memory
  removals as a numbered report for morning review. Only trivially safe fixes are auto-applied.
  Use when the user says "dream", "run dream", "consolidate memory", or asks what last night's
  dream proposed. Also runs unattended on a 3am schedule.
---

# Dream — overnight memory consolidation

Working sessions generate two things worth keeping: corrections the user made, and
facts that turned out to be true. Both are normally lost, because the agent that
learned them is busy finishing the task and the next session starts cold.

This skill separates learning from doing. It runs when nothing else is happening,
reads across *all* sessions rather than one, and proposes memory changes with
evidence attached.

---

## Guardrails

Read these before anything else. This skill usually runs at 3am with nobody watching.

1. **Never block.** No `AskUserQuestion`, no clarifying questions, no waiting for input.
   If something is ambiguous, propose it and let the morning review settle it.
2. **Never delete a memory outright.** Removal is always a *proposal*. The one exception
   is an exact duplicate line, which is covered under auto-apply below.
3. **Auto-apply is deliberately tiny.** See the allowlist in Step 5. When in doubt, propose.
4. **Every proposal carries evidence** — a short verbatim quote from a transcript plus the
   session it came from. A proposal you cannot quote for is a proposal you should drop.
5. **Never touch project code, git state, or anything outside the memory targets.**
6. **Absent input is success, not failure.** A quiet day means a short report, not an
   invented one. Do not manufacture proposals to fill space.

---

## Step 1 — Gather the window

```bash
DREAM_HOME="$HOME/.claude/dream"
mkdir -p "$DREAM_HOME/reports" "$DREAM_HOME/state"
STAMP=$(date +%Y-%m-%d)

python3 "$HOME/.claude/skills/dream/scripts/scan_transcripts.py" \
  --hours 24 \
  --out "$DREAM_HOME/state/digest-$STAMP.json"
```

The scanner reduces the raw transcripts (often tens of MB) to a digest of a few
hundred KB by keeping only what matters: real user messages, agent conclusions,
failed tool calls, and pre-flagged correction/preference candidates.

Read the digest. Note the shape of the day before analysing it:

- `totals.corrections` and `totals.tool_errors` — how rough the day was
- `totals.subagent_turns` — whether multi-agent work was involved
- `sessions[].cwd` and `.git_branch` — which projects were touched

**If `session_count` is 0**: write a report saying so and stop. Do not fabricate.

The scanner's `corrections` and `preferences` arrays are *candidates from a regex*,
not conclusions. Verify each against its surrounding message before trusting it, and
read the full `user_messages` list too — the regex misses corrections phrased politely.

---

## Step 2 — Load current memory

Read what already exists, so proposals are diffs against reality rather than
free-floating suggestions.

```bash
cat "$HOME/.claude/CLAUDE.md" 2>/dev/null
ls "$HOME/.claude/dream/reports/" | tail -5
```

For the vault, resolve the mount the same way the `session-memory` skill does:

```bash
VAULT=""
for c in "/Volumes/Obsidian/VVault" "/Volumes/VVault" "/Volumes/Obsidian VVault/VVault"; do
  [ -d "$c" ] && VAULT="$c" && break
done
[ -z "$VAULT" ] && osascript -e 'mount volume "smb://DS224plus._smb._tcp.local/Obsidian"' 2>/dev/null && sleep 3
for c in "/Volumes/Obsidian/VVault" "/Volumes/VVault" "/Volumes/Obsidian VVault/VVault"; do
  [ -d "$c" ] && VAULT="$c" && break
done
echo "VAULT=$VAULT"
```

If the vault is unreachable (NAS asleep, laptop off the network), **carry on anyway**:
propose CLAUDE.md changes only, and record `vault_reachable: false` in the report so
the morning review knows the picture is partial. Do not fail the whole run over it.

When the vault is available, read the last few days of `Sessions/YYYY-MM/` notes —
those are the existing record that new facts must be checked against for duplication.

---

## Step 3 — Analyse

Work through five categories. For each finding, hold onto the quote that proves it.

**1. Corrections** — the user told the agent it was wrong.
The highest-value category by far: each one is a mistake with the fix attached.
Look for repeats across *different* sessions. A correction made once is an incident;
the same correction in three sessions is a missing memory rule, and should be
proposed as one rule rather than three notes.

**2. Preferences** — a standing instruction, not a one-off request.
The test is whether it generalises. "Use tabs in this file" is a task detail;
"I always use tabs" is a preference. Only the second belongs in CLAUDE.md.

**3. New facts worth keeping** — durable truths about the user's projects, environment,
or setup that were discovered and would cost real time to rediscover. Prefer facts
that were *expensive* to learn: a non-obvious build step, a service that isn't
reachable from a given environment, an API that behaves unexpectedly.

**4. Duplicates** — the same fact recorded in two places, possibly worded differently.
Propose a merge, naming which copy survives.

**5. Stale or wrong** — memory contradicted by what actually happened today.
This is the category that quietly corrupts a memory file, because a confidently
wrong note is worse than no note. Quote both the memory and the contradicting
evidence.

### Cross-session patterns

This is the part a single session genuinely cannot do, so spend effort here.
Explicitly ask:

- Did the same error appear in more than one project today?
- Did the user correct the same behaviour in unrelated contexts?
- Did several subagents repeat one mistake, suggesting a bad instruction upstream?
- Is there a workaround being reinvented repeatedly that deserves to be written down?

A pattern seen in **two or more distinct `session_id`s** is worth a proposal on its
own, even when no single session would have justified one.

### What not to propose

- Task-specific details with no future value ("the bug was on line 42")
- Anything already in memory in equivalent words
- Restatements of general knowledge the model already has
- Preferences inferred from a single ambiguous message
- Anything you cannot attach a quote to

---

## Step 4 — Write the proposals file

Write `$DREAM_HOME/state/proposals-$STAMP.json`. The structured file is what makes
approval precise later — the HTML report is rendered from it, not the reverse.

```json
{
  "date": "2026-08-04",
  "window_hours": 24,
  "vault_reachable": true,
  "sessions_reviewed": 7,
  "projects": ["timetracker", "Aegis-Bot"],
  "day_summary": "Two projects. Repeated correction about commit message style across both.",
  "auto_applied": [
    {"id": "A1", "target": "~/.claude/CLAUDE.md", "what": "Fixed typo 'preferrence' -> 'preference'", "line": 42}
  ],
  "proposals": [
    {
      "id": 1,
      "category": "correction",
      "target": "~/.claude/CLAUDE.md",
      "action": "add",
      "confidence": "high",
      "summary": "Never push directly to main; always branch first.",
      "change": "Add under '## Git': Always create a branch before committing. Never push to main.",
      "evidence": [
        {"quote": "no — I said branch first, don't commit straight to main",
         "session_id": "9c313ac2", "project": "timetracker", "ts": "2026-08-04T14:22:00Z"}
      ],
      "rationale": "Same correction appeared in two unrelated projects today."
    }
  ]
}
```

Field rules:

- `id` — integers from 1, stable within a report. Auto-applied items use `A1`, `A2`.
- `category` — `correction` | `preference` | `fact` | `duplicate` | `stale`
- `action` — `add` | `edit` | `remove` | `merge`
- `confidence` — `high` (explicit and repeated) | `medium` (explicit, once) | `low` (inferred)
- `change` — precise enough to apply without re-reading transcripts
- `evidence` — at least one quote, trimmed to the relevant sentence

Order proposals by category, then by confidence descending. Corrections first —
they are what the user most wants to see.

---

## Step 5 — Auto-apply, narrowly

Apply **only** these, and only to `~/.claude/CLAUDE.md`:

- Spelling typos in existing prose, where the intended word is unambiguous
- Broken markdown syntax — unclosed code fences, malformed links
- **Exact** duplicate lines (byte-identical after whitespace normalisation)
- Heading/TOC index repair where a heading was renamed and the index wasn't

Everything else is a proposal. Specifically **never** auto-apply: new rules, new
facts, removals, rewording that changes meaning, or any vault change.

Back up before touching anything:

```bash
cp "$HOME/.claude/CLAUDE.md" "$DREAM_HOME/state/CLAUDE.md.bak-$STAMP" 2>/dev/null
```

Record every auto-applied change in `auto_applied` so the morning review sees it.
If there is nothing to auto-apply — the normal case — leave the array empty.

---

## Step 6 — Render the report

```bash
python3 "$HOME/.claude/skills/dream/scripts/render_report.py" \
  --proposals "$DREAM_HOME/state/proposals-$STAMP.json" \
  --out "$DREAM_HOME/reports/dream-$STAMP.html"
```

Then update the pointer to the newest report:

```bash
ln -sf "$DREAM_HOME/reports/dream-$STAMP.html" "$DREAM_HOME/latest.html"
```

---

## Step 7 — Close out

Print a short summary: sessions reviewed, proposal count by category, auto-applied
count, and the report path. Two or three lines. Nobody is reading this at 3am; it
exists for the log.

---

## Morning review

When the user asks about the dream — "what did dream find", "show me the dream
report", "apply 1, 3 and 5" — read the newest `proposals-*.json` and act:

- **Show** — summarise by category, corrections first. Do not re-derive anything.
- **Apply** — for each approved id, make exactly the edit in `change`, nothing more.
  Back up first. Confirm each one applied.
- **Reject** — append the id to `$DREAM_HOME/state/rejected.json` with the date and
  the reason if given. Consult this file on future runs and do not re-propose
  something already rejected twice — that is the signal it was a bad idea, not a
  missed one.

After applying, append a line to `$DREAM_HOME/state/applied.log` recording the date,
the ids, and the targets.
