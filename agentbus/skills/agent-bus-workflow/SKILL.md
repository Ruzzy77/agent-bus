---
name: agent-bus-workflow
description: >-
  Use this skill when Codex or another agent must collaborate with peers
  through agent-bus: joining a bus, running the heartbeat and inbox loop, using
  task states, reporting input_required, handling stop.json, or writing a
  prompt/AGENTS.md section for agent-bus collaboration, including minimum
  agent requirements.
---

# agent-bus workflow

Start the loop in the active agent thread. Use `agentbus` as volatile coordination state, and put durable decisions and outputs in project files.

## Minimum requirements

Use this workflow only when the agent can meet these requirements.

| Requirement | Reason |
| --- | --- |
| Run shell commands | The loop uses the `agentbus` CLI. |
| Read and write the shared bus directory | Messages, acks, status, tasks, locks, and stop signals are files. |
| Use a stable agent name | Status, inbox targeting, and acks key on `--agent <name>`. |
| Access referenced project files | `--ref <path>` is useful only if the next agent can inspect the file. |
| Return to the loop at work boundaries | Heartbeat is a status update, not a background daemon. |

Do not use agent-bus as the primary coordination channel for an agent that cannot write the bus directory. Use chat handoff or a relay agent instead.

Local network access is not required for CLI coordination. The dashboard is optional and binds to `127.0.0.1`.

## Variables

| Name | Meaning |
| --- | --- |
| `<name>` | This agent name, such as `my-agent` or `reviewer`. |
| `<bus_dir>` | Shared bus directory. Use `AGENTBUS_BUS_DIR` or `--bus-dir`. |
| `<peer>` | Specific peer agent, `all`, or `user`. |

Configuration precedence is CLI flag, then `AGENTBUS_*`, then cwd default.

## Join

```bash
export AGENTBUS_BUS_DIR=<bus_dir>
agentbus init
agentbus check-stop
agentbus status --agent <name> --state running --note "joined"
```

If `check-stop` exits 2, do not start new work. Report the stop and set a terminal or waiting state.

## Loop

Repeat this sequence at every work boundary.

```bash
agentbus check-stop
agentbus status --agent <name> --state running --task <task_id> --note "working"
agentbus inbox --agent <name>
agentbus ack --agent <name> <message_id>
agentbus task-state --id <task_id> --state working --by <name> --note "current slice"
agentbus send --from <name> --to <peer> --kind report --subject "status" --body "short result"
agentbus status --agent <name> --state waiting --task <task_id> --note "waiting for next signal"
```

Acknowledge only messages already read and handled. Use `--reply-to <message_id>`, `--task <task_id>`, and `--ref <path>` when they help the next reader.

## Sensitive data

Treat `sensitivity` and `retention` as handling signals from the bus.

- Read `sensitivity` before using web tools, remote SDKs, A2A endpoints, or external adapters.
- Do not send `confidential` or `restricted` data outside the local bus unless the task or user explicitly permits it.
- Use `--allow-sensitive` only for that explicit handoff.
- Use `--retention no_archive` for NDA data that should stay out of message archives.
- Run `agentbus security-check` when a bus may contain NDA or restricted data.
- Blocked `watch-events` and `wakeup` output is a redacted notice unless sensitive handling is explicitly allowed.

## Tasks and states

Use task state for the work item.

| State | Use |
| --- | --- |
| `submitted` | Work exists but has not started. |
| `working` | An agent is actively changing or checking it. |
| `input_required` | User decision or missing external input blocks progress. |
| `completed` | Requested work is done. |
| `failed` | Work cannot complete under current constraints. |
| `canceled` | Work was intentionally stopped. |

Use agent status for the agent process.

| State | Use |
| --- | --- |
| `running` | The agent is active. This is also the heartbeat. |
| `waiting` | The agent is idle or blocked without active work. |
| `done` | The agent has no remaining work. |
| `error` | The agent hit an unresolved fault. |

## Input required

When progress needs the user, record it in both channels available to the current run.

```bash
agentbus task-state --id <task_id> --state input_required --by <name> --note "decision needed"
agentbus send --from <name> --to user --kind request --task <task_id> --subject "input required" --body "decision, options, risk"
agentbus status --agent <name> --state waiting --task <task_id> --note "input_required"
```

If a chat channel with the user exists, report the same decision point there once. Do not rely on dashboard state alone for user-blocking choices.

## Stop

Check for stop before starting a chunk and before long-running commands.

```bash
agentbus check-stop
```

If the user asks to stop in chat, write the stop signal.

```bash
agentbus stop --by <name> --reason user_stop --detail "requested in chat"
```

After a stop, finish only the safe boundary already in progress. Send a short report with changed files, unfinished work, and risk. Do not begin a new task.

## Reports

Send reports that change coordination. Skip heartbeat-only chatter.

Use this shape for final or blocking reports:

```text
Judgment: current decision.
Output: concrete change or artifact.
Risk: remaining uncertainty.
Next: smallest useful next action.
```

Use `kind=request` for a decision needed from a peer or user. Use `kind=report` for completed work or a changed risk.

## Ticket intake

Autonomous work is the default. Do not use tickets as the default work queue, and do not create tickets that add review fatigue, stop the loop, or interrupt safe forward progress. For work that can proceed without human acceptance, create a task and send a request message directly.

```bash
TASK_ID=$(agentbus task-new --title "short work title" --by <name> --assign <peer>)
agentbus send --from <name> --to <peer> --kind request --subject "short work title" --body "work request" --task "$TASK_ID"
```

Use a ticket only for a new proposal, a critical or risky change, or work that cannot safely proceed until a human accepts it.

```bash
agentbus ticket-new --title "short candidate" --by <name> --body "why it matters" --ref path/to/file
agentbus ticket-list
agentbus ticket-accept --id <ticket_id> --by user --to <name>
agentbus ticket-reject --id <ticket_id> --by user
```

Do not add priority, category, or long planning fields. The human decision is only accept or reject. Accepting a ticket creates a task and sends a request message to the selected agent.

## Event bridges and agent runners

Use `agentbus events`, `agentbus watch-events`, or `agentbus wakeup` when a user-run runtime must observe the bus. The event contract is `agentbus.event.v1`.

```bash
agentbus events --types ticket.* --jsonl
agentbus watch-events --types message.created,ticket.created --cursor-file .agent-bus/adapters/<name>.cursor --exec ./wake-agent.sh
agentbus wakeup --profile "$(agentbus examples wakeup/<name>.json)" --once
agentbus adapter-status
```

`wakeup` reads a `wakeup-profile.v1` JSON file. Use `mode=inbox` for ack-based agent self-wake and `mode=events` for event bridges. The core bus does not start or resume agents by itself. Platform wakeups, webhooks, A2A, AAS (Asset Administration Shell), and SDK bridges should be user-run helpers that consume events or pending inbox data, keep a cursor when needed, and then reread the bus before acting. Sensitive payloads are blocked by default unless the profile allows them. Use `agentbus adapter-status` to inspect event bridge cursor and failure summaries without replaying payload bodies.

Use `agentbus examples adapters/openai-compatible.sh` when a checked payload should go to an OpenAI-compatible endpoint and the response should return as a bus message.
Use `agentbus examples adapters/run-agent.sh` when an accepted ticket should become an inbox request processed by a user-run agent command, then close with report, task-state, and ack records.
Use `agentbus examples adapters/codex-runner.py` when that local agent command should be Codex; choose `CODEX_RUNNER_MODE=cli`, `sdk`, or `auto` per runtime.
Use `agentbus examples adapters/claude-runner.py` when that local agent command should be Claude; choose `CLAUDE_RUNNER_MODE=cli`, `sdk`, `api`, or `auto` per runtime.

## Codex use

Codex app use is interactive. Give the thread the bus directory and this workflow, then let the agent run the loop while the thread is active. Automatic app wakeup is outside this package.

```text
Use agent-bus for this thread.
You are codex.
Bus directory: <bus_dir>

Start by running check-stop, status, and inbox.
Ack only handled messages, update task-state when a task id exists, and report with agentbus send.
```

Codex CLI or SDK use is runner-based. The runner receives inbox work through `agentbus wakeup`, calls Codex, records the report, completes the task, and acks the handled message.

```bash
PROFILE=$(agentbus examples wakeup/codex-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CODEX_RUNNER_MODE=cli CODEX_RUNNER_CWD="$PWD" CODEX_RUNNER_SANDBOX=read-only agentbus wakeup --profile "$PROFILE" --once
```

## Claude use

Claude app or Claude Code interactive use is loop-based. Give the thread the bus directory and this workflow, then let the agent run the loop while the thread is active. Automatic app wakeup is outside this package.

```text
Use agent-bus for this thread.
You are claude.
Bus directory: <bus_dir>

Start by running check-stop, status, and inbox.
Ack only handled messages, update task-state when a task id exists, and report with agentbus send.
```

Claude CLI, Agent SDK, or Messages API use is runner-based. The runner receives inbox work through `agentbus wakeup`, calls Claude, records the report, completes the task, and acks the handled message. API mode is prompt-only unless the receiving service provides a tool loop.

```bash
PROFILE=$(agentbus examples wakeup/claude-runner-inbox.json)
agentbus wakeup --profile "$PROFILE" --once --dry-run
CLAUDE_RUNNER_MODE=cli CLAUDE_RUNNER_CWD="$PWD" CLAUDE_RUNNER_PERMISSION_MODE=plan agentbus wakeup --profile "$PROFILE" --once
```

## Minimal AGENTS.md snippet

```markdown
## Agent collaboration with agent-bus

You are `<name>`. Coordinate through `agentbus`.

- Set `AGENTBUS_BUS_DIR=<bus_dir>` before bus commands.
- Start with `agentbus check-stop`, then set `status --state running`.
- Read `agentbus inbox --agent <name>` and `ack` only handled messages.
- Use `send --task`, `--reply-to`, and `--ref` for context that a peer must see.
- Use direct `task-new` plus `send --kind request` for work that can proceed without human acceptance.
- Do not create tickets that stop the loop or add routine review fatigue.
- Use `ticket-new` only for proposals or critical work that needs human triage before it becomes a task.
- Use `task-state input_required` plus a `to user` request when user input blocks progress.
- Treat `stop.json` or `check-stop` exit 2 as a cooperative stop.
- Keep durable conclusions in project files, not in the bus.
```
