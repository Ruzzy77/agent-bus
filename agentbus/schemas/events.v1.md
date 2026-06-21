# agentbus.event.v1

`agentbus bridge events` exposes bus changes as JSON events with outbound-safe redaction. Bridge handlers use the stream to trigger agents, call webhooks, or map bus state to external protocols.

## Shape

```json
{
  "version": "agentbus.event.v1",
  "id": "messages:1:2026-06-15T00:00:00+00:00:abc123",
  "position": "messages:1:2026-06-15T00:00:00+00:00:abc123",
  "time": "2026-06-15T00:00:00+00:00",
  "type": "message.created",
  "source": "messages",
  "actor": "user",
  "target": "my-agent",
  "object": {"type": "message", "id": "abc123"},
  "data": {}
}
```

| Field | Meaning |
| --- | --- |
| `version` | Event contract version. |
| `id`, `position` | Source stream position, time, and object id. |
| `type` | Normalized event type. Prefix filters such as `ticket.*` are accepted. |
| `source` | Source capsule stream. |
| `actor` | Sender, agent, or `by` field. |
| `target` | Receiver, assignee, or empty string. |
| `object` | Primary object touched by the event. |
| `data` | Source row projection. `restricted` content is redacted; `internal` content is redacted on bridge output paths. |

`data` may include `sensitivity` and redaction metadata. Bridge handlers use those fields before webhooks, SDK bridge calls, or protocol transfer.

## Event types

| Type | Source |
| --- | --- |
| `message.created`, `message.deleted`, `message.acked`, `message.delivered` | Message streams. |
| `task.created`, `task.state`, `task.deleted` | Task stream. |
| `ticket.created`, `ticket.accepted`, `ticket.rejected` | Ticket stream. |

## Bridge handler rule

The event is a trigger signal. The bridge handler reloads the bus or referenced files before acting.
