# demo-bus

Safe sample bus for dashboard screenshots and local UI checks.

Use it read-only:

```bash
AGENTBUS_BUS_DIR="$(agentbus examples demo-bus)" agentbus serve --port 8791
```

Copy it before editing or before refreshing agent activity times:

```bash
DEMO_WORK=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-demo.XXXXXX")
cp -R "$(agentbus examples demo-bus)" "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus status --agent codex --state running --task t-demo-review --note "demo screenshot"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus status --agent claude --state waiting --task t-demo-ops --note "waiting for approval"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus serve --port 8791
```
