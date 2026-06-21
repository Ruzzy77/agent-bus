# demo-bus

Safe sample bus for dashboard screenshots and local UI checks. The fixture shows Key Context, teammate reports, task and ticket states, bridge profiles, gateway cards, restricted records, and packet/security boundaries without packaging raw restricted content or fixed credentials.

Run it from a copy and migrate the copy into a capsule so dashboard send/delete/auth actions stay local to the temporary demo bus:

```bash
DEMO_WORK=$(mktemp -d "${TMPDIR:-/tmp}/agentbus-demo.XXXXXX")
cp -R "$(agentbus resource path demo-bus)" "$DEMO_WORK/bus"
echo "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus migrate --from "$DEMO_WORK/bus"
AGENTBUS_BUS_DIR="$DEMO_WORK/bus" agentbus bus serve --port 8791
```

In another shell, issue a temporary viewer token and enter the printed `viewer` and `token` in dashboard Settings. The token lasts 1 hour by default. Restricted demo messages and tickets open after authentication inside the copied capsule.

```bash
export AGENTBUS_BUS_DIR=<printed-demo-bus-path>
agentbus auth demo
```

Refresh agent activity times on a copied bus when preparing a screenshot:

```bash
export AGENTBUS_BUS_DIR=/path/to/copied-demo-bus
agentbus agent set --name codex-lead --state running --task t-demo-lead --note "demo screenshot"
agentbus agent set --name codex-docs --state waiting --task t-demo-docs --note "waiting for final fixture check"
```
