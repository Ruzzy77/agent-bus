# a2a-rpc.v1

`a2a-rpc.v1` is the A2A-facing projection of raw bus messages. It creates and checks A2A 1.0 `SendMessage` JSON-RPC request bodies, sends them with stdlib HTTP, and can record responses back to the raw bus.

It does not provide public hosting, OAuth, streaming, task polling, or push delivery.

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

`a2a-post` refuses `confidential` and `restricted` requests unless `--allow-sensitive` is set.

## HTTP defaults

| Header | Value |
| --- | --- |
| `Content-Type` | `application/json` |
| `Accept` | `application/json` |
| `A2A-Version` | `1.0` |
| `Authorization` | `Bearer <token>` when supplied |

`--record-response-to` records `result.message` as a bus message and maps `result.task.status.state` to the local task state when a local task id is available. Failures are written to `--fail-log` when it is set.

## Local inbound endpoints

`agentbus serve` exposes local test endpoints on 127.0.0.1 only.

| Path | Meaning |
| --- | --- |
| `/.well-known/agent-card.json?agent=<id>` | Project a local card as an A2A Agent Card. |
| `/a2a/rpc` | Accept `SendMessage` and append it to the raw bus. |

These endpoints are for local testing and dashboard integration. They are not a public A2A server.

## Minimum checks

| Command | Checks |
| --- | --- |
| `a2a-card-check` | Agent Card required fields, interface, modes, skills. |
| `a2a-rpc-check` | JSON-RPC envelope, `SendMessage`, message id, role, non-empty parts, Part one-of rule. |
