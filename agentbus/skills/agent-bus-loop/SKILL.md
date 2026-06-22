---
name: agent-bus-loop
description: >-
  Use this skill when a user asks an agent to start, continue, pause, or stop an
  agent-bus loop in any platform, including slash-style requests such as /agent-bus-loop.
  It is the single entry skill for agent-bus collaboration; detailed workflow rules
  live in references/workflow.md.
---

# agent-bus loop

Start, resume, pause, or close an agent-bus collaboration loop in the current agent thread. Treat agent-bus as the shared coordination record; the surrounding app, CLI, or runner owns the process.

This skill is the entrypoint. Use it to attach to the bus and decide the next loop boundary. When you need detailed rules for Key Context, lead planning, teammate requests, task states, tickets, security, runner behavior, or termination reports, read `references/workflow.md` or run `agentbus guide workflow`.

## Inputs

Find these values from the user prompt, environment, project notes, or shell.

| Value | Meaning |
| --- | --- |
| `<agent>` | Display name; agent-bus stores a generated `a-...` id behind it. |
| `<bus_dir>` | Shared channel directory, usually `./.agent-bus` or `AGENTBUS_BUS_DIR`. |
| `<task_id>` | Optional task id from an inbox message or user instruction. |

If `<bus_dir>` is unclear, use `AGENTBUS_BUS_DIR` when set; otherwise use `./.agent-bus` in the current project. The operator or lead should run `agentbus bus init` once and keep `agentbus bus serve` running for dashboard/API access.

## First turn

When the user asks for a full bus workflow, act as the lead entrypoint until another lead is assigned. Ask only for facts that change the loop:

- goal and completion criterion
- scope to keep out of the work
- security level and restricted-data handling
- teammates, runners, or bridge profiles to involve
- whether the dashboard should be used

If those facts are already clear, proceed with reasonable defaults: current project, `AGENTBUS_BUS_DIR` or `./.agent-bus`, current agent display name, lead-managed task/request records when needed, and a standard closure report. State the chosen defaults briefly, then start or join the bus.

## Start or resume

```bash
export AGENTBUS_BUS_DIR=<bus_dir>
agentbus bus status --stop-exit-code
agentbus agent set --name <agent> --state running --note "joined"
agentbus agent inbox --name <agent>
```

If ordinary CLI commands cannot reach the bus server, report the setup boundary instead of reading or editing `.agent-bus/store`. If `agentbus bus status --stop-exit-code` exits 2, enter the stop boundary and set the agent to `waiting` or `done` according to the platform context.

## Work boundary

At each work boundary:

1. Run `agentbus bus status --stop-exit-code`.
2. Set the agent `running` while working.
3. Read `agentbus agent inbox --name <agent>`.
4. Handle messages addressed to `<agent>`, `all`, or `*`.
5. Use task state when a task id exists.
6. Send reports with `agentbus message send --kind report`.
7. If working outside `teammate run`, ack messages that have been handled.
8. Set the agent `waiting` before yielding control.

```bash
agentbus agent set --name <agent> --state running --task <task_id> --note "working"
agentbus task state --id <task_id> --state working --by <agent> --note "current slice"
agentbus message send --from <agent> --to user --kind report --subject "result" --body "short result" --task <task_id>
agentbus agent set --name <agent> --state waiting --task <task_id> --note "waiting"
```

When this thread handles inbox messages directly, run `agentbus agent ack --name <agent> <message_id>` after the report, task state, or follow-up request proves the message was handled.

## Lead boundary

When acting as lead, keep Key Context current and plan teammate work before sending requests. For broad or alignment-sensitive work, use `lead-strategic-approach`, then send bounded requests with owned scope, expected result, nearby causal links, evidence path, and report shape. Detailed lead and teammate rules are in `references/workflow.md`.

User-authored `작업`, `티켓`, and `정지` messages from the dashboard compose are lead-management requests. Interpret them in the current work context, then create task, ticket, or stop records only when that is the right bus action.

## Stop or close

A stop request puts the loop at a closure boundary. Finish the smallest safe cleanup, report changed state and remaining risk, then wait or close.

```bash
agentbus bus status --stop-exit-code
agentbus agent set --name <agent> --state waiting --note "stopped by request"
```

When closing a completed loop, run one final inbox sweep, handle or defer closure-changing messages, send the termination report as the final bus `report`, mark the task completed, mark the lead done, then send `bus stop --reason loop_closed` when the whole loop is closed. Use `references/workflow.md` or `agentbus guide workflow` for the report structure and closure order.
