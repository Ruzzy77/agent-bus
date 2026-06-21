// Shared rendering primitives for dashboard.js. Keep this file small and reusable.
window.AgentBusDashboardPrimitives = (() => {
  const esc = s => String(s ?? "").replace(/[&<>\"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const cls = s => String(s ?? "").replace(/[^a-zA-Z0-9_-]/g, "_");
  const byId = id => document.getElementById(id);
  const fmtTime = iso => {
    const d = new Date(iso);
    if (isNaN(d)) return esc(iso);
    const now = new Date();
    const t = d.toLocaleTimeString("ko-KR", {hour:"numeric", minute:"2-digit"});
    if (d.toDateString() === now.toDateString()) return t;
    const sameYear = d.getFullYear() === now.getFullYear();
    const date = d.toLocaleDateString("ko-KR",
      sameYear ? {month:"numeric", day:"numeric"} : {year:"numeric", month:"numeric", day:"numeric"});
    return date + " " + t;
  };
  const fmtAge = sec => {
    if (sec < 90) return "방금";
    if (sec < 5400) return Math.round(sec / 60) + "분 전";
    if (sec < 86400) return Math.round(sec / 3600) + "시간 전";
    return Math.round(sec / 86400) + "일 전";
  };
  const fmtDur = sec => {
    sec = Math.max(0, sec);
    if (sec < 60) return "1분 미만";
    if (sec < 3600) return Math.round(sec / 60) + "분";
    if (sec < 86400) return (sec / 3600).toFixed(1).replace(/\\.0$/, "") + "시간";
    let days = Math.floor(sec / 86400);
    let hours = Math.round((sec % 86400) / 3600);
    if (hours === 24) { days += 1; hours = 0; }
    return hours ? `${days}일 ${hours}시간` : `${days}일`;
  };
  const fmtCompactCount = n => {
    n = Number(n) || 0;
    if (n < 1000) return String(n);
    if (n < 10000) return (n / 1000).toFixed(1).replace(/\\.0$/, "") + "K";
    return Math.round(n / 1000) + "K";
  };

  function attrString(attrs = {}) {
    return Object.entries(attrs)
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .map(([key, value]) => ` ${key}="${esc(value)}"`)
      .join("");
  }

  // Lucide icon subset, sourced from lucide-static v1.21.0 (ISC).
  // Keep dashboard icons in this registry instead of drawing one-off SVGs in feature code.
  const LUCIDE_ICONS = Object.freeze({
    "panel-left": `<rect width="18" height="18" x="3" y="3" rx="2" /><path d="M9 3v18" />`,
    "message-circle": `<path d="M2.992 16.342a2 2 0 0 1 .094 1.167l-1.065 3.29a1 1 0 0 0 1.236 1.168l3.413-.998a2 2 0 0 1 1.099.092 10 10 0 1 0-4.777-4.719" />`,
    "settings": `<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915" /><circle cx="12" cy="12" r="3" />`,
    "monitor": `<rect width="20" height="14" x="2" y="3" rx="2" /><line x1="8" x2="16" y1="21" y2="21" /><line x1="12" x2="12" y1="17" y2="21" />`,
    "sun": `<circle cx="12" cy="12" r="4" /><path d="M12 2v2" /><path d="M12 20v2" /><path d="m4.93 4.93 1.41 1.41" /><path d="m17.66 17.66 1.41 1.41" /><path d="M2 12h2" /><path d="M20 12h2" /><path d="m6.34 17.66-1.41 1.41" /><path d="m19.07 4.93-1.41 1.41" />`,
    "moon": `<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401" />`,
    "lock": `<circle cx="12" cy="16" r="1" /><rect x="3" y="10" width="18" height="12" rx="2" /><path d="M7 10V7a5 5 0 0 1 10 0v3" />`,
    "unlock": `<circle cx="12" cy="16" r="1" /><rect width="18" height="12" x="3" y="10" rx="2" /><path d="M7 10V7a5 5 0 0 1 9.33-2.5" />`,
    "archive": `<rect width="20" height="5" x="2" y="3" rx="1" /><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" /><path d="M10 12h4" />`,
    "trash": `<path d="M10 11v6" /><path d="M14 11v6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />`,
    "send": `<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z" /><path d="m21.854 2.147-10.94 10.939" />`,
    "search": `<path d="m21 21-4.34-4.34" /><circle cx="11" cy="11" r="8" />`,
    "filter": `<path d="M10 20a1 1 0 0 0 .553.895l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .517-1.341L21.74 4.67A1 1 0 0 0 21 3H3a1 1 0 0 0-.742 1.67l7.225 7.989A2 2 0 0 1 10 14z" />`,
    "key": `<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z" /><circle cx="16.5" cy="7.5" r=".5" fill="currentColor" />`,
    "edit": `<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z" /><path d="m15 5 4 4" />`,
    "chevron-down": `<path d="m6 9 6 6 6-6" />`,
    "circle": `<circle cx="12" cy="12" r="10" />`,
    "circle-check": `<circle cx="12" cy="12" r="10" /><path d="m9 12 2 2 4-4" />`,
    "circle-x": `<circle cx="12" cy="12" r="10" /><path d="m15 9-6 6" /><path d="m9 9 6 6" />`,
    "circle-alert": `<circle cx="12" cy="12" r="10" /><line x1="12" x2="12" y1="8" y2="12" /><line x1="12" x2="12.01" y1="16" y2="16" />`,
    "circle-minus": `<circle cx="12" cy="12" r="10" /><path d="M8 12h8" />`,
    "loader-circle": `<path d="M21 12a9 9 0 1 1-6.219-8.56" />`,
    "circle-help": `<circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><path d="M12 17h.01" />`,
    "list": `<path d="M3 5h.01" /><path d="M3 12h.01" /><path d="M3 19h.01" /><path d="M8 5h13" /><path d="M8 12h13" /><path d="M8 19h13" />`,
    "agent": `<rect x="16" y="16" width="6" height="6" rx="1" /><rect x="2" y="16" width="6" height="6" rx="1" /><rect x="9" y="2" width="6" height="6" rx="1" /><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3" /><path d="M12 12V8" />`,
    "bus": `<path d="M8 6v6" /><path d="M15 6v6" /><path d="M2 12h19.6" /><path d="M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3" /><circle cx="7" cy="18" r="2" /><path d="M9 18h5" /><circle cx="16" cy="18" r="2" />`,
    "bridge": `<path d="M12 22v-5" /><path d="M15 8V2" /><path d="M17 8a1 1 0 0 1 1 1v4a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1z" /><path d="M9 8V2" />`,
    "plus": `<path d="M5 12h14" /><path d="M12 5v14" />`,
    "check": `<path d="M20 6 9 17l-5-5" />`,
    "x": `<path d="M18 6 6 18" /><path d="m6 6 12 12" />`,
    "octagon-x": `<path d="m15 9-6 6" /><path d="m9 9 6 6" /><path d="M7.86 2h8.28L22 7.86v8.28L16.14 22H7.86L2 16.14V7.86z" />`,
    "copy": `<rect width="14" height="14" x="8" y="8" rx="2" ry="2" /><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />`,
    "check-check": `<path d="M18 6 7 17l-5-5" /><path d="m22 10-7.5 7.5L13 16" />`,
    "reply": `<path d="M20 18v-2a4 4 0 0 0-4-4H4" /><path d="m9 17-5-5 5-5" />`,
    "ticket": `<path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z" /><path d="M13 5v2" /><path d="M13 17v2" /><path d="M13 11v2" />`,
    "message": `<path d="M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z" />`,
  });
  function icon(name, attrs = {}) {
    const svgAttrs = {
      viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      "stroke-width": "1.9", "stroke-linecap": "round", "stroke-linejoin": "round",
      "aria-hidden": "true", ...attrs,
    };
    svgAttrs.class = ["lucide-icon", attrs.class].filter(Boolean).join(" ");
    return `<svg${attrString(svgAttrs)}>${LUCIDE_ICONS[name] || LUCIDE_ICONS.message}</svg>`;
  }
  function hydrateIcons(root) {
    const scope = root || (typeof document !== "undefined" ? document : null);
    if (!scope) return;
    scope.querySelectorAll("[data-icon]").forEach(el => {
      el.outerHTML = icon(el.dataset.icon, el.dataset.iconClass ? {class: el.dataset.iconClass} : {});
    });
  }

  const ICON_TASK = icon("list");
  const ICON_REPLY = icon("reply");
  const ICON_TICKET = icon("ticket");
  const ICON_MESSAGE = icon("message");
  const ICON_AGENT = icon("agent");
  const ICON_EMPTY = icon("message-circle");
  const ICON_LOCK = icon("lock");
  const ICON_UNLOCK = icon("unlock");
  const ICON_COPY = icon("copy");
  const ICON_COPY_DONE = icon("check");
  const ICON_TRASH = icon("trash");
  const ICON_SEND = icon("send");
  const ICON_CHECK = icon("check");
  const ICON_DBLCHECK = icon("check-check");
  const ICON_X = icon("x");

  const HEALTH_STATE = {ok:"completed", warning:"input_required", problem:"failed"};
  const STATUS_ICONS = {
    submitted:"circle", working:"loader-circle", input_required:"circle-alert",
    completed:"circle-check", failed:"circle-x", canceled:"circle-minus",
  };
  const ID_PILL_ICONS = {task: ICON_TASK, reply: ICON_REPLY, ticket: ICON_TICKET, issue: ICON_TICKET, agent: ICON_AGENT, message: ICON_MESSAGE, id: ICON_MESSAGE};
  let refRoot = "";

  function setTip(el, text) {
    el.dataset.tip = text;
    el.removeAttribute("title");
  }
  function idPill(kind, id, attrs = {}, extraClass = "") {
    if (!id) return "";
    const safeKind = cls(kind || "id");
    const classes = ["chip", "idpill", `idpill-${safeKind}`, extraClass].filter(Boolean).join(" ");
    const icon = ID_PILL_ICONS[kind] || ID_PILL_ICONS.id;
    return `<span class="${classes}" data-id-kind="${esc(kind || "id")}"${attrString(attrs)}>${icon}<span class="idpill-text">${esc(id)}</span></span>`;
  }
  function statusMark(state, label = "", extraClass = "") {
    const safe = STATUS_ICONS[state] ? state : "input_required";
    const classes = ["todo-mark", "status-mark", safe, extraClass].filter(Boolean).join(" ");
    return `<span class="${classes}" aria-label="${esc(label || safe)}">${icon(STATUS_ICONS[safe])}</span>`;
  }
  function healthMark(kind, label) {
    const k = HEALTH_STATE[kind] ? kind : "warning";
    return statusMark(HEALTH_STATE[k], label || k, "health-mark");
  }
  function setRefRoot(root) {
    refRoot = root || "";
  }
  function splitRefs(refs = []) {
    return refs.flatMap(r => String(r).split(",")).map(s => s.trim()).filter(Boolean);
  }
  function renderRef(p) {
    let s = p.trim();
    if (refRoot && s.startsWith(refRoot + "/")) s = s.slice(refRoot.length + 1);
    const m = s.match(/^([\w./-]+\/)(.*)$/);
    const dir = m ? m[1] : "", base = m ? m[2] : s;
    return `<span class="ref"><span class="dir">${esc(dir)}</span><span class="base">${esc(base)}</span></span>`;
  }
  function renderRefsExpander(refs = []) {
    const items = splitRefs(refs);
    if (!items.length) return "";
    return `<details class="refs-expander">` +
      `<summary><span class="refs-label">참조 ${items.length}개<span class="refs-caret"></span></span></summary>` +
      `<div class="refs-list">${items.map(renderRef).join("")}</div>` +
      `</details>`;
  }
  function securityMark(row) {
    const level = String(row.sensitivity || "");
    if (!level) return "";
    const label = level === "restricted"
      ? (row.redacted === false ? "보안 원문" : "보안 처리됨")
      : "보안";
    return `<span class="security-mark ${cls(level)}" data-tip="${esc(label)}" aria-label="${esc(label)}">${ICON_LOCK}</span>`;
  }

  return {
    esc, cls, byId, fmtTime, fmtAge, fmtDur, fmtCompactCount, icon, hydrateIcons,
    setTip, idPill, statusMark, healthMark, setRefRoot, splitRefs, renderRefsExpander, securityMark,
    ICON_REPLY, ICON_EMPTY, ICON_COPY, ICON_COPY_DONE, ICON_TRASH, ICON_SEND, ICON_CHECK, ICON_DBLCHECK, ICON_X, ICON_UNLOCK,
  };
})();
