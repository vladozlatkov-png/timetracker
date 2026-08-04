#!/bin/bash
#
# Headless entry point for the nightly dream pass. Invoked by launchd at 03:00,
# and safe to run by hand at any time.
#
# launchd starts jobs with a nearly empty environment — no PATH beyond the bare
# defaults, no shell profile, no nvm. That is the single most common reason a
# scheduled job that works in a terminal does nothing at 3am, so everything this
# script depends on is resolved explicitly below.

set -uo pipefail

DREAM_HOME="$HOME/.claude/dream"
LOG_DIR="$DREAM_HOME/logs"
LOCK="$DREAM_HOME/state/.lock"
STAMP="$(date +%Y-%m-%d)"
LOG="$LOG_DIR/dream-$STAMP.log"

mkdir -p "$LOG_DIR" "$DREAM_HOME/state" "$DREAM_HOME/reports"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

log "=== dream run starting (pid $$) ==="

# --- single instance -------------------------------------------------------
# A dream pass can outlive its slot on a slow night. Overlapping runs would
# race on the same proposals file, so the second one steps aside.
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -f "$LOCK/pid" ] && kill -0 "$(cat "$LOCK/pid" 2>/dev/null)" 2>/dev/null; then
    log "another run is active (pid $(cat "$LOCK/pid")); exiting"
    exit 0
  fi
  log "clearing stale lock"
  rm -rf "$LOCK" && mkdir "$LOCK" || { log "cannot acquire lock"; exit 1; }
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"; log "=== dream run finished (exit $?) ==="' EXIT

# --- locate the claude CLI -------------------------------------------------
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$HOME/.bun/bin:$PATH"

# Version managers install claude outside any standard PATH entry, so check the
# usual suspects before giving up.
if ! command -v claude >/dev/null 2>&1; then
  for candidate in \
    "$HOME/.claude/local/claude" \
    "$HOME/.local/bin/claude" \
    "$HOME/.bun/bin/claude" \
    /opt/homebrew/bin/claude \
    /usr/local/bin/claude \
    "$HOME"/.nvm/versions/node/*/bin/claude
  do
    if [ -x "$candidate" ]; then
      export PATH="$(dirname "$candidate"):$PATH"
      break
    fi
  done
fi

if ! command -v claude >/dev/null 2>&1; then
  log "FATAL: claude CLI not found on PATH. Set CLAUDE_BIN in the plist, or"
  log "       run: launchctl setenv PATH \"\$PATH\""
  exit 127
fi
log "claude: $(command -v claude)"

if ! command -v python3 >/dev/null 2>&1; then
  log "FATAL: python3 not found; the scanner cannot run"
  exit 127
fi

# --- guard against an empty window ----------------------------------------
# Cheap pre-check: if no transcript was touched recently there is nothing to
# dream about, and starting a model session would only burn tokens to conclude
# exactly that.
RECENT=$(find "$HOME/.claude/projects" -name '*.jsonl' -mtime -1 2>/dev/null | wc -l | tr -d ' ')
log "transcripts modified in last 24h: $RECENT"
if [ "$RECENT" -eq 0 ]; then
  log "nothing to dream about; exiting without starting a session"
  exit 0
fi

# --- run ------------------------------------------------------------------
PROMPT='Run the dream skill now. This is an unattended scheduled run: do not ask
questions, do not wait for input, and follow the skill'"'"'s guardrails exactly.
Auto-apply only the narrow allowlist; everything else goes in the report.'

log "invoking claude"
claude -p "$PROMPT" \
  --permission-mode acceptEdits \
  --allowedTools Bash Read Write Edit Glob Grep \
  >> "$LOG" 2>&1
STATUS=$?

if [ $STATUS -ne 0 ]; then
  log "claude exited non-zero: $STATUS"
  exit $STATUS
fi

REPORT="$DREAM_HOME/reports/dream-$STAMP.html"
if [ -f "$REPORT" ]; then
  ln -sf "$REPORT" "$DREAM_HOME/latest.html"
  log "report ready: $REPORT"
else
  log "WARNING: run completed but no report at $REPORT"
fi

# Keep 30 days of logs and reports; the state dir holds the durable record.
find "$LOG_DIR" -name 'dream-*.log' -mtime +30 -delete 2>/dev/null
find "$DREAM_HOME/reports" -name 'dream-*.html' -mtime +30 -delete 2>/dev/null
find "$DREAM_HOME/state" -name 'digest-*.json' -mtime +7 -delete 2>/dev/null

exit 0
