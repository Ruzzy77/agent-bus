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
    if (sec < 60) return Math.round(sec) + "초";
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

  const ICON_TASK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/></svg>`;
  const ICON_REPLY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 7l-5 5 5 5"/><path d="M4 12h11a5 5 0 0 1 5 5v1"/></svg>`;
  const ICON_TICKET = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4V9z"/><path d="M9 7v12"/></svg>`;
  const ICON_MESSAGE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H8l-4 4V5z"/></svg>`;
  const ICON_AGENT = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="7" r="3"/><circle cx="7" cy="17" r="2.6"/><circle cx="17" cy="17" r="2.6"/><path d="M10.6 9.7 8.2 14.7M13.4 9.7l2.4 5M9.6 17h4.8"/></svg>`;
  const ICON_EMPTY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 11.3a8 8 0 0 1-8.6 8 8.7 8.7 0 0 1-3.6-.8L3.5 20l1.5-4.8a8 8 0 0 1-.8-3.6 8 8 0 0 1 8-7.6 8 8 0 0 1 8.3 7.3z"/></svg>`;
  const ICON_LOCK = `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17 9V7A5 5 0 0 0 7 7v2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1Zm-8 0V7a3 3 0 0 1 6 0v2H9Z"/></svg>`;
  const ICON_UNLOCK = `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17 9h1a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h9V7a3 3 0 0 0-5.78-1.14 1 1 0 1 1-1.85-.76A5 5 0 0 1 17 7v2Zm-5 4a1.75 1.75 0 0 0-.75 3.33V18h1.5v-1.67A1.75 1.75 0 0 0 12 13Z"/></svg>`;
  const ICON_COPY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10"/></svg>`;
  const ICON_COPY_DONE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4 4L19 7"/></svg>`;
  const ICON_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13"/></svg>`;
  const ICON_SEND = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 3 10.5 13.5"/><path d="M21 3l-6.5 18-4-8-8-4z"/></svg>`;
  const ICON_CHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4 4L19 6.5"/></svg>`;
  const ICON_DBLCHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 12.5l4 4L15 6.5"/><path d="M9.5 12.5l.4.4M13 16.5L22.5 6.5"/></svg>`;
  const ICON_X = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>`;

  const HEALTH_STATE = {ok:"completed", warning:"input_required", problem:"failed"};
  const ID_PILL_ICONS = {task: ICON_TASK, reply: ICON_REPLY, ticket: ICON_TICKET, issue: ICON_TICKET, agent: ICON_AGENT, message: ICON_MESSAGE, id: ICON_MESSAGE};
  let refRoot = "";

  function attrString(attrs = {}) {
    return Object.entries(attrs)
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .map(([key, value]) => ` ${key}="${esc(value)}"`)
      .join("");
  }
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
  function healthMark(kind, label) {
    const k = HEALTH_STATE[kind] ? kind : "warning";
    return `<span class="todo-mark health-mark ${HEALTH_STATE[k]}" aria-label="${esc(label || k)}"></span>`;
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
    esc, cls, byId, fmtTime, fmtAge, fmtDur, fmtCompactCount,
    setTip, idPill, healthMark, setRefRoot, splitRefs, renderRefsExpander, securityMark,
    ICON_REPLY, ICON_EMPTY, ICON_COPY, ICON_COPY_DONE, ICON_TRASH, ICON_SEND, ICON_CHECK, ICON_DBLCHECK, ICON_X, ICON_UNLOCK,
  };
})();
