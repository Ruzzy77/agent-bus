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
CLAUDE_API_PID=""
DASH_PID=""
cleanup() {
  [ -n "$REMOTE_PID" ] && kill "$REMOTE_PID" 2>/dev/null || true
  [ -n "$MODEL_PID" ] && kill "$MODEL_PID" 2>/dev/null || true
  [ -n "$CLAUDE_API_PID" ] && kill "$CLAUDE_API_PID" 2>/dev/null || true
  [ -n "$DASH_PID" ] && kill "$DASH_PID" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

ab() { "$PYTHON" -m agentbus "$@"; }

"$PYTHON" -m py_compile agentbus/*.py agentbus/examples/adapters/codex-runner.py agentbus/examples/adapters/claude-runner.py
if command -v node >/dev/null 2>&1; then
  node --check agentbus/static/dashboard.js >/dev/null
  node --check agentbus/examples/smoke/dashboard-ui-smoke.js >/dev/null
  node agentbus/examples/smoke/dashboard-ui-smoke.js
fi
sh -n agentbus/examples/adapters/a2a-outbound.sh agentbus/examples/adapters/wake-shell.sh agentbus/examples/adapters/openai-compatible.sh agentbus/examples/adapters/run-agent.sh

ab loop | grep -q '^# agent-bus loop$'
ab loop | grep -q 'Loop closure report'
LOOP_SKILL=$(ab loop --path)
[ -f "$LOOP_SKILL" ]
grep -q 'agent-bus-workflow' "$LOOP_SKILL"
ab workflow | grep -q '^# agent-bus workflow$'
ab workflow | grep -q 'Termination report'
WORKFLOW_SKILL=$(ab workflow --path)
[ -f "$WORKFLOW_SKILL" ]

ab examples | grep -q '^wakeup/claude-inbox.json$'
ab examples | grep -q '^wakeup/agent-runner-inbox.json$'
ab examples | grep -q '^wakeup/codex-runner-inbox.json$'
ab examples | grep -q '^wakeup/claude-runner-inbox.json$'
ab examples | grep -q '^demo-bus/messages.jsonl$'
ab examples | grep -q '^demo-bus/dashboard-demo.png$'
CLAUDE_PROFILE=$(ab examples wakeup/claude-inbox.json)
[ -f "$CLAUDE_PROFILE" ]
DEMO_BUS=$(ab examples demo-bus)
[ -d "$DEMO_BUS" ]
ab --bus-dir "$DEMO_BUS" task-list > "$TMP/demo-tasks.txt"
ab --bus-dir "$DEMO_BUS" ticket-list --json > "$TMP/demo-tickets.json"
grep -q "t-demo-review" "$TMP/demo-tasks.txt"
"$PYTHON" - "$TMP/demo-tickets.json" <<'PY'
import json, sys
tickets = json.load(open(sys.argv[1]))
assert any(row.get("issue_id") == "i-demo-a2a" for row in tickets)
PY
WAKE_SHELL=$(ab examples adapters/wake-shell.sh)
[ -x "$WAKE_SHELL" ]
OPENAI_ADAPTER=$(ab examples adapters/openai-compatible.sh)
[ -x "$OPENAI_ADAPTER" ]
RUN_AGENT=$(ab examples adapters/run-agent.sh)
[ -x "$RUN_AGENT" ]
CODEX_RUNNER=$(ab examples adapters/codex-runner.py)
[ -x "$CODEX_RUNNER" ]
CLAUDE_RUNNER=$(ab examples adapters/claude-runner.py)
[ -x "$CLAUDE_RUNNER" ]
if ab examples ../pyproject.toml >/dev/null 2>&1; then
  echo "example path escape passed" >&2
  exit 1
fi
printf '%s\n' '{"schemaVersion":"wakeup-profile.v1","mode":"inbox","agent":"claude","pending":[{"id":"m1"}]}' | "$WAKE_SHELL" 2>"$TMP/wake-shell.err"
grep -q 'wake candidate: inbox agent=claude pending=1 ids=m1' "$TMP/wake-shell.err"

cat > "$TMP/codex-work.json" <<'JSON'
{
  "schemaVersion": "agent-runner-work.v1",
  "agent": "codex",
  "messageId": "m-codex",
  "taskId": "t-codex",
  "subject": "Codex runner dry smoke",
  "body": "summarize this packet"
}
JSON
CODEX_RUNNER_DRY_RUN=1 CODEX_RUNNER_MODE=cli "$CODEX_RUNNER" < "$TMP/codex-work.json" > "$TMP/codex-runner-cli.json"
CODEX_RUNNER_DRY_RUN=1 CODEX_RUNNER_MODE=sdk "$CODEX_RUNNER" < "$TMP/codex-work.json" > "$TMP/codex-runner-sdk.json"
"$PYTHON" - "$TMP/codex-runner-cli.json" "$TMP/codex-runner-sdk.json" <<'PY'
import json, sys
cli = json.load(open(sys.argv[1]))
sdk = json.load(open(sys.argv[2]))
assert cli["mode"] == "cli"
assert sdk["mode"] == "sdk"
assert cli["messageId"] == "m-codex"
assert "Codex runner dry smoke" in cli["prompt"]
assert cli["work"]["body"] == "summarize this packet"
PY

cat > "$TMP/claude-work.json" <<'JSON'
{
  "schemaVersion": "agent-runner-work.v1",
  "agent": "claude",
  "messageId": "m-claude",
  "taskId": "t-claude",
  "subject": "Claude runner dry smoke",
  "body": "summarize this packet"
}
JSON
CLAUDE_RUNNER_DRY_RUN=1 CLAUDE_RUNNER_MODE=cli "$CLAUDE_RUNNER" < "$TMP/claude-work.json" > "$TMP/claude-runner-cli.json"
CLAUDE_RUNNER_DRY_RUN=1 CLAUDE_RUNNER_MODE=sdk "$CLAUDE_RUNNER" < "$TMP/claude-work.json" > "$TMP/claude-runner-sdk.json"
CLAUDE_RUNNER_DRY_RUN=1 CLAUDE_RUNNER_MODE=api "$CLAUDE_RUNNER" < "$TMP/claude-work.json" > "$TMP/claude-runner-api.json"
"$PYTHON" - "$TMP/claude-runner-cli.json" "$TMP/claude-runner-sdk.json" "$TMP/claude-runner-api.json" <<'PY'
import json, sys
cli = json.load(open(sys.argv[1]))
sdk = json.load(open(sys.argv[2]))
api = json.load(open(sys.argv[3]))
assert cli["mode"] == "cli"
assert sdk["mode"] == "sdk"
assert api["mode"] == "api"
assert cli["messageId"] == "m-claude"
assert "Claude runner dry smoke" in cli["prompt"]
assert cli["work"]["body"] == "summarize this packet"
PY
"$PYTHON" - "$TMP/claude-work.json" "$TMP/claude-sensitive-work.json" <<'PY'
import json, sys
work = json.load(open(sys.argv[1]))
work['sensitivity'] = 'confidential'
json.dump(work, open(sys.argv[2], 'w', encoding='utf-8'))
PY
if CLAUDE_RUNNER_MODE=cli "$CLAUDE_RUNNER" < "$TMP/claude-sensitive-work.json" >"$TMP/claude-sensitive.out" 2>"$TMP/claude-sensitive.err"; then
  echo "sensitive Claude runner work was not blocked" >&2
  exit 1
fi
grep -q "sensitive work packet blocked" "$TMP/claude-sensitive.err"
! grep -q "summarize this packet" "$TMP/claude-sensitive.out"

cat > "$TMP/claude_server.py" <<'PY'
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
port_file, request_file = sys.argv[1], sys.argv[2]
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))).decode())
        assert self.headers.get('x-api-key') == 'claude-smoke-key'
        assert self.headers.get('anthropic-version') == '2023-06-01'
        assert req.get('model') == 'claude-smoke-model'
        assert req.get('max_tokens') == 77
        open(request_file, 'w', encoding='utf-8').write(json.dumps(req, ensure_ascii=False, sort_keys=True))
        body = {'id': 'msg-smoke', 'type': 'message', 'role': 'assistant', 'content': [{'type': 'text', 'text': 'mock claude saw agent-runner-work'}]}
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
"$PYTHON" "$TMP/claude_server.py" "$TMP/claude.port" "$TMP/claude-request.json" &
CLAUDE_API_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  [ -s "$TMP/claude.port" ] && break
  sleep 0.1
done
CLAUDE_PORT=$(cat "$TMP/claude.port")
ANTHROPIC_API_KEY=claude-smoke-key \
CLAUDE_RUNNER_MODE=api \
CLAUDE_RUNNER_ENDPOINT="http://127.0.0.1:$CLAUDE_PORT/v1/messages" \
CLAUDE_RUNNER_MODEL=claude-smoke-model \
CLAUDE_RUNNER_MAX_TOKENS=77 \
  "$CLAUDE_RUNNER" < "$TMP/claude-work.json" > "$TMP/claude-api.out"
kill "$CLAUDE_API_PID" 2>/dev/null || true
CLAUDE_API_PID=""
grep -q "mock claude saw agent-runner-work" "$TMP/claude-api.out"
"$PYTHON" - "$TMP/claude-request.json" <<'PY'
import json, sys
req = json.load(open(sys.argv[1]))
assert req['messages'][0]['role'] == 'user'
assert 'agent-runner-work.v1' in req['messages'][0]['content']
assert 'Claude runner dry smoke' in req['system']
PY

export AGENTBUS_BUS_DIR="$TMP/bus"
ab init >/dev/null
TASK_ID=$(ab task-new --title "Smoke remote check" --by operator --assign reviewer)
MSG_ID=$(ab send --from operator --to reviewer --kind request --subject "Smoke" --body "Review smoke data" --task "$TASK_ID")

ab aas-packet \
  --data agentbus/examples/aas/operational-data.sample.json \
  --asset-id urn:example:asset:line-7-press-2 \
  --assessment-summary agentbus/examples/aas/assessment-summary.sample.json \
  --out "$TMP/packet.json"
ab aas-packet-check --file "$TMP/packet.json" >/dev/null
"$PYTHON" - "$TMP/packet.json" <<'PY'
import json, sys
packet = json.load(open(sys.argv[1]))
text = json.dumps(packet, ensure_ascii=False)
assert "assessmentSummary" in text
assert "individualAssessments" in text
assert "participants" in text
assert "statement" in text
assert "evidenceGaps" in text
PY
cat > "$TMP/bad-assessment-summary.json" <<'JSON'
{"consensus": ["unattributed agreement"]}
JSON
if ab aas-packet \
  --data agentbus/examples/aas/operational-data.sample.json \
  --asset-id urn:example:asset:line-7-press-2 \
  --assessment-summary "$TMP/bad-assessment-summary.json" \
  --out "$TMP/bad-packet.json" 2>"$TMP/bad-summary.err"; then
  echo "expected bare consensus summary to be rejected" >&2
  exit 1
fi
grep -F "assessmentSummary.consensus[0] must be a JSON object" "$TMP/bad-summary.err" >/dev/null
cat > "$TMP/bad-assessment-participants.json" <<'JSON'
{"consensus": [{"statement": "mixed participant list", "participants": ["reviewer-a", 7]}]}
JSON
if ab aas-packet \
  --data agentbus/examples/aas/operational-data.sample.json \
  --asset-id urn:example:asset:line-7-press-2 \
  --assessment-summary "$TMP/bad-assessment-participants.json" \
  --out "$TMP/bad-participants-packet.json" 2>"$TMP/bad-participants.err"; then
  echo "expected mixed consensus participant list to be rejected" >&2
  exit 1
fi
grep -F "assessmentSummary.consensus[0].participants must be a non-empty list of strings" "$TMP/bad-participants.err" >/dev/null
"$PYTHON" - "$TMP/packet.json" "$TMP/bad-projected-packet.json" <<'PY'
import json, sys
packet = json.load(open(sys.argv[1]))

def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

for row in walk(packet):
    if row.get("idShort") == "consensus":
        row["value"] = [{
            "modelType": "Property",
            "idShort": "Item1",
            "valueType": "xs:string",
            "value": "unattributed agreement",
        }]
        break
else:
    raise SystemExit("consensus element not found")
json.dump(packet, open(sys.argv[2], "w"), ensure_ascii=False)
PY
if ab aas-packet-check --file "$TMP/bad-projected-packet.json" 2>"$TMP/bad-projected.err"; then
  echo "expected projected bare consensus to be rejected" >&2
  exit 1
fi
grep -F "assessmentSummary.consensus[0] must be a collection with statement and participants" "$TMP/bad-projected.err" >/dev/null
cat > "$TMP/operational-consensus-field.json" <<'JSON'
{"consensus": "operational field name, not an assessment summary"}
JSON
ab aas-packet \
  --data "$TMP/operational-consensus-field.json" \
  --asset-id urn:example:asset:line-7-press-2 \
  --out "$TMP/operational-consensus-packet.json"
ab aas-packet-check --file "$TMP/operational-consensus-packet.json" >/dev/null

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
            'choices': [{'message': {'role': 'assistant', 'content': 'mock model saw assessmentSummary'}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
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
OPENAI_COMPAT_ENDPOINT="http://127.0.0.1:$MODEL_PORT/v1/chat/completions"
OPENAI_COMPAT_MODEL=smoke-model
OPENAI_COMPAT_API_KEY=smoke-key
OPENAI_COMPAT_RESPONSE_TO=operator
AGENTBUS_CLI="$PYTHON -m agentbus"
export OPENAI_COMPAT_ENDPOINT OPENAI_COMPAT_MODEL OPENAI_COMPAT_API_KEY OPENAI_COMPAT_RESPONSE_TO AGENTBUS_CLI
"$OPENAI_ADAPTER" < "$TMP/packet.json" > "$TMP/openai.out"
"$PYTHON" - "$TMP/openai.out" "$TMP/model-request.json" "$AGENTBUS_BUS_DIR/messages.jsonl" <<'PY'
import json, sys
summary = json.load(open(sys.argv[1]))
request = json.load(open(sys.argv[2]))
messages = [json.loads(line) for line in open(sys.argv[3]) if line.strip()]
assert summary['content'] == 'mock model saw assessmentSummary'
assert 'assessmentSummary' in request['messages'][1]['content']
assert any(row.get('to') == 'operator' and row.get('body') == 'mock model saw assessmentSummary' for row in messages)
PY
"$PYTHON" - "$TMP/packet.json" "$TMP/sensitive-packet.json" <<'PY'
import json, sys
packet = json.load(open(sys.argv[1]))
packet['sensitivity'] = 'confidential'
json.dump(packet, open(sys.argv[2], 'w', encoding='utf-8'))
PY
if "$OPENAI_ADAPTER" < "$TMP/sensitive-packet.json" >"$TMP/openai-sensitive.out" 2>"$TMP/openai-sensitive.err"; then
  echo "sensitive OpenAI-compatible payload was not blocked" >&2
  exit 1
fi
grep -q "sensitive payload blocked" "$TMP/openai-sensitive.err"
unset OPENAI_COMPAT_ENDPOINT OPENAI_COMPAT_MODEL OPENAI_COMPAT_API_KEY OPENAI_COMPAT_RESPONSE_TO AGENTBUS_CLI

cat > "$TMP/agent-command.py" <<'PY'
import json, os, sys
work = json.load(sys.stdin)
assert work["schemaVersion"] == "agent-runner-work.v1"
assert os.environ["AGENTBUS_RUNNER_AGENT"] == work["agent"]
assert os.environ["AGENTBUS_RUNNER_MESSAGE_ID"] == work["messageId"]
print("agent command completed " + work["messageId"])
PY
"$PYTHON" - "$TMP/run-agent-profile.json" "$RUN_AGENT" <<'PY'
import json, sys
profile = {
    "schemaVersion": "wakeup-profile.v1",
    "name": "smoke-agent-runner",
    "mode": "inbox",
    "agent": "my-agent",
    "kinds": ["request"],
    "command": sys.argv[2],
    "markDelivered": True,
    "execTimeout": 0,
}
json.dump(profile, open(sys.argv[1], "w", encoding="utf-8"))
PY
TICKET_ID=$(ab ticket-new --title "Run agent smoke" --by user --body "run body")
ACCEPT_OUT=$(ab ticket-accept --id "$TICKET_ID" --by user --to my-agent --note "run")
RUN_TASK=$(printf '%s\n' "$ACCEPT_OUT" | awk '{print $4}')
RUN_MSG=$(printf '%s\n' "$ACCEPT_OUT" | awk '{print $6}')
AGENT_RUNNER_COMMAND="$PYTHON $TMP/agent-command.py"
AGENTBUS_CLI="$PYTHON -m agentbus"
export AGENT_RUNNER_COMMAND AGENTBUS_CLI
ab wakeup --profile "$TMP/run-agent-profile.json" --once > "$TMP/run-agent.out"
"$PYTHON" - "$TMP/run-agent.out" "$AGENTBUS_BUS_DIR/messages.jsonl" "$AGENTBUS_BUS_DIR/tasks.jsonl" "$AGENTBUS_BUS_DIR/acks.jsonl" "$RUN_TASK" "$RUN_MSG" <<'PY'
import json, sys
lines = [line for line in open(sys.argv[1]) if line.strip()]
summary = json.loads(lines[-1])
messages = [json.loads(line) for line in open(sys.argv[2]) if line.strip()]
tasks = [json.loads(line) for line in open(sys.argv[3]) if line.strip()]
acks = [json.loads(line) for line in open(sys.argv[4]) if line.strip()]
task_id, msg_id = sys.argv[5], sys.argv[6]
assert summary["processed"][0]["messageId"] == msg_id
assert any(row.get("reply_to") == msg_id and row.get("body") == "agent command completed " + msg_id for row in messages)
assert any(row.get("task_id") == task_id and row.get("state") == "completed" for row in tasks)
assert any(row.get("agent") == "my-agent" and row.get("id") == msg_id for row in acks)
PY
cat > "$TMP/agent-fail.py" <<'PY'
import sys
print("agent failed")
raise SystemExit(5)
PY
FAIL_TASK=$(ab task-new --title "Run agent fail" --by user --assign my-agent)
FAIL_MSG=$(ab send --from user --to my-agent --kind request --subject "Fail run" --body "fail" --task "$FAIL_TASK")
AGENT_RUNNER_COMMAND="$PYTHON $TMP/agent-fail.py"
export AGENT_RUNNER_COMMAND
if ab wakeup --profile "$TMP/run-agent-profile.json" --once >"$TMP/run-agent-fail.out" 2>"$TMP/run-agent-fail.err"; then
  echo "failing agent runner passed" >&2
  exit 1
fi
"$PYTHON" - "$AGENTBUS_BUS_DIR/tasks.jsonl" "$AGENTBUS_BUS_DIR/acks.jsonl" "$FAIL_TASK" "$FAIL_MSG" <<'PY'
import json, sys
from pathlib import Path
tasks = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
acks_path = Path(sys.argv[2])
acks = [json.loads(line) for line in acks_path.open() if line.strip()] if acks_path.exists() else []
task_id, msg_id = sys.argv[3], sys.argv[4]
assert any(row.get("task_id") == task_id and row.get("state") == "failed" for row in tasks)
assert not any(row.get("agent") == "my-agent" and row.get("id") == msg_id for row in acks)
PY
unset AGENT_RUNNER_COMMAND AGENTBUS_CLI

ab a2a-card --agent example --cards-dir agentbus/cards --url http://127.0.0.1:8799/a2a/rpc --out "$TMP/card.json"
ab a2a-card-check --file "$TMP/card.json" >/dev/null
ab a2a-rpc --message-id "$MSG_ID" --tenant example --data "$TMP/packet.json" --request-id rpc-smoke --out "$TMP/request.json"
ab a2a-rpc-check --file "$TMP/request.json" >/dev/null

SENSITIVE_ID=$(ab send --from operator --to reviewer --kind request --subject "NDA" --body "sensitive smoke" --sensitivity confidential --retention no_archive)
ab a2a-rpc --message-id "$SENSITIVE_ID" --request-id rpc-sensitive --out "$TMP/sensitive-request.json"
if ab a2a-post --file "$TMP/sensitive-request.json" --endpoint http://127.0.0.1:9/rpc >"$TMP/sensitive.out" 2>"$TMP/sensitive.err"; then
  echo "sensitive request was not blocked" >&2
  exit 1
fi
grep -q "sensitive request blocked" "$TMP/sensitive.err"
ab rotate >/dev/null
"$PYTHON" - "$AGENTBUS_BUS_DIR/messages.jsonl" <<'PY'
import json, sys
rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
assert any(row.get('retention') == 'no_archive' for row in rows)
PY
ab security-check --json > "$TMP/security.json"
"$PYTHON" -m json.tool "$TMP/security.json" >/dev/null
"$PYTHON" - "$TMP/security.json" <<'PY'
import json, sys
checks = {row["name"]: row for row in json.load(open(sys.argv[1]))["checks"]}
assert checks["bus_file_permissions"]["status"] == "ok"
PY

ab wakeup-check --file agentbus/examples/wakeup/claude-inbox.json >/dev/null
ab wakeup-check --file agentbus/examples/wakeup/codex-inbox.json >/dev/null
ab wakeup-check --file agentbus/examples/wakeup/codex-runner-inbox.json >/dev/null
ab wakeup-check --file agentbus/examples/wakeup/claude-runner-inbox.json >/dev/null
AGENT_RUNNER_COMMAND=true
export AGENT_RUNNER_COMMAND
ab wakeup-check --file agentbus/examples/wakeup/agent-runner-inbox.json >/dev/null
unset AGENT_RUNNER_COMMAND
A2A_ENDPOINT=http://127.0.0.1:9/rpc
export A2A_ENDPOINT
ab wakeup-check --file agentbus/examples/wakeup/a2a-events.json >/dev/null
unset A2A_ENDPOINT
OPENAI_COMPAT_ENDPOINT=http://127.0.0.1:9/v1/chat/completions
OPENAI_COMPAT_MODEL=smoke-model
OPENAI_COMPAT_API_KEY=smoke-key
OPENAI_COMPAT_RESPONSE_TO=operator
export OPENAI_COMPAT_ENDPOINT OPENAI_COMPAT_MODEL OPENAI_COMPAT_API_KEY OPENAI_COMPAT_RESPONSE_TO
ab wakeup-check --file agentbus/examples/wakeup/openai-compatible-events.json >/dev/null
unset OPENAI_COMPAT_ENDPOINT OPENAI_COMPAT_MODEL OPENAI_COMPAT_API_KEY OPENAI_COMPAT_RESPONSE_TO

cat > "$TMP/wakeup-bad-mode.json" <<'JSON'
{"schemaVersion":"wakeup-profile.v1","name":"bad","mode":"unknown"}
JSON
if ab wakeup-check --file "$TMP/wakeup-bad-mode.json" >/dev/null 2>&1; then
  echo "invalid wakeup profile passed" >&2
  exit 1
fi
cat > "$TMP/wakeup-missing-agent.json" <<'JSON'
{"schemaVersion":"wakeup-profile.v1","name":"missing-agent","mode":"inbox"}
JSON
if ab wakeup-check --file "$TMP/wakeup-missing-agent.json" >/dev/null 2>&1; then
  echo "missing inbox agent passed" >&2
  exit 1
fi
cat > "$TMP/wakeup-missing-types.json" <<'JSON'
{"schemaVersion":"wakeup-profile.v1","name":"missing-types","mode":"events"}
JSON
if ab wakeup-check --file "$TMP/wakeup-missing-types.json" >/dev/null 2>&1; then
  echo "missing event types passed" >&2
  exit 1
fi
cat > "$TMP/wakeup-bad-sensitive.json" <<'JSON'
{"schemaVersion":"wakeup-profile.v1","name":"bad-sensitive","mode":"inbox","agent":"agent","allowSensitive":"true"}
JSON
if ab wakeup-check --file "$TMP/wakeup-bad-sensitive.json" >/dev/null 2>&1; then
  echo "invalid wakeup sensitivity config passed" >&2
  exit 1
fi
cat > "$TMP/wakeup-missing-env.json" <<'JSON'
{"schemaVersion":"wakeup-profile.v1","name":"missing-env","mode":"inbox","agent":"agent","requiredEnv":["AGENTBUS_MISSING_ENV_FOR_SMOKE"]}
JSON
if ab wakeup-check --file "$TMP/wakeup-missing-env.json" >/dev/null 2>&1; then
  echo "missing requiredEnv passed" >&2
  exit 1
fi

cat > "$TMP/capture.py" <<'PY'
import json, os, sys
payload = json.load(sys.stdin)
payload["_env"] = {
    "AGENTBUS_EVENT_ID": os.environ.get("AGENTBUS_EVENT_ID", ""),
    "AGENTBUS_EVENT_TYPE": os.environ.get("AGENTBUS_EVENT_TYPE", ""),
    "AGENTBUS_OBJECT_TYPE": os.environ.get("AGENTBUS_OBJECT_TYPE", ""),
    "AGENTBUS_OBJECT_ID": os.environ.get("AGENTBUS_OBJECT_ID", ""),
    "AGENTBUS_WAKEUP_MODE": os.environ.get("AGENTBUS_WAKEUP_MODE", ""),
    "AGENTBUS_WAKEUP_AGENT": os.environ.get("AGENTBUS_WAKEUP_AGENT", ""),
}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, sort_keys=True)
PY
cat > "$TMP/capture-event.py" <<'PY'
import json, os, sys
payload = json.load(sys.stdin)
payload["_env"] = {
    "AGENTBUS_EVENT_ID": os.environ.get("AGENTBUS_EVENT_ID", ""),
    "AGENTBUS_EVENT_TYPE": os.environ.get("AGENTBUS_EVENT_TYPE", ""),
    "AGENTBUS_OBJECT_TYPE": os.environ.get("AGENTBUS_OBJECT_TYPE", ""),
    "AGENTBUS_OBJECT_ID": os.environ.get("AGENTBUS_OBJECT_ID", ""),
}
with open(sys.argv[1], "a", encoding="utf-8") as f:
    f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
PY
"$PYTHON" - "$TMP/inbox-profile.json" "$TMP/capture.py" "$TMP/inbox-capture.json" <<'PY'
import json, sys
profile = {
    "schemaVersion": "wakeup-profile.v1",
    "name": "smoke-inbox",
    "mode": "inbox",
    "agent": "claude",
    "kinds": ["request"],
    "command": f"{sys.executable} {sys.argv[2]} {sys.argv[3]}",
    "markDelivered": True,
}
json.dump(profile, open(sys.argv[1], "w", encoding="utf-8"))
PY
CLAUDE_MSG=$(ab send --from operator --to claude --kind request --subject "Wake" --body "wake smoke")
ab wakeup --profile "$TMP/inbox-profile.json" --once > "$TMP/inbox.out"
"$PYTHON" - "$TMP/inbox.out" "$TMP/inbox-capture.json" "$AGENTBUS_BUS_DIR/delivered.jsonl" "$AGENTBUS_BUS_DIR/acks.jsonl" "$CLAUDE_MSG" <<'PY'
import json, sys
from pathlib import Path
out = json.load(open(sys.argv[1]))
cap = json.load(open(sys.argv[2]))
delivered = [json.loads(line) for line in open(sys.argv[3]) if line.strip()]
ack_path = Path(sys.argv[4])
acks = [json.loads(line) for line in ack_path.open() if line.strip()] if ack_path.exists() else []
mid = sys.argv[5]
assert out["pending"][0]["id"] == mid
assert cap["pending"][0]["id"] == mid
assert cap["_env"]["AGENTBUS_WAKEUP_MODE"] == "inbox"
assert cap["_env"]["AGENTBUS_WAKEUP_AGENT"] == "claude"
assert any(row.get("id") == mid and row.get("agent") == "claude" for row in delivered)
assert not any(row.get("id") == mid and row.get("agent") == "claude" for row in acks)
PY

SECRET_MSG=$(ab send --from operator --to claude --kind request --subject "Secret" --body "secret smoke body" --sensitivity confidential)
if ab wakeup --profile "$TMP/inbox-profile.json" --once >"$TMP/sensitive-wakeup.out" 2>"$TMP/sensitive-wakeup.err"; then
  echo "sensitive inbox wake was not blocked" >&2
  exit 1
fi
grep -q '"blocked": true' "$TMP/sensitive-wakeup.out"
! grep -q "secret smoke body" "$TMP/sensitive-wakeup.out"
! grep -R "secret smoke body" "$AGENTBUS_BUS_DIR/adapters" >/dev/null 2>&1

WATCH_BUS="$TMP/watch-sensitive-bus"
OLD_BUS="$AGENTBUS_BUS_DIR"
export AGENTBUS_BUS_DIR="$WATCH_BUS"
ab init >/dev/null
ab send --from operator --to reviewer --kind request --subject "Secret watch" --body "watch secret body" --sensitivity confidential >/dev/null
if ab watch-events --types message.created --from-start --once --fail-log "$WATCH_BUS/adapters/watch.failures.jsonl" >"$TMP/watch-sensitive.out" 2>"$TMP/watch-sensitive.err"; then
  echo "sensitive watch event was not blocked" >&2
  exit 1
fi
grep -q '"blocked": true' "$TMP/watch-sensitive.out"
! grep -q "watch secret body" "$TMP/watch-sensitive.out"
! grep -R "watch secret body" "$WATCH_BUS/adapters" >/dev/null 2>&1
ab watch-events --types message.created --from-start --once --allow-sensitive >"$TMP/watch-sensitive-allow.out"
grep -q "watch secret body" "$TMP/watch-sensitive-allow.out"
export AGENTBUS_BUS_DIR="$OLD_BUS"

STOP_BUS="$TMP/stop-bus"
OLD_BUS="$AGENTBUS_BUS_DIR"
export AGENTBUS_BUS_DIR="$STOP_BUS"
ab init >/dev/null
ab stop --by user --reason smoke >/dev/null
if ab wakeup --profile "$TMP/inbox-profile.json" --once >"$TMP/stop-wakeup.out" 2>&1; then
  echo "wakeup ignored stop" >&2
  exit 1
fi
export AGENTBUS_BUS_DIR="$OLD_BUS"

EVENT_BUS="$TMP/event-bus"
export AGENTBUS_BUS_DIR="$EVENT_BUS"
ab init >/dev/null
"$PYTHON" - "$TMP/events-profile.json" "$TMP/capture-event.py" "$TMP/event-capture.jsonl" <<'PY'
import json, sys
profile = {
    "schemaVersion": "wakeup-profile.v1",
    "name": "smoke-events",
    "mode": "events",
    "types": ["message.created", "task.created", "ticket.created"],
    "fromStart": True,
    "command": f"{sys.executable} {sys.argv[2]} {sys.argv[3]}",
}
json.dump(profile, open(sys.argv[1], "w", encoding="utf-8"))
PY
EVENT_MSG=$(ab send --from operator --to reviewer --kind request --subject "Event" --body "event smoke")
EVENT_TASK=$(ab task-new --title "Event task" --by operator --assign reviewer)
EVENT_TICKET=$(ab ticket-new --title "Event ticket" --by operator --body "event ticket")
ab wakeup --profile "$TMP/events-profile.json" --once > "$TMP/events.out"
"$PYTHON" - "$TMP/event-capture.jsonl" "$EVENT_MSG" "$EVENT_TASK" "$EVENT_TICKET" "$EVENT_BUS/adapters/smoke-events.cursor" <<'PY'
import json, sys
rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
by_type = {row["object"]["type"]: row for row in rows}
assert by_type["message"]["object"]["id"] == sys.argv[2]
assert by_type["task"]["object"]["id"] == sys.argv[3]
assert by_type["ticket"]["object"]["id"] == sys.argv[4]
for row in rows:
    assert row["_env"]["AGENTBUS_EVENT_ID"]
    assert row["_env"]["AGENTBUS_EVENT_TYPE"] == row["type"]
    assert row["_env"]["AGENTBUS_OBJECT_TYPE"] == row["object"]["type"]
    assert row["_env"]["AGENTBUS_OBJECT_ID"] == row["object"]["id"]
assert open(sys.argv[5]).read().strip()
PY
CURSOR_BEFORE=$(cat "$EVENT_BUS/adapters/smoke-events.cursor")
ab send --from operator --to reviewer --kind request --subject "Fail" --body "fail smoke" >/dev/null
"$PYTHON" - "$TMP/events-fail-profile.json" <<'PY'
import json, sys
profile = {
    "schemaVersion": "wakeup-profile.v1",
    "name": "smoke-events",
    "mode": "events",
    "types": ["message.created", "task.created", "ticket.created"],
    "command": "sh -c 'exit 7'",
}
json.dump(profile, open(sys.argv[1], "w", encoding="utf-8"))
PY
if ab wakeup --profile "$TMP/events-fail-profile.json" --once >"$TMP/events-fail.out" 2>&1; then
  echo "failing wakeup event command passed" >&2
  exit 1
fi
[ "$(cat "$EVENT_BUS/adapters/smoke-events.cursor")" = "$CURSOR_BEFORE" ]
grep -q '"returncode": 7' "$EVENT_BUS/adapters/smoke-events.failures.jsonl"
ab adapter-status --json > "$TMP/adapter-status.json"
"$PYTHON" - "$TMP/adapter-status.json" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1]))["adapters"]
row = next(item for item in rows if item["name"] == "smoke-events")
assert row["failureCount"] >= 1
assert row["lastFailure"]["returncode"] == 7
assert "event" not in row["lastFailure"]
assert "payload" not in row["lastFailure"]
PY
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
if ab a2a-post --file "$TMP/request.json" --endpoint "http://127.0.0.1:$REMOTE_PORT/rpc" --bearer-token smoke-token >"$TMP/post-token-http.out" 2>"$TMP/post-token-http.err"; then
  echo "a2a-post allowed bearer token over http" >&2
  exit 1
fi
grep -q "bearer token over http blocked" "$TMP/post-token-http.err"
if ab a2a-post --file "$TMP/request.json" --endpoint " http://127.0.0.1:$REMOTE_PORT/rpc" --bearer-token smoke-token >"$TMP/post-token-http-space.out" 2>"$TMP/post-token-http-space.err"; then
  echo "a2a-post allowed bearer token over http with leading space" >&2
  exit 1
fi
grep -q "bearer token over http blocked" "$TMP/post-token-http-space.err"
if ab a2a-post --file "$TMP/request.json" --endpoint "http://127.0.0.1:$REMOTE_PORT/rpc" --header "Authorization: Bearer smoke-token" >"$TMP/post-header-token-http.out" 2>"$TMP/post-header-token-http.err"; then
  echo "a2a-post allowed credential header over http" >&2
  exit 1
fi
grep -q "credential header over http blocked" "$TMP/post-header-token-http.err"
if ab a2a-post --file "$TMP/request.json" --endpoint "http://127.0.0.1:$REMOTE_PORT/rpc" --header "X-Auth: smoke-token" >"$TMP/post-x-auth-http.out" 2>"$TMP/post-x-auth-http.err"; then
  echo "a2a-post allowed x-auth credential header over http" >&2
  exit 1
fi
grep -q "credential header over http blocked" "$TMP/post-x-auth-http.err"
if ab a2a-post --file "$TMP/request.json" --endpoint "http://127.0.0.1:$REMOTE_PORT/rpc" --header "X-ApiKey: smoke-token" >"$TMP/post-x-apikey-http.out" 2>"$TMP/post-x-apikey-http.err"; then
  echo "a2a-post allowed x-apikey credential header over http" >&2
  exit 1
fi
grep -q "credential header over http blocked" "$TMP/post-x-apikey-http.err"
ab a2a-post --file "$TMP/request.json" --endpoint "http://127.0.0.1:$REMOTE_PORT/rpc" --record-response-to reviewer > "$TMP/post-summary.json"
"$PYTHON" - "$TMP/post-summary.json" "$AGENTBUS_BUS_DIR/tasks.jsonl" "$AGENTBUS_BUS_DIR/messages.jsonl" <<'PY'
import json, sys
summary = json.load(open(sys.argv[1]))
assert summary['ok'] is True
assert summary['recorded']['taskState'] == 'completed'
tasks = [json.loads(line) for line in open(sys.argv[2]) if line.strip()]
assert tasks[-1]['state'] == 'completed'
messages = [json.loads(line) for line in open(sys.argv[3]) if line.strip()]
assert any(row.get('body') == 'remote complete' for row in messages)
PY

PORT=8799
ab serve --port "$PORT" --cards-dir agentbus/cards >"$TMP/serve.log" 2>&1 &
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
for row in state["task_reports"]:
    assert "task_id" in row
    assert "reports" in row
    assert "report_count" in row
PY
curl -fsS "http://127.0.0.1:$PORT/.well-known/agent-card.json?agent=example" > "$TMP/well-known-card.json"
ab a2a-card-check --file "$TMP/well-known-card.json" >/dev/null
CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: 127.evil.test:$PORT" "http://127.0.0.1:$PORT/api/state")
[ "$CODE" = "403" ] || { echo "expected 403 for non-local Host, got $CODE" >&2; exit 1; }
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/clear" -d '{}')
[ "$CODE" = "415" ] || { echo "expected 415 for non-json POST, got $CODE" >&2; exit 1; }
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/clear" -H 'Content-Type: application/json' -H "Origin: http://127.evil.test:$PORT" --data-binary '{}')
[ "$CODE" = "403" ] || { echo "expected 403 for non-local origin host, got $CODE" >&2; exit 1; }
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/clear" -H 'Content-Type: application/json' -H 'Origin: https://example.com' --data-binary '{}')
[ "$CODE" = "403" ] || { echo "expected 403 for remote origin, got $CODE" >&2; exit 1; }
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
    'agentbus/examples/adapters/a2a-outbound.sh',
    'agentbus/examples/adapters/openai-compatible.sh',
    'agentbus/examples/adapters/run-agent.sh',
    'agentbus/examples/adapters/codex-runner.py',
    'agentbus/examples/adapters/claude-runner.py',
    'agentbus/examples/demo-bus/README.md',
    'agentbus/examples/demo-bus/dashboard-demo.png',
    'agentbus/examples/demo-bus/messages.jsonl',
    'agentbus/examples/demo-bus/tasks.jsonl',
    'agentbus/examples/demo-bus/issues.jsonl',
    'agentbus/examples/demo-bus/status.json',
    'agentbus/examples/aas/assessment-summary.sample.json',
    'agentbus/examples/smoke/publish-smoke.sh',
    'agentbus/examples/wakeup/agent-runner-inbox.json',
    'agentbus/examples/wakeup/claude-inbox.json',
    'agentbus/examples/wakeup/codex-runner-inbox.json',
    'agentbus/examples/wakeup/claude-runner-inbox.json',
    'agentbus/examples/wakeup/openai-compatible-events.json',
    'agentbus/schemas/a2a-rpc.v1.md',
    'agentbus/schemas/assessment-packet.v1.md',
    'agentbus/schemas/wakeup-profile.v1.md',
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
  INSTALLED_DEMO=$("$INSTALL_VENV/bin/agentbus" examples demo-bus)
  test -f "$INSTALLED_DEMO/dashboard-demo.png"
  INSTALLED_LOOP=$("$INSTALL_VENV/bin/agentbus" loop --path)
  INSTALLED_WORKFLOW=$("$INSTALL_VENV/bin/agentbus" workflow --path)
  test -f "$INSTALLED_LOOP"
  test -f "$INSTALLED_WORKFLOW"
  INSTALL_BUS="$TMP/install-bus"
  "$INSTALL_VENV/bin/agentbus" --bus-dir "$INSTALL_BUS" init >/dev/null
  INSTALL_MSG=$("$INSTALL_VENV/bin/agentbus" --bus-dir "$INSTALL_BUS" send --from user --to reviewer --kind request --subject "Install smoke" --body "installed wheel")
  "$INSTALL_VENV/bin/agentbus" --bus-dir "$INSTALL_BUS" inbox --agent reviewer | grep -q "$INSTALL_MSG"
  rm -rf "$OUT" build agent_bus.egg-info agent-bus.egg-info agentbus/__pycache__
fi

printf 'publish-smoke-ok\n'
