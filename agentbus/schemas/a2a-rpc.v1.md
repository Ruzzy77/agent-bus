# a2a-rpc.v1

`a2a-rpc.v1` is the A2A-facing projection of bus messages. It creates and checks A2A 1.0 `SendMessage` JSON-RPC request bodies, sends them over HTTP, and can record responses back to the bus.

Public hosting, OAuth, streaming, task polling, and push delivery stay in the surrounding A2A integration layer.

## Local commands

```bash
agentbus packet transport --protocol a2a --artifact card --agent reviewer --url http://127.0.0.1:8765/a2a/rpc --out agent-card.json
agentbus packet transport --protocol a2a --artifact card --file agent-card.json
agentbus packet transport --protocol a2a --artifact message --message-id <id> --data packet.json --out request.json
agentbus packet transport --protocol a2a --artifact message --file request.json
agentbus packet send --protocol a2a --file request.json --endpoint https://example.com/a2a/rpc --token-env A2A_TOKEN
agentbus packet receive --protocol a2a --file request.json
```

## Mapping

| Raw source | A2A field |
| --- | --- |
| message id | `params.message.messageId` |
| message body | first `params.message.parts[].text` |
| structured JSON | additional `params.message.parts[].data` |
| task id | `params.message.taskId`, `referenceTaskIds` |
| sender, recipient, subject, refs | `params.message.metadata` |
| sensitivity | `params.message.metadata`, `parts[].metadata` for packet data |
| shared endpoint route | `params.tenant`, `supportedInterfaces[].tenant` |

Structured JSON such as `assessment-packet.v1` stays in the same `SendMessage` request as a `data` part.

`packet send --protocol a2a` blocks `restricted` requests. `internal` sources can be sent only as redacted projections.

## HTTP defaults

| Header | Value |
| --- | --- |
| `Content-Type` | `application/json` |
| `Accept` | `application/json` |
| `A2A-Version` | `1.0` |
| `Authorization` | `Bearer <token>` when supplied |

`--record-response-to` records `result.message` as a bus message and maps `result.task.status.state` to the local task state when a local task id is available. Failures are written to `--fail-log` when it is set.

## Local inbound endpoints

`agentbus bus serve` exposes local test endpoints on 127.0.0.1 for development. Its `/a2a/rpc` handler uses the same receive path as `agentbus packet receive --protocol a2a`.

| Path | Meaning |
| --- | --- |
| `/.well-known/agent-card.json?agent=<id>` | Project a local card as an A2A Agent Card. |
| `/a2a/rpc` | Accept `SendMessage` and append it to the bus. |

These endpoints support local testing and dashboard integration. Public A2A serving belongs to an external host.

## Minimum checks

| Command | Checks |
| --- | --- |
| `packet transport --protocol a2a --artifact card --file` | Agent Card required fields, interface, modes, skills. |
| `packet transport --protocol a2a --artifact message --file` | JSON-RPC envelope, `SendMessage`, message id, role, non-empty parts, Part one-of rule. |
