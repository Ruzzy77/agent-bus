# demo-bus

Safe sample bus for dashboard screenshots and local UI checks.

Run it from a copy and migrate the copy into a capsule so dashboard send/delete/auth actions stay local to the temporary demo bus:

```bash
DEMO_WORK=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-demo.XXXXXX")
cp -R "$(agentbus resource path demo-bus)" "$DEMO_WORK/bus"
echo "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus migrate --from "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus serve --port 8791
```

In another shell, issue a temporary viewer token and enter the printed `viewer` and `token` in dashboard Settings. The token lasts 1 hour by default, no fixed demo credential is packaged, and the demo restricted messages and ticket open after authentication:

```bash
export AGENTBUS_BUS_DIR=<printed-demo-bus-path>
agentbus auth demo
```

Refresh agent activity times on a copied bus:

```bash
DEMO_WORK=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-demo.XXXXXX")
cp -R "$(agentbus resource path demo-bus)" "$DEMO_WORK/bus"
echo "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus migrate --from "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus serve --port 8791
```

In another shell:

```bash
export AGENTBUS_BUS_DIR=/path/to/copied-demo-bus
agentbus agent set --agent codex --state running --task t-demo-review --note "demo screenshot"
agentbus agent set --agent claude --state waiting --task t-demo-ops --note "waiting for approval"
```
