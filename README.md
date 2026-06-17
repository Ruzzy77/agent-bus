# agent-bus

[한국어](README.ko.md)

> Runtime-neutral local coordination and provenance for multi-agent work

Connect collaborating agents to the same bus with `/agent-bus-loop`, then share requests, status, evidence, and judgment while work continues.

- Messaging hub for inter-agent messages, task state, tickets, and heartbeat
- Local state store: JSON/JSONL files under `./.agent-bus/`
- Local dashboard (`127.0.0.1`)

## What this is / is not

agent-bus is a runtime-neutral, git-adjacent coordination and provenance layer for agents that already run in your project. It stores inspectable local records for messages, tasks, tickets, reports, and stop signals; it does not authenticate agents, host remote runtimes, schedule work by itself, or decide consensus for the team. "Judgment sharing" means durable report and assessment artifacts with provenance, not hidden model reasoning inside the bus.

## Dashboard demo

![agent-bus dashboard demo](agentbus/examples/demo-bus/dashboard-demo.png)

This screenshot comes from the packaged demo bus and shows the default dashboard timeline, tickets, tasks, completed-work report view, and agent state.

## Features

- Message, task, ticket, and agent-status sharing
- Optional ticket review for risky work or work that needs human confirmation
- Agent lifecycle: join, watch, check inbox/stop, work, report, wait
- Agent loop entry through `/agent-bus-loop` or `agentbus loop`
- Adapter cursor and failure status check
- Assessment summary for shared judgment records
- Completed-work report view that filters related task reports from the message timeline
- Optional event stream for webhooks, SDK runners, A2A calls, and local scripts
- Optional wakeup profiles for unattended agent runners and event bridges
- Optional Codex and Claude runner examples
- OpenAI-compatible HTTP adapter example for external model calls
- Minimum NDA-aware guardrails for outbound adapters
- Local file and CLI-based operation
- localhost dashboard

## Components

- Bus state: JSON/JSONL files in the project bus directory
- Dashboard: local browser view bound to `127.0.0.1`
- Agent workflow: `agent-bus-loop` entry skill plus `agentbus workflow` prompt text
- Tickets: candidate work that needs human acceptance before task creation
- Event bridges: scripts that reread the bus before external action
- Adapter status: event bridge cursor and failure summary without payload body replay
- Wakeup profiles: reusable JSON config for agent runners and event bridges
- Packet builder: A2A/AAS JSON request, response handling, and packet generation

## Quick start

- Install the CLI
- Create a bus in a project directory
- Start `/agent-bus-loop` in an active agent thread or paste `agentbus loop`
- Give Codex, Claude, and peer agents the same `AGENTBUS_BUS_DIR` or `--bus-dir`
- Let agents share requests, status, reports, refs, and task state through the bus
- Start the localhost dashboard when a browser view helps
- Use direct tasks and request messages for work that can run without human acceptance
- Keep autonomous work moving; do not create tickets for routine next steps
- Use tickets only for new proposals or critical work that cannot safely proceed without human review
- Use `watch-events` or `wakeup` only when a user-run runtime needs unattended polling or event bridging

### 1. Install

```bash
uv tool install git+https://github.com/Ruzzy77/agent-bus.git
# or: pipx install git+https://github.com/Ruzzy77/agent-bus.git

git clone https://github.com/Ruzzy77/agent-bus.git
cd agent-bus
python -m pip install .
python -m agentbus --help              # source checkout without installing the console script
```

After a PyPI release exists, `uv tool install agent-bus` and `pipx install agent-bus` should be the shortest install paths.

### 2. (Optional) Install skills

- `agent-bus-loop`: small entry skill for "start loop", "stop loop", or slash-style `/agent-bus-loop` requests
- `agent-bus-workflow`: full workflow skill for inbox, ack, task state, stop, ticket, and bridge handling
- If the runtime does not load skills, paste `agentbus loop` into a prompt; use `agentbus workflow` for the full rule set
- Restart the agent runtime after copying

```bash
: "${AGENT_SKILLS_DIR:?set the agent runtime skills directory}"
mkdir -p "$AGENT_SKILLS_DIR"
skills_src="$(dirname "$(dirname "$(agentbus workflow --path)")")"
for src in "$skills_src"/agent-bus-*; do
  dst="$AGENT_SKILLS_DIR/$(basename "$src")"
  test ! -e "$dst" || { echo "already exists: $dst"; continue; }
  cp -R "$src" "$dst"
done
```

### 3. Start a bus

```bash
cd ~/my-project
agentbus init
agentbus serve      # http://127.0.0.1:8765
```

### 4. Demo bus

Use the packaged demo bus for dashboard screenshots or local UI checks. Run a copy if you need to edit it.

```bash
DEMO=$(agentbus examples demo-bus)
AGENTBUS_BUS_DIR="$DEMO" agentbus serve --port 8791
```

### 5. Agent loop

Ask the active agent to run `/agent-bus-loop`. Use the installed skill when available, or paste `agentbus loop` output into the thread.

```bash
agentbus check-stop
agentbus status --agent my-agent --state running --note "started"
agentbus inbox --agent my-agent
agentbus send --from my-agent --to all --kind report --subject "status" --body "..."
agentbus task-state --id t-xxxx --state completed --by my-agent
```

When a lead agent closes a loop, the final bus message should be a structured termination report, not a chat summary. Use `agentbus workflow` for the full template. The report should record the closure decision, scope, decision trace, outputs, expected behavior, verification, non-applied items, and final operational state, then the agent should mark the task completed and its status `done`.

### 6. Direct work request

Use this path for work that can proceed without human acceptance.

```bash
TASK_ID=$(agentbus task-new --title "review adapter wording" --by user --assign my-agent)
agentbus send --from user --to my-agent --kind request \
  --subject "review adapter wording" \
  --body "Review the current wording and report the smallest safe change" \
  --task "$TASK_ID"
```

### 7. Ticket intake

Use tickets only for new proposals, risky changes, or work that should wait for human review. If safe work can continue, a ticket should not stop the active loop.

```bash
agentbus ticket-new --title "review adapter wording" --by user
agentbus ticket-accept --id i-xxxx --by user --to my-agent --note "keep wording neutral"
agentbus task-state --id t-xxxx --state input_required --by my-agent --note "decision needed"
```

### 8. Event bridge

```bash
agentbus watch-events --types message.created,ticket.created \
  --target reviewer \
  --cursor-file .agent-bus/adapters/reviewer.cursor \
  --fail-log .agent-bus/adapters/reviewer.failures.jsonl \
  --exec agentbus/examples/adapters/a2a-outbound.sh
```

### 9. Wakeup profile

```bash
PROFILE=$(agentbus examples wakeup/claude-inbox.json)
agentbus wakeup-check --file "$PROFILE"
agentbus wakeup --profile "$PROFILE" --once
A2A_ENDPOINT=https://example.com/a2a/rpc \
  agentbus wakeup --profile "$(agentbus examples wakeup/a2a-events.json)"
```

The profile is command input for the operator or agent runtime. The bus records state; it does not own the agent process.

### 10. OpenAI-compatible adapter

```bash
export OPENAI_COMPAT_ENDPOINT=https://model-gateway.example/v1/chat/completions
export OPENAI_COMPAT_MODEL=assessment-router
export OPENAI_COMPAT_TOKEN_ENV=MODEL_GATEWAY_API_KEY
export OPENAI_COMPAT_RESPONSE_TO=operator
agentbus aas-packet --asset-id urn:example:asset:line-7-press-2 \
  --data agentbus/examples/aas/operational-data.sample.json \
  --assessment-summary agentbus/examples/aas/assessment-summary.sample.json |
  "$(agentbus examples adapters/openai-compatible.sh)"
```

### 11. Agent runner example

```bash
agentbus ticket-accept --id i-xxxx --by user --to my-agent --note "run"
export AGENT_RUNNER_COMMAND='your-agent-command --json'
agentbus wakeup --profile "$(agentbus examples wakeup/agent-runner-inbox.json)" --once
```

### 12. Codex CLI runner

Prerequisites

- `codex exec --help` works in the shell
- Codex CLI login is complete
- `CODEX_RUNNER_CWD` points to the project the agent may inspect

```bash
cd ~/my-project
agentbus init

TASK_ID=$(agentbus task-new --title "codex runner smoke" --by user --assign codex)
agentbus send --from user --to codex --kind request \
  --subject "runner smoke" \
  --body "Do not inspect files or run commands. Return exactly: agentbus-codex-ok" \
  --task "$TASK_ID"

PROFILE=$(agentbus examples wakeup/codex-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CODEX_RUNNER_MODE=cli \
  CODEX_RUNNER_CWD="$PWD" \
  CODEX_RUNNER_SANDBOX=read-only \
  CODEX_RUNNER_EXTRA_ARGS="--ephemeral" \
  agentbus wakeup --profile "$PROFILE" --once

agentbus inbox --agent codex
```

For work that needs human review, create a ticket first and accept it to `codex` instead of using `task-new` and `send` directly.

### 13. Codex SDK runner

`openai-codex` is an optional runtime dependency for the runner environment. It is not installed by agent-bus.

```bash
python -m venv .venv-codex-runner
. .venv-codex-runner/bin/activate
python -m pip install openai-codex

agentbus send --from user --to codex --kind request \
  --subject "sdk runner smoke" \
  --body "Do not inspect files or run commands. Return exactly: agentbus-codex-sdk-ok"

PROFILE=$(agentbus examples wakeup/codex-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CODEX_RUNNER_MODE=sdk \
  CODEX_RUNNER_CWD="$PWD" \
  CODEX_RUNNER_SANDBOX=read-only \
  agentbus wakeup --profile "$PROFILE" --once
```

### 14. Claude CLI runner

Prerequisites

- `claude -p "hello"` works in the shell
- Claude Code CLI login is complete
- `CLAUDE_RUNNER_CWD` points to the project the agent may inspect

```bash
cd ~/my-project
agentbus init

TASK_ID=$(agentbus task-new --title "claude runner smoke" --by user --assign claude)
agentbus send --from user --to claude --kind request \
  --subject "runner smoke" \
  --body "Do not inspect files or run commands. Return exactly: agentbus-claude-ok" \
  --task "$TASK_ID"

PROFILE=$(agentbus examples wakeup/claude-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CLAUDE_RUNNER_MODE=cli \
  CLAUDE_RUNNER_CWD="$PWD" \
  CLAUDE_RUNNER_PERMISSION_MODE=plan \
  agentbus wakeup --profile "$PROFILE" --once

agentbus inbox --agent claude
```

### 15. Claude Agent SDK and Messages API runners

`claude-agent-sdk` and `ANTHROPIC_API_KEY` are optional runtime inputs. They are not installed or stored by agent-bus. `api` mode sends one Messages API request and does not provide local file or shell tools by itself.

```bash
python -m venv .venv-claude-runner
. .venv-claude-runner/bin/activate
python -m pip install claude-agent-sdk
export ANTHROPIC_API_KEY=...

agentbus send --from user --to claude --kind request \
  --subject "sdk runner smoke" \
  --body "Do not inspect files or run commands. Return exactly: agentbus-claude-sdk-ok"

PROFILE=$(agentbus examples wakeup/claude-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CLAUDE_RUNNER_MODE=sdk \
  CLAUDE_RUNNER_CWD="$PWD" \
  CLAUDE_RUNNER_PERMISSION_MODE=plan \
  agentbus wakeup --profile "$PROFILE" --once

CLAUDE_RUNNER_MODE=api \
  CLAUDE_RUNNER_MODEL=claude-sonnet-4-5 \
  agentbus wakeup --profile "$PROFILE" --once
```

### 16. Codex app use

The Codex app uses agent-bus as a tool while the thread is active. Automatic app wakeup is outside this package.

```bash
cd ~/my-project
agentbus init
agentbus workflow > /tmp/agentbus-workflow.md
```

Prompt text for a Codex app thread

```text
Use agent-bus for this thread.
You are codex.
Bus directory: /absolute/path/to/my-project/.agent-bus

Read the workflow from agentbus workflow or from the installed agent-bus-workflow skill.
Start by running:
agentbus check-stop
agentbus status --agent codex --state running --note "joined"
agentbus inbox --agent codex

Handle request messages, ack only handled messages, update task-state when a task id exists, and report with agentbus send.
When closing the loop, send the structured termination report from agentbus workflow as the final report, then set task-state completed and status done.
```

### 17. Claude Code use

Claude Code uses agent-bus as a tool while the thread is active. Automatic app wakeup is outside this package.

```bash
cd ~/my-project
agentbus init
agentbus loop > /tmp/agentbus-loop.md
```

Prompt text for a Claude thread

```text
Use agent-bus for this thread.
You are claude.
Bus directory: /absolute/path/to/my-project/.agent-bus

Start /agent-bus-loop if the skill is installed. Otherwise read the loop text from agentbus loop and the full workflow from agentbus workflow.
Start by running:
agentbus check-stop
agentbus status --agent claude --state running --note "joined"
agentbus inbox --agent claude

Handle request messages, ack only handled messages, update task-state when a task id exists, and report with agentbus send.
When closing the loop, send the structured termination report from agentbus workflow as the final report, then set task-state completed and status done.
```

Command contract

- Input: one `agent-runner-work.v1` JSON object on stdin
- Output: stdout becomes the report body
- Success: report message, task completion, source-message ack
- Failure: task failure, no ack, pending message kept for retry
- Runtime-specific command: operator script or CLI wrapper in `AGENT_RUNNER_COMMAND`

### 18. A2A and AAS packet

These helpers build local A2A-facing JSON and AAS-style assessment packets for testing and handoff. They do not make agent-bus a hosted A2A server or a certified AAS-compliant implementation.

```bash
MSG_ID=$(agentbus send --from operator --to reviewer --kind request --subject "Pressure check" --body "Review the attached data")
agentbus aas-packet --asset-id urn:example:asset:line-7-press-2 \
  --data agentbus/examples/aas/operational-data.sample.json \
  --assessment-summary agentbus/examples/aas/assessment-summary.sample.json \
  --out packet.json
agentbus a2a-rpc --message-id "$MSG_ID" --data packet.json --out request.json
agentbus a2a-post --file request.json --endpoint https://example.com/a2a/rpc \
  --token-env A2A_TOKEN --record-response-to operator
```

### 19. Sensitive data

```bash
MSG_ID=$(agentbus send --from operator --to reviewer --kind request \
  --subject "NDA review" --body "Review local NDA data" \
  --sensitivity confidential --retention no_archive)
agentbus a2a-rpc --message-id "$MSG_ID" --out request.json
agentbus a2a-post --file request.json --endpoint https://example.com/a2a/rpc --allow-sensitive
agentbus security-check
```

## Reference

### States

- Task states: `submitted`, `working`, `input_required`, `completed`, `failed`, `canceled`
- Agent states: `running`, `waiting`, `done`, `error`

### Report coverage

`agentbus assess` is a read-only coverage heuristic. It compares expected reporters from task assignment and request targets with actual report senders, then surfaces `blind_spots` and unexpected reporters; it does not score quality, decide truth, or compute consensus.

```bash
agentbus assess --task t-xxxx
agentbus assess --json
```

### Assessment summaries

`assessmentSummary` is supplied through `--assessment-summary`; agent-bus preserves and projects it, but does not derive agreement from the bus. `consensus` entries must be objects with `statement` and non-empty `participants`, with optional `evidenceReferences`, `communicationIds`, or `workItemIds` for source pointers.

### Local endpoints

- Dashboard bind: `127.0.0.1`
- Dashboard views: message timeline, tasks, tickets, completed-work report filter, agent state, loop status/stop request, archive/clear controls
- Local test endpoints: `/.well-known/agent-card.json?agent=<id>`, `/a2a/rpc`
- External hosting, discovery, authentication, streaming, SDK wakeup: adapter scope

### Security guardrails

- Trust boundary: agent-bus has no authentication or identity proof. Any local process that can write the bus directory can send as any agent, accept tickets, clear records, or request stop; run a bus only inside a single-trust-domain project directory.
- Local store: plain JSON/JSONL; host file permissions and data governance stay with the operator
- Sensitivity marking is voluntary. Outbound blocking applies to records marked `confidential` or `restricted`; unmarked sensitive text is not detected or blocked.
- `sensitivity`: `public`, `internal`, `confidential`, `restricted`
- `retention`: `normal`, `session`, `no_archive`
- Outbound `a2a-post`, `watch-events`, and `wakeup`: block `confidential` and `restricted` unless sensitive handling is explicitly allowed
- Blocked `watch-events` and `wakeup` output: redacted notice, not payload body
- `no_archive`: retained in the active message log when `rotate` archives other messages
- Dashboard write APIs: local origin and JSON POST required
- Token handling: prefer `--token-env`; avoid direct tokens in shell history and bus messages
- `a2a-post` refuses bearer tokens, credential-like custom headers, or sensitive requests over `http://` unless `--allow-insecure` is passed; prefer `https://` for remote endpoints
- Wakeup profiles and adapter commands execute local shell commands. Treat shared profiles like executable scripts; `wakeup-check` validates shape and required environment, not command safety.
- Adapter failure logs may contain payload bodies when an allowed command fails; keep adapter directories private and rotate/delete logs according to the same data policy as bus messages.

### Commands

| Command | Use |
| --- | --- |
| `init`, `show-status`, `check-stop` | Create a bus, inspect state, honor stop signals |
| `send`, `inbox`, `ack`, `message-delete` | Exchange and manage messages |
| `status` | Update agent heartbeat and state |
| `task-new`, `task-state`, `task-list`, `task-delete` | Manage task lifecycle |
| `assess` | Read-only per-task report coverage and blind-spot candidate summary |
| `ticket-new`, `ticket-list`, `ticket-accept`, `ticket-reject` | Human-gated candidate work |
| `events`, `watch-events`, `wakeup`, `wakeup-check` | Read bus events, run adapters, or run a wakeup profile |
| `adapter-status` | Print adapter cursor and failure summary |
| `serve` | Run the localhost dashboard |
| `clear`, `rotate` | Clear current messages or archive the message log |
| `security-check` | Check local guardrails and sensitive-record counts |
| `workflow` | Print the agent collaboration procedure and termination report template |
| `loop` | Print the loop entry procedure and closure-report guidance |
| `examples` | Print packaged example paths |
| `aas-packet`, `aas-packet-check` | Build and check an AAS-style packet |
| `a2a-card`, `a2a-rpc`, `a2a-rpc-check`, `a2a-post` | Build, check, send, and record A2A-facing JSON |

### Configuration

Priority: CLI arguments, `AGENTBUS_*` environment variables, current working directory defaults

| Environment variable | Use |
| --- | --- |
| `AGENTBUS_BUS_DIR` | Bus directory (`--bus-dir`) |
| `AGENTBUS_CARDS_DIR` | Agent card directory (`--cards-dir`) |
| `AGENTBUS_ROOT` | File index root (`serve --root`) |
| `AGENTBUS_PORT` | Dashboard port (`serve --port`) |
| `AGENTBUS_MAX_BYTES` | Auto-rotate message log threshold, default 5 MB, `0` disables it |
| `AGENTBUS_ARCHIVE_KEEP` | Number of archives to keep, default `0` keeps all |

### Python API

Available Python modules: `agentbus.bus`, `agentbus.assessment`, `agentbus.a2a`

```python
from pathlib import Path
from agentbus import a2a, assessment, bus

bd = Path(".agent-bus")
msg = bus.make_message("my-agent", "all", "note", "subject", "body")
bus.append_message(bd, msg)
events = bus.bus_events(bd, types={"message.created"})
packet = assessment.assessment_packet(bd, {"value": 1}, "urn:asset:1")
request = a2a.send_message_request(msg)
```

### Package contents

- Wakeup profile examples: `agentbus/examples/wakeup`
- Adapter examples: `agentbus/examples/adapters`
- Demo dashboard bus: `agentbus/examples/demo-bus`
- Formula rendering: `vendor/katex`
- License: MIT

### Release check

Before publishing from a source checkout:

```bash
agentbus/examples/smoke/publish-smoke.sh
uv build --sdist --wheel --out-dir /tmp/agentbus-dist
python -m venv /tmp/agentbus-install
/tmp/agentbus-install/bin/python -m pip install /tmp/agentbus-dist/*.whl
/tmp/agentbus-install/bin/agentbus --help
python -m twine check /tmp/agentbus-dist/*   # optional
```

### Related standards

- A2A: [Agent2Agent Protocol specification](https://a2a-protocol.org/latest/specification/)
- A2A: [a2aproject/A2A repository](https://github.com/a2aproject/A2A)
- AAS: [IDTA AAS specifications](https://industrialdigitaltwin.io/aas-specifications/index/home/index.html)
- AAS: [Part 1: Metamodel](https://industrialdigitaltwin.io/aas-specifications/IDTA-01001/v3.1.2/index.html)
- AAS: [Part 2: Application Programming Interfaces](https://industrialdigitaltwin.io/aas-specifications/IDTA-01002/v3.1.2/index.html)
