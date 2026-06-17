#!/usr/bin/env sh
# Minimal outbound A2A adapter for `agentbus watch-events --exec`.
# Required: A2A_ENDPOINT.
# Optional: A2A_TOKEN_ENV, A2A_TENANT, A2A_FAIL_LOG, A2A_RESPONSE_TO,
#           A2A_OPERATIONAL_DATA, A2A_ASSET_ID, A2A_ASSET_NAME,
#           A2A_SENSITIVITY, A2A_RETENTION.
set -eu

EVENT_JSON=$(cat)
OBJECT_TYPE=$(printf '%s' "$EVENT_JSON" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("object") or {}).get("type", ""))')
MESSAGE_ID=$(printf '%s' "$EVENT_JSON" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("object") or {}).get("id", ""))')

if [ "$OBJECT_TYPE" != "message" ] || [ -z "$MESSAGE_ID" ]; then
  exit 0
fi
if [ -z "${A2A_ENDPOINT:-}" ]; then
  echo "A2A_ENDPOINT required" >&2
  exit 1
fi

TMPDIR=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-a2a.XXXXXX")
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT INT TERM

DATA_FILE=""
if [ -n "${A2A_OPERATIONAL_DATA:-}" ] && [ -n "${A2A_ASSET_ID:-}" ]; then
  DATA_FILE="$TMPDIR/packet.json"
  set -- aas-packet \
    --data "$A2A_OPERATIONAL_DATA" \
    --asset-id "$A2A_ASSET_ID" \
    --asset-name "${A2A_ASSET_NAME:-}"
  if [ -n "${A2A_SENSITIVITY:-}" ]; then
    set -- "$@" --sensitivity "$A2A_SENSITIVITY"
  fi
  if [ -n "${A2A_RETENTION:-}" ]; then
    set -- "$@" --retention "$A2A_RETENTION"
  fi
  set -- "$@" --out "$DATA_FILE"
  agentbus "$@"
  agentbus aas-packet-check --file "$DATA_FILE" >/dev/null
fi

set -- a2a-rpc --message-id "$MESSAGE_ID" --tenant "${A2A_TENANT:-}"
if [ -n "$DATA_FILE" ]; then
  set -- "$@" --data "$DATA_FILE"
fi
set -- "$@" --out "$TMPDIR/request.json"
agentbus "$@"
agentbus a2a-rpc-check --file "$TMPDIR/request.json" >/dev/null

set -- a2a-post --file "$TMPDIR/request.json" --endpoint "$A2A_ENDPOINT"
if [ -n "${A2A_TOKEN_ENV:-}" ]; then
  set -- "$@" --token-env "$A2A_TOKEN_ENV"
fi
if [ -n "${A2A_FAIL_LOG:-}" ]; then
  set -- "$@" --fail-log "$A2A_FAIL_LOG"
fi
if [ -n "${A2A_RESPONSE_TO:-}" ]; then
  set -- "$@" --record-response-to "$A2A_RESPONSE_TO"
fi
if [ -n "${AGENTBUS_ALLOW_SENSITIVE:-}" ]; then
  set -- "$@" --allow-sensitive
fi
agentbus "$@"
