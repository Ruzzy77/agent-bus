# Agent-Bus Dashboard Design

Agent-Bus dashboard is a local workbench for agent collaboration. Its visual language should stay quiet, compact, and operational: the UI supports reading state, following work, and making small decisions without drawing attention to itself.

## Direction

- Use a system-app feel: SF-style type, restrained spacing, soft cards, one blue accent, and muted secondary text.
- Let structure carry meaning. Cards, pills, dividers, icons, and motion should explain state or interaction.
- Keep the interface calm in dense states. Prefer fewer visible controls, hover overlays, compact metadata, and collapsed detail.
- Match light and dark mode from the same token set.

## Canonical primitives

- Surfaces: `--bg`, `--card`, `--bar-bg`, `--hover`, `--line`, `--hair`, `--shadow`.
- Text: `--ink`, `--dim`, `--mid`.
- Accent and state: `--accent`, `--running`, `--waiting`, `--done`, `--error`.
- Shape: `--radius-control` for controls and side cards, `--radius-card` for message cards, `--radius-pill` for chips, `--radius-menu` for popovers.
- Motion: use `--ease-ui` and the named transition tokens before adding a new timing.

## Component grammar

- `iconbtn` is the base for icon-only controls.
- `chip idpill` is the only ID/reference pill style for task, ticket, issue, agent, reply, and message IDs.
- `tag` is for semantic labels such as `note`, `report`, and `request`. Keep it flatter than ID pills so filled-pill emphasis is reserved for references and selected controls.
- `security-mark` is a lock-only marker with tooltip text. Use the Apple-style semantic palette for marker colors (`#fdbc00` yellow, `#818186` gray) instead of reusing request colors.
- `todo-mark` is the shared state marker. `health-mark` reuses it for agent, skill, bridge, and gateway status.
- `summary-card` is the base for side-panel cards: completed work, agents, skills, bridge profiles, and gateways.
- `inline-actions` is the shared translucent hover overlay for per-card actions.
- `seg` and `side-tabs` are the segmented-control family. Selected thumbs use `--segment-thumb`.
- `refs-expander` is the collapsed reference-file pattern.
- `panel-empty` is the neutral empty state for side-panel sections. Empty text should not borrow card, task, or agent classes.
- `/static/dashboard-primitives.js` owns reusable render helpers such as escaping, ID pills, status marks, reference expanders, security marks, shared icons, and time formatting. Keep feature state and network behavior in `/static/dashboard.js`.

## Before adding UI

1. Find the nearest existing primitive above and reuse it.
2. Add a new class only when an existing primitive cannot express the behavior.
3. Put color, radius, shadow, and transition changes behind variables unless the value is intrinsic to one component.
4. Check the new element in light mode, dark mode, docked side panel, floating side panel, and a narrow viewport.
