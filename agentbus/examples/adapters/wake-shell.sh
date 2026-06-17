#!/usr/bin/env sh
# Minimal wake adapter. Reads one event or wakeup JSON object from stdin.
# Replace the log line with a platform command that resumes an agent runtime.

set -eu

tmp=$(mktemp "${TMPDIR:-/tmp}/agentbus-wake.XXXXXX")
cleanup() { rm -f "$tmp"; }
trap cleanup EXIT INT TERM
cat > "$tmp"

python3 - "$tmp" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))

if payload.get("schemaVersion") == "wakeup-profile.v1" and payload.get("mode") == "inbox":
    rows = [row for row in payload.get("pending", []) if isinstance(row, dict)]
    ids = ",".join(str(row.get("id", "")) for row in rows if row.get("id"))
    print(
        f"wake candidate: inbox agent={payload.get('agent', '')} pending={len(rows)} ids={ids}",
        file=sys.stderr,
    )
elif payload.get("version") == "agentbus.event.v1":
    obj = payload.get("object") or {}
    event_type = payload.get("type", "")
    object_type = obj.get("type", "")
    object_id = obj.get("id", "")
    if event_type in {"message.created", "ticket.created", "task.created", "task.state"}:
        print(f"wake candidate: {event_type} {object_type} {object_id}", file=sys.stderr)
    else:
        print(f"ignored: {event_type}", file=sys.stderr)
else:
    print("ignored: unknown payload", file=sys.stderr)
PY
