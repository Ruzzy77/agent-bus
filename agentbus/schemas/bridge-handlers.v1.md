# bridge handlers

Bridge handlers connect predefined bus events to a monitor handler, an agent runtime, or an API endpoint. The reusable configuration contract is `bridge-profile.v1`.

## Event stream

```bash
agentbus bridge events --types message.created,ticket.created --jsonl
agentbus bridge watch --types message.created --position-file .agent-bus/bridge/watch.position
```

`bridge watch` observes and advances event positions. Handler execution belongs to `bridge run --profile`.

## Agent handlers

Agent handlers use fixed runtime entrypoints and pass options as argv arrays in the profile.

| Provider | Entrypoint |
| --- | --- |
| `codex` | `codex exec <args...> <agent-bus prompt>` |
| `claude` | `claude <args...> -p <agent-bus prompt>` |
| `gemini` | `gemini <args...> -p <agent-bus prompt>` |

Agent-bus supplies the prompt and sends one `agent-runner-work.v1` JSON packet on stdin. The agent stdout becomes the report body.

## API handlers

`http` sends JSON to an endpoint. `protocol: "a2a"` converts a message event into an A2A message request before sending it.

`openai-compatible` sends the event to a chat completions endpoint and can record the response as a bus report.

Profiles list required environment names in `envs`; values stay in the environment and are not shown in the dashboard.
