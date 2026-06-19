#!/usr/bin/env sh
# Source-tree smoke check for publish preparation. It uses only temporary buses.
set -eu

PYTHON=${PYTHON:-python3}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
cd "$ROOT"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-smoke.XXXXXX")
REMOTE_PID=""
MODEL_PID=""
DASH_PID=""
cleanup() {
  [ -n "$REMOTE_PID" ] && kill "$REMOTE_PID" 2>/dev/null || true
  [ -n "$MODEL_PID" ] && kill "$MODEL_PID" 2>/dev/null || true
  [ -n "$DASH_PID" ] && kill "$DASH_PID" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

ab() { "$PYTHON" -m agentbus "$@"; }
export AGENTBUS_CAPSULE_SERVER=1

"$PYTHON" -m py_compile agentbus/*.py
if command -v node >/dev/null 2>&1; then
  node --check agentbus/static/dashboard.js >/dev/null
  node --check agentbus/resources/smoke/dashboard-ui-smoke.js >/dev/null
  node agentbus/resources/smoke/dashboard-ui-smoke.js
fi

ab guide loop | grep -q '^# agent-bus loop$'
ab guide loop | grep -q 'Loop closure report'
LOOP_SKILL=$(ab guide loop --path)
[ -f "$LOOP_SKILL" ]
grep -q 'agent-bus-workflow' "$LOOP_SKILL"
ab guide workflow | grep -q '^# agent-bus workflow$'
ab guide workflow | grep -q 'Termination report'
WORKFLOW_SKILL=$(ab guide workflow --path)
[ -f "$WORKFLOW_SKILL" ]

SKILL_BUS="$TMP/skill-bus"
ab --bus-dir "$SKILL_BUS" bus init >/dev/null
ab --bus-dir "$SKILL_BUS" skill new smoke-skill --description "Checks bus-local skill discovery." >/dev/null
ab --bus-dir "$SKILL_BUS" skill state smoke-skill --state active >/dev/null
ab --bus-dir "$SKILL_BUS" skill list | grep -q '^smoke-skill'
ab --bus-dir "$SKILL_BUS" skill show smoke-skill | grep -q '^# smoke-skill'
ab --bus-dir "$SKILL_BUS" skill evidence smoke-skill --type check --ref smoke:workflow --note "skill CLI works" >/dev/null
ab --bus-dir "$SKILL_BUS" skill review | grep -q 'pending: check 1'
ab --bus-dir "$SKILL_BUS" skill list --prompt | grep -q 'pending evidence: check 1'
ab --bus-dir "$SKILL_BUS" guide workflow | grep -q 'Bus-local skill summary'
ab --bus-dir "$SKILL_BUS" task new --title "Grouped task command" --by smoke >/dev/null

ab resource list | grep -q '^bridge/a2a-reviewer.json$'
ab resource list | grep -q '^bridge/claude-inbox.json$'
ab resource list | grep -q '^bridge/codex-inbox.json$'
ab resource list | grep -q '^bridge/codex-runner-inbox.json$'
ab resource list | grep -q '^bridge/claude-runner-inbox.json$'
ab resource list | grep -q '^bridge/gemini-runner-inbox.json$'
ab resource list | grep -q '^bridge/openai-compatible-messages.json$'
ab resource list | grep -q '^bridge/openai-compatible-tasks.json$'
ab resource list | grep -q '^bridge/openai-compatible-tickets.json$'
ab resource list | grep -q '^demo-bus/dashboard-demo.png$'
ab resource list | grep -q '^demo-bus/skills/loop-closure-report/SKILL.md$'
if ab resource path ../pyproject.toml >/dev/null 2>&1; then
  echo "resource path escape passed" >&2
  exit 1
fi
DEMO_SRC=$(ab resource path demo-bus)
DEMO_BUS="$TMP/demo-bus"
cp -R "$DEMO_SRC" "$DEMO_BUS"
ab --bus-dir "$DEMO_BUS" bus migrate --from "$DEMO_BUS" >/dev/null
ab --bus-dir "$DEMO_BUS" task list > "$TMP/demo-tasks.txt"
ab --bus-dir "$DEMO_BUS" ticket list --json > "$TMP/demo-tickets.json"
ab --bus-dir "$DEMO_BUS" auth demo --json > "$TMP/demo-auth.json"
ab --bus-dir "$DEMO_BUS" skill list | grep -q '^loop-closure-report'
grep -q "t-demo-review" "$TMP/demo-tasks.txt"
"$PYTHON" - "$TMP/demo-tickets.json" <<'PY'
import json, sys
tickets = json.load(open(sys.argv[1]))
assert any(row.get("issue_id") == "i-demo-a2a" for row in tickets)
PY
"$PYTHON" - "$TMP/demo-auth.json" "$DEMO_BUS" <<'PY'
import json, sys
from pathlib import Path
from agentbus import bus
auth = json.load(open(sys.argv[1]))
bus_dir = Path(sys.argv[2])
assert auth["viewer"] == "demo"
assert len(auth["token"]) >= 24
assert auth["expiresAt"]
assert auth["messageId"]
assert {"m-demo-002", "m-demo-004", "i-demo-nda"}.issubset(set(auth["demoRecordIds"]))
messages = bus.read_jsonl(bus.paths(bus_dir)["messages"])
issues = bus.read_jsonl(bus.paths(bus_dir)["issues"])
assert any(row.get("id") == auth["messageId"] and "sample-only restricted demo text" in row.get("body", "") for row in messages)
assert any(row.get("id") == "m-demo-002" and "compact assessment packet" in row.get("body", "") for row in messages)
assert any(row.get("id") == "m-demo-004" and "Runner boundary" == row.get("subject") for row in messages)
assert any(row.get("issue_id") == "i-demo-nda" and "NDA packet redaction" in row.get("title", "") for row in issues)
store_text = (bus_dir / "store" / "capsule.sqlite").read_bytes().decode("latin1", errors="ignore")
assert "sample-only restricted demo text" not in store_text
assert "compact assessment packet" not in store_text
assert "NDA packet redaction" not in store_text
PY

export AGENTBUS_BUS_DIR="$TMP/bus"
ab bus init >/dev/null
[ -f "$AGENTBUS_BUS_DIR/bridge/profile.template.json" ]
ab auth init >/dev/null
ab auth grant --agent reviewer --ttl-seconds 3600 >/dev/null
ab auth list > "$TMP/auth-list.txt"
ab auth list --json > "$TMP/auth-list.json"
grep -q 'expires=' "$TMP/auth-list.txt"
"$PYTHON" - "$TMP/auth-list.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
row = next(row for row in data["agents"] if row.get("agent") == "reviewer")
assert row["expiresAt"]
assert row["expired"] is False
PY
mkdir -p "$AGENTBUS_BUS_DIR/skills/smoke-skill"
cp "$SKILL_BUS/skills/smoke-skill/SKILL.md" "$AGENTBUS_BUS_DIR/skills/smoke-skill/SKILL.md"
ab skill evidence smoke-skill --type grounding --ref smoke:dashboard --note "dashboard exposes skill rows" >/dev/null
TASK_ID=$(ab task new --title "Smoke remote check" --by operator --assign reviewer)
MSG_ID=$(ab message send --from operator --to reviewer --kind request --subject "Smoke" --body "Review smoke data" --task "$TASK_ID")
ab message send --from operator --to reviewer --kind note --subject "Grouped command body" --body "task command" >/dev/null

ab packet data --protocol aas \
  --data agentbus/resources/aas/operational-data.sample.json \
  --asset-id urn:example:asset:line-7-press-2 \
  --assessment-summary agentbus/resources/aas/assessment-summary.sample.json \
  --out "$TMP/packet.json"
ab packet data --protocol aas --file "$TMP/packet.json" >/dev/null
"$PYTHON" - "$TMP/packet.json" <<'PY'
import json, sys
packet = json.load(open(sys.argv[1]))
text = json.dumps(packet, ensure_ascii=False)
assert "assessmentSummary" in text
assert "individualAssessments" in text
assert "participants" in text
assert "evidenceGaps" in text
PY
cat > "$TMP/bad-assessment-summary.json" <<'JSON'
{"consensus": ["unattributed agreement"]}
JSON
if ab packet data --protocol aas \
  --data agentbus/resources/aas/operational-data.sample.json \
  --asset-id urn:example:asset:line-7-press-2 \
  --assessment-summary "$TMP/bad-assessment-summary.json" \
  --out "$TMP/bad-packet.json" 2>"$TMP/bad-summary.err"; then
  echo "expected bare consensus summary to be rejected" >&2
  exit 1
fi
grep -F "assessmentSummary.consensus[0] must be a JSON object" "$TMP/bad-summary.err" >/dev/null

ab packet transport --protocol a2a --artifact card --agent example --cards-dir agentbus/cards --url http://127.0.0.1:8799/a2a/rpc --out "$TMP/card.json"
ab packet transport --protocol a2a --artifact card --file "$TMP/card.json" >/dev/null
ab packet transport --protocol a2a --artifact message --message-id "$MSG_ID" --tenant example --data "$TMP/packet.json" --request-id rpc-smoke --out "$TMP/request.json"
ab packet transport --protocol a2a --artifact message --file "$TMP/request.json" >/dev/null
RECEIVE_BUS="$TMP/receive-bus"
OLD_BUS="$AGENTBUS_BUS_DIR"
export AGENTBUS_BUS_DIR="$RECEIVE_BUS"
ab bus init >/dev/null
ab packet receive --protocol a2a --file "$TMP/request.json" --response > "$TMP/receive-response.json"
"$PYTHON" - "$TMP/receive-response.json" "$RECEIVE_BUS" <<'PY'
import json, sys
from pathlib import Path
from agentbus import bus
response = json.load(open(sys.argv[1]))
bd = Path(sys.argv[2])
messages = bus.read_jsonl(bus.paths(bd)["messages"])
assert response["jsonrpc"] == "2.0"
assert "result" in response
assert any(row.get("subject") == "Smoke" and row.get("to") == "reviewer" for row in messages)
PY
export AGENTBUS_BUS_DIR="$OLD_BUS"

SENSITIVE_ID=$(ab message send --from operator --to reviewer --kind request --subject "NDA" --body "sensitive smoke" --sensitivity restricted --retention no_archive)
ab packet transport --protocol a2a --artifact message --message-id "$SENSITIVE_ID" --request-id rpc-sensitive --out "$TMP/sensitive-request.json"
if ab packet send --protocol a2a --file "$TMP/sensitive-request.json" --endpoint http://127.0.0.1:9/rpc >"$TMP/sensitive.out" 2>"$TMP/sensitive.err"; then
  echo "sensitive request was not blocked" >&2
  exit 1
fi
grep -q "restricted request blocked" "$TMP/sensitive.err"
ab bus rotate >/dev/null
ab bus security-check --json > "$TMP/security.json"
"$PYTHON" -m json.tool "$TMP/security.json" >/dev/null
"$PYTHON" - "$TMP/security.json" <<'PY'
import json, sys
checks = {row["name"]: row for row in json.load(open(sys.argv[1]))["checks"]}
assert checks["bus_file_permissions"]["status"] == "ok"
PY

ab bridge check --file agentbus/resources/bridge/claude-inbox.json >/dev/null
ab bridge check --file agentbus/resources/bridge/codex-inbox.json >/dev/null
ab bridge check --file agentbus/resources/bridge/codex-runner-inbox.json >/dev/null
ab bridge check --file agentbus/resources/bridge/claude-runner-inbox.json >/dev/null
ab bridge check --file agentbus/resources/bridge/gemini-runner-inbox.json >/dev/null
env A2A_ENDPOINT=http://127.0.0.1:9/rpc "$PYTHON" -m agentbus bridge check --file agentbus/resources/bridge/a2a-reviewer.json >/dev/null
env OPENAI_COMPAT_ENDPOINT=http://127.0.0.1:9/v1/chat/completions \
  OPENAI_COMPAT_MODEL=smoke-model \
  OPENAI_COMPAT_API_KEY=smoke-key \
  OPENAI_COMPAT_RESPONSE_TO=operator \
  "$PYTHON" -m agentbus bridge check --file agentbus/resources/bridge/openai-compatible-messages.json >/dev/null
env OPENAI_COMPAT_ENDPOINT=http://127.0.0.1:9/v1/chat/completions \
  OPENAI_COMPAT_MODEL=smoke-model \
  OPENAI_COMPAT_API_KEY=smoke-key \
  OPENAI_COMPAT_RESPONSE_TO=operator \
  "$PYTHON" -m agentbus bridge check --file agentbus/resources/bridge/openai-compatible-tasks.json >/dev/null
env OPENAI_COMPAT_ENDPOINT=http://127.0.0.1:9/v1/chat/completions \
  OPENAI_COMPAT_MODEL=smoke-model \
  OPENAI_COMPAT_API_KEY=smoke-key \
  OPENAI_COMPAT_RESPONSE_TO=operator \
  "$PYTHON" -m agentbus bridge check --file agentbus/resources/bridge/openai-compatible-tickets.json >/dev/null

cat > "$TMP/bridge-invalid-mode.json" <<'JSON'
{"schemaVersion":"bridge-profile.v1","name":"bad","mode":"inbox","handler":{"type":"monitor"}}
JSON
if ab bridge check --file "$TMP/bridge-invalid-mode.json" >/dev/null 2>&1; then
  echo "invalid bridge mode passed" >&2
  exit 1
fi
cat > "$TMP/bridge-missing-event.json" <<'JSON'
{"schemaVersion":"bridge-profile.v1","name":"missing-event","handler":{"type":"monitor"}}
JSON
if ab bridge check --file "$TMP/bridge-missing-event.json" >/dev/null 2>&1; then
  echo "missing event bridge profile passed" >&2
  exit 1
fi
cat > "$TMP/bridge-missing-handler.json" <<'JSON'
{"schemaVersion":"bridge-profile.v1","name":"missing-handler","event":"message.created"}
JSON
if ab bridge check --file "$TMP/bridge-missing-handler.json" >/dev/null 2>&1; then
  echo "missing handler bridge profile passed" >&2
  exit 1
fi
cat > "$TMP/bridge-bad-args.json" <<'JSON'
{"schemaVersion":"bridge-profile.v1","name":"bad-args","event":"message.created","handler":{"type":"agent","provider":"codex","args":"--model x"}}
JSON
if ab bridge check --file "$TMP/bridge-bad-args.json" >/dev/null 2>&1; then
  echo "bad args bridge profile passed" >&2
  exit 1
fi
cat > "$TMP/bridge-bad-claude-prompt.json" <<'JSON'
{"schemaVersion":"bridge-profile.v1","name":"bad-claude","event":"message.created","handler":{"type":"agent","provider":"claude","args":["-p"]}}
JSON
if ab bridge check --file "$TMP/bridge-bad-claude-prompt.json" >/dev/null 2>&1; then
  echo "claude prompt override bridge profile passed" >&2
  exit 1
fi
cat > "$TMP/bridge-bad-env.json" <<'JSON'
{"schemaVersion":"bridge-profile.v1","name":"bad-env","event":"message.created","handler":{"type":"monitor"},"envs":["BAD-NAME"]}
JSON
if ab bridge check --file "$TMP/bridge-bad-env.json" >/dev/null 2>&1; then
  echo "bad env bridge profile passed" >&2
  exit 1
fi

cat > "$TMP/bridge-bad-target-list.json" <<'JSON'
{"schemaVersion":"bridge-profile.v1","name":"bad-target-list","event":"message.created","matcher":{"target":["codex","claude"]},"handler":{"type":"monitor"}}
JSON
if ab bridge check --file "$TMP/bridge-bad-target-list.json" >/dev/null 2>&1; then
  echo "target list bridge profile passed" >&2
  exit 1
fi
cat > "$TMP/bridge-bad-target-all.json" <<'JSON'
{"schemaVersion":"bridge-profile.v1","name":"bad-target-all","event":"message.created","matcher":{"target":"all"},"handler":{"type":"monitor"}}
JSON
if ab bridge check --file "$TMP/bridge-bad-target-all.json" >/dev/null 2>&1; then
  echo "target all bridge profile passed" >&2
  exit 1
fi

cat > "$TMP/monitor-profile.json" <<'JSON'
{
  "schemaVersion": "bridge-profile.v1",
  "name": "smoke-monitor",
  "event": "message.created",
  "matcher": {"target": "claude", "kind": ["request"]},
  "handler": {"type": "monitor"},
  "fromStart": true
}
JSON
cp "$TMP/monitor-profile.json" "$AGENTBUS_BUS_DIR/bridge/smoke-monitor.json"
CLAUDE_MSG=$(ab message send --from operator --to claude --kind request --subject "Bridge" --body "bridge smoke")
ab bridge run --profile "$TMP/monitor-profile.json" --once > "$TMP/monitor.out"
grep -q "$CLAUDE_MSG" "$TMP/monitor.out"
[ -s "$AGENTBUS_BUS_DIR/bridge/smoke-monitor.position" ]

SECRET_MSG=$(ab message send --from operator --to claude --kind request --subject "Secret" --body "secret smoke body" --sensitivity restricted)
ab bridge run --profile "$TMP/monitor-profile.json" --once >"$TMP/sensitive-bridge.out" 2>"$TMP/sensitive-bridge.err"
grep -q '"blocked": true' "$TMP/sensitive-bridge.out"
! grep -q "secret smoke body" "$TMP/sensitive-bridge.out"
! grep -R "secret smoke body" "$AGENTBUS_BUS_DIR/bridge" >/dev/null 2>&1

cat > "$TMP/bin-codex" <<'SH2'
#!/usr/bin/env sh
if [ "$1" != "exec" ]; then
  echo "expected codex exec" >&2
  exit 9
fi
shift
printf '%s\n' "$@" > "$CODEX_ARGS_CAPTURE"
cat > "$CODEX_STDIN_CAPTURE"
printf 'mock codex completed\n'
SH2
chmod +x "$TMP/bin-codex"
mkdir -p "$TMP/bin"
cp "$TMP/bin-codex" "$TMP/bin/codex"
cat > "$TMP/codex-profile.json" <<'JSON'
{
  "schemaVersion": "bridge-profile.v1",
  "name": "smoke-codex-runner",
  "event": "message.created",
  "matcher": {"target": "codex", "kind": ["request"]},
  "handler": {"type": "agent", "provider": "codex", "args": ["--mock-option"]},
  "fromStart": true,
  "markDelivered": true
}
JSON
CODEX_TASK=$(ab task new --title "Codex bridge runner" --by operator --assign codex)
CODEX_MSG=$(ab message send --from operator --to codex --kind request --subject "Run codex" --body "run body" --task "$CODEX_TASK")
CODEX_ARGS_CAPTURE="$TMP/codex.args" CODEX_STDIN_CAPTURE="$TMP/codex.stdin" PATH="$TMP/bin:$PATH" \
  ab bridge run --profile "$TMP/codex-profile.json" --once > "$TMP/codex-run.out"
"$PYTHON" - "$TMP/codex.args" "$TMP/codex.stdin" "$AGENTBUS_BUS_DIR" "$CODEX_MSG" "$CODEX_TASK" <<'PY'
import json, sys
from pathlib import Path
from agentbus import bus
args_path, stdin_path, bus_dir, msg_id, task_id = sys.argv[1:]
bd = Path(bus_dir)
args = open(args_path).read()
work = json.load(open(stdin_path))
paths = bus.paths(bd)
messages = bus.read_jsonl(paths["messages"])
tasks = bus.read_jsonl(paths["tasks"])
acks = bus.read_jsonl(paths["acks"])
delivered = bus.read_jsonl(paths["delivered"])
assert "--mock-option" in args
assert "You are an agent-bus runtime" in args
assert work["schemaVersion"] == "agent-runner-work.v1"
assert work["messageId"] == msg_id
assert any(row.get("reply_to") == msg_id and row.get("body") == "mock codex completed" for row in messages)
assert any(row.get("task_id") == task_id and row.get("state") == "completed" for row in tasks)
assert any(row.get("agent") == "codex" and row.get("id") == msg_id for row in acks)
assert any(row.get("agent") == "codex" and row.get("id") == msg_id for row in delivered)
PY

CODEX_TOKEN=$(ab auth grant --agent codex)
SECRET_CODEX_MSG=$(ab message send --from operator --to codex --kind request --subject "Sealed codex" --body "sealed codex body" --sensitivity restricted)
CODEX_ARGS_CAPTURE="$TMP/codex-restricted.args" CODEX_STDIN_CAPTURE="$TMP/codex-restricted.stdin" AGENTBUS_AGENT_TOKEN="$CODEX_TOKEN" PATH="$TMP/bin:$PATH" \
  ab bridge run --profile "$TMP/codex-profile.json" --once > "$TMP/codex-restricted-run.out"
"$PYTHON" - "$TMP/codex-restricted.stdin" "$AGENTBUS_BUS_DIR" "$SECRET_CODEX_MSG" <<'PY'
import json, sys
from pathlib import Path
from agentbus import bus
stdin_path, bus_dir, msg_id = sys.argv[1:]
work = json.load(open(stdin_path))
messages_text = json.dumps(bus.read_jsonl(bus.paths(Path(bus_dir))["messages"]), ensure_ascii=False)
assert work["messageId"] == msg_id
assert work["subject"] == "Sealed codex"
assert work["body"] == "sealed codex body"
assert "sealed codex body" in messages_text
assert "sealed codex body" not in (Path(bus_dir) / "store" / "capsule.sqlite").read_bytes().decode("latin1", errors="ignore")
PY

cat > "$TMP/model_server.py" <<'PY'
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
port_file, request_file = sys.argv[1], sys.argv[2]
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))).decode())
        assert self.headers.get('Authorization') == 'Bearer smoke-key'
        assert req.get('model') == 'smoke-model'
        open(request_file, 'w', encoding='utf-8').write(json.dumps(req, ensure_ascii=False, sort_keys=True))
        body = {
            'id': 'chatcmpl-smoke',
            'model': req.get('model'),
            'choices': [{'message': {'role': 'assistant', 'content': 'mock model saw bridge event'}}],
        }
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
open(port_file, 'w').write(str(server.server_port))
server.serve_forever()
PY
"$PYTHON" "$TMP/model_server.py" "$TMP/model.port" "$TMP/model-request.json" &
MODEL_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  [ -s "$TMP/model.port" ] && break
  sleep 0.1
done
MODEL_PORT=$(cat "$TMP/model.port")
cat > "$TMP/openai-profile.json" <<'JSON'
{
  "schemaVersion": "bridge-profile.v1",
  "name": "smoke-openai-compatible",
  "event": "message.created",
  "matcher": {"target": "model", "kind": ["request"]},
  "handler": {
    "type": "openai-compatible",
    "endpoint": "$OPENAI_COMPAT_ENDPOINT",
    "model": "$OPENAI_COMPAT_MODEL",
    "apiKey": "$OPENAI_COMPAT_API_KEY",
    "responseTo": "operator"
  },
  "envs": ["OPENAI_COMPAT_ENDPOINT", "OPENAI_COMPAT_MODEL", "OPENAI_COMPAT_API_KEY"],
  "fromStart": true
}
JSON
MODEL_MSG=$(ab message send --from operator --to model --kind request --subject "Model bridge" --body "summarize event")
env OPENAI_COMPAT_ENDPOINT="http://127.0.0.1:$MODEL_PORT/v1/chat/completions" \
  OPENAI_COMPAT_MODEL=smoke-model \
  OPENAI_COMPAT_API_KEY=smoke-key \
  "$PYTHON" -m agentbus bridge run --profile "$TMP/openai-profile.json" --once > "$TMP/openai-run.out"
kill "$MODEL_PID" 2>/dev/null || true
MODEL_PID=""
"$PYTHON" - "$TMP/model-request.json" "$AGENTBUS_BUS_DIR" "$MODEL_MSG" <<'PY'
import json, sys
from pathlib import Path
from agentbus import bus
req = json.load(open(sys.argv[1]))
messages = bus.read_jsonl(bus.paths(Path(sys.argv[2]))["messages"])
msg_id = sys.argv[3]
assert req['messages'][1]['role'] == 'user'
assert msg_id in req['messages'][1]['content']
assert any(row.get('to') == 'operator' and row.get('body') == 'mock model saw bridge event' for row in messages)
PY

WATCH_BUS="$TMP/watch-sensitive-bus"
OLD_BUS="$AGENTBUS_BUS_DIR"
export AGENTBUS_BUS_DIR="$WATCH_BUS"
ab bus init >/dev/null
ab auth init >/dev/null
WATCH_TOKEN=$(ab auth grant --agent reviewer)
ab message send --from operator --to reviewer --kind request --subject "Secret watch" --body "watch secret body" --sensitivity restricted >/dev/null
ab bridge watch --types message.created --from-start --once >"$TMP/watch-sensitive.out" 2>"$TMP/watch-sensitive.err"
grep -q '"blocked": true' "$TMP/watch-sensitive.out"
! grep -q "watch secret body" "$TMP/watch-sensitive.out"
! grep -R "watch secret body" "$WATCH_BUS/bridge" >/dev/null 2>&1
ab agent inbox --agent reviewer >"$TMP/restricted-inbox-redacted.out"
! grep -q "watch secret body" "$TMP/restricted-inbox-redacted.out"
AGENTBUS_AGENT_TOKEN="$WATCH_TOKEN" ab agent inbox --agent reviewer >"$TMP/restricted-inbox-raw.out"
grep -q "watch secret body" "$TMP/restricted-inbox-raw.out"
export AGENTBUS_BUS_DIR="$OLD_BUS"

cat > "$TMP/remote.py" <<'PY'
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
port_file = sys.argv[1]
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))).decode())
        task_id = req['params']['message'].get('taskId', '')
        body = {
            'jsonrpc': '2.0',
            'id': req.get('id'),
            'result': {
                'task': {
                    'id': 'remote-task',
                    'status': {
                        'state': 'TASK_STATE_COMPLETED',
                        'message': {
                            'messageId': 'remote-message',
                            'role': 'ROLE_AGENT',
                            'taskId': task_id,
                            'parts': [{'text': 'remote complete', 'mediaType': 'text/plain'}],
                        },
                    },
                }
            },
        }
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
open(port_file, 'w').write(str(server.server_port))
server.serve_forever()
PY
"$PYTHON" "$TMP/remote.py" "$TMP/remote.port" &
REMOTE_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  [ -s "$TMP/remote.port" ] && break
  sleep 0.1
done
REMOTE_PORT=$(cat "$TMP/remote.port")
if A2A_SMOKE_TOKEN=smoke-token ab packet send --protocol a2a --file "$TMP/request.json" --endpoint "http://127.0.0.1:$REMOTE_PORT/rpc" --token-env A2A_SMOKE_TOKEN >"$TMP/post-token-http.out" 2>"$TMP/post-token-http.err"; then
  echo "packet send allowed bearer token over http" >&2
  exit 1
fi
grep -q "bearer token over http blocked" "$TMP/post-token-http.err"
ab packet send --protocol a2a --file "$TMP/request.json" --endpoint "http://127.0.0.1:$REMOTE_PORT/rpc" --record-response-to reviewer > "$TMP/post-summary.json"
"$PYTHON" - "$TMP/post-summary.json" "$AGENTBUS_BUS_DIR" <<'PY'
import json, sys
from pathlib import Path
from agentbus import bus
summary = json.load(open(sys.argv[1]))
bd = Path(sys.argv[2])
paths = bus.paths(bd)
assert summary['ok'] is True
assert summary['recorded']['taskState'] == 'completed'
tasks = bus.read_jsonl(paths["tasks"])
assert tasks[-1]['state'] == 'completed'
messages = bus.read_jsonl(paths["messages"])
assert any(row.get('body') == 'remote complete' for row in messages)
PY

PORT=8799
ab bus serve --port "$PORT" --cards-dir agentbus/cards >"$TMP/serve.log" 2>&1 &
DASH_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if curl -fsS "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done
curl -fsS "http://127.0.0.1:$PORT/api/state" > "$TMP/dashboard-state.json"
"$PYTHON" - "$TMP/dashboard-state.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1]))
assert "task_reports" in state
assert any(row.get("skill_id") == "smoke-skill" for row in state.get("skills", []))
assert any(row.get("name") == "A2A inbound" for row in state.get("bridge_gateways", []))
assert any(row.get("name") == "smoke-monitor" for row in state.get("bridge_profiles", []))
assert not any(row.get("source") == "package" for row in state.get("bridge_profiles", []))
assert not any(row.get("name") == "profile.template" for row in state.get("bridge_profiles", []))
blob = json.dumps({"profiles": state.get("bridge_profiles", []), "gateways": state.get("bridge_gateways", [])})
for token in ("A2A_ENDPOINT", "OPENAI_COMPAT"):
    assert token not in blob
for row in state["task_reports"]:
    assert "task_id" in row
    assert "reports" in row
    assert "report_count" in row
PY
curl -fsS "http://127.0.0.1:$PORT/.well-known/agent-card.json?agent=example" > "$TMP/well-known-card.json"
ab packet transport --protocol a2a --artifact card --file "$TMP/well-known-card.json" >/dev/null
CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: 127.evil.test:$PORT" "http://127.0.0.1:$PORT/api/state")
[ "$CODE" = "403" ] || { echo "expected 403 for non-local Host, got $CODE" >&2; exit 1; }
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/clear" -d '{}')
[ "$CODE" = "415" ] || { echo "expected 415 for non-json POST, got $CODE" >&2; exit 1; }
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/clear" -H 'Content-Type: application/json' -H "Origin: http://127.evil.test:$PORT" --data-binary '{}')
[ "$CODE" = "403" ] || { echo "expected 403 for non-local origin host, got $CODE" >&2; exit 1; }
curl -fsS -X POST "http://127.0.0.1:$PORT/a2a/rpc" -H 'Content-Type: application/json' --data-binary @"$TMP/request.json" > "$TMP/inbound.json"
"$PYTHON" - "$TMP/inbound.json" <<'PY'
import json, sys
response = json.load(open(sys.argv[1]))
assert response['jsonrpc'] == '2.0'
assert 'result' in response
PY

if command -v uv >/dev/null 2>&1; then
  OUT=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-dist.XXXXXX")
  uv build --sdist --wheel --out-dir "$OUT" >/dev/null
  WHEEL=$(ls "$OUT"/*.whl | head -n 1)
  SDIST=$(ls "$OUT"/*.tar.gz | head -n 1)
  "$PYTHON" - "$WHEEL" "$SDIST" <<'PY'
import sys, tarfile, zipfile
required = {
    'agentbus/a2a.py',
    'agentbus/assessment.py',
    'agentbus/resources/aas/assessment-summary.sample.json',
    'agentbus/resources/aas/operational-data.sample.json',
    'agentbus/resources/bridge/a2a-reviewer.json',
    'agentbus/resources/bridge/claude-inbox.json',
    'agentbus/resources/bridge/claude-runner-inbox.json',
    'agentbus/resources/bridge/codex-inbox.json',
    'agentbus/resources/bridge/codex-runner-inbox.json',
    'agentbus/resources/bridge/gemini-runner-inbox.json',
    'agentbus/resources/bridge/openai-compatible-messages.json',
    'agentbus/resources/bridge/openai-compatible-tasks.json',
    'agentbus/resources/bridge/openai-compatible-tickets.json',
    'agentbus/resources/demo-bus/README.md',
    'agentbus/resources/demo-bus/dashboard-demo.png',
    'agentbus/resources/demo-bus/messages.jsonl',
    'agentbus/resources/demo-bus/tasks.jsonl',
    'agentbus/resources/demo-bus/issues.jsonl',
    'agentbus/resources/demo-bus/status.json',
    'agentbus/resources/demo-bus/skills/loop-closure-report/SKILL.md',
    'agentbus/resources/demo-bus/skills/loop-closure-report/evidence.jsonl',
    'agentbus/resources/smoke/publish-smoke.sh',
    'agentbus/schemas/a2a-rpc.v1.md',
    'agentbus/schemas/assessment-packet.v1.md',
    'agentbus/schemas/bridge-profile.v1.md',
    'agentbus/schemas/bridge-handlers.v1.md',
    'agentbus/schemas/events.v1.md',
    'agentbus/skills/agent-bus-loop/SKILL.md',
    'agentbus/skills/agent-bus-workflow/SKILL.md',
    'agentbus/static/dashboard.js',
    'agentbus/vendor/katex/katex.min.js',
}
with zipfile.ZipFile(sys.argv[1]) as z:
    wheel_names = set(z.namelist())
missing = sorted(required - wheel_names)
if missing:
    raise SystemExit('missing from wheel: ' + ', '.join(missing))
with tarfile.open(sys.argv[2]) as t:
    sdist_names = {'/'.join(name.split('/')[1:]) for name in t.getnames()}
missing = sorted(required - sdist_names)
if missing:
    raise SystemExit('missing from sdist: ' + ', '.join(missing))
PY
  INSTALL_VENV="$TMP/install-venv"
  "$PYTHON" -m venv "$INSTALL_VENV"
  "$INSTALL_VENV/bin/python" -m pip --disable-pip-version-check install "$WHEEL" >/dev/null
  "$INSTALL_VENV/bin/agentbus" --help >/dev/null
  "$INSTALL_VENV/bin/agentbus-dashboard" --help >/dev/null
  INSTALLED_DEMO=$("$INSTALL_VENV/bin/agentbus" resource path demo-bus)
  test -f "$INSTALLED_DEMO/dashboard-demo.png"
  test -f "$INSTALLED_DEMO/skills/loop-closure-report/SKILL.md"
  INSTALLED_LOOP=$("$INSTALL_VENV/bin/agentbus" guide loop --path)
  INSTALLED_WORKFLOW=$("$INSTALL_VENV/bin/agentbus" guide workflow --path)
  test -f "$INSTALLED_LOOP"
  test -f "$INSTALLED_WORKFLOW"
  INSTALL_BUS="$TMP/install-bus"
  "$INSTALL_VENV/bin/agentbus" --bus-dir "$INSTALL_BUS" bus init >/dev/null
  INSTALL_MSG=$("$INSTALL_VENV/bin/agentbus" --bus-dir "$INSTALL_BUS" message send --from user --to reviewer --kind request --subject "Install smoke" --body "installed wheel")
  "$INSTALL_VENV/bin/agentbus" --bus-dir "$INSTALL_BUS" agent inbox --agent reviewer | grep -q "$INSTALL_MSG"
  rm -rf "$OUT" build agent_bus.egg-info agent-bus.egg-info agentbus/__pycache__
fi

printf 'publish-smoke-ok\n'
