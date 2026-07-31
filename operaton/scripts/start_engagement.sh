#!/usr/bin/env bash
# Start one engagement process instance.
#
#   ./start_engagement.sh EV-2026-CIC CIC "КОМПАНИЯ ЗА МЕЖДУНАРОДНИ КОНГРЕСИ ЕООД" 2025 2026-09-15
#
# The last argument is the deadline WARNING date — when it passes, the
# non-interrupting event sub-process raises a partner task. Set it before the
# contractual delivery date, not on it.
set -euo pipefail

OPERATON_URL="${OPERATON_URL:-http://localhost:8080/engine-rest}"

if [[ $# -lt 5 ]]; then
  sed -n '2,10p' "$0" >&2
  exit 1
fi

ENGAGEMENT_ID="$1"
CLIENT_CODE="$2"
CLIENT_NAME="$3"
YEAR="$4"
WARN_DATE="$5"

# Operaton expects ISO 8601 with an offset for timeDate expressions.
WARN_TS="${WARN_DATE}T09:00:00.000+03:00"

payload=$(python3 - "$ENGAGEMENT_ID" "$CLIENT_CODE" "$CLIENT_NAME" "$YEAR" "$WARN_TS" <<'PY'
import json, sys
eid, code, name, year, warn = sys.argv[1:6]
print(json.dumps({
    "businessKey": eid,
    "variables": {
        "engagementId":     {"value": eid,        "type": "String"},
        "clientCode":       {"value": code,       "type": "String"},
        "clientName":       {"value": name,       "type": "String"},
        "engagementYear":   {"value": int(year),  "type": "Long"},
        "deadlineWarningAt":{"value": warn,       "type": "String"},
    },
}))
PY
)

curl --fail-with-body -sS -X POST \
  "${OPERATON_URL}/process-definition/key/statutory-audit/start" \
  -H 'Content-Type: application/json' \
  -d "${payload}" \
  | python3 -m json.tool

echo
echo "Tasklist: ${OPERATON_URL%/engine-rest}/operaton/app/tasklist/"
