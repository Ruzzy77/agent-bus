# bridge handlers

Bridge handlers connect predefined bus events to a monitor handler, a local teammate runner, or an API endpoint. Local CLI teammates use `agentbus teammate run --profile <profile>` with a bus-local profile in `.agent-bus/bridge`. The reusable configuration contract is `bridge-profile.v1`.

## Event stream

```bash
agentbus bridge events --types message.created,ticket.created --jsonl
agentbus bridge watch --types message.created --position-file .agent-bus/bridge/watch.position
```

`bridge watch` observes and advances event positions. `bridge run --profile` owns handler execution and keeps profile position files current.

## Agent handlers

`agentbus teammate run --profile <profile>` is the local teammate runner entrypoint. The bus-local profile selects one target agent, one provider, and provider options as an argv array.

| Provider | Entrypoint |
| --- | --- |
| `codex` | `codex exec <args...> <agent-bus prompt>` |
| `claude` | `claude <args...> -p <agent-bus prompt>` |
| `gemini` | `gemini <args...> -p <agent-bus prompt>` |

Agent-bus supplies the prompt and sends one `teammate-cycle.v1` JSON packet on stdin. The packet includes Key Context and trigger metadata. The teammate ends each cycle by waiting with a report, leaving a bounded self follow-up, asking lead/user input, or completing the slice. The invoked agent writes durable reports, task state, acks, and status through the bus; stdout remains an operator log. Existing matching request events are picked up unless they are already acked or delivered. Runner timeout is a visibility signal; the provider process keeps running and is judged by its final exit code and bus records.

## API handlers

`http` sends JSON to an endpoint. `protocol: "a2a"` converts a message event into an A2A message request before sending it.

`openai-compatible` sends the event to a chat completions endpoint and can record the response as a bus report.

Profiles list required environment names in `envs`; values stay in the environment and are not shown in the dashboard.
