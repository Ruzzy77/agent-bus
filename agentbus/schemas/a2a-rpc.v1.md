# a2a-rpc.v1

`a2a-rpc.v1` is the A2A-facing projection of raw bus messages. It creates and checks A2A 1.0 `SendMessage` JSON-RPC request bodies, sends them with stdlib HTTP, and can record responses back to the raw bus.

Public hosting, OAuth, streaming, task polling, and push delivery stay in the surrounding A2A integration layer.

## Local commands

```bash
agentbus a2a-card --agent reviewer --url http://127.0.0.1:8765/a2a/rpc --out agent-card.json
agentbus a2a-card-check --file agent-card.json
agentbus a2a-rpc --message-id <id> --data packet.json --out request.json
agentbus a2a-rpc-check --file request.json
agentbus a2a-post --file request.json --endpoint https://example.com/a2a/rpc --token-env A2A_TOKEN
```

## Mapping

| Raw source | A2A field |
| --- | --- |
| message id | `params.message.messageId` |
| message body | first `params.message.parts[].text` |
| structured JSON | additional `params.message.parts[].data` |
| task id | `params.message.taskId`, `referenceTaskIds` |
| sender, recipient, subject, refs | `params.message.metadata` |
| sensitivity, retention | `params.message.metadata`, `parts[].metadata` for packet data |
| shared endpoint route | `params.tenant`, `supportedInterfaces[].tenant` |

Structured JSON such as `assessment-packet.v1` stays in the same `SendMessage` request as a `data` part.

`a2a-post` requires `--allow-sensitive` for `confidential` and `restricted` requests.

## HTTP defaults

| Header | Value |
| --- | --- |
| `Content-Type` | `application/json` |
| `Accept` | `application/json` |
| `A2A-Version` | `1.0` |
| `Authorization` | `Bearer <token>` when supplied |

`--record-response-to` records `result.message` as a bus message and maps `result.task.status.state` to the local task state when a local task id is available. Failures are written to `--fail-log` when it is set.

## Local inbound endpoints

`agentbus serve` exposes local test endpoints on 127.0.0.1 for development.

| Path | Meaning |
| --- | --- |
| `/.well-known/agent-card.json?agent=<id>` | Project a local card as an A2A Agent Card. |
| `/a2a/rpc` | Accept `SendMessage` and append it to the raw bus. |

These endpoints support local testing and dashboard integration. Public A2A serving belongs to an external host.

## Minimum checks

| Command | Checks |
| --- | --- |
| `a2a-card-check` | Agent Card required fields, interface, modes, skills. |
| `a2a-rpc-check` | JSON-RPC envelope, `SendMessage`, message id, role, non-empty parts, Part one-of rule. |
