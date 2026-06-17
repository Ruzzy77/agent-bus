---
name: agent-bus-workflow
description: >-
  Use this skill when Codex or another agent collaborates with peers
  through agent-bus: joining a bus, running the heartbeat and inbox loop, using
  task states, reporting input_required, handling stop.json, or writing a
  prompt/AGENTS.md section for agent-bus collaboration, including minimum
  agent requirements.
---

# agent-bus workflow

Start the loop in the active agent thread. Use `agentbus` as volatile coordination state, and put durable decisions and outputs in project files.

## Minimum requirements

Use this workflow with agents that meet these requirements.

| Requirement | Reason |
| --- | --- |
| Run shell commands | The loop uses the `agentbus` CLI. |
| Read and write the shared bus directory | Messages, acks, status, tasks, locks, and stop signals are files. |
| Use a stable agent name | Status, inbox targeting, and acks key on `--agent <name>`. |
| Access referenced project files | `--ref <path>` is most useful when the next agent can inspect the file. |
| Return to the loop at work boundaries | Heartbeat is a status update owned by the active thread or runner. |

Use agent-bus as the primary coordination channel when the agent can write the bus directory. For agents with read-only access, use chat handoff or a relay agent.

CLI coordination works through local files. The dashboard is optional and binds to `127.0.0.1`.

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

If `check-stop` exits 2, enter the stop boundary. Report the stop and set a terminal or waiting state.

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

Acknowledge messages already read and handled. Use `--reply-to <message_id>`, `--task <task_id>`, and `--ref <path>` when they help the next reader.

## Sensitive data

Treat `sensitivity` and `retention` as handling signals from the bus.

- Read `sensitivity` before using web tools, remote SDKs, A2A endpoints, or external adapters.
- Send `confidential` or `restricted` data outside the local bus with explicit task or user permission for that handoff.
- Use `--allow-sensitive` for that explicit handoff.
- Use `--retention no_archive` for NDA data that should stay out of message archives.
- Run `agentbus security-check` when a bus may contain NDA or restricted data.
- Sensitive-blocked `watch-events` and `wakeup` output is a redacted notice; explicit sensitive handling releases the payload to the selected command/output.

## Tasks and states

Use task state for the work item.

| State | Use |
| --- | --- |
| `submitted` | Work is registered and ready for assignment or pickup. |
| `working` | An agent is actively changing or checking it. |
| `input_required` | User decision or missing external input blocks progress. |
| `completed` | Requested work is done. |
| `failed` | Current constraints prevent completion. |
| `canceled` | Work was intentionally stopped. |

Use agent status for the agent process.

| State | Use |
| --- | --- |
| `running` | The agent is active. This is also the heartbeat. |
| `waiting` | The agent is idle or waiting on an external signal. |
| `done` | The agent has closed its assigned work. |
| `error` | The agent hit an unresolved fault. |

## Input required

When progress needs the user, record it in both channels available to the current run.

```bash
agentbus task-state --id <task_id> --state input_required --by <name> --note "decision needed"
agentbus send --from <name> --to user --kind request --task <task_id> --subject "input required" --body "decision, options, risk"
agentbus status --agent <name> --state waiting --task <task_id> --note "input_required"
```

If a chat channel with the user exists, report the same decision point there once so user-blocking choices appear both in chat and on the dashboard.

## Stop

Check for stop before starting a chunk and before long-running commands.

```bash
agentbus check-stop
```

If the user asks to stop in chat, write the stop signal.

```bash
agentbus stop --by <name> --reason user_stop --detail "requested in chat"
```

After a stop, finish the safe boundary already in progress. Send a short report with changed files, unfinished work, and risk, then wait.

## Reports

Send reports that change coordination. Keep heartbeat chatter in status updates.

Use this shape for final reports or reports that change a blocking decision:

```text
Judgment: current decision.
Output: concrete change or artifact.
Risk: remaining uncertainty.
Next: smallest useful next action.
```

Use `kind=request` for a decision needed from a peer or user. Use `kind=report` for completed work or a changed risk.

## Termination report

When a loop is complete, the lead agent should synthesize peer reports, evidence refs, disagreements, verification, and remaining decisions into a polished termination report as the final bus `report` message, then close task/status records. The report should support user alignment and follow-up interaction, and let a later reader trace decisions, outputs, expected behavior, verification, and remaining boundaries from the dashboard or bus records.

Required sections:

```markdown
# 종료 보고서

## 종료 판정
- 상태:
- 종료 사유:
- 최종 책임 에이전트:

## 작업 범위
- 포함:
- 제외:

## 의사결정 기록
| 판단 출처 | 검토 내용 | 반영 판단 | 반영 산출물 |
| --- | --- | --- | --- |
|  |  |  |  |

## 산출물
| 산출물 | 경로 또는 식별자 | 기대 동작 |
| --- | --- | --- |
|  |  |  |

## 검증
| 검증 | 결과 | 근거 |
| --- | --- | --- |
|  |  |  |

## 미반영 항목과 남은 위험
-

## 운영 상태
- 최종 report message:
- task state:
- agent status:
- stop signal:
```

Closure order:

```bash
MSG_ID=$(agentbus send --from <name> --to user --kind report --subject "종료 보고서: <scope>" --body "$(cat report.md)" --task <task_id>)
agentbus task-state --id <task_id> --state completed --by <name> --note "closed with termination report $MSG_ID"
agentbus status --agent <name> --state done --task <task_id> --note "closed with termination report $MSG_ID"
```

To close the whole bus loop, run `agentbus stop --by <name> --reason loop_closed --detail "termination report $MSG_ID"` after the final report. The dashboard then shows `루프 종료됨` in the top loop-state control, and the final bus `report` remains the last message until a user explicitly reopens the loop.

## Ticket intake

Autonomous work is the default. Use direct tasks and request messages for work that can proceed on agent judgment, and reserve tickets for human-triage decisions.

```bash
TASK_ID=$(agentbus task-new --title "short work title" --by <name> --assign <peer>)
agentbus send --from <name> --to <peer> --kind request --subject "short work title" --body "work request" --task "$TASK_ID"
```

Use a ticket for a new proposal, a critical or risky change, or work that needs human acceptance before execution.

```bash
agentbus ticket-new --title "short candidate" --by <name> --body "why it matters" --ref path/to/file
agentbus ticket-list
agentbus ticket-accept --id <ticket_id> --by user --to <name>
agentbus ticket-reject --id <ticket_id> --by user
```

Keep ticket fields minimal: title, body, refs, and assignee target are enough. The human decision is accept or reject. Accepting a ticket creates a task and sends a request message to the selected agent.

## Event bridges and agent runners

Use `agentbus events`, `agentbus watch-events`, or `agentbus wakeup` when a user-run runtime observes the bus. The event contract is `agentbus.event.v1`.

```bash
agentbus events --types ticket.* --jsonl
agentbus watch-events --types message.created,ticket.created --cursor-file .agent-bus/adapters/<name>.cursor --exec ./wake-agent.sh
agentbus wakeup --profile "$(agentbus examples wakeup/<name>.json)" --once
agentbus adapter-status
```

`wakeup` reads a `wakeup-profile.v1` JSON file. Use `mode=inbox` for ack-based agent self-wake and `mode=events` for event bridges. The core bus records coordination state, while platform wakeups, webhooks, A2A, AAS (Asset Administration Shell), and SDK bridges are user-run helpers that consume events or pending inbox data, keep a cursor when needed, and then reread the bus before acting. Sensitive payloads require explicit profile permission. Use `agentbus adapter-status` to inspect event bridge cursor and redacted failure summaries.

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
Ack handled messages, update task-state when a task id exists, and report with agentbus send.
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
Ack handled messages, update task-state when a task id exists, and report with agentbus send.
```

Claude CLI, Agent SDK, or Messages API use is runner-based. The runner receives inbox work through `agentbus wakeup`, calls Claude, records the report, completes the task, and acks the handled message. API mode is prompt-only; file or shell tools come from the receiving service when provided.

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
- Read `agentbus inbox --agent <name>` and `ack` handled messages.
- Use `send --task`, `--reply-to`, and `--ref` for context that a peer needs.
- Use direct `task-new` plus `send --kind request` for work that can proceed on agent judgment.
- Reserve tickets for human-triage decisions so routine work keeps moving.
- Use `ticket-new` for proposals or critical work that needs human triage before it becomes a task.
- Use `task-state input_required` plus a `to user` request when user input blocks progress.
- Treat `stop.json` or `check-stop` exit 2 as a cooperative stop.
- Keep durable conclusions in project files, with bus records as provenance and coordination context.
- Close a completed loop with a structured `# 종료 보고서` report, then mark the task completed and the agent done.
```
