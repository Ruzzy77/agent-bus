# agent-bus

[한국어](README.ko.md)

> A secure capsule channel for agents to share requests, status, reports, and judgment material

Connect agents to the same bus with `/agent-bus-loop`, then keep sharing requests, status, evidence, and judgment while work continues.

- Messaging hub for inter-agent messages, task state, tickets, and heartbeat
- Local state store: encrypted capsule store under `./.agent-bus/store/`
- Local dashboard (`127.0.0.1`)

## Scope

agent-bus is a local tool that lets agents already running in your project collaborate over the same secure capsule channel. `.agent-bus/` keeps public channel metadata and an encrypted capsule store, while Codex, Claude, local scripts, and the dashboard use the local API opened by `agentbus bus serve`. Authentication, remote execution hosting, and scheduling belong to the surrounding operator or execution environment. The lead agent synthesizes the bus record, makes the final judgment, and aligns with the user. "Judgment sharing" means keeping participant reports, references, and the lead's synthesis together.

## Dashboard demo

![agent-bus dashboard demo](agentbus/resources/demo-bus/dashboard-demo.png)

## Features

- Message, task, ticket, and agent-status sharing
- Ticket review for risky work or work that needs human confirmation
- Agent flow: join, watch, check inbox/stop, work, report, wait
- Agent loop through `/agent-bus-loop` or `agentbus guide loop`
- Bridge position and failure status review
- Lead synthesis of agent reports and evidence
- Completed-work report view that filters related task reports from the message timeline
- Event stream for webhooks, A2A calls, and agent runtimes
- Bridge profiles for agent runtimes and API bridges
- Codex, Claude, and Gemini runner profile examples
- OpenAI-compatible handler example for external model calls
- Minimum NDA-aware guardrails for outbound bridge handlers
- Capsule API and CLI-based operation
- localhost dashboard

## Components

- Bus state: project-local secure capsule channel in `.agent-bus/`
- Dashboard: local browser view bound to `127.0.0.1`
- Agent workflow: `agent-bus-loop` entry skill plus `agentbus guide workflow` prompt text
- Tickets: candidate work that needs human acceptance before task creation
- Event bridges: profiles that route events through typed handlers
- Bridge status: event bridge position and redacted failure summary
- Bridge profiles: reusable JSON config with event, matcher, and handler
- Packet builder: A2A/AAS JSON request, response handling, and packet generation

## Reports and judgment

agent-bus gives agents one shared record for judgment material. Each agent can leave reports, evidence pointers, progress state, disagreements, verification results, and remaining decisions. The lead agent gathers that material into the final judgment, user-facing report, and follow-up interaction.

When the bus record is exported or reviewed later, the lead's synthesis stays with the source record.

- Each agent’s observations and reports
- Shared judgments and remaining disagreements
- What is well-supported and what still needs checking
- The next decisions for the user
- The messages, work items, and file references behind the judgment

## Lifecycle

The user does not need to learn every command before starting. After installing the skill, ask an agent to run `/agent-bus-loop` or “start an agent-bus collaboration loop for this project.” The first agent acts as the lead until another lead is assigned.

```text
/agent-bus-loop
Start an agent-bus collaboration loop in this project.
Goal: <work to complete>
Avoid: <scope to leave alone>
Clarify the requirements only where needed, then guide the bus setup, task creation, collaboration loop, and closure report.
```

The lead agent asks only for lifecycle-changing missing facts: objective, scope, sensitivity, participating agents or runtimes, and completion criteria. When defaults are safe, it proceeds without expanding the questionnaire. The lead opens or joins the bus, creates the task and request messages, guides dashboard and auth setup when needed, and keeps the loop moving while workers leave reports, refs, and task-state updates.

At closure, the lead writes the final bus `report` as a termination report, marks the task `completed`, marks the agent `done`, and sends a `loop_closed` stop signal when the whole loop is finished. This makes the skill the human-facing entrypoint: the agent can discover the lifecycle and guide the user instead of requiring the user to operate the bus from README memory.

## Quick start

- Install the CLI
- Create a bus in a project directory
- Start `/agent-bus-loop` in an active agent thread or paste `agentbus guide loop`
- Give Codex, Claude, and peer agents the same `AGENTBUS_BUS_DIR` or `--bus-dir` channel
- Let agents share requests, status, reports, refs, and work state through the bus
- Accumulate reusable work patterns as bus-local skills in `.agent-bus/skills/<skill-id>/SKILL.md` plus `evidence.jsonl`
- Start the localhost dashboard when a browser view helps
- Use tasks and request messages for work an agent can judge and start directly
- Keep autonomous work moving; reserve tickets for human-triage decisions
- Use tickets for new proposals or risky changes that need human review before execution
- Use `bridge watch` or `bridge run` for user-run runtimes that need unattended polling or event bridging

### 1. Install

```bash
uv tool install git+https://github.com/Ruzzy77/agent-bus.git
# or: pipx install git+https://github.com/Ruzzy77/agent-bus.git

git clone https://github.com/Ruzzy77/agent-bus.git
cd agent-bus
python -m pip install .
python -m agentbus --help              # source checkout direct run
```

### 2. (Optional) Install skills

- `agent-bus-loop`: small entry skill for "start loop", "stop loop", or slash-style `/agent-bus-loop` requests
- `agent-bus-workflow`: full workflow skill for inbox, ack, task state, stop, ticket, and bridge handling
- For runtimes that load prompt text manually, paste `agentbus guide loop`; use `agentbus guide workflow` for the full rule set
- Restart the agent runtime after copying

```bash
: "${AGENT_SKILLS_DIR:?set the agent runtime skills directory}"
mkdir -p "$AGENT_SKILLS_DIR"
skills_src="$(dirname "$(dirname "$(agentbus guide workflow --path)")")"
for src in "$skills_src"/agent-bus-*; do
  dst="$AGENT_SKILLS_DIR/$(basename "$src")"
  test ! -e "$dst" || { echo "already exists: $dst"; continue; }
  cp -R "$src" "$dst"
done
```

Bus-local skills are project-local reuse records. After the bus is initialized and `agentbus bus serve` is running, record reusable flows or corrected paths in `.agent-bus/skills/<skill-id>/SKILL.md` and append use evidence through the CLI. `agentbus guide loop` and `agentbus guide workflow` show a compact local-skill summary at the normal start point.
Skill cleanup happens in the same maturation pass: run `agentbus skill review`, then decide at closure whether to keep, retire, install, combine, or simplify the local skill. Record the handled review boundary with `agentbus skill state`.

```bash
agentbus skill new loop-close --description "Keep loop closure reports short and traceable"
agentbus skill list
agentbus skill show <skill-id>
agentbus skill evidence <skill-id> --type check --ref <message-or-file-ref> --note "reusable observation"
agentbus skill review
agentbus skill state <skill-id> --state active
```

### 3. Start a bus

```bash
cd ~/my-project
agentbus bus init
agentbus bus serve      # http://127.0.0.1:8765
```

### 4. Demo bus

Use the packaged demo bus for dashboard screenshots or local UI checks. Run it from a copy so send/delete/auth actions stay out of the packaged fixture.

```bash
DEMO_WORK=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-demo.XXXXXX")
cp -R "$(agentbus resource path demo-bus)" "$DEMO_WORK/bus"
echo "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus migrate --from "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus serve --port 8791
```

In another shell, issue a temporary demo viewer token to try dashboard authentication from Settings. The token lasts 1 hour by default, and the package does not ship a fixed credential. `auth demo` also prepares the demo restricted messages and ticket so authenticated viewing visibly unlocks them.

```bash
export AGENTBUS_BUS_DIR=<printed-demo-bus-path>
agentbus auth demo
```

### 5. Agent loop

Ask the active agent to run `/agent-bus-loop`. Use the installed skill when available, or paste `agentbus guide loop` output into the thread.

```bash
agentbus bus status --stop-exit-code
agentbus agent set --agent my-agent --state running --note "started"
agentbus agent inbox --agent my-agent
agentbus message send --from my-agent --to all --kind report --subject "status" --body "..."
agentbus task state --id t-xxxx --state completed --by my-agent
```

When a lead agent closes a loop, the final bus message should be a structured termination report for dashboard reading and later audit. Use `agentbus guide workflow` for the full template. The report should record the closure decision, scope, decision trace, outputs, expected behavior, verification, non-applied items, and final operational state, then the agent should mark the task completed and its status `done`. If the whole bus loop is closed, send `agentbus bus stop --by <agent> --reason loop_closed --detail "termination report <message-id>"` after that final report.

### 6. Direct work request

Use this path for work that can proceed on agent judgment.

```bash
TASK_ID=$(agentbus task new --title "review bridge wording" --by user --assign my-agent)
agentbus message send --from user --to my-agent --kind request \
  --subject "review bridge wording" \
  --body "Review the current wording and report the smallest safe change" \
  --task "$TASK_ID"
```

### 7. Ticket intake

Use tickets for new proposals, risky changes, or work that should wait for human review. While a ticket waits for triage, continue safe active tasks.

```bash
agentbus ticket new --title "review bridge wording" --by user
agentbus ticket accept --id i-xxxx --by user --to my-agent --note "keep wording neutral"
agentbus task state --id t-xxxx --state input_required --by my-agent --note "decision needed"
```

### 8. Event bridge

```bash
agentbus bridge watch --types message.created,ticket.created \
  --target reviewer \
  --position-file .agent-bus/bridge/reviewer.position
```

### 9. Bridge profile

```bash
cp .agent-bus/bridge/profile.template.json .agent-bus/bridge/reviewer.json
$EDITOR .agent-bus/bridge/reviewer.json

agentbus bridge check --file .agent-bus/bridge/reviewer.json
agentbus bridge run --profile .agent-bus/bridge/reviewer.json --once
```

The profile routes bus events through a small matcher and a typed handler. Active profiles live in `.agent-bus/bridge/*.json`; package resources are examples that can be copied into that local directory. Dashboard gateways show the inbound endpoints currently opened by `bus serve`.

```bash
cp "$(agentbus resource path bridge/claude-inbox.json)" .agent-bus/bridge/claude-inbox.json
```

## Recipes

### OpenAI-compatible handler

```bash
export OPENAI_COMPAT_ENDPOINT=https://model-gateway.example/v1/chat/completions
export OPENAI_COMPAT_MODEL=assessment-router
export OPENAI_COMPAT_API_KEY=...
export OPENAI_COMPAT_RESPONSE_TO=operator
agentbus bridge run --profile "$(agentbus resource path bridge/openai-compatible-messages.json)" --once
```

### Codex CLI runner

Codex runner profiles call `codex exec`. Put Codex options in `handler.args`.

```bash
PROFILE=$(agentbus resource path bridge/codex-runner-inbox.json)
agentbus bridge run --profile "$PROFILE" --once --dry-run
agentbus bridge run --profile "$PROFILE" --once
```

### Claude CLI runner

Claude runner profiles call `claude -p`. Put Claude options in `handler.args`.

```bash
PROFILE=$(agentbus resource path bridge/claude-runner-inbox.json)
agentbus bridge run --profile "$PROFILE" --once --dry-run
agentbus bridge run --profile "$PROFILE" --once
```

### Gemini CLI runner

Gemini runner profiles call `gemini -p`. Put Gemini options in `handler.args`.

```bash
PROFILE=$(agentbus resource path bridge/gemini-runner-inbox.json)
agentbus bridge run --profile "$PROFILE" --once --dry-run
agentbus bridge run --profile "$PROFILE" --once
```

### Codex app use

The Codex app uses agent-bus as a tool while the thread is active. Automatic app launch is outside this package.

```bash
cd ~/my-project
agentbus bus init
agentbus guide workflow > /tmp/agentbus-workflow.md
```

Prompt text for a Codex app thread

```text
Use agent-bus for this thread.
You are codex.
Bus directory: /absolute/path/to/my-project/.agent-bus

Read the workflow from agentbus guide workflow or from the installed agent-bus-workflow skill.
Start by running:
agentbus bus status --stop-exit-code
agentbus agent set --agent codex --state running --note "joined"
agentbus agent inbox --agent codex

Handle request messages, ack handled messages, update task state when a task id exists, and report with `agentbus message send`.
When closing the loop, send the structured termination report from agentbus guide workflow as the final report, then set task state completed and status done.
```

### Claude Code use

Claude Code uses agent-bus as a tool while the thread is active. Automatic app launch is outside this package.

```bash
cd ~/my-project
agentbus bus init
agentbus guide loop > /tmp/agentbus-loop.md
```

Prompt text for a Claude thread

```text
Use agent-bus for this thread.
You are claude.
Bus directory: /absolute/path/to/my-project/.agent-bus

Start /agent-bus-loop if the skill is installed. Otherwise read the loop text from agentbus guide loop and the full workflow from agentbus guide workflow.
Start by running:
agentbus bus status --stop-exit-code
agentbus agent set --agent claude --state running --note "joined"
agentbus agent inbox --agent claude

Handle request messages, ack handled messages, update task state when a task id exists, and report with `agentbus message send`.
When closing the loop, send the structured termination report from agentbus guide workflow as the final report, then set task state completed and status done.
```

### Command contract

- Input: one `agent-runner-work.v1` JSON object on stdin
- Output: stdout becomes the report body
- Success: report message, task completion, source-message ack
- Failure: task failure, pending ack, message remains available for retry
- Runtime entrypoint: fixed provider entrypoint (`codex exec`, `claude -p`, `gemini -p`)

## A2A and AAS packet

Internal collaboration uses `message`, `task`, `ticket`, and `bridge` without packet conversion. `packet` appears at external protocol boundaries: building AAS-compatible data packets, wrapping them for A2A, sending them, or receiving A2A requests back into the bus. Public A2A hosting and certified AAS conformance belong to the surrounding integration layer.

```bash
MSG_ID=$(agentbus message send --from operator --to reviewer --kind request --subject "Pressure check" --body "Review the attached data")
agentbus packet data --protocol aas --asset-id urn:example:asset:line-7-press-2 \
  --data agentbus/resources/aas/operational-data.sample.json \
  --assessment-summary agentbus/resources/aas/assessment-summary.sample.json \
  --out packet.json
agentbus packet transport --protocol a2a --artifact message --message-id "$MSG_ID" --data packet.json --out request.json
agentbus packet send --protocol a2a --file request.json --endpoint https://example.com/a2a/rpc \
  --token-env A2A_TOKEN --record-response-to operator
```

## Sensitive data

With `agentbus bus serve` running, grant access before reading `restricted` raw projections. Grant commands print each token once. Agents present agent tokens with `AGENTBUS_AGENT_TOKEN`; dashboard viewers enter viewer tokens in Settings.

```bash
# In another shell while bus serve is running
AGENT_TOKEN=$(agentbus auth grant --agent reviewer --ttl-seconds 604800)
VIEWER_TOKEN=$(agentbus auth grant --viewer operator --ttl-seconds 86400)
MSG_ID=$(agentbus message send --from operator --to reviewer --kind request \
  --subject "NDA review" --body "Review local NDA data" \
  --sensitivity restricted --retention no_archive)
AGENTBUS_AGENT_TOKEN="$AGENT_TOKEN" agentbus agent inbox --agent reviewer
agentbus bus security-check
```

## Reference

### States

- Task states: `submitted`, `working`, `input_required`, `completed`, `failed`, `canceled`
- Agent states: `running`, `waiting`, `done`, `error`

### Local endpoints

- Dashboard bind: `127.0.0.1`
- Dashboard views: message timeline, tasks, tickets, completed-work report filter, agent state, loop status/stop request, archive/clear controls
- Local test endpoints: `/.well-known/agent-card.json?agent=<id>`, `/a2a/rpc`
- External hosting, discovery, authentication, streaming, SDK bridge: gateway or bridge-handler scope

### Security guardrails

- Trust boundary: agent identity comes from the local trust domain. Normal commands mutate records through the capsule daemon API; run a bus inside one trusted project boundary.
- Local store: `.agent-bus/channel.json` keeps public channel metadata, and `.agent-bus/store/capsule.sqlite` stores content-bearing fields as AEAD-encrypted payloads. The raw key lives outside the project in user config.
- `sensitivity`: `normal` permits local/external raw use, `internal` permits local raw sharing plus external redacted projection, and `restricted` permits raw reads for authorized agents and dashboard viewers.
- `retention`: `normal`, `session`, `no_archive`
- Agent auth: `agentbus auth grant --agent <agent> --ttl-seconds <seconds>` issues a one-time token. The agent presents it with `AGENTBUS_AGENT_TOKEN` to read `restricted` inbox/watch payloads. Granting the same name again replaces the token and acts as rotation.
- Dashboard auth: `agentbus auth grant --viewer <name> --ttl-seconds <seconds>` issues a one-time token. The viewer enters it in Settings to read `restricted` records during that session. Replaced or expired tokens also remove raw view from existing dashboard sessions.
- Packet send: `restricted` sources are blocked for external send; `internal` sources can leave only as redacted projections.
- Bridge: HTTP, A2A, and OpenAI-compatible handlers do not run on `restricted` events. Local agent handlers receive raw work packets only when the target agent token matches.
- Dashboard: default `/api/state` and `/api/events` return redacted `restricted` records; an authenticated viewer session receives raw local records.
- `no_archive`: stays in the active message log during `rotate`
- Dashboard write APIs: local origin and JSON POST required
- Token handling: use `--token-env` for A2A bearer tokens and `AGENTBUS_AGENT_TOKEN` for agent capability tokens.
- `packet send --protocol a2a` uses `https://` for bearer tokens and credential-like custom headers; `--allow-insecure` is the explicit local/test override.
- Bridge profiles use monitor, agent, HTTP, and OpenAI-compatible handlers. Agent handlers call fixed `codex exec`, `claude -p`, or `gemini -p` entrypoints.
- Bridge failure logs never store raw restricted payloads; keep bridge directories private and rotate/delete logs according to the same data policy as bus messages.
- agent-bus does not fully block deliberate same-OS-user memory/process attacks. NDA operations can add OS users, sandboxing, containers, or key isolation when that boundary matters.

### Commands

#### bus

| Command | Use |
| --- | --- |
| `bus init` | Create a secure capsule channel |
| `bus serve` | Run the localhost dashboard |
| `bus status` | Inspect bus state and stop request |
| `bus stop` | Write a cooperative stop request |
| `bus clear` | Clear current session records |
| `bus rotate` | Archive the message log |
| `bus security-check` | Check local guardrails and sensitive records |
| `bus supervise` | Supervise agent heartbeat and time limits |

#### agent

| Command | Use |
| --- | --- |
| `agent list` | Print agent state rows |
| `agent set` | Update agent heartbeat and state |
| `agent delete` | Delete an agent state row |
| `agent inbox` | Read an agent inbox |
| `agent ack` | Mark a handled message |
| `agent watch` | Watch unacked requests |

#### auth

| Command | Use |
| --- | --- |
| `auth init` | Check or prepare capsule auth state |
| `auth grant --agent/--viewer [--ttl-seconds <seconds>]` | Issue an agent or dashboard viewer restricted token |
| `auth demo` | Create a demo viewer token and demo-only restricted sample |
| `auth revoke --agent/--viewer` | Revoke an agent or dashboard viewer restricted token |
| `auth list` | Print restricted grants |

#### message

| Command | Use |
| --- | --- |
| `message send` | Send a message |
| `message delete` | Record a message deletion event |

#### task

| Command | Use |
| --- | --- |
| `task new` | Create a task |
| `task state` | Update task state |
| `task list` | Print task rows |
| `task delete` | Record a task deletion event |

#### ticket

| Command | Use |
| --- | --- |
| `ticket new` | Create candidate work |
| `ticket list` | Print ticket rows |
| `ticket accept` | Promote a ticket to a task and request message |
| `ticket reject` | Reject a ticket |

#### skill

| Command | Use |
| --- | --- |
| `skill new` | Create a bus-local skill draft |
| `skill list` | Print bus-local skills |
| `skill show` | Print bus-local `SKILL.md` |
| `skill state` | Change bus-local skill state |
| `skill review` | Summarize skill evidence and warnings to handle |
| `skill evidence` | Record skill use evidence |

#### bridge

| Command | Use |
| --- | --- |
| `bridge events` | Read bus events |
| `bridge watch` | Watch new bus events |
| `bridge run` | Run a bridge profile |
| `bridge check` | Check a bridge profile |
| `bridge status` | Print bridge positions and failure summaries |

#### packet

| Command | Use |
| --- | --- |
| `packet data --protocol aas` | Build or check an AAS-compatible data packet |
| `packet transport --protocol a2a --artifact card` | Build or check an A2A Agent Card |
| `packet transport --protocol a2a --artifact message` | Build or check an A2A SendMessage request |
| `packet send --protocol a2a` | Send an A2A request |
| `packet receive --protocol a2a` | Import an A2A request as a bus message |

#### guide / resource

| Command | Use |
| --- | --- |
| `guide workflow` | Print the collaboration workflow and termination report template |
| `guide loop` | Print the loop entry and closure-report guidance |
| `resource list` | Print packaged resource names |
| `resource path` | Print a packaged resource path |

### Configuration

Priority: CLI arguments, `AGENTBUS_*` environment variables, current working directory defaults

| Environment variable | Use |
| --- | --- |
| `AGENTBUS_BUS_DIR` | Channel directory (`--bus-dir`) |
| `AGENTBUS_CARDS_DIR` | Agent card directory (`--cards-dir`) |
| `AGENTBUS_ROOT` | File index root (`bus serve --root`) |
| `AGENTBUS_PORT` | Dashboard port (`bus serve --port`) |
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

- Bridge profile resources: `agentbus/resources/bridge`
- Demo dashboard bus: `agentbus/resources/demo-bus`
- Formula rendering: `vendor/katex`
- License: MIT

### Release check

Before publishing from a source checkout:

```bash
agentbus/resources/smoke/publish-smoke.sh
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
