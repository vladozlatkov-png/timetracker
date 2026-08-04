# Dream — overnight memory consolidation for Claude Code

Every working session produces two things worth keeping: the corrections you made,
and the facts that turned out to be true. Both are normally lost. The agent that
learned them is busy finishing your task, and tomorrow's session starts cold.

Dream separates learning from doing. At 3am, with nothing else running, it reads
your session transcripts from the last 24 hours — **across every project, not just
one** — compares them against your current memory, and leaves a report of proposed
changes for you to approve over coffee.

Nothing enters memory without your say-so.

---

## Why cross-session matters

A single session can only see itself. It cannot tell the difference between a
one-off slip and a habit, so it either records nothing or records everything.

Reading across sessions changes what is knowable:

- You corrected the same behaviour in two unrelated projects → that is a missing
  rule, not two incidents.
- Three subagents made the same mistake → the fault is upstream, in their instructions.
- A workaround got reinvented twice → it should have been written down the first time.

None of those are visible from inside one transcript.

---

## Install

On your Mac:

```bash
git clone https://github.com/vladozlatkov-png/timetracker.git
cd timetracker/dream
./install.sh
```

The installer checks prerequisites, copies the skill to `~/.claude/skills/dream/`,
self-tests the scanner against your real transcripts, and registers a launchd job
for 03:00 daily.

```bash
./install.sh --no-schedule   # skill only, run it manually
./install.sh --uninstall     # remove the schedule, keep reports and state
```

Linux: skip the installer and point cron at `scripts/run_dream.sh`.

---

## The loop

**Overnight** — the job wakes at 03:00, scans the last 24 hours, and writes a report.
If nothing happened, it exits without starting a session. If your Mac was asleep,
launchd runs it at the next wake rather than skipping the day.

**Morning** — open the report:

```bash
open ~/.claude/dream/latest.html
```

Proposals are grouped by category, corrections first, each with the quote that
justifies it. Tick the ones you want, hit Copy, and paste the line back into
Claude Code:

```
apply dream proposals 1, 3, 7
```

Rejections are remembered. Anything you turn down twice stops being proposed.

---

## What it proposes

| Category | What it catches |
|---|---|
| **Corrections** | You told me I was wrong. Highest value — a mistake with the fix attached. |
| **Preferences** | Standing instructions, not one-off requests. Only things that generalise. |
| **New facts** | Durable truths that were expensive to learn and would cost time to rediscover. |
| **Duplicates** | The same fact in two places, possibly worded differently. |
| **Stale or wrong** | Memory contradicted by what actually happened. A confidently wrong note is worse than no note. |

Every proposal carries a verbatim quote and the session it came from. A finding
that cannot be quoted for is dropped rather than guessed at.

### What it will not do

- Delete a memory on its own. Removal is always a proposal.
- Record task trivia with no future value.
- Infer a preference from one ambiguous message.
- Touch your code, your git state, or anything outside the two memory targets.

**Auto-apply is deliberately tiny** — spelling typos, broken markdown fences,
byte-identical duplicate lines, and heading-index repair. Nothing semantic, and
nothing in the vault. A backup is taken first, and every auto-applied change is
listed at the top of the report.

---

## Targets

- `~/.claude/CLAUDE.md` — how I behave: your preferences, corrections, recurring
  mistakes to avoid.
- **Obsidian vault** (`smb://DS224plus…/Obsidian → VVault/`) — project facts and
  session retrospectives, alongside what `session-memory` writes.

If the NAS is unreachable the run continues against `CLAUDE.md` alone and the
report says so, rather than failing outright.

---

## Layout

```
~/.claude/skills/dream/     the skill and its scripts
~/.claude/dream/
├── latest.html             symlink to the newest report
├── reports/                dream-YYYY-MM-DD.html      (30 days)
├── state/
│   ├── digest-*.json       distilled transcripts       (7 days)
│   ├── proposals-*.json    the machine-readable report
│   ├── rejected.json       what you turned down
│   ├── applied.log         what you approved
│   └── CLAUDE.md.bak-*     backup before any auto-apply
└── logs/                   dream-YYYY-MM-DD.log        (30 days)
```

---

## How the scanner earns its keep

Raw transcripts are far too large to hand to a model — a busy day runs to tens of
megabytes, most of it tool output that is worthless the moment it is read. On a
real session, `scan_transcripts.py` reduced 1.1 MB to 11 KB, a 100:1 cut, while
keeping every user message.

It keeps what a consolidation pass can act on:

- Real user messages, with Claude Code's injected wrappers (`<system-reminder>`,
  slash-command echoes, skill dumps) stripped out
- Failed tool calls — `is_error: true` is the clearest mistake signal in a transcript
- Subagent turns, flagged via `isSidechain`, so multi-agent mistakes are attributable
- Pre-flagged correction and preference candidates

Those flags are regex candidates, not conclusions — the skill verifies each one in
context. Patterns are anchored to a second-person subject or an imperative,
because bare keywords like *instead*, *again* and *stop* fire constantly inside
pasted articles. In a long message only the opening window counts, since a real
correction leads with the pushback rather than burying it 4 kB deep.

Run it standalone any time:

```bash
python3 ~/.claude/skills/dream/scripts/scan_transcripts.py --hours 24 --out -
```

---

## Troubleshooting

**Job never runs.** Almost always PATH. launchd starts jobs with a nearly empty
environment — no shell profile, no nvm. `run_dream.sh` resolves `claude` from the
usual install locations, but check:

```bash
launchctl list | grep claude-dream
cat ~/.claude/dream/logs/launchd.err.log
```

**Report is empty.** Check the window actually had activity:

```bash
find ~/.claude/projects -name '*.jsonl' -mtime -1 | wc -l
```

Zero means the job correctly did nothing.

**Force a run now.**

```bash
launchctl kickstart -k gui/$(id -u)/com.vlado.claude-dream
tail -f ~/.claude/dream/logs/dream-$(date +%F).log
```

**Proposals feel noisy.** Reject them — twice-rejected proposals stop appearing.
If a whole category is unhelpful, say so and the skill's analysis section can be
narrowed.

---

## Not on the cloud

This only works where your transcripts live. Claude Code on the web clones a fresh
container per session and reclaims it afterwards, so there is no 24-hour history to
read and no route to the NAS. A cloud Routine would run faithfully every night and
find nothing. Dream belongs on the machine that does the work.
