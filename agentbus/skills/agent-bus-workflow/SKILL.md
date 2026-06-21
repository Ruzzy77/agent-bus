---
name: agent-bus-workflow
description: >-
  Use this skill when Codex or another agent collaborates with teammates
  through agent-bus: joining a bus, running the heartbeat and inbox loop, using
  task states, reporting input_required, handling stop signals, or writing a
  prompt/AGENTS.md section for agent-bus collaboration, including minimum
  agent requirements.
---

# agent-bus workflow

Start the loop in the active agent thread. Use `agentbus` for coordination records and provenance, and put durable project outputs in project files.

## Minimum requirements

Use this workflow with agents that meet these requirements.

| Requirement | Reason |
| --- | --- |
| Run shell commands | The loop uses the `agentbus` CLI. |
| Use the shared capsule channel | Messages, acks, status, tasks, and stop signals go through `agentbus` CLI/API. |
| Use a stable agent identity | Create an agent id from a display name, then use `--id` or unique `--name` for status, inbox, and acks. |
| Access referenced project files | `--ref <path>` is most useful when the next agent can inspect the file. |
| Return to the loop at work boundaries | Heartbeat is a status update owned by the active thread or runner. |

Use agent-bus as the primary coordination channel when the agent can reach the capsule daemon. For agents without daemon access, use chat handoff or a relay agent.

Ordinary message, task, ticket, and auth commands go through the capsule daemon. Teammate and bridge runners are operator-started local loops that use the same CLI contract. The dashboard is optional and binds to `127.0.0.1`. Do not read, edit, attach, or summarize `.agent-bus/store`; use `agentbus` CLI/API.

## Variables

| Name | Meaning |
| --- | --- |
| `<name>` | Display name, such as `my-agent` or `reviewer`. The bus stores a generated `a-...` id. |
| `<bus_dir>` | Shared channel directory. Use `AGENTBUS_BUS_DIR` or `--bus-dir`. |
| `<teammate>` | Specific teammate agent, `all`, or `user`. |

Configuration precedence is CLI flag, then `AGENTBUS_*`, then cwd default.

## User-facing lifecycle entrypoint

When a user asks to "use agent-bus", "start a bus loop", or run `/agent-bus-loop` with only a goal and boundary, the first capable agent acts as the lead until another lead is named. The lead guides the lifecycle from the skill entrypoint.

Ask only for missing facts that change the lifecycle:

- objective and completion criterion
- files, repo area, or scope to leave alone
- sensitivity level and whether restricted access is needed
- participating teammates, runners, or bridge profiles
- whether the dashboard should be opened for inspection

If safe defaults are available, state the default and proceed. Use the current project, `AGENTBUS_BUS_DIR`, or `./.agent-bus`; use the current thread's agent display name; create a direct task and request message for work that can proceed on agent judgment.

Lifecycle order:

1. Clarify the objective, boundary, sensitivity, participants, and completion criterion only as needed.
2. Run or instruct the operator to run `agentbus bus init` and keep `agentbus bus serve` active.
3. Join as the lead agent, then create the first task and request messages.
4. Grant restricted agent/viewer tokens only when the work actually needs raw restricted projections.
5. Keep Key Context current before teammate cycles.
6. Let each teammate run its loop through status, inbox, work, report, and waiting state; managed teammate runners auto-ack the trigger after a successful cycle with bus records.
7. Route user decisions through `input_required` and a `to user` request.
8. Run a final lead inbox sweep and handle or defer closure-changing messages.
9. Synthesize teammate reports into the final judgment and termination report.
10. Mark the task completed, mark the lead done, and send `loop_closed` when the whole bus loop is closed.

The lead owns user alignment and final judgment. Teammate reports, bridge outputs, and local skills provide judgment material; the lead decides what is reflected in the final report.

## Key Context

Key Context is the live work meaning that the user and lead tune together. It steers the next lead and teammate cycles.

- Keep actual work meaning, judgment background, and current interpretive center.
- Leave task lists, agent state, message summaries, and general runner rules in their existing records.
- Put sensitive raw content in `restricted` messages, tasks, tickets, or file refs; keep Key Context focused on viewpoint and judgment background.
- Update it when teammate reports change the center of judgment or the user corrects the work meaning.
- Use `agentbus context show` and `agentbus context set --stdin` when the dashboard is not the active editing place.
- `teammate run` receives Key Context in the cycle input and prompt inside `<agent-bus-system>`.

## Lead strategic approach

The lead turns the user's goal into a strategic work plan before distributing requests. Treat the user request as the completion criterion. Recover the objective, boundary, owned scope, outside state, expected result, and verification path before changing project state.

For broad, ambiguous, multi-teammate, or user-alignment-sensitive work, apply the `lead-strategic-approach` skill before writing teammate requests. It keeps the lead focused on the expected picture, user alignment, Key Context, causal review, and strategy changes when evidence differs from the plan.

Plan by work meaning, judgment character, and dependency; file boundaries are secondary. First map the target, then split the work into slices that can be judged with one clean standard. Common lenses include product behavior, architecture, interaction design, writing, research, security, operations, and release readiness. Use only the lenses that fit the work, and add a more specific lens when it keeps context from mixing.

For each slice, name:

- owned scope: artifacts, claims, decisions, or user-facing behavior the slice may change
- expected result: what should behave, read, or decide differently after the slice
- causal links: adjacent state, controls, wording, data paths, or teammate work that may shift because of the change
- evidence path: the smallest direct check that would confirm the result and reveal likely side effects
- handoff shape: what the teammate should report so the lead can synthesize without re-running the whole slice

Execute in bounded chunks. After each change, re-check the neighboring state that the change may have shifted, then fold the result back into the plan. When teammate findings conflict or drift from the user's intent, the lead reads the relevant artifact directly, updates Key Context if the work meaning changed, and narrows the next request. Before closure, the lead compares the final outputs against the original completion criterion and records remaining risk or follow-up work.

## Lead request design

Write teammate requests as a work-loop contract. Put the shared work meaning in Key Context, then use the request for the teammate's owned slice.

Include these parts when they matter:

- Owned scope: files, commands, artifacts, or claims the teammate should inspect directly.
- Cycle expectation: inspect, act, report, then either leave a bounded follow-up request, wait, mark `input_required`, or complete the task.
- Report contract: concise judgment, evidence or refs, risk or gap, and next intent.
- Continuation path: if useful work remains, send a bounded follow-up request to self or ask the lead for the next narrowed slice; if user judgment is needed, use `input_required` plus a `to user` or `to lead` request.

For continuity work, ask teammates to preserve their task context through bus records, refine their own next step, and publish the smallest useful judgment after each cycle. The lead periodically reads those judgments, updates Key Context, and sends narrower follow-up requests when the group is drifting or converging.

## Join

```bash
export AGENTBUS_BUS_DIR=<bus_dir>
agentbus bus status --stop-exit-code
agentbus agent set --name <name> --state running --note "joined"
```

The operator or lead should run `agentbus bus init` once and keep `agentbus bus serve` running for dashboard/API access. If the channel is missing or ordinary CLI commands cannot reach the daemon, report that setup boundary instead of editing `.agent-bus` files.

If `agentbus bus status --stop-exit-code` exits 2, enter the stop boundary. Report the stop and set a terminal or waiting state.

## Loop

Repeat this sequence at every work boundary.

```bash
agentbus bus status --stop-exit-code
agentbus agent set --name <name> --state running --task <task_id> --note "working"
agentbus agent inbox --name <name>
agentbus task state --id <task_id> --state working --by <name> --note "current slice"
agentbus message send --from <name> --to <teammate> --kind report --subject "status" --body "short result"
agentbus agent ack --name <name> <message_id>
agentbus agent set --name <name> --state waiting --task <task_id> --note "waiting for next signal"
```

Acknowledge messages after the task state, report, or request that proves the message was handled. Use `--reply-to <message_id>`, `--task <task_id>`, and `--ref <path>` when they help the next reader.

## Local skills

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

Use `grounding`, `check`, `gap`, and `risk` for observations gathered while doing the real task. Change the skill state at a review boundary to mark the current evidence as handled. Patch `SKILL.md` when the bus work reveals a reusable workflow, corrected path, repeated failure, or verified improvement. Keep active-work patches small; use the loop closure to simplify, combine, retire, keep local, or nominate a skill for agent installation.

## Sensitive data

Treat `sensitivity` as the bus handling signal for sensitive content.

- `normal`: local and external raw use.
- `internal`: local raw sharing; external paths use a redacted projection.
- `restricted`: content-bearing fields live in the encrypted capsule store, and authorized local agents read raw projections through `AGENTBUS_AGENT_TOKEN`; dashboard viewers authenticate separately in Settings.
- Dashboard compose sets `sensitivity`; CLI task and ticket commands use the same flag when lead or agent operations create records directly.
- With `agentbus bus serve` running, use `agentbus auth grant --agent-name <agent>` for agents and `agentbus auth grant --viewer <name>` for dashboard raw viewing.
- `packet send` blocks `restricted` sources. Use a separate approved channel outside agent-bus for external NDA handoff.
- HTTP handlers, including A2A profiles, and OpenAI-compatible bridge handlers skip `restricted` events; local CLI teammates receive raw cycle input only when the target agent token matches.
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
agentbus agent set --name <name> --state waiting --task <task_id> --note "input_required"
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

Use `kind=request` for a decision needed from a teammate or user. Use `kind=report` for completed work or a changed risk.

## Termination report

When a loop is complete, the lead agent first runs one final inbox sweep for messages addressed to the lead, `all`, or `*`, including user-authored requests routed to the lead. Handle and ack anything that changes the closure decision. If a new request belongs after the current loop, record it as a follow-up task or ticket before closing.

After that sweep, synthesize teammate reports, evidence refs, disagreements, verification, and remaining decisions into a polished termination report as the final bus `report` message, then close task/status records. The report should support user alignment and follow-up interaction, and let a later reader trace decisions, outputs, expected behavior, verification, and remaining boundaries from the dashboard or bus records.

If local skills were used or changed, fold the skill review into the termination report as a short judgment with the skill id, the useful evidence, and the next action. Keep it as prose or a small bullet list; skip empty fields.

When the user asks the lead to clean up or close the loop, treat it as closure work:

- Sweep the lead inbox and handle, ack, or defer closure-changing messages.
- Turn remaining work into follow-up tasks or tickets before the final report.
- Fold teammate reports, skill review, verification, and remaining risk into the termination report.
- Mark the current task completed and the lead done.
- Send `bus stop --reason loop_closed` when the whole loop is closed so teammate runners stop at their next boundary.
- Run archive/clear session cleanup only after an explicit user request.

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
agentbus agent inbox --name <name>
# handle or defer any closure-changing messages here
MSG_ID=$(agentbus message send --from <name> --to user --kind report --subject "종료 보고서: <scope>" --body "$(cat report.md)" --task <task_id>)
agentbus task state --id <task_id> --state completed --by <name> --note "closed with termination report $MSG_ID"
agentbus agent set --name <name> --state done --task <task_id> --note "closed with termination report $MSG_ID"
```

To close the whole bus loop, run `agentbus bus stop --by <name> --reason loop_closed --detail "termination report $MSG_ID"` after the final report. The dashboard then shows `루프 종료됨` in the top loop-state control, and the final bus `report` remains the last message until a user explicitly reopens the loop.

## Ticket intake

Autonomous work is the default. User-originated `작업`, `티켓`, and `정지` entries in the dashboard compose are lead-management requests; the lead interprets them and creates task, ticket, or stop records when that is the right bus action. For agent-to-agent work, use direct tasks and request messages when work can proceed on agent judgment, and reserve tickets for human-triage decisions.

```bash
TASK_ID=$(agentbus task new --title "short work title" --by <name> --assign <teammate>)
agentbus message send --from <name> --to <teammate> --kind request --subject "short work title" --body "work request" --task "$TASK_ID"
```

Use a ticket for a new proposal, a critical or risky change, or work that needs human acceptance before execution.

For parallel work, create one task per work package and send one request to each assigned agent. Keep the lead synthesis in a separate lead task so teammate reports stay traceable to their own task ids. Shape each request as a work-loop contract when the teammate should keep refining its slice across cycles, and keep the shared work meaning in Key Context.

```bash
agentbus ticket new --title "short candidate" --by <name> --body "why it matters" --ref path/to/file
agentbus ticket list
agentbus ticket accept --id <ticket_id> --by user --to <name>
agentbus ticket reject --id <ticket_id> --by user
```

Keep ticket fields minimal: title, body, refs, and assignee target are enough. The human decision is accept or reject. Accepting a ticket creates a task and sends a request message to the selected agent.

## Local teammates and event bridges

Use `agentbus teammate run` as the opt-in local teammate loop for Codex, Claude, or Gemini. Keep provider CLI calls inside the runner so each cycle receives the bus cycle input, Key Context, and delivery tracking. Use `agentbus bridge events`, `agentbus bridge watch`, or `agentbus bridge run` when an external process or API observes the bus. The event contract is `agentbus.event.v1`.

```bash
cp "$(agentbus resource path bridge/codex-runner-inbox.json)" .agent-bus/bridge/codex-runner-inbox.json
agentbus teammate run --profile codex-runner-inbox --once --dry-run
agentbus teammate run --profile codex-runner-inbox
agentbus bridge events --types ticket.* --jsonl
agentbus bridge watch --types message.created,ticket.created --position-file .agent-bus/bridge/<name>.position
agentbus bridge run --profile "$(agentbus resource path bridge/<name>.json)"
agentbus bridge status
```

`teammate run` runs a bus-local profile from `.agent-bus/bridge`. The profile owns the target agent, provider, provider args, event filter, polling interval, and timeout policy. The runner polls for matching requests and invokes the provider only when a cycle is needed. It owns polling, delivery position, and the ack for the request that triggered a successful cycle; the invoked agent owns inbox inspection, task state, report/request messages, and final waiting or done status. Key Context is included in the cycle input and separated from normal message text in `<agent-bus-system>`. When the teammate needs another cycle, it leaves a bounded follow-up request to itself or asks the lead for a narrowed next slice. Individual task completion leaves the runner waiting; a bus stop signal closes the runner and marks the teammate done. `timeoutSeconds` marks a long-running provider cycle and keeps waiting for it; provider exit failures or cycles that leave no bus records become runner errors. Stdout remains an operator log. Restricted payloads stay redacted unless the target local agent presents a valid token.

`bridge run` uses a `bridge-profile.v1` JSON file. Use `handler.type=monitor`, `handler.type=http`, or `handler.type=openai-compatible` for event monitors, webhooks, A2A outbound, and model API calls. For A2A outbound, use `handler.type=http` with `protocol=a2a`. For inbound A2A, use the dashboard/API gateway endpoint exposed by `agentbus bus serve`.

## Codex use

Codex app use is interactive. Give the thread the channel directory and this workflow, then let the agent run the loop while the thread is active. Automatic app launch is outside this package.

```text
Use agent-bus for this thread.
You are codex.
Bus directory: <bus_dir>

Start with `agentbus bus status --stop-exit-code`, then set `agentbus agent set --name <agent> --state running` and read `agentbus agent inbox --name <agent>`.
Ack handled messages, update task state when a task id exists, and report with `agentbus message send`.
```

Codex CLI use is teammate runner-based. Keep `agentbus teammate run --profile <profile>` as the normal entrypoint. The bus-local profile chooses the Codex target agent and stores Codex options in `handler.args`; the runner watches bus requests, calls `codex exec` internally, and the invoked Codex cycle records the report, task state, and status through agent-bus.

```bash
cp "$(agentbus resource path bridge/codex-runner-inbox.json)" .agent-bus/bridge/codex-runner-inbox.json
agentbus teammate run --profile codex-runner-inbox --once --dry-run
agentbus teammate run --profile codex-runner-inbox
```

## Claude use

Claude app or Claude Code interactive use is loop-based. Give the thread the channel directory and this workflow, then let the agent run the loop while the thread is active. Automatic app launch is outside this package.

```text
Use agent-bus for this thread.
You are claude.
Bus directory: <bus_dir>

Start with `agentbus bus status --stop-exit-code`, then set `agentbus agent set --name <agent> --state running` and read `agentbus agent inbox --name <agent>`.
Ack handled messages, update task state when a task id exists, and report with `agentbus message send`.
```

Claude CLI use is teammate runner-based. Keep `agentbus teammate run --profile <profile>` as the normal entrypoint. The bus-local profile chooses the Claude target agent and stores Claude options in `handler.args`; the runner watches bus requests, calls `claude -p` internally, and the invoked Claude cycle records the report, task state, and status through agent-bus.

```bash
cp "$(agentbus resource path bridge/claude-runner-inbox.json)" .agent-bus/bridge/claude-runner-inbox.json
agentbus teammate run --profile claude-runner-inbox --once --dry-run
agentbus teammate run --profile claude-runner-inbox
```

## Gemini use

Gemini CLI use is teammate runner-based. Keep `agentbus teammate run --profile <profile>` as the normal entrypoint. The bus-local profile chooses the Gemini target agent and stores Gemini options in `handler.args`; the runner watches bus requests, calls `gemini -p` internally, and the invoked Gemini cycle records the report, task state, and status through agent-bus.

```bash
cp "$(agentbus resource path bridge/gemini-runner-inbox.json)" .agent-bus/bridge/gemini-runner-inbox.json
agentbus teammate run --profile gemini-runner-inbox --once --dry-run
agentbus teammate run --profile gemini-runner-inbox
```

## Minimal AGENTS.md snippet

```markdown
## Agent collaboration with agent-bus

You are `<name>`. Coordinate through `agentbus`.

- Set `AGENTBUS_BUS_DIR=<bus_dir>` before bus commands and use the CLI/API instead of reading `.agent-bus/store` directly.
- Start with `agentbus bus status --stop-exit-code`, then set `agentbus agent set --name <name> --state running`.
- Read or update Key Context before writing teammate work-loop requests when the shared work meaning changed.
- When leading, apply `lead-strategic-approach` for broad or alignment-sensitive work; split by work meaning, judgment character, and dependency, then name owned scope, expected result, causal links, and the evidence path before assigning teammates.
- Read `agentbus agent inbox --name <name>` and ack handled messages with `agentbus agent ack --name <name>` when working outside `teammate run`.
- Use `agentbus message send --task`, `--reply-to`, and `--ref` for context that a teammate needs.
- Treat dashboard `작업`, `티켓`, and `정지` messages from the user as requests to the lead; materialize them into task, ticket, or stop records only after interpreting the current work context.
- Use direct `agentbus task new` plus `agentbus message send --kind request` for agent-to-agent work that can proceed on agent judgment.
- Reserve tickets for human-triage decisions so routine work keeps moving.
- Use `agentbus ticket new` for proposals or critical work that needs human triage before it becomes a task.
- Use `agentbus task state --state input_required` plus a `to user` request when user input blocks progress.
- Treat `agentbus bus status --stop-exit-code` exit 2 as a cooperative stop.
- Keep durable conclusions in project files, with bus records as provenance and coordination context.
- Before closure, run a final inbox sweep; then close with a structured `# 종료 보고서` report, mark the task completed, and mark the agent done.
```
