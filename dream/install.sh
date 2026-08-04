#!/bin/bash
#
# Install the dream skill and its 3am schedule on macOS.
#
#   ./install.sh              install or upgrade
#   ./install.sh --uninstall  remove the schedule (keeps reports and state)
#   ./install.sh --no-schedule  install the skill only, no launchd job

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$HOME/.claude/skills/dream"
DREAM_HOME="$HOME/.claude/dream"
LABEL="com.vlado.claude-dream"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# --- uninstall -------------------------------------------------------------
if [ "${1:-}" = "--uninstall" ]; then
  bold "Removing the dream schedule"
  if [ -f "$PLIST" ]; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    ok "schedule removed"
  else
    warn "no schedule was installed"
  fi
  echo
  echo "The skill, reports and state are untouched:"
  echo "  skill:   $SKILL_DIR"
  echo "  reports: $DREAM_HOME"
  echo "Delete those by hand if you want them gone."
  exit 0
fi

SCHEDULE=true
[ "${1:-}" = "--no-schedule" ] && SCHEDULE=false

bold "Installing dream"

# --- preflight -------------------------------------------------------------
[ "$(uname -s)" = "Darwin" ] || die "this installer targets macOS (launchd). On Linux, use cron with dream/scripts/run_dream.sh"
command -v python3 >/dev/null 2>&1 || die "python3 not found"
ok "python3 $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"

if command -v claude >/dev/null 2>&1; then
  ok "claude CLI at $(command -v claude)"
else
  warn "claude CLI not on PATH — run_dream.sh will search the usual install"
  warn "locations, but verify with: dream/scripts/run_dream.sh"
fi

if [ -d "$HOME/.claude/projects" ]; then
  n=$(find "$HOME/.claude/projects" -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
  ok "transcript store found ($n sessions)"
  [ "$n" -eq 0 ] && warn "no transcripts yet — dream needs a day of use before it has anything to read"
else
  warn "no ~/.claude/projects yet; it appears the first time you use Claude Code"
fi

# --- install skill ---------------------------------------------------------
mkdir -p "$SKILL_DIR/scripts" "$DREAM_HOME"/{reports,state,logs}
cp "$SRC/SKILL.md" "$SKILL_DIR/SKILL.md"
cp "$SRC/scripts/scan_transcripts.py" "$SKILL_DIR/scripts/"
cp "$SRC/scripts/render_report.py"    "$SKILL_DIR/scripts/"
cp "$SRC/scripts/run_dream.sh"        "$SKILL_DIR/scripts/"
chmod +x "$SKILL_DIR/scripts/"*.py "$SKILL_DIR/scripts/run_dream.sh"
ok "skill installed to $SKILL_DIR"

# Sanity-check the scanner against the real transcript store rather than
# trusting that a copied file runs.
if [ -d "$HOME/.claude/projects" ]; then
  if python3 "$SKILL_DIR/scripts/scan_transcripts.py" --hours 24 --out /tmp/dream-selftest.json >/dev/null 2>&1; then
    sessions=$(python3 -c "import json;print(json.load(open('/tmp/dream-selftest.json'))['session_count'])" 2>/dev/null || echo "?")
    ok "scanner self-test passed ($sessions sessions in the last 24h)"
    rm -f /tmp/dream-selftest.json
  else
    warn "scanner self-test failed — run it by hand to see why:"
    warn "  python3 $SKILL_DIR/scripts/scan_transcripts.py --hours 24 --out -"
  fi
fi

# --- install schedule ------------------------------------------------------
if [ "$SCHEDULE" = true ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  sed "s|__HOME__|$HOME|g" "$SRC/launchd/$LABEL.plist" > "$PLIST"

  plutil -lint "$PLIST" >/dev/null 2>&1 || die "generated plist is malformed"

  # bootout first so re-running the installer upgrades cleanly.
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
    ok "scheduled for 03:00 daily"
  elif launchctl load "$PLIST" 2>/dev/null; then
    ok "scheduled for 03:00 daily (legacy launchctl)"
  else
    die "could not register the launchd job; check $PLIST"
  fi

  if launchctl list | grep -q "$LABEL"; then
    ok "job is registered"
  else
    warn "job did not appear in launchctl list — check Console.app for errors"
  fi
else
  ok "skill installed without a schedule (--no-schedule)"
fi

echo
bold "Done."
cat <<EOF

  Run it now          claude "run dream"
  Read last report    open $DREAM_HOME/latest.html
  Watch the log       tail -f $DREAM_HOME/logs/dream-\$(date +%F).log
  Fire the job early  launchctl kickstart -k gui/$(id -u)/$LABEL
  Remove the schedule $SRC/install.sh --uninstall

Nothing lands in memory without your approval. Open the morning report,
tick what you want, and paste the line it gives you back into Claude Code.
EOF
