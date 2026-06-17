#!/usr/bin/env sh
# Generic agent runner. Reads one wakeup inbox payload from stdin.
# Required: AGENT_RUNNER_COMMAND.
# The command receives one agent-runner-work.v1 JSON object on stdin per message.

set -eu

payload_tmp=$(mktemp "${TMPDIR:-/tmp}/agentbus-run-agent.XXXXXX")
cleanup() { rm -f "$payload_tmp"; }
trap cleanup EXIT INT TERM
cat > "$payload_tmp"

python3 - "$payload_tmp" <<'PY'
import json
import os
import shlex
import subprocess
import sys

payload_path = sys.argv[1]
with open(payload_path, encoding="utf-8") as f:
    payload = json.load(f)


def truthy(value, default=True):
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def sensitive_marks(value):
    marks = set()
    if isinstance(value, dict):
        level = str(value.get("sensitivity", "")).strip().lower()
        if level:
            marks.add(level)
        for child in value.values():
            marks.update(sensitive_marks(child))
    elif isinstance(value, list):
        for child in value:
            marks.update(sensitive_marks(child))
    return marks


if sensitive_marks(payload) & {"confidential", "restricted"}:
    if not os.environ.get("AGENTBUS_ALLOW_SENSITIVE"):
        print("sensitive payload blocked; set AGENTBUS_ALLOW_SENSITIVE to run", file=sys.stderr)
        raise SystemExit(2)

command = os.environ.get("AGENT_RUNNER_COMMAND", "").strip()
if not command:
    print("AGENT_RUNNER_COMMAND required", file=sys.stderr)
    raise SystemExit(1)

pending = [row for row in payload.get("pending", []) if isinstance(row, dict)]
if payload.get("mode") != "inbox" or not pending:
    print(json.dumps({"ok": True, "status": "idle", "processed": 0}, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0)

cli = shlex.split(os.environ.get("AGENTBUS_CLI", "agentbus")) or ["agentbus"]
agent = os.environ.get("AGENT_RUNNER_NAME", "").strip() or str(payload.get("agent") or "agent-runner")
report_enabled = truthy(os.environ.get("AGENT_RUNNER_REPORT"), True)
ack_enabled = truthy(os.environ.get("AGENT_RUNNER_ACK"), True)
update_task = truthy(os.environ.get("AGENT_RUNNER_UPDATE_TASK"), True)
report_kind = os.environ.get("AGENT_RUNNER_REPORT_KIND", "report")
report_subject_prefix = os.environ.get("AGENT_RUNNER_REPORT_SUBJECT_PREFIX", "Result")
processed = []


def run_agent_command(work):
    env = os.environ.copy()
    env.update({
        "AGENTBUS_RUNNER_AGENT": agent,
        "AGENTBUS_RUNNER_MESSAGE_ID": str(work.get("messageId") or ""),
        "AGENTBUS_RUNNER_TASK_ID": str(work.get("taskId") or ""),
    })
    return subprocess.run(
        command,
        input=json.dumps(work, ensure_ascii=False, sort_keys=True) + "\n",
        text=True,
        shell=True,
        env=env,
        capture_output=True,
        check=False,
    )


def bus_call(args, capture=False):
    return subprocess.run(
        cli + args,
        text=True,
        capture_output=capture,
        check=True,
    )


for message in pending:
    mid = str(message.get("id") or "")
    task_id = str(message.get("task_id") or "")
    work = {
        "schemaVersion": "agent-runner-work.v1",
        "agent": agent,
        "messageId": mid,
        "taskId": task_id,
        "subject": message.get("subject", ""),
        "body": message.get("body", ""),
        "refs": message.get("refs") or [],
        "message": message,
        "source": {
            "schemaVersion": payload.get("schemaVersion", ""),
            "profile": payload.get("profile", ""),
            "mode": payload.get("mode", ""),
        },
    }
    if update_task and task_id:
        bus_call(["task-state", "--id", task_id, "--state", "working", "--by", agent, "--note", f"runner started from {mid}"])
    proc = run_agent_command(work)
    body = proc.stdout.strip() or proc.stderr.strip() or "completed"
    if proc.returncode:
        if update_task and task_id:
            bus_call(["task-state", "--id", task_id, "--state", "failed", "--by", agent, "--note", f"runner exit {proc.returncode}"])
        print(json.dumps({
            "ok": False,
            "agent": agent,
            "messageId": mid,
            "taskId": task_id,
            "returncode": proc.returncode,
        }, ensure_ascii=False, sort_keys=True))
        raise SystemExit(proc.returncode)
    report_id = ""
    if report_enabled:
        to = os.environ.get("AGENT_RUNNER_REPORT_TO", "").strip() or str(message.get("from") or "")
        if to:
            args = [
                "send",
                "--from", agent,
                "--to", to,
                "--kind", report_kind,
                "--subject", f"{report_subject_prefix}: {message.get('subject', '')}".strip(),
                "--body", body,
            ]
            if task_id:
                args.extend(["--task", task_id])
            if mid:
                args.extend(["--reply-to", mid])
            report_id = bus_call(args, capture=True).stdout.strip()
    if update_task and task_id:
        bus_call(["task-state", "--id", task_id, "--state", "completed", "--by", agent, "--note", f"runner completed from {mid}"])
    if ack_enabled and mid:
        bus_call(["ack", "--agent", agent, mid])
    processed.append({"messageId": mid, "taskId": task_id, "reportId": report_id})

print(json.dumps({"ok": True, "agent": agent, "processed": processed}, ensure_ascii=False, sort_keys=True))
PY
