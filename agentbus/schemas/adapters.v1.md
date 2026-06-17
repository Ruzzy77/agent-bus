# adapter contract v1

Adapters connect the raw file bus to external runtimes. Core remains stdlib-only and handles files, locks, messages, tickets, tasks, status, dashboard, and event folding.

## Event bridge contract

```bash
agentbus watch-events --types message.created,ticket.created \
  --target reviewer \
  --cursor-file .agent-bus/adapters/reviewer.cursor \
  --fail-log .agent-bus/adapters/reviewer.failures.jsonl \
  --exec-timeout 60 \
  --exec './adapter.sh'

agentbus wakeup --profile "$(agentbus examples wakeup/a2a-events.json)"
```

| Option | Meaning |
| --- | --- |
| `--types` | Event type filter. Prefix filters such as `message.*` are allowed. |
| `--target` | Target filter. Events for `all` or `*` match every target. |
| `--cursor-file` | Last processed event position. |
| `--from-start` | Process existing events before waiting. |
| `--dry-run` | Print events while leaving `--exec` and cursor state untouched. |
| `--fail-log` | Append failed adapter calls as JSONL. |
| `--exec` | Command that receives one event JSON object on stdin. |
| `--exec-timeout` | Adapter timeout seconds; `0` disables it. |
| `--allow-sensitive` | Allow `confidential` and `restricted` events to reach the adapter. |

A successful event bridge exit advances the cursor. A failed exit leaves the cursor ready for retry. A sensitive-blocked event advances the cursor, prints a redacted notice, and withholds the event body from `--fail-log`.

Check adapter state with:

```bash
agentbus adapter-status
agentbus adapter-status --json
```

`adapter-status` reports event bridge cursor and redacted failure summaries from `<bus>/adapters/`.

## Adapter input

| Env | Meaning |
| --- | --- |
| `AGENTBUS_EVENT_ID` | Event cursor. |
| `AGENTBUS_EVENT_TYPE` | Event type. |
| `AGENTBUS_OBJECT_TYPE` | `message`, `task`, or `ticket`. |
| `AGENTBUS_OBJECT_ID` | Primary object id. |
| `AGENTBUS_ALLOW_SENSITIVE` | Set to `1` for adapter children when `--allow-sensitive` is used. |

Events and wakeup payloads are hints. An adapter rereads the bus or referenced files before acting.

A user-run agent runner command should accept one JSON object on stdin, write a concise result to stdout, and use a nonzero exit when the source message should remain pending. `run-agent.sh` applies that contract to inbox wakeups.

## Sensitive data

Adapters treat `sensitivity` and `retention` as handling signals.

- `confidential` and `restricted` events require explicit sensitive handling
- Sensitive-blocked events and wakeups print a redacted notice with the payload body withheld
- `no_archive` messages stay in the active message log during `rotate`
- External tokens should come from environment variables rather than command history or bus messages

## A2A flow

1. Watch a candidate event.
2. Reread the source message and references.
3. Create a request body with `agentbus a2a-rpc`.
4. Check it with `agentbus a2a-rpc-check`.
5. Send it with `agentbus a2a-post` or another HTTP adapter.
6. Record the response when local agents need to continue from it.

`agentbus/examples/adapters/a2a-outbound.sh` is the minimal `watch-events --exec` example. Use `agentbus examples wakeup/a2a-events.json` to locate the reusable wakeup profile for the same flow. `agentbus serve` also exposes local Agent Card and `SendMessage` test endpoints for development; public A2A serving belongs to an external host.

## OpenAI-compatible HTTP flow

`agentbus/examples/adapters/openai-compatible.sh` sends one wakeup, event, or assessment packet JSON payload to an OpenAI-compatible chat completions endpoint.

| Environment variable | Use |
| --- | --- |
| `OPENAI_COMPAT_ENDPOINT` | OpenAI-compatible HTTP endpoint, for example an internal gateway URL. |
| `OPENAI_COMPAT_MODEL` | Model or router name. |
| `OPENAI_COMPAT_API_KEY` | Default bearer token source. |
| `OPENAI_COMPAT_TOKEN_ENV` | Alternate environment variable name for the bearer token. |
| `OPENAI_COMPAT_RESPONSE_TO` | Optional bus recipient for the model response. |
| `OPENAI_COMPAT_RESPONSE_FROM` | Bus sender, default `openai-compatible`. |
| `OPENAI_COMPAT_EXTRA_JSON` | Optional JSON object merged into the request body. |
| `AGENTBUS_CLI` | Optional command for recording responses, default `agentbus`. |

The adapter requires `AGENTBUS_ALLOW_SENSITIVE` for `confidential` and `restricted` payloads. It prints a compact response summary and records the model response with `agentbus send` when `OPENAI_COMPAT_RESPONSE_TO` is set.

## Agent runner flow

`agentbus/examples/adapters/run-agent.sh` lets a user-run command process inbox wakeup payloads.

| Environment variable | Use |
| --- | --- |
| `AGENT_RUNNER_COMMAND` | Shell command that receives one `agent-runner-work.v1` JSON object on stdin. Required. |
| `AGENT_RUNNER_NAME` | Agent name used in bus records. Default: wakeup payload agent. |
| `AGENT_RUNNER_REPORT_TO` | Optional fixed report recipient. Default: original message sender. |
| `AGENT_RUNNER_REPORT` | `0` disables report messages. Default: enabled. |
| `AGENT_RUNNER_ACK` | `0` disables ack after successful command. Default: enabled. |
| `AGENT_RUNNER_UPDATE_TASK` | `0` disables task-state updates. Default: enabled. |
| `AGENTBUS_CLI` | Optional command for recording bus results, default `agentbus`. |

The runner processes pending messages one at a time. For each successful command it records a report, marks the task completed when a task id exists, and acks the source message. On command failure it marks the task failed and exits nonzero, so `wakeup` keeps the failed message pending.

## Codex runner flow

`agentbus/examples/adapters/codex-runner.py` receives one `agent-runner-work.v1` object and passes it to Codex through CLI or SDK.

| Environment variable | Use |
| --- | --- |
| `CODEX_RUNNER_MODE` | `cli`, `sdk`, or `auto`. Default: `cli`. |
| `CODEX_RUNNER_CLI` | CLI command, default `codex`. |
| `CODEX_RUNNER_MODEL` | Optional Codex model. |
| `CODEX_RUNNER_SANDBOX` | Optional sandbox, for example `read-only` or `workspace-write`. |
| `CODEX_RUNNER_CWD` | Optional working directory. |
| `CODEX_RUNNER_PROMPT` | Optional instruction prefix. |
| `CODEX_RUNNER_EXTRA_ARGS` | Extra CLI args for `codex exec` mode. |
| `CODEX_RUNNER_RESUME` | Optional CLI resume target: `last` or a session id. `CODEX_RUNNER_SANDBOX` and `CODEX_RUNNER_CWD` apply only to new CLI runs. |
| `CODEX_RUNNER_TIMEOUT` | Optional CLI timeout seconds. `0` disables it. |
| `CODEX_RUNNER_DRY_RUN` | Print prompt and packet summary while leaving Codex uncalled. |

`cli` mode calls `codex exec` and uses the local Codex login. `sdk` mode imports `openai-codex` and uses the SDK thread API. Use `agentbus examples wakeup/codex-runner-inbox.json` for an inbox profile that wires `codex-runner.py` through `run-agent.sh`.

## Claude runner flow

`agentbus/examples/adapters/claude-runner.py` receives one `agent-runner-work.v1` object and passes it to Claude through CLI, Agent SDK, or Messages API.

| Environment variable | Use |
| --- | --- |
| `CLAUDE_RUNNER_MODE` | `cli`, `sdk`, `api`, or `auto`. Default: `cli`. |
| `CLAUDE_RUNNER_CLI` | CLI command, default `claude`. |
| `CLAUDE_RUNNER_MODEL` | Optional model. `api` mode uses it, with `ANTHROPIC_MODEL` as fallback. |
| `CLAUDE_RUNNER_CWD` | Optional working directory for CLI and SDK modes. |
| `CLAUDE_RUNNER_PERMISSION_MODE` | Optional Claude permission mode, for example `plan`. |
| `CLAUDE_RUNNER_MAX_TURNS` | Optional CLI max-turns value. |
| `CLAUDE_RUNNER_OUTPUT_FORMAT` | Optional CLI output format. |
| `CLAUDE_RUNNER_BARE` | `1` adds `--bare` to CLI mode. |
| `CLAUDE_RUNNER_ALLOWED_TOOLS` | Comma-separated allowed tool list for SDK mode. |
| `CLAUDE_RUNNER_ENDPOINT` | Messages API endpoint for `api` mode. Default: `https://api.anthropic.com/v1/messages`. |
| `CLAUDE_RUNNER_API_KEY_ENV` | Token environment variable name for `api` mode. Default: `ANTHROPIC_API_KEY`. |
| `CLAUDE_RUNNER_MAX_TOKENS` | Messages API max token count. Default: `1024`. |
| `CLAUDE_RUNNER_ANTHROPIC_VERSION` | Anthropic API version header. Default: `2023-06-01`. |
| `CLAUDE_RUNNER_PROMPT` | Optional instruction prefix. |
| `CLAUDE_RUNNER_EXTRA_ARGS` | Extra CLI args. |
| `CLAUDE_RUNNER_EXTRA_JSON` | Optional JSON object merged into the Messages API request body. |
| `CLAUDE_RUNNER_TIMEOUT` | Optional timeout seconds. `0` disables it. |
| `CLAUDE_RUNNER_DRY_RUN` | Print prompt and packet summary while leaving Claude uncalled. |

`cli` mode calls `claude -p` and sends the work packet on stdin. `sdk` mode imports `claude-agent-sdk` and uses `query()`. `api` mode uses the Messages API directly; it sends a prompt and uses file or shell tools when the receiving service supplies them. Use `agentbus examples wakeup/claude-runner-inbox.json` for an inbox profile that wires `claude-runner.py` through `run-agent.sh`.

## AAS packet flow

1. Read manufacturing or process JSON.
2. Create `assessment-packet.v1` with `agentbus aas-packet`.
3. Check it with `agentbus aas-packet-check`.
4. Send the checked packet or include it as an A2A `data` part.

Full AAS HTTP/REST API support and AASX export remain optional adapters with separate conformance tests.

## External connection checklist

- Discovery: resolve endpoint or Agent Card outside core bus state.
- Authentication: use token environment variables or operator-managed headers.
- Payload: keep raw bus data and AAS-style data in one JSON request when both are needed.
- Sensitive data: require explicit allow mode before external transfer.
- Response: record a bus message or task state when local agents continue from the result.
- Failure: write event bridge cursor and failure logs under `<bus>/adapters/`, then inspect with `agentbus adapter-status`.
