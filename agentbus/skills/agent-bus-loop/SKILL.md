---
name: agent-bus-loop
description: >-
  Use this skill when a user asks an agent to start, continue, pause, or stop an
  agent-bus loop in any platform, including slash-style requests such as /agent-bus-loop.
  It provides a platform-neutral entrypoint that tells the agent how to join the
  bus, check stop signals, read inbox, report work, wait, and close cleanly.
---

# agent-bus loop

Start or resume the loop in the current agent thread. Treat agent-bus as a shared record that the agent uses, not as a process manager.

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

If `check-stop` exits 2, do not start new work. Report the stop request and set `status --state waiting` or `done` according to the platform context.

## Loop

At each work boundary:

1. Run `agentbus check-stop`
2. Update `status --state running` while working
3. Read `agentbus inbox --agent <agent>`
4. Handle only messages addressed to `<agent>`, `all`, or `*`
5. Use `task-state` when a task id exists
6. Send reports with `send --from <agent> --to <peer> --kind report`
7. Ack only messages already handled
8. Set `status --state waiting` before yielding control

```bash
agentbus status --agent <agent> --state running --task <task_id> --note "working"
agentbus task-state --id <task_id> --state working --by <agent> --note "current slice"
agentbus send --from <agent> --to user --kind report --subject "result" --body "short result" --task <task_id>
agentbus ack --agent <agent> <message_id>
agentbus status --agent <agent> --state waiting --task <task_id> --note "waiting"
```

## Work intake

Autonomous work is the default. Do not create tickets that add review fatigue, stop the loop, or interrupt safe forward progress.

Do not turn every new work item into a ticket. If work can proceed without human acceptance, create or use a task and send a request to the target agent.

```bash
TASK_ID=$(agentbus task-new --title "short work title" --by <agent> --assign <peer>)
agentbus send --from <agent> --to <peer> --kind request --subject "short work title" --body "work request" --task "$TASK_ID"
```

Use a ticket only for a new proposal, a critical or risky change, or work that cannot safely proceed without human review. If a ticket is created, keep working on safe active tasks instead of waiting on that ticket.

## Stop or pause

Stop means no new work. Finish only the smallest safe cleanup, then report and wait.

```bash
agentbus check-stop
agentbus status --agent <agent> --state waiting --note "stopped by request"
```

Use `input_required` when progress needs a user decision rather than more agent work.

```bash
agentbus task-state --id <task_id> --state input_required --by <agent> --note "decision needed"
```

## Platform notes

- Chat or app thread: treat `/agent-bus-loop`, "start loop", or "attach to agent-bus" as a request to run Start, then Loop while the thread is active
- CLI runner: use this loop as the behavior inside the invoked agent, not as a background daemon unless the user asked for one
- External bridge: use `agentbus wakeup` or `watch-events`; keep adapter cursors separate from agent state
- Sensitive work: respect `sensitivity` and `retention`; do not send `confidential` or `restricted` payloads to external tools unless explicitly allowed

For the full workflow, run `agentbus workflow` or use the `agent-bus-workflow` skill.
