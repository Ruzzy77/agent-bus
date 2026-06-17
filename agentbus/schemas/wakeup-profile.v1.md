# wakeup-profile.v1

`wakeup-profile.v1` is a JSON profile for `agentbus wakeup`. It turns inbox polling or event watching into a reusable adapter runner.

## Shape

```json
{
  "schemaVersion": "wakeup-profile.v1",
  "name": "claude-inbox",
  "mode": "inbox",
  "command": "",
  "intervalSeconds": 30,
  "maxSeconds": 1500,
  "allowSensitive": false,
  "requiredEnv": [],
  "cursorFile": "",
  "failLog": ""
}
```

## Common fields

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Must be `wakeup-profile.v1`. |
| `name` | Profile name. Used for default adapter state paths. |
| `mode` | `inbox` or `events`. |
| `command` | Optional shell command. It receives one JSON object on stdin. |
| `intervalSeconds` | Poll interval for loop mode. |
| `maxSeconds` | Maximum run time. `0` means unlimited. |
| `execTimeout` | Command timeout seconds. `0` disables it. |
| `allowSensitive` | Allows `confidential` and `restricted` payloads to reach stdout and `command`. |
| `requiredEnv` | Environment variable names expected before the profile runs. |
| `cursorFile` | Adapter cursor path. Relative paths are under the bus directory. |
| `failLog` | Adapter failure JSONL path. Relative paths are under the bus directory. |

Default state paths are `<bus>/adapters/<name>.cursor` and `<bus>/adapters/<name>.failures.jsonl`.

Profiles reference secret names. Put tokens in environment variables and list the names in `requiredEnv`.

## Inbox mode

```json
{
  "schemaVersion": "wakeup-profile.v1",
  "name": "claude-inbox",
  "mode": "inbox",
  "agent": "claude",
  "kinds": ["request", "report", "note"],
  "markDelivered": true
}
```

| Field | Meaning |
| --- | --- |
| `agent` | Inbox owner. Required. |
| `kinds` | Message kinds to wake on. Default is `request`. |
| `markDelivered` | Write `delivered.jsonl` after a successful wake command. Ack remains the receiving agent's responsibility. |

`inbox` mode checks `stop.json` before each poll. If pending messages exist, it prints the pending JSON, sends the same JSON to `command` when set, and exits. Sensitive pending data requires explicit sensitive handling; otherwise the output is a redacted notice.

## Events mode

```json
{
  "schemaVersion": "wakeup-profile.v1",
  "name": "a2a-events",
  "mode": "events",
  "types": ["message.created"],
  "target": "reviewer",
  "command": "agentbus/examples/adapters/a2a-outbound.sh",
  "execTimeout": 60,
  "requiredEnv": ["A2A_ENDPOINT"]
}
```

| Field | Meaning |
| --- | --- |
| `types` | Event type filters. Prefix filters such as `message.*` are allowed. Required. |
| `target` | Target filter. Events for `all` or `*` match every target. |
| `fromStart` | Process existing events before waiting. |
| `execTimeout` | Command timeout seconds. `0` disables it. |

`events` mode keeps the `watch-events` contract: a successful command advances the cursor, a failed command leaves the cursor ready for retry, and a sensitive-blocked event advances the cursor while withholding the event body from output and logs.

## Commands

```bash
PROFILE=$(agentbus examples wakeup/claude-inbox.json)
agentbus wakeup-check --file "$PROFILE"
agentbus wakeup --profile "$PROFILE" --once
AGENT_RUNNER_COMMAND='your-agent-command --json' \
  agentbus wakeup --profile "$(agentbus examples wakeup/agent-runner-inbox.json)"
OPENAI_COMPAT_ENDPOINT=https://model-gateway.example/v1/chat/completions \
OPENAI_COMPAT_MODEL=assessment-router \
OPENAI_COMPAT_API_KEY=... \
OPENAI_COMPAT_RESPONSE_TO=operator \
  agentbus wakeup --profile "$(agentbus examples wakeup/openai-compatible-events.json)"
```
