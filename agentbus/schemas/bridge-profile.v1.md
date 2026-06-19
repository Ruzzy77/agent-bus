# bridge-profile.v1

`bridge-profile.v1` routes predefined bus events to a monitor handler, an agent runtime, or an API handler. It does not carry arbitrary shell commands.

## Shape

```json
{
  "schemaVersion": "bridge-profile.v1",
  "name": "codex-requests",
  "event": "message.created",
  "matcher": {
    "target": "codex",
    "kind": ["request"]
  },
  "handler": {
    "type": "agent",
    "provider": "codex",
    "args": ["--sandbox", "workspace-write"]
  },
  "envs": [],
  "intervalSeconds": 5,
  "maxSeconds": 0,
  "timeoutSeconds": 0
}
```

## Common fields

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Must be `bridge-profile.v1`. |
| `name` | Profile name. Used for bridge state paths. |
| `event` | Bus event name or list. Prefix filters such as `message.*` are accepted. |
| `matcher` | Narrow JSON matcher for event fields. |
| `handler` | Routing target. See handler types below. |
| `envs` | Environment variable names required by the handler. Values stay outside the profile. |
| `intervalSeconds` | Poll interval for `bridge run`. |
| `maxSeconds` | Maximum run time. `0` means unlimited. |
| `timeoutSeconds` | Handler timeout seconds. `0` disables it where the handler supports timeout. |
| `fromStart` | Process existing matching events before waiting. |
| `markDelivered` | For agent handlers, write `delivered.jsonl` after successful processing. |
| `positionFile` | Bridge position path. Relative paths are under the channel directory. |
| `failLog` | Bridge failure log path. Relative paths are under the channel directory. |

Default state paths are `<bus>/bridge/<name>.position` and `<bus>/bridge/<name>.failures.jsonl`.

## Data handling

- `http`, `a2a`, and `openai-compatible` handlers do not receive `restricted` events.
- `internal` events are projected with content-bearing fields redacted before external handlers run.
- `agent` handlers receive `restricted` raw fields only when the matcher target agent presents a valid `AGENTBUS_AGENT_TOKEN`; otherwise the work packet stays redacted.
- Failure logs omit raw restricted payloads.

## Matcher

Supported matcher keys are deliberately small:

| Key | Matches |
| --- | --- |
| `target` | Single event target agent id. Omit this key to leave the profile untargeted. |
| `kind` | Message kind from `event.data.kind`. |
| `actor` | Event actor. |
| `objectType` | `event.object.type`. |
| `objectId` | `event.object.id`. |

`target` is a single string. Other matcher values can be a string or a list of strings.

## Handler types

### `monitor`

Print matching events and update the profile position. No external process or network call runs.

```json
{"type": "monitor"}
```

### `agent`

Runs a fixed agent CLI entrypoint with `shell=False`.

| Provider | Entrypoint |
| --- | --- |
| `codex` | `codex exec <args...> <agent-bus prompt>` |
| `claude` | `claude <args...> -p <agent-bus prompt>` |
| `gemini` | `gemini <args...> -p <agent-bus prompt>` |

`args` is an argv array. Agent-bus supplies the prompt and sends one `agent-runner-work.v1` packet on stdin.

### `http`

Sends matching events to an HTTP endpoint. `protocol: "a2a"` builds and sends an A2A message request from a message event.

```json
{
  "type": "http",
  "protocol": "a2a",
  "url": "$A2A_ENDPOINT"
}
```

### `openai-compatible`

Sends matching events to an OpenAI-compatible chat completions endpoint.

```json
{
  "type": "openai-compatible",
  "endpoint": "$OPENAI_COMPAT_ENDPOINT",
  "model": "$OPENAI_COMPAT_MODEL",
  "apiKey": "$OPENAI_COMPAT_API_KEY",
  "responseTo": "$OPENAI_COMPAT_RESPONSE_TO"
}
```

Environment references use whole-string `$ENV_NAME` values. Put the required names in `envs` so `bridge check` and the dashboard can show setup state without exposing values.

## Commands

```bash
cp .agent-bus/bridge/profile.template.json .agent-bus/bridge/codex-runner-inbox.json
agentbus bridge check --file .agent-bus/bridge/codex-runner-inbox.json
agentbus bridge run --profile .agent-bus/bridge/codex-runner-inbox.json --once

cp "$(agentbus resource path bridge/a2a-reviewer.json)" .agent-bus/bridge/a2a-reviewer.json
```
