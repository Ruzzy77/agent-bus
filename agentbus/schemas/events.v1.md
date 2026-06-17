# agentbus.event.v1

`agentbus events` exposes raw bus changes as JSON events. Adapters use the stream to wake agents, call webhooks, or map bus state to external protocols.

## Shape

```json
{
  "version": "agentbus.event.v1",
  "id": "messages:1:2026-06-15T00:00:00+00:00:abc123",
  "cursor": "messages:1:2026-06-15T00:00:00+00:00:abc123",
  "time": "2026-06-15T00:00:00+00:00",
  "type": "message.created",
  "source": "messages.jsonl",
  "actor": "user",
  "target": "my-agent",
  "object": {"type": "message", "id": "abc123"},
  "data": {}
}
```

| Field | Meaning |
| --- | --- |
| `version` | Event contract version. |
| `id`, `cursor` | Source log, line number, time, and object id. |
| `type` | Normalized event type. Prefix filters such as `ticket.*` are accepted. |
| `source` | Source JSONL file. |
| `actor` | Sender, agent, or `by` field. |
| `target` | Receiver, assignee, or empty string. |
| `object` | Primary object touched by the event. |
| `data` | Original source row. |

`data` may include `sensitivity` and `retention`. External adapters must check those fields before webhooks, SDK wakeups, or protocol transfer.

## Event types

| Type | Source |
| --- | --- |
| `message.created`, `message.deleted`, `message.acked`, `message.delivered` | Message logs. |
| `task.created`, `task.state`, `task.deleted` | Task log. |
| `ticket.created`, `ticket.accepted`, `ticket.rejected` | Ticket log. |

## Adapter rule

The event is a wake signal, not authority. The adapter rereads the bus or referenced files before acting.
