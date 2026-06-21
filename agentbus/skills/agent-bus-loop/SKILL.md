---
name: agent-bus-loop
description: >-
  Use this skill when a user asks an agent to start, continue, pause, or stop an
  agent-bus loop in any platform, including slash-style requests such as /agent-bus-loop.
  It provides a platform-neutral entrypoint that tells the agent how to join the
  bus, check stop signals, read inbox, report work, wait, and close cleanly.
---

# agent-bus loop

Start or resume the loop in the current agent thread. Treat agent-bus as the shared coordination record used by the agent, with process ownership kept by the surrounding runner.

Use this skill as the entrypoint. For detailed inbox, ack, task state, ticket, stop, input_required, event bridge, runner, and security rules, consult `agentbus guide workflow` or the `agent-bus-workflow` skill while running the loop.

## Inputs

Find these values from the prompt, environment, project notes, or current shell.

| Value | Meaning |
| --- | --- |
| `<agent>` | Display name; agent-bus stores a generated `a-...` id behind it |
| `<bus_dir>` | Shared channel directory, usually `./.agent-bus` or `AGENTBUS_BUS_DIR` |
| `<task_id>` | Optional task id from an inbox message or user instruction |

If `<bus_dir>` is unclear, use `AGENTBUS_BUS_DIR` when set, otherwise initialize `./.agent-bus` in the current project and keep `agentbus bus serve` running.

## First-turn behavior

When the user asks for a full bus workflow rather than a single inbox pass, act as the lead entrypoint until another lead is assigned. Start from the goal the user provided and clarify only the facts that change the loop:

- goal and completion criterion
- scope to keep out of the work
- sensitivity or restricted-data handling
- teammates, runners, or bridge profiles to involve
- whether the dashboard should be used

If those facts are already clear, proceed with reasonable defaults: current project, `AGENTBUS_BUS_DIR` or `./.agent-bus`, current agent display name, a direct task plus request message, and the standard closure report. Tell the user the chosen defaults briefly, then start or join the bus.

## Key Context

Key Context is the current work meaning that the user and lead tune together. Keep it focused on the actual judgment background that should steer the next agent cycle.

- Use `agentbus context show` before writing work-loop requests when the shared work meaning may have changed.
- Use `agentbus context set --stdin` when user corrections or teammate reports change the interpretive center.
- Leave task lists, agent status, message summaries, and general runner rules in their existing records.
- Put sensitive raw content in `restricted` messages, tasks, tickets, or file refs; keep Key Context focused on viewpoint and judgment background.
- `teammate run` receives Key Context inside `<agent-bus-system>`, separated from normal message text.

## Start

```bash
export AGENTBUS_BUS_DIR=<bus_dir>
agentbus bus status --stop-exit-code
agentbus agent set --name <agent> --state running --note "joined"
agentbus agent inbox --name <agent>
```

The operator or lead should run `agentbus bus init` once and keep `agentbus bus serve` running for dashboard/API access. If ordinary CLI commands cannot reach the capsule daemon, report the setup boundary instead of reading or editing `.agent-bus/store`.

If `agentbus bus status --stop-exit-code` exits 2, enter the stop boundary. Report the stop request and set `agentbus agent set --name <agent> --state waiting` or `done` according to the platform context.

## Loop

At each work boundary:

1. Run `agentbus bus status --stop-exit-code`
2. Update `agentbus agent set --name <agent> --state running` while working
3. Read `agentbus agent inbox --name <agent>`
4. Handle messages addressed to `<agent>`, `all`, or `*`
5. Use `task state` when a task id exists
6. Send reports with `message send --from <agent> --to <teammate> --kind report`
7. Ack messages already handled
8. Set `agentbus agent set --name <agent> --state waiting` before yielding control

```bash
agentbus agent set --name <agent> --state running --task <task_id> --note "working"
agentbus task state --id <task_id> --state working --by <agent> --note "current slice"
agentbus message send --from <agent> --to user --kind report --subject "result" --body "short result" --task <task_id>
agentbus agent ack --name <agent> <message_id>
agentbus agent set --name <agent> --state waiting --task <task_id> --note "waiting"
```

## Lead strategic planning

When acting as lead, plan the work before sending requests. For broad or alignment-sensitive work, use the `lead-strategic-approach` skill to form the expected picture, align with the user's stake, and keep Key Context steady. Split by work meaning, judgment character, and dependency so each slice has one clear standard. For each slice, name the owned scope, expected result, causal links to nearby state, and the evidence path. After a change, check the nearby state affected by that change, then fold the result back into the next request or closure judgment.

Use Key Context for the shared interpretation of the work, then use tasks and requests for the current slice. If teammate reports change the meaning of the work or reveal drift from the user's intent, update Key Context before the next cycle.

## Work intake

Autonomous work is the default. User-originated `작업`, `티켓`, and `정지` entries in the dashboard compose are lead-management requests; the lead interprets them and creates task, ticket, or stop records when that is the right bus action. For agent-to-agent work, use direct tasks and request messages when work can proceed on agent judgment, and reserve tickets for human-triage decisions.

```bash
TASK_ID=$(agentbus task new --title "short work title" --by <agent> --assign <teammate>)
agentbus message send --from <agent> --to <teammate> --kind request --subject "short work title" --body "work request" --task "$TASK_ID"
```

Use a ticket for a new proposal, a critical or risky change, or work that needs human review before execution. While a ticket waits for triage, continue safe active tasks.

For parallel work, create one task per work package and send one request to each assigned agent. Keep the lead synthesis in a separate lead task so teammate reports stay traceable to their own task ids. Keep shared work meaning in Key Context, and write each teammate request as a work-loop contract: owned scope, expected report shape, and the condition for a follow-up cycle, waiting, input_required, or completed.

## Local skills

When `.agent-bus/skills/<skill-id>/SKILL.md` exists, `agentbus guide loop` appends a compact local skill summary. Treat those files as project-local working aids. Open the full text with `agentbus skill show <skill-id>` only when it is relevant to the current slice. Create a local draft with `agentbus skill new <skill-id> --description "..."` when the reusable path is already clear enough to name.

After a skill-guided work slice reveals reusable evidence, add one compact record:

```bash
agentbus skill evidence <skill-id> --type check --ref <message-or-file-ref> --note "reusable observation"
```

Patch a local `SKILL.md` when real work reveals a reusable workflow, a corrected path, a repeated failure, or a verified improvement. Prefer small edits while work is active. At loop closure, run `agentbus skill review`, then keep, simplify, combine, retire, or mark a skill as an install candidate through the closure judgment.

## Stop or pause

A stop request puts the loop at a closure boundary. Finish the smallest safe cleanup, then report and wait.

```bash
agentbus bus status --stop-exit-code
agentbus agent set --name <agent> --state waiting --note "stopped by request"
```

Use `input_required` when progress needs a user decision rather than more agent work.

```bash
agentbus task state --id <task_id> --state input_required --by <agent> --note "decision needed"
```

## Loop closure report

When closing a completed loop, the lead agent first runs one final inbox sweep for messages addressed to the lead, `all`, or `*`, including user-authored requests routed to the lead. Handle and ack anything that changes the closure decision. If a new request should be deferred, record it as a follow-up task or ticket before closing.

After that sweep, synthesize teammate reports, evidence refs, disagreements, verification, and remaining decisions into a polished termination report as the last bus `report` message, then close task/status records. Keep it suitable for user alignment, user-facing follow-up, dashboard reading, the completed-work report filter, and later audit.

If local skills shaped the work, include the skill review in the nearest relevant section as a short judgment: kept as-is, patched, retired, or worth installing later.

When the user asks the lead to clean up, close the loop through the same closure boundary: inbox sweep, follow-up task or ticket for deferred work, termination report, completed task, done lead status, then `bus stop --reason loop_closed` for the whole loop. Archive or clear session records after a separate explicit request.

Use this shape:

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

Close in this order so the termination report remains the last message:

```bash
agentbus agent inbox --name <agent>
# handle or defer any closure-changing messages here
MSG_ID=$(agentbus message send --from <agent> --to user --kind report --subject "종료 보고서: <scope>" --body "$(cat report.md)" --task <task_id>)
agentbus task state --id <task_id> --state completed --by <agent> --note "closed with termination report $MSG_ID"
agentbus agent set --name <agent> --state done --task <task_id> --note "closed with termination report $MSG_ID"
```

To close the whole bus loop, run `agentbus bus stop --by <agent> --reason loop_closed --detail "termination report $MSG_ID"` after the final report. The dashboard then shows `루프 종료됨` in the top loop-state control while the final bus report remains the last message.

## Platform notes

- Chat or app thread: treat `/agent-bus-loop`, "start loop", or "attach to agent-bus" as a request to run Start, then Loop while the thread is active
- Local CLI teammate: create or copy a bus-local profile in `.agent-bus/bridge`, then use `agentbus teammate run --profile <profile>` as the opt-in runner path; provider CLI calls stay inside the runner, successful cycles with bus records auto-ack the message that triggered the cycle, stdout remains an operator log, teammates continue by leaving bounded follow-up requests to themselves or asking the lead for the next narrowed slice, individual task completion leaves the runner waiting, and a bus stop signal closes it
- External bridge: use `agentbus bridge run` or `agentbus bridge watch`; keep bridge positions separate from agent state
- Sensitive work: respect `sensitivity`; `restricted` raw payloads stay local, agent inbox/watch reads require `AGENTBUS_AGENT_TOKEN`, and dashboard raw viewing uses a separate viewer token

For the full workflow, run `agentbus guide workflow` or use the `agent-bus-workflow` skill.
