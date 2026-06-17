---
name: agent-bus-loop
description: >-
  Use this skill when a user asks an agent to start, continue, pause, or stop an
  agent-bus loop in any platform, including slash-style requests such as /agent-bus-loop.
  It provides a platform-neutral entrypoint that tells the agent how to join the
  bus, check stop signals, read inbox, report work, wait, and close cleanly.
---

# agent-bus loop

Start or resume the loop in the current agent thread. Treat agent-bus as the shared coordination record used by the agent, with process ownership kept by the surrounding runtime.

Use this skill as the entrypoint. For detailed inbox, ack, task-state, ticket, stop, input_required, event bridge, runner, and security rules, consult `agentbus workflow` or the `agent-bus-workflow` skill while running the loop.

## Inputs

Find these values from the prompt, environment, project notes, or current shell.

| Value | Meaning |
| --- | --- |
| `<agent>` | Stable agent name for status, inbox, and ack records |
| `<bus_dir>` | Shared bus directory, usually `./.agent-bus` or `AGENTBUS_BUS_DIR` |
| `<task_id>` | Optional task id from an inbox message or user instruction |

If `<bus_dir>` is unclear, use `AGENTBUS_BUS_DIR` when set, otherwise initialize `./.agent-bus` in the current project.

## Start

```bash
export AGENTBUS_BUS_DIR=<bus_dir>
agentbus init
agentbus check-stop
agentbus status --agent <agent> --state running --note "joined"
agentbus inbox --agent <agent>
```

If `check-stop` exits 2, enter the stop boundary. Report the stop request and set `status --state waiting` or `done` according to the platform context.

## Loop

At each work boundary:

1. Run `agentbus check-stop`
2. Update `status --state running` while working
3. Read `agentbus inbox --agent <agent>`
4. Handle messages addressed to `<agent>`, `all`, or `*`
5. Use `task-state` when a task id exists
6. Send reports with `send --from <agent> --to <peer> --kind report`
7. Ack messages already handled
8. Set `status --state waiting` before yielding control

```bash
agentbus status --agent <agent> --state running --task <task_id> --note "working"
agentbus task-state --id <task_id> --state working --by <agent> --note "current slice"
agentbus send --from <agent> --to user --kind report --subject "result" --body "short result" --task <task_id>
agentbus ack --agent <agent> <message_id>
agentbus status --agent <agent> --state waiting --task <task_id> --note "waiting"
```

## Work intake

Autonomous work is the default. Use direct tasks and request messages for work that can proceed on agent judgment, and reserve tickets for human-triage decisions.

```bash
TASK_ID=$(agentbus task-new --title "short work title" --by <agent> --assign <peer>)
agentbus send --from <agent> --to <peer> --kind request --subject "short work title" --body "work request" --task "$TASK_ID"
```

Use a ticket for a new proposal, a critical or risky change, or work that needs human review before execution. While a ticket waits for triage, continue safe active tasks.

## Stop or pause

A stop request puts the loop at a closure boundary. Finish the smallest safe cleanup, then report and wait.

```bash
agentbus check-stop
agentbus status --agent <agent> --state waiting --note "stopped by request"
```

Use `input_required` when progress needs a user decision rather than more agent work.

```bash
agentbus task-state --id <task_id> --state input_required --by <agent> --note "decision needed"
```

## Loop closure report

When closing a completed loop, the lead agent synthesizes peer reports, evidence refs, disagreements, verification, and remaining decisions into a polished termination report as the last bus `report` message, then closes task/status records. Keep it suitable for user alignment, user-facing follow-up, dashboard reading, the completed-work report filter, and later audit.

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
MSG_ID=$(agentbus send --from <agent> --to user --kind report --subject "종료 보고서: <scope>" --body "$(cat report.md)" --task <task_id>)
agentbus task-state --id <task_id> --state completed --by <agent> --note "closed with termination report $MSG_ID"
agentbus status --agent <agent> --state done --task <task_id> --note "closed with termination report $MSG_ID"
```

To close the whole bus loop, run `agentbus stop --by <agent> --reason loop_closed --detail "termination report $MSG_ID"` after the final report. The dashboard then shows `루프 종료됨` in the top loop-state control while the final bus report remains the last message.

## Platform notes

- Chat or app thread: treat `/agent-bus-loop`, "start loop", or "attach to agent-bus" as a request to run Start, then Loop while the thread is active
- CLI runner: use this loop as the behavior inside the invoked agent; background daemon behavior is an explicit user-runner choice
- External bridge: use `agentbus wakeup` or `watch-events`; keep adapter cursors separate from agent state
- Sensitive work: respect `sensitivity` and `retention`; external tools require explicit sensitive handling for `confidential` or `restricted` payloads

For the full workflow, run `agentbus workflow` or use the `agent-bus-workflow` skill.
