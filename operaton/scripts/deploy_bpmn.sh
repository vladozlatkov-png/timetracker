#!/usr/bin/env bash
# Deploy the BPMN models to Operaton.
#
# Deployments are versioned by the engine: redeploying creates a new version and
# leaves running instances on the version they started with. That is the point —
# an engagement mid-fieldwork is never silently moved onto a new methodology.
set -euo pipefail

OPERATON_URL="${OPERATON_URL:-http://localhost:8080/engine-rest}"
BPMN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../bpmn" && pwd)"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-audit-orchestrator}"

args=(
  -F "deployment-name=${DEPLOYMENT_NAME}"
  -F "deploy-changed-only=true"
  -F "deployment-source=$(basename "$0")"
)

shopt -s nullglob
files=("${BPMN_DIR}"/*.bpmn)
if [[ ${#files[@]} -eq 0 ]]; then
  echo "no .bpmn files in ${BPMN_DIR}" >&2
  exit 1
fi

for f in "${files[@]}"; do
  echo "  + $(basename "$f")"
  args+=(-F "$(basename "$f")=@${f}")
done

echo "deploying to ${OPERATON_URL}"
curl --fail-with-body -sS -X POST "${OPERATON_URL}/deployment/create" "${args[@]}" \
  | python3 -m json.tool
echo
echo "done. Cockpit: ${OPERATON_URL%/engine-rest}/operaton/app/cockpit/"
