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
| Use the shared capsule channel | Messages, acks, status, tasks, locks, and stop signals go through `agentbus` CLI/API. |
| Use a stable agent name | Status, inbox targeting, and acks key on `--agent <name>`. |
| Access referenced project files | `--ref <path>` is most useful when the next agent can inspect the file. |
| Return to the loop at work boundaries | Heartbeat is a status update owned by the active thread or runner. |

Use agent-bus as the primary coordination channel when the agent can reach the capsule daemon. For agents without daemon access, use chat handoff or a relay agent.

CLI coordination goes through the capsule daemon. The dashboard is optional and binds to `127.0.0.1`. Do not read, edit, attach, or summarize `.agent-bus/store`; use `agentbus` CLI/API.

## Variables

| Name | Meaning |
| --- | --- |
| `<name>` | This agent name, such as `my-agent` or `reviewer`. |
| `<bus_dir>` | Shared channel directory. Use `AGENTBUS_BUS_DIR` or `--bus-dir`. |
| `<peer>` | Specific peer agent, `all`, or `user`. |

Configuration precedence is CLI flag, then `AGENTBUS_*`, then cwd default.

## User-facing lifecycle entrypoint

When a user asks to "use agent-bus", "start a bus loop", or run `/agent-bus-loop` with only a goal and boundary, the first capable agent acts as the lead until another lead is named. The lead guides the lifecycle from the skill entrypoint.

Ask only for missing facts that change the lifecycle:

- objective and completion criterion
- files, repo area, or scope to leave alone
- sensitivity level and whether restricted access is needed
- participating agents, runners, or bridge profiles
- whether the dashboard should be opened for inspection

If safe defaults are available, state the default and proceed. Use the current project, `AGENTBUS_BUS_DIR`, or `./.agent-bus`; use the current thread's stable agent name; create a direct task and request message for work that can proceed on agent judgment.

Lifecycle order:

1. Clarify the objective, boundary, sensitivity, participants, and completion criterion only as needed.
2. Run or instruct the operator to run `agentbus bus init` and keep `agentbus bus serve` active.
3. Join as the lead agent, then create the first task and request messages.
4. Grant restricted agent/viewer tokens only when the work actually needs raw restricted projections.
5. Let each agent run its loop through status, inbox, work, report, ack, and waiting state.
6. Route user decisions through `input_required` and a `to user` request.
7. Synthesize peer reports into the final judgment and termination report.
8. Mark the task completed, mark the lead done, and send `loop_closed` when the whole bus loop is closed.

The lead owns user alignment and final judgment. Worker reports, bridge outputs, and local skills provide judgment material; the lead decides what is reflected in the final report.

## Join

```bash
export AGENTBUS_BUS_DIR=<bus_dir>
agentbus bus status --stop-exit-code
agentbus agent set --agent <name> --state running --note "joined"
```

The operator or lead should run `agentbus bus init` once and keep `agentbus bus serve` running. If the channel is missing or the daemon is unavailable, report that setup boundary instead of editing `.agent-bus` files.

If `agentbus bus status --stop-exit-code` exits 2, enter the stop boundary. Report the stop and set a terminal or waiting state.

## Loop

Repeat this sequence at every work boundary.

```bash
agentbus bus status --stop-exit-code
agentbus agent set --agent <name> --state running --task <task_id> --note "working"
agentbus agent inbox --agent <name>
agentbus agent ack --agent <name> <message_id>
agentbus task state --id <task_id> --state working --by <name> --note "current slice"
agentbus message send --from <name> --to <peer> --kind report --subject "status" --body "short result"
agentbus agent set --agent <name> --state waiting --task <task_id> --note "waiting for next signal"
```

Acknowledge messages already read and handled. Use `--reply-to <message_id>`, `--task <task_id>`, and `--ref <path>` when they help the next reader.

## Bus-local skills

A bus may carry local skills in `.agent-bus/skills/<skill-id>/SKILL.md`. `agentbus guide workflow` and `agentbus guide loop` append a compact summary when such skills exist, so agents see reusable local knowledge at the normal start point.

Use the full text only when the current task needs it:

```bash
agentbus skill new <skill-id> --description "reusable path"
agentbus skill list
agentbus skill show <skill-id>
```

After a skill-guided slice produces reusable evidence, append it through the CLI instead of editing evidence files by hand:

```bash
agentbus skill evidence <skill-id> --type grounding --ref <message-or-file-ref> --note "what became reusable"
agentbus skill state <skill-id> --state active
agentbus skill review
```

Use `grounding`, `check`, `gap`, and `risk` for observations gathered while doing the real task. Change the skill state at a review boundary to mark the current evidence as handled. Patch `SKILL.md` when the bus work reveals a reusable workflow, corrected path, repeated failure, or verified improvement. Keep active-work patches small; use the loop closure to simplify, combine, retire, keep local, or nominate a skill for runtime installation.

## Sensitive data

Treat `sensitivity` and `retention` as handling signals from the bus.

- `normal`: local and external raw use.
- `internal`: local raw sharing; external paths use a redacted projection.
- `restricted`: content-bearing fields live in the encrypted capsule store, and authorized local agents read raw projections through `AGENTBUS_AGENT_TOKEN`; dashboard viewers authenticate separately in Settings.
- With `agentbus bus serve` running, use `agentbus auth grant --agent <agent>` for agents and `agentbus auth grant --viewer <name>` for dashboard raw viewing.
- `packet send` blocks `restricted` sources. Use a separate approved channel outside agent-bus for external NDA handoff.
- HTTP, A2A, and OpenAI-compatible bridge handlers skip `restricted` events; local agent handlers receive raw work packets only when the target agent token matches.
- Use `--retention no_archive` for NDA data that should stay out of message archives.
- Run `agentbus bus security-check` when a bus may contain NDA or restricted data.

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
agentbus task state --id <task_id> --state input_required --by <name> --note "decision needed"
agentbus message send --from <name> --to user --kind request --task <task_id> --subject "input required" --body "decision, options, risk"
agentbus agent set --agent <name> --state waiting --task <task_id> --note "input_required"
```

If a chat channel with the user exists, report the same decision point there once so user-blocking choices appear both in chat and on the dashboard.

## Stop

Check for stop before starting a chunk and before long-running commands.

```bash
agentbus bus status --stop-exit-code
```

If the user asks to stop in chat, write the stop signal.

```bash
agentbus bus stop --by <name> --reason user_stop --detail "requested in chat"
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

If bus-local skills were used or changed, fold the skill review into the termination report as a short judgment with the skill id, the useful evidence, and the next action. Keep it as prose or a small bullet list; skip empty fields.

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
MSG_ID=$(agentbus message send --from <name> --to user --kind report --subject "종료 보고서: <scope>" --body "$(cat report.md)" --task <task_id>)
agentbus task state --id <task_id> --state completed --by <name> --note "closed with termination report $MSG_ID"
agentbus agent set --agent <name> --state done --task <task_id> --note "closed with termination report $MSG_ID"
```

To close the whole bus loop, run `agentbus bus stop --by <name> --reason loop_closed --detail "termination report $MSG_ID"` after the final report. The dashboard then shows `루프 종료됨` in the top loop-state control, and the final bus `report` remains the last message until a user explicitly reopens the loop.

## Ticket intake

Autonomous work is the default. Use direct tasks and request messages for work that can proceed on agent judgment, and reserve tickets for human-triage decisions.

```bash
TASK_ID=$(agentbus task new --title "short work title" --by <name> --assign <peer>)
agentbus message send --from <name> --to <peer> --kind request --subject "short work title" --body "work request" --task "$TASK_ID"
```

Use a ticket for a new proposal, a critical or risky change, or work that needs human acceptance before execution.

```bash
agentbus ticket new --title "short candidate" --by <name> --body "why it matters" --ref path/to/file
agentbus ticket list
agentbus ticket accept --id <ticket_id> --by user --to <name>
agentbus ticket reject --id <ticket_id> --by user
```

Keep ticket fields minimal: title, body, refs, and assignee target are enough. The human decision is accept or reject. Accepting a ticket creates a task and sends a request message to the selected agent.

## Event bridges and agent runners

Use `agentbus bridge events`, `agentbus bridge watch`, or `agentbus bridge run` when a runtime observes the bus. The event contract is `agentbus.event.v1`.

```bash
agentbus bridge events --types ticket.* --jsonl
agentbus bridge watch --types message.created,ticket.created --position-file .agent-bus/bridge/<name>.position
agentbus bridge run --profile "$(agentbus resource path bridge/<name>.json)" --once
agentbus bridge status
```

`bridge run` uses a `bridge-profile.v1` JSON file. Profiles route predefined bus events through a small matcher and a handler. Handler types are `monitor`, `agent`, `http`, and `openai-compatible`. Agent handlers use fixed runtime entrypoints: `codex exec`, `claude -p`, or `gemini -p`; profile `args` are argv arrays appended to that fixed entrypoint. Restricted payloads stay redacted unless the target local agent presents a valid token. Use `agentbus bridge status` to inspect bridge positions and redacted failure summaries.

For API bridges, use `handler.type=http` or `handler.type=openai-compatible`. For A2A outbound, use `handler.type=http` with `protocol=a2a`. For inbound A2A, use the dashboard/API gateway endpoint exposed by `agentbus bus serve`.

## Codex use

Codex app use is interactive. Give the thread the channel directory and this workflow, then let the agent run the loop while the thread is active. Automatic app launch is outside this package.

```text
Use agent-bus for this thread.
You are codex.
Bus directory: <bus_dir>

Start with `agentbus bus status --stop-exit-code`, then set `agentbus agent set --state running` and read `agentbus agent inbox`.
Ack handled messages, update task state when a task id exists, and report with `agentbus message send`.
```

Codex CLI use is runner-based. The runner receives work through `agentbus bridge run`, calls `codex exec`, records the report, completes the task, and acks the handled message. Put Codex options in the profile `handler.args`.

```bash
PROFILE=$(agentbus resource path bridge/codex-runner-inbox.json)
agentbus bridge run --profile "$PROFILE" --once --dry-run
agentbus bridge run --profile "$PROFILE" --once
```

## Claude use

Claude app or Claude Code interactive use is loop-based. Give the thread the channel directory and this workflow, then let the agent run the loop while the thread is active. Automatic app launch is outside this package.

```text
Use agent-bus for this thread.
You are claude.
Bus directory: <bus_dir>

Start with `agentbus bus status --stop-exit-code`, then set `agentbus agent set --state running` and read `agentbus agent inbox`.
Ack handled messages, update task state when a task id exists, and report with `agentbus message send`.
```

Claude CLI use is runner-based. The runner receives work through `agentbus bridge run`, calls `claude -p`, records the report, completes the task, and acks the handled message. Put Claude options in the profile `handler.args`.

```bash
PROFILE=$(agentbus resource path bridge/claude-runner-inbox.json)
agentbus bridge run --profile "$PROFILE" --once --dry-run
agentbus bridge run --profile "$PROFILE" --once
```

## Gemini use

Gemini CLI use is runner-based. The runner receives work through `agentbus bridge run`, calls `gemini -p`, records the report, completes the task, and acks the handled message. Put Gemini options in the profile `handler.args`.

```bash
PROFILE=$(agentbus resource path bridge/gemini-runner-inbox.json)
agentbus bridge run --profile "$PROFILE" --once --dry-run
agentbus bridge run --profile "$PROFILE" --once
```

## Minimal AGENTS.md snippet

```markdown
## Agent collaboration with agent-bus

You are `<name>`. Coordinate through `agentbus`.

- Set `AGENTBUS_BUS_DIR=<bus_dir>` before bus commands and use the CLI/API instead of reading `.agent-bus/store` directly.
- Start with `agentbus bus status --stop-exit-code`, then set `agentbus agent set --state running`.
- Read `agentbus agent inbox --agent <name>` and ack handled messages with `agentbus agent ack`.
- Use `agentbus message send --task`, `--reply-to`, and `--ref` for context that a peer needs.
- Use direct `agentbus task new` plus `agentbus message send --kind request` for work that can proceed on agent judgment.
- Reserve tickets for human-triage decisions so routine work keeps moving.
- Use `agentbus ticket new` for proposals or critical work that needs human triage before it becomes a task.
- Use `agentbus task state --state input_required` plus a `to user` request when user input blocks progress.
- Treat `agentbus bus status --stop-exit-code` exit 2 as a cooperative stop.
- Keep durable conclusions in project files, with bus records as provenance and coordination context.
- Close a completed loop with a structured `# 종료 보고서` report, then mark the task completed and the agent done.
```
