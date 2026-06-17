const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
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
const fmtAge = sec => sec < 90 ? "방금" : sec < 5400 ? Math.round(sec/60) + "분 전" : Math.round(sec/3600) + "시간 전";

function fitProjectBadge() {
  const header = document.querySelector("header");
  const proj = byId("project");
  if (!header || !proj || !proj.textContent) return;
  proj.classList.remove("project-hidden");
  if (header.scrollWidth > header.clientWidth + 1) proj.classList.add("project-hidden");
}

// ID pill 아이콘. 같은 종류의 식별자는 같은 렌더러를 통해 표시한다.
const ICON_TASK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/></svg>`;
const ICON_REPLY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 7l-5 5 5 5"/><path d="M4 12h11a5 5 0 0 1 5 5v1"/></svg>`;
const ICON_TICKET = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4V9z"/><path d="M9 7v12"/></svg>`;
const ICON_MESSAGE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H8l-4 4V5z"/></svg>`;
const ICON_EMPTY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 11.3a8 8 0 0 1-8.6 8 8.7 8.7 0 0 1-3.6-.8L3.5 20l1.5-4.8a8 8 0 0 1-.8-3.6 8 8 0 0 1 8-7.6 8 8 0 0 1 8.3 7.3z"/></svg>`;
const ICON_LOCK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>`;
const ICON_COPY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10"/></svg>`;
const ICON_COPY_DONE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4 4L19 7"/></svg>`;
const ICON_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13"/></svg>`;
// ack 체크 (단일 / 전체확인 더블체크)
const ICON_CHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4 4L19 6.5"/></svg>`;
const ICON_DBLCHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 12.5l4 4L15 6.5"/><path d="M9.5 12.5l.4.4M13 16.5L22.5 6.5"/></svg>`;

// 펼친 메시지 상태를 유지한다.
const expanded = new Set();
function onToggle(id, open) { if (open) expanded.add(id); else expanded.delete(id); }
let replyOpenId = null, replyDraft = "";

let AGENT_NAMES = [];
let RECIPIENT_NAMES = [];
let RECIPIENT_OPTIONS = [];

// 참조 경로는 작업 루트를 줄이고 파일명을 강조한다.
let STATE_ROOT = "";
function splitRefs(refs = []) {
  return refs.flatMap(r => String(r).split(",")).map(s => s.trim()).filter(Boolean);
}
function renderRef(p) {
  let s = p.trim();
  if (STATE_ROOT && s.startsWith(STATE_ROOT + "/")) s = s.slice(STATE_ROOT.length + 1);
  const m = s.match(/^([\w./-]+\/)(.*)$/);
  const dir = m ? m[1] : "", base = m ? m[2] : s;
  return `<span class="ref"><span class="dir">${esc(dir)}</span><span class="base">${esc(base)}</span></span>`;
}

function renderAcks(ackers, sender) {
  if (!ackers.length) return "";
  const expected = AGENT_NAMES.filter(a => a !== sender);
  if (expected.length > 0 && expected.every(a => ackers.includes(a))) {
    return `<span class="ackchip ackall" data-tip="전체 확인: ${esc(ackers.join(", "))}">${ICON_DBLCHECK}</span>`;
  }
  const shown = ackers.slice(0, 2).map(a => `<span class="ackchip">${ICON_CHECK}${esc(a)}</span>`).join("");
  const hidden = ackers.slice(2);
  if (!hidden.length) return shown;
  const pop = hidden.map(a => `<span>${ICON_CHECK}${esc(a)}</span>`).join("");
  return shown + `<span class="ackchip ackmore" tabindex="0">+${hidden.length}<span class="ackmore-pop">${pop}</span></span>`;
}

function securityChip(row) {
  const level = String(row.sensitivity || "");
  if (!level) return "";
  return `<span class="chip security ${cls(level)}">${ICON_LOCK}<span>${esc(level)}</span></span>`;
}

const ID_PILL_ICONS = {task: ICON_TASK, reply: ICON_REPLY, ticket: ICON_TICKET, issue: ICON_TICKET, message: ICON_MESSAGE, id: ICON_MESSAGE};
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

function splitMdTableRow(line) {
  let row = String(line || "").trim();
  if (row.startsWith("|")) row = row.slice(1);
  if (row.endsWith("|")) row = row.slice(0, -1);
  const cells = [];
  let cur = "", escaped = false;
  for (const ch of row) {
    if (escaped) {
      cur += ch;
      escaped = false;
    } else if (ch === "\\") {
      escaped = true;
      cur += ch;
    } else if (ch === "|") {
      cells.push(cur.trim());
      cur = "";
    } else cur += ch;
  }
  cells.push(cur.trim());
  return cells;
}

function mdTableSeparator(cells) {
  if (cells.length < 2) return false;
  return cells.every(cell => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, "")));
}

function mdTableAlign(cell) {
  const text = cell.replace(/\s+/g, "");
  if (text.startsWith(":") && text.endsWith(":")) return "center";
  if (text.endsWith(":")) return "right";
  return "left";
}

function mdTablePlain(value) {
  return String(value || "")
    .replace(/@@KTEX\d+@@/g, "")
    .replace(/\[([^\]]+?)\]\([^)]+\)/g, "$1")
    .replace(/[`*_~]/g, "")
    .replace(/&(?:amp|lt|gt|quot);/g, "x")
    .replace(/\s+/g, " ")
    .trim();
}

function mdTableColumnKind(header, cells) {
  const h = mdTablePlain(header);
  const values = [h, ...cells.map(mdTablePlain)];
  const body = cells.map(mdTablePlain).filter(Boolean);
  const lengths = values.map(v => v.length);
  const maxLen = lengths.length ? Math.max(...lengths) : 0;
  const avgBody = body.length ? body.reduce((sum, v) => sum + v.length, 0) / body.length : 0;
  const wordCount = v => v.split(/\s+/).filter(Boolean).length;
  const longPhrase = body.some(v => v.length >= 32 || wordCount(v) >= 5);
  const isPathToken = v =>
    /^(https?:\/\/|~?\/|\.{1,2}\/|[\w.-]+\/[\w./-]+|[\w.-]+\.[a-z0-9]{1,8})$/i.test(v.trim());
  const isCompactPath = v => {
    const parts = v.split(/\s+/).filter(Boolean);
    return parts.length <= 2 && parts.some(isPathToken);
  };
  const pathCount = body.filter(isCompactPath).length;
  if (body.length > 0 && pathCount / body.length >= 0.6) return "path";
  if (longPhrase) return "text";
  if (maxLen <= 12 && avgBody <= 10) return "short";
  if (maxLen <= 28 && avgBody <= 18) return "medium";
  return "text";
}

function renderMdTables(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const header = splitMdTableRow(lines[i]);
    const sep = i + 1 < lines.length ? splitMdTableRow(lines[i + 1]) : [];
    if (!lines[i].includes("|") || !mdTableSeparator(sep)) {
      out.push(lines[i]);
      continue;
    }
    const width = header.length;
    const aligns = sep.slice(0, width).map(mdTableAlign);
    const rows = [];
    i += 2;
    while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
      rows.push(splitMdTableRow(lines[i]));
      i++;
    }
    i--;
    const bodyRows = rows.map(row => {
      const padded = row.slice(0, width);
      while (padded.length < width) padded.push("");
      return padded;
    });
    const colKinds = header.slice(0, width).map((value, idx) =>
      mdTableColumnKind(value, bodyRows.map(row => row[idx] || "")));
    const minByKind = { short:72, medium:140, path:220, text:260 };
    const tableMin = Math.max(180, colKinds.reduce((sum, kind) => sum + (minByKind[kind] || 180), 0));
    const cell = (tag, value, idx) => {
      const kind = colKinds[idx] || "text";
      return `<${tag} class="md-align-${aligns[idx] || "left"} md-col-${kind}">${value || ""}</${tag}>`;
    };
    const headerHtml = header.slice(0, width).map((value, idx) => cell("th", value, idx)).join("");
    const bodyHtml = bodyRows.map(row =>
      `<tr>${row.map((value, idx) => cell("td", value, idx)).join("")}</tr>`).join("");
    out.push(`<div class="md-table-wrap"><table class="md-table" style="--md-cols:${width};--md-min:${tableMin}px">` +
      `<thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`);
  }
  return out.join("\n");
}

// 본문을 escape한 뒤 코드·수식·경량 마크다운을 렌더한다.
function renderBody(raw) {
  let s = esc(raw);
  const keep = [];
  const stash = (html) => "@@KTEX" + (keep.push(html) - 1) + "@@";
  s = s.replace(/```([\s\S]*?)```/g, (_, c) => stash('<pre class="md-pre"><code>' + c.trim() + "</code></pre>"));
  s = s.replace(/`([^`\n]+?)`/g, (_, c) => stash('<code class="md-code">' + c + "</code>"));
  s = s.replace(/\$\$([\s\S]+?)\$\$/g, (m) => stash(m));
  s = s.replace(/\$(?!\s)([^\n$]+?)(?<!\s)\$/g, (m) => stash(m));
  s = renderMdTables(s);
  s = s.replace(/\*\*([^\n]+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^\s*][^\n*]*?)\*(?!\*)/g, "$1<em>$2</em>");
  s = s.replace(/\[([^\]]+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  s = s.replace(/^\s*#{1,3}\s+(.+)$/gm, '<div class="md-h">$1</div>');
  s = s.replace(/^\s*[-*]\s+(.+)$/gm, '<div class="md-li">$1</div>');
  for (let i = keep.length - 1; i >= 0; i--) s = s.split("@@KTEX" + i + "@@").join(keep[i]);
  s = s.replace(/\n+(<(?:div class="md-|pre class="md-))/g, "$1");
  s = s.replace(/(<\/(?:div|pre)>|<\/table><\/div>)\n+/g, "$1");
  return s;
}

function messageCopyText(m) {
  const parts = [];
  const subject = String(m?.subject || "").trim();
  const body = String(m?.body || "").trim();
  const refs = splitRefs(m?.refs || []);
  if (subject) parts.push(subject);
  if (body) parts.push(body);
  if (refs.length) parts.push("Refs:\n" + refs.join("\n"));
  return parts.join("\n\n").trim();
}

function stopDetailText(detail) {
  if (detail === undefined || detail === null || detail === "") return "";
  if (typeof detail === "string") return detail;
  try { return JSON.stringify(detail); }
  catch { return String(detail); }
}

function stopBannerMode(stop) {
  return stop?.reason === "loop_closed" ? "closed" : "requested";
}

function loopStatusMode(stop) {
  return stop ? stopBannerMode(stop) : "open";
}

function loopStatusLabel(stop) {
  const mode = loopStatusMode(stop);
  if (mode === "closed") return "루프 종료됨";
  if (mode === "requested") return "정지 요청됨";
  return "루프 열림";
}

function renderStopBanner(stop) {
  const mode = loopStatusMode(stop);
  const label = loopStatusLabel(stop);
  if (!stop) {
    return `<form class="stop-inner stop-form" data-stop-form>
      <div class="stop-copy">
        <span class="stop-label">${label}</span>
        <span class="stop-detail" data-tip="정지 사유를 입력하면 협업 루프에 정지 요청을 보냅니다.">정지 사유를 입력하면 협업 루프에 정지 요청을 보냅니다.</span>
      </div>
      <input class="stop-reason" id="stop-reason" autocomplete="off" placeholder="정지 사유 · 기본 user_stop">
      <button class="stop-action stop-submit" type="submit">요청</button>
    </form>`;
  }
  const detail = stopDetailText(stop?.detail);
  const closed = mode === "closed";
  const meta = [stop?.by, stop?.reason].filter(Boolean).join(" · ");
  const time = stop?.time ? fmtTime(stop.time) : "";
  const detailHtml = detail ? `<span class="stop-detail" data-tip="${esc(detail)}">${esc(detail)}</span>` : "";
  return `<div class="stop-inner">
    <div class="stop-copy">
      <span class="stop-label">${label}</span>
      ${meta ? `<span class="stop-meta">${esc(meta)}</span>` : ""}
      ${time ? `<span class="stop-time">${esc(time)}</span>` : ""}
      ${detailHtml}
    </div>
    ${closed ? "" : `<button class="stop-action stop-clear" type="button" data-clear-stop>해제</button>`}
  </div>`;
}

function renderMessageRefs(refs = []) {
  const html = splitRefs(refs).map(renderRef).join("");
  return html ? `<div class="refs">${html}</div>` : "";
}
function renderMessageMeta(m) {
  const metaBits = [idPill("message", m.id, {"data-message": m.id})];
  if (m.task_id) metaBits.push(idPill("task", m.task_id, {"data-task": m.task_id}));
  if (m.reply_to) metaBits.push(idPill("reply", m.reply_to, {"data-reply": m.reply_to}));
  return `<div class="msg-meta">${metaBits.join("")}</div>`;
}
function renderMessageContent(m) {
  const body = m.body || "";
  const subject = m.subject || "";
  const bodyHtml = body ? `<div class="body">${renderBody(body)}</div>` : "";
  const refsHtml = renderMessageRefs(m.refs || []);
  const metaHtml = renderMessageMeta(m);
  if (!subject) return `${bodyHtml.replace('class="body"', 'class="body nosubj"')}${refsHtml}${metaHtml}`;
  return `<details data-msgid="${esc(m.id)}" ${expanded.has(m.id) ? "open" : ""}>
         <summary><span class="subject">${esc(subject)}</span><span class="disc-caret"></span></summary>
         <div class="detail">${bodyHtml}${refsHtml}${metaHtml}</div>
       </details>`;
}
function renderMessageActions(m, canReply) {
  const copyBtn = `<button class="msg-act msg-copy" type="button" data-copy-message="${esc(m.id)}" ` +
    `data-tip="내용 복사" aria-label="내용 복사">${ICON_COPY}</button>`;
  const replyBtn = canReply
    ? `<button class="msg-act msg-reply" type="button" data-id="${esc(m.id)}" ` +
      `data-tip="답장" aria-label="답장">${ICON_REPLY}</button>`
    : "";
  const deleteBtn = `<button class="msg-act msg-del" type="button" data-delete-message="${esc(m.id)}" ` +
    `data-tip="삭제" aria-label="삭제">${ICON_TRASH}</button>`;
  return copyBtn + replyBtn + deleteBtn;
}
function renderReplyBox(m, canReply) {
  if (!canReply || replyOpenId !== m.id) return "";
  return `<div class="reply-box" data-to="${esc(m.from)}" data-reply="${esc(m.id)}">
    <div class="reply-row">
      <input class="reply-in" type="text" placeholder="${esc(m.from)}에게 답장…">
      <button class="reply-go" type="button">보내기</button>
    </div>
    <div class="mention-menu"></div>
  </div>`;
}
function renderMsg(m, acks) {
  if (m._decode_error) return `<div class="card msg"><div class="body">${esc(m._decode_error)}</div></div>`;
  const ackers = acks[m.id] || [];
  const canReply = m.from && m.from !== "user";
  return `<div class="card msg" data-id="${esc(m.id)}">
    <span class="msg-actions">${renderMessageActions(m, canReply)}</span>
    <div class="head">
      <span class="route">${esc(m.from)} → ${esc(m.to)}</span>
      <span class="chip kind ${cls(m.kind)}">${esc(m.kind)}</span>
      ${securityChip(m)}
      <span>${fmtTime(m.time)}</span>
      ${renderAcks(ackers, m.from)}
    </div>
    ${renderMessageContent(m)}
    ${renderReplyBox(m, canReply)}
  </div>`;
}

let TASK_STATES = [];
let openTaskDD = null;
const PANEL_LIMIT = {tasks: 3, tickets: 3, completed: 3, agents: 3};
const panelExpanded = {tasks: false, tickets: false, completed: false, agents: false};
const taskTextOpen = new Set();
const STATE_LABEL = {submitted:"대기", working:"진행 중", input_required:"확인 필요",
                     completed:"완료", failed:"오류", canceled:"취소"};
function renderTicket(ticket) {
  const id = ticket.issue_id || ticket.ticket_id;
  const refs = splitRefs(ticket.refs || []);
  const refsHtml = refs.length
    ? `<div class="todo-desc">${refs.map(renderRef).join("")}</div>`
    : "";
  return `<div class="todo ticket" data-ticket="${esc(id)}">
    <span class="todo-mark submitted"></span>
    <div class="todo-body">
      <div class="todo-text">${esc(ticket.title || "(제목 없음)")}</div>
      ${ticket.body ? `<div class="todo-desc">${esc(ticket.body)}</div>` : ""}
      ${refsHtml}
      <div class="todo-meta">
        ${idPill(ticket.issue_id ? "issue" : "ticket", id, {"data-ticket": id}, "idpill-compact")}
        ${securityChip(ticket)}
        <span>${fmtTime(ticket.created_at)}</span>
      </div>
    </div>
    <div class="todo-actions">
      <button type="button" class="todo-run" data-tip="진행" aria-label="진행" data-accept-ticket="${esc(id)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 6.5"/></svg>
      </button>
      <button type="button" class="todo-del" data-tip="삭제" aria-label="삭제" data-reject-ticket="${esc(id)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>
      </button>
    </div>
  </div>`;
}
function renderTask(t) {
  const assignStr = (t.assign || []).length ? t.assign.map(esc).join(", ") : "";
  const c = t.created_at ? new Date(t.created_at).getTime() / 1000 : "";
  const u = t.updated_at ? new Date(t.updated_at).getTime() / 1000 : "";
  const opts = TASK_STATES.map(s =>
    `<div class="tdd-opt ${s === t.state ? "sel" : ""}" data-task="${esc(t.task_id)}" data-state="${esc(s)}">` +
    `<span class="tdot ${cls(s)}"></span>${STATE_LABEL[s] || s}</div>`).join("");
  const descHtml = t.note
    ? `<div class="todo-desc${taskTextOpen.has(t.task_id) ? "" : " clamp"}">${esc(t.note)}</div>` +
      `<button type="button" class="todo-more" hidden>더보기</button>`
    : "";
  return `<div class="todo ${cls(t.state)}" data-task="${esc(t.task_id)}">
    <span class="todo-mark ${cls(t.state)}"></span>
    <div class="todo-body">
      <div class="todo-text">${esc(t.title || "(제목 없음)")}</div>
      ${descHtml}
      <div class="todo-meta">
        ${idPill("task", t.task_id, {"data-task": t.task_id}, `idpill-compact${filterTasks.has(t.task_id) ? " on" : ""}`)}
        ${securityChip(t)}
        <span class="todo-time" data-c="${c}" data-u="${u}" data-s="${esc(t.state)}"></span>
        ${assignStr ? `<span class="todo-rest">${assignStr}</span>` : ""}
      </div>
    </div>
    <div class="todo-actions">
      <button type="button" class="todo-del" data-tip="삭제" aria-label="삭제" data-delete-task="${esc(t.task_id)}">${ICON_TRASH}</button>
      <div class="tdd ${openTaskDD === t.task_id ? "open" : ""}" data-task="${esc(t.task_id)}">
        <button type="button" class="tdd-btn">${esc(STATE_LABEL[t.state] || t.state)}<span class="dd-caret"></span></button>
        <div class="tdd-menu">${opts}</div>
      </div>
    </div>
  </div>`;
}

function renderCompletedTask(t, reportInfo = {}) {
  const reportCount = reportInfo.report_count || 0;
  const latestReport = latestReportTime(reportInfo);
  return `<div class="completed-card ${filterTasks.has(t.task_id) ? "on" : ""}" data-task="${esc(t.task_id)}">
    <div class="summary-head">
      <span class="summary-title">${esc(t.title || reportInfo.title || "(제목 없음)")}</span>
    </div>
    <div class="summary-meta">
      ${idPill("task", t.task_id, {"data-task": t.task_id}, "idpill-compact")}
      <span>보고 ${esc(reportCount)}건</span>
      <span>${latestReport ? fmtTime(latestReport) : "-"}</span>
    </div>
  </div>`;
}

function latestReportTime(reportInfo = {}) {
  const times = (reportInfo.reports || []).map(r => String(r.time || "")).filter(Boolean).sort();
  return times.length ? times[times.length - 1] : "";
}

function renderAgent(name, a) {
  const task = a.task ? idPill("task", a.task, {"data-task": a.task}, "agent-task") : "";
  return `<div class="agent ${filterAgents.has(name) ? "on" : ""}" data-agent="${esc(name)}" data-hb="${a.heartbeat || ""}">
    <div class="summary-head agent-head">
      <span class="summary-title agent-name">${esc(name)}</span>
      <span class="agent-status">
        <span class="state ${cls(a.state)}">${esc(AGENT_STATE_LABEL[a.state] || a.state)}</span>
        <span class="beat"><span class="age"></span></span>
      </span>
    </div>
    ${task ? `<div class="summary-meta agent-meta">${task}</div>` : ""}
    ${a.note ? `<div class="agent-note">${esc(a.note)}</div>` : ""}
    <div class="agent-actions">
      <button type="button" class="todo-del" data-tip="제거" aria-label="제거" data-delete-agent="${esc(name)}">${ICON_TRASH}</button>
    </div>
  </div>`;
}
function updateAgentAges(now) {
  for (const card of document.querySelectorAll("#agents .agent")) {
    const beat = card.querySelector(".beat"), ageEl = card.querySelector(".age");
    if (!ageEl) continue;
    const hb = parseFloat(card.dataset.hb);
    if (isNaN(hb)) { ageEl.textContent = "활동 없음"; continue; }
    const age = now - hb;
    ageEl.textContent = "활동 " + fmtAge(age);
  }
}
const fmtDur = sec => sec < 60 ? Math.max(0, Math.round(sec)) + "초"
  : sec < 3600 ? Math.round(sec / 60) + "분" : (sec / 3600).toFixed(1) + "시간";
// 작업 시간 텍스트를 갱신한다.
function updateTaskTimes(now) {
  for (const el of document.querySelectorAll("#tasks .todo-time")) {
    const c = parseFloat(el.dataset.c);
    if (isNaN(c)) { el.textContent = ""; continue; }
    if (["completed", "failed", "canceled"].includes(el.dataset.s)) {
      const u = parseFloat(el.dataset.u);
      el.textContent = "소요 " + fmtDur((isNaN(u) ? now : u) - c);
    } else {
      el.textContent = "시작 " + fmtAge(now - c);
    }
  }
}
// 긴 작업 설명은 접고 펼친다.
function fitTaskTexts() {
  for (const todo of document.querySelectorAll("#tasks .todo")) {
    const id = todo.dataset.task, txt = todo.querySelector(".todo-desc"), btn = todo.querySelector(".todo-more");
    if (!txt || !btn) continue;
    if (taskTextOpen.has(id)) { txt.classList.remove("clamp"); btn.hidden = false; btn.textContent = "접기"; }
    else { txt.classList.add("clamp"); btn.hidden = txt.scrollHeight <= txt.clientHeight + 1; btn.textContent = "더보기"; }
  }
}
window.addEventListener("resize", fitTaskTexts);
function invalidatePanelSig(panel) {
  if (panel === "tickets") sigTickets = null;
  else if (panel === "tasks") sigTasks = null;
  else if (panel === "completed") sigAssess = null;
  else if (panel === "agents") sigAgents = null;
}
function setPanelExpanded(panel, expanded) {
  panelExpanded[panel] = expanded;
  invalidatePanelSig(panel);
  refresh();
}
const PANEL_TOGGLE_ACTIONS = {
  tickets_more: () => setPanelExpanded("tickets", true),
  tickets_less: () => setPanelExpanded("tickets", false),
  tasks_more: () => setPanelExpanded("tasks", true),
  tasks_less: () => setPanelExpanded("tasks", false),
  completed_more: () => setPanelExpanded("completed", true),
  completed_less: () => setPanelExpanded("completed", false),
  agents_more: () => setPanelExpanded("agents", true),
  agents_less: () => setPanelExpanded("agents", false),
};
function renderPanelToggle(action, label, dir) {
  return `<button type="button" class="todo-expand" data-panel-toggle="${esc(action)}">` +
    `${esc(label)}<span class="exp-caret ${cls(dir)}"></span></button>`;
}
function handlePanelToggle(e) {
  const btn = e.target.closest("[data-panel-toggle]");
  if (!btn) return false;
  const fn = PANEL_TOGGLE_ACTIONS[btn.dataset.panelToggle];
  if (!fn) return false;
  e.stopPropagation();
  fn();
  return true;
}
function renderPanelList(items, opts) {
  const shown = opts.expanded ? items : items.slice(0, opts.limit);
  const more = items.length - shown.length;
  let html = shown.map(opts.renderItem).join("") || opts.emptyHtml;
  if (more > 0) html += renderPanelToggle(opts.moreAction, opts.moreLabel(more), "down");
  else if (opts.expanded && items.length > opts.limit) html += renderPanelToggle(opts.lessAction, "접기", "up");
  return html;
}
async function clearDone() {
  const done = (lastTasks || []).filter(t => t.state === "completed");
  if (!done.length) return;
  if (!await modal({message: `완료된 작업 ${done.length}개를 지울까요?`, confirmText: "지우기", danger: true})) return;
  for (const t of done) await fetch("/api/task-delete", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({id: t.task_id}),
  });
  resetSigs(); await refresh();
}

// 섹션별 시그니처가 바뀔 때만 다시 그린다.
let sigStop = null, sigMsg = null, sigTickets = null, sigTasks = null, sigAssess = null, sigAgents = null, sigDD = null;
function resetSigs() { sigStop = sigMsg = sigTickets = sigTasks = sigAssess = sigAgents = sigDD = null; }
function sig(...parts) { return JSON.stringify(parts); }

let loopPanelOpen = false, loopPanelKeyNow = "", focusStopReason = false;
function loopPanelKey() {
  return "agentbus.loopPanelOpen." + (STATE_ROOT || location.pathname || "default");
}
function syncLoopPanelKey() {
  const key = loopPanelKey();
  if (key === loopPanelKeyNow) return;
  loopPanelKeyNow = key;
  try { loopPanelOpen = localStorage.getItem(key) === "1"; }
  catch { loopPanelOpen = false; }
  sigStop = null;
}
function setLoopPanelOpen(open) {
  loopPanelOpen = !!open;
  try { localStorage.setItem(loopPanelKey(), loopPanelOpen ? "1" : "0"); }
  catch {}
  if (loopPanelOpen) focusStopReason = true;
  sigStop = null;
  refresh();
}
function toggleLoopPanel() {
  setLoopPanelOpen(!loopPanelOpen);
}
function setLoopModeClasses(el, mode) {
  el.classList.toggle("loop-open", mode === "open");
  el.classList.toggle("loop-closed", mode === "closed");
  el.classList.toggle("stop-requested", mode === "requested");
}
function updateLoopStateButton(stop) {
  const btn = byId("loopstate");
  if (!btn) return;
  const mode = loopStatusMode(stop);
  btn.textContent = loopStatusLabel(stop);
  setLoopModeClasses(btn, mode);
  btn.classList.toggle("on", loopPanelOpen);
  btn.setAttribute("aria-expanded", loopPanelOpen ? "true" : "false");
  setTip(btn, "루프 상태 패널 " + (loopPanelOpen ? "접기" : "열기"));
  requestAnimationFrame(fitProjectBadge);
}

// 최근 N건을 불러온다.
let msgLimit = 100, pinScroll = false;
function loadMore() { msgLimit += 100; pinScroll = true; sigMsg = null; refresh(); }

// 메시지 필터.
let filterAgents = new Set(), filterTasks = new Set(), filterKinds = new Set(), searchQuery = "";
let lastMsgs = [], lastAcks = {}, lastHidden = 0;
function filterSig() {
  return [...filterAgents].sort().join(",") + "|" +
    [...filterTasks].sort().join(",") + "|" +
    [...filterKinds].sort().join(",") + "|" + searchQuery;
}
function hasFacetFilters() {
  return !!(filterAgents.size || filterTasks.size || filterKinds.size);
}
function hasTimelineConstraints() {
  return hasFacetFilters() || !!searchQuery;
}
function passesFilter(m) {
  if (filterAgents.size && !filterAgents.has(m.from) && !filterAgents.has(m.to)) return false;
  if (filterTasks.size && !filterTasks.has(m.task_id)) return false;
  if (filterKinds.size && !filterKinds.has(m.kind || "")) return false;
  if (searchQuery && !(((m.subject || "") + " " + (m.body || "")).toLowerCase().includes(searchQuery))) return false;
  return true;
}
function renderTimelineHtml(msgs) {
  if (!msgs.length) return `<div class="empty-state">${ICON_EMPTY}<span>메시지 없음</span></div>`;
  let html = msgs.slice().reverse().map(m => renderMsg(m, lastAcks)).join("");
  if (!hasTimelineConstraints() && lastHidden > 0)
    html += `<button type="button" class="load-more" data-load-more>이전 메시지 ${lastHidden}개</button>`;
  return html;
}
function renderMath(root) {
  if (window.renderMathInElement) renderMathInElement(root, {
    delimiters: [{left:"$$", right:"$$", display:true}, {left:"$", right:"$", display:false}],
    throwOnError: false,
    ignoredClasses: ["md-code", "md-pre"],
  });
}
function restoreReplyDraft(root) {
  if (!replyOpenId) return;
  const box = root.querySelector(".reply-box");
  if (!box) return;
  const inp = box.querySelector(".reply-in");
  inp.value = replyDraft;
  makeMention(inp, box.querySelector(".mention-menu"), () => { replyDraft = inp.value; });
}
function renderTimeline() {
  const tl = byId("timeline");
  const prevH = tl.scrollHeight, prevY = tl.scrollTop;
  tl.innerHTML = renderTimelineHtml(lastMsgs.filter(passesFilter));
  renderMath(tl);
  restoreReplyDraft(tl);
  if (pinScroll) { tl.scrollTop = prevY; pinScroll = false; }
  else if (prevY > 50) tl.scrollTop = prevY + (tl.scrollHeight - prevH);
}
byId("timeline").addEventListener("toggle", e => {
  const d = e.target.closest("details[data-msgid]");
  if (d) onToggle(d.dataset.msgid, d.open);
}, true);

function byCreatedDesc(rows) {
  return (rows || []).slice().sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
}
function ackIndex(rows) {
  const acks = {};
  for (const r of rows || []) (acks[r.id] = acks[r.id] || []).push(r.agent);
  return acks;
}
function updateProjectRoot(root) {
  STATE_ROOT = root || "";
  const proj = byId("project");
  if (STATE_ROOT && proj.dataset.tip !== STATE_ROOT) {
    proj.textContent = STATE_ROOT.split("/").filter(Boolean).pop() || STATE_ROOT;
    proj.dataset.tip = STATE_ROOT;   // 전체 경로는 커스텀 툴팁으로
  }
  fitProjectBadge();
}
function updateStopPanel(stop) {
  const stopPanelSig = sig(stop || null, loopPanelOpen);
  if (stopPanelSig === sigStop) return;
  sigStop = stopPanelSig;
  const bar = byId("stopbar");
  if (loopPanelOpen) {
    const mode = loopStatusMode(stop);
    bar.classList.add("open");
    setLoopModeClasses(bar, mode);
    bar.innerHTML = renderStopBanner(stop);
    if (focusStopReason && !stop) {
      focusStopReason = false;
      requestAnimationFrame(() => byId("stop-reason")?.focus());
    }
  } else {
    bar.classList.remove("open");
  }
}
function updateMessagePanel(st, acks) {
  lastMsgs = st.messages; lastAcks = acks;
  lastHidden = Math.max(0, (st.messages_total || st.messages.length) - st.messages.length);
  updateOverview(st);
  const msgSig = sig(st.messages, st.acks, lastHidden, filterSig());
  if (msgSig !== sigMsg) { sigMsg = msgSig; renderTimeline(); }
}
function updateTicketPanel(tickets) {
  const ticketSig = sig(tickets, panelExpanded.tickets);
  if (ticketSig === sigTickets) return;
  sigTickets = ticketSig;
  byId("tickets").innerHTML = renderPanelList(tickets, {
    expanded: panelExpanded.tickets,
    limit: PANEL_LIMIT.tickets,
    renderItem: renderTicket,
    emptyHtml: `<div class="todo muted todo-empty">티켓 없음</div>`,
    moreAction: "tickets_more",
    lessAction: "tickets_less",
    moreLabel: n => `티켓 ${n}개 더 보기`,
  });
}
function updateTaskPanel(tasks, now) {
  const taskSig = sig(tasks, panelExpanded.tasks);
  if (taskSig !== sigTasks) {
    sigTasks = taskSig;
    byId("tasks").innerHTML = renderPanelList(tasks, {
      expanded: panelExpanded.tasks,
      limit: PANEL_LIMIT.tasks,
      renderItem: renderTask,
      emptyHtml: `<div class="todo muted todo-empty">작업 없음</div>`,
      moreAction: "tasks_more",
      lessAction: "tasks_less",
      moreLabel: n => `작업 ${n}개 더 보기`,
    });
    fitTaskTexts();
  }
  byId("clear-done").hidden = !tasks.some(t => t.state === "completed");
  updateTaskTimes(now);
}
function updateCompletedPanel(tasks, taskReports) {
  const reportsByTask = new Map(taskReports.map(r => [r.task_id, r]));
  const completed = tasks.filter(t => t.state === "completed");
  const completedSig = sig(completed, taskReports, panelExpanded.completed, filterSig());
  if (completedSig === sigAssess) return;
  sigAssess = completedSig;
  byId("completed").innerHTML = renderPanelList(completed, {
    expanded: panelExpanded.completed,
    limit: PANEL_LIMIT.completed,
    renderItem: t => renderCompletedTask(t, reportsByTask.get(t.task_id)),
    emptyHtml: `<div class="todo muted todo-empty">완료 작업 없음</div>`,
    moreAction: "completed_more",
    lessAction: "completed_less",
    moreLabel: n => `완료 ${n}개 더 보기`,
  });
}
function updateAgentPanel(agents, now) {
  const agentSig = sig(AGENT_NAMES.map(n => [n, agents[n].state, agents[n].task, agents[n].note, agents[n].updated_at]), panelExpanded.agents);
  if (agentSig !== sigAgents) {
    sigAgents = agentSig;
    byId("agents").innerHTML = renderPanelList(AGENT_NAMES, {
      expanded: panelExpanded.agents,
      limit: PANEL_LIMIT.agents,
      renderItem: n => renderAgent(n, agents[n]),
      emptyHtml: `<div class="agent muted">등록된 에이전트 없음</div>`,
      moreAction: "agents_more",
      lessAction: "agents_less",
      moreLabel: n => `에이전트 ${n}개 더 보기`,
    });
  }
  updateAgentAges(now);
}
function updateComposeOptions(cards, tasks) {
  lastTasks = tasks;
  const recipients = [...new Set([...AGENT_NAMES, ...Object.keys(cards)])].sort();
  RECIPIENT_NAMES = recipients.filter(n => n && n !== "all");
  const ddSig = sig(recipients, tasks.map(t => [t.task_id, t.title]), composeTo, composeTask);
  if (ddSig === sigDD) return;
  sigDD = ddSig;
  toOptions = recipients.map(n => ({value:n, label:n, sub:(cards[n] && cards[n].name && cards[n].name !== n) ? cards[n].name : ""}))
    .concat({value:"all", label:"all"});
  RECIPIENT_OPTIONS = toOptions.filter(o => o.value && o.value !== "all");
  if (!toOptions.some(o => o.value === composeTo)) composeTo = toOptions.length ? toOptions[0].value : "all";
  buildDD("dd-to", toOptions, composeTo, pickTo);
  rebuildTaskDD();
}

async function refresh() {
  let st;
  try { st = await (await fetch("/api/state?limit=" + msgLimit)).json(); }
  catch { byId("refreshed").textContent = "서버 연결 끊김"; return; }
  byId("refreshed").textContent = "";
  updateProjectRoot(st.root);
  const agents = st.status.agents || {};
  AGENT_NAMES = Object.keys(agents).sort();
  TASK_STATES = st.task_states || [];
  syncLoopPanelKey();
  updateLoopStateButton(st.stop);
  updateStopPanel(st.stop);

  updateMessagePanel(st, ackIndex(st.acks));
  updateTicketPanel(byCreatedDesc(st.tickets || st.issues));
  const tasks = byCreatedDesc(st.tasks);
  updateTaskPanel(tasks, st.now);
  const taskReports = (st.task_reports || []).slice();
  updateCompletedPanel(tasks, taskReports);
  updateAgentPanel(agents, st.now);
  updateComposeOptions(st.cards || {}, tasks);
}

async function post(url, data) {
  const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)});
  if (!r.ok) {
    await modal({message: "요청 실패: " + await r.text(), cancelText: null});
    return false;
  }
  resetSigs();
  await refresh();
  return true;
}

function modalShell(html, setup) {
  return new Promise(resolve => {
    let settled = false;
    const ov = document.createElement("div");
    ov.className = "modal-ov";
    ov.innerHTML = html;
    document.body.appendChild(ov);
    requestAnimationFrame(() => ov.classList.add("show"));
    function done(val) {
      if (settled) return;
      settled = true;
      ov.classList.remove("show");
      setTimeout(() => ov.remove(), 160);
      resolve(val);
    }
    setup(ov, done);
  });
}

// 모달은 input이면 문자열/null, 아니면 true/false를 반환한다.
function modal(opts) {
  const {message = "", input = false, value = "", confirmText = "확인", cancelText = "취소", danger = false} = opts || {};
  return modalShell(`<div class="modal" role="dialog" aria-modal="true">
      <div class="modal-msg"></div>
      ${input ? `<input class="modal-input" type="text">` : ""}
      <div class="modal-actions">
        ${cancelText ? `<button type="button" class="modal-btn" data-act="cancel">${esc(cancelText)}</button>` : ""}
        <button type="button" class="modal-btn ${danger ? "danger" : "primary"}" data-act="ok">${esc(confirmText)}</button>
      </div>
    </div>`, (ov, done) => {
    ov.querySelector(".modal-msg").textContent = message;
    const inp = ov.querySelector(".modal-input");
    if (inp) inp.value = value;
    const cancel = () => done(input ? null : false);
    const ok = () => done(input ? (inp ? inp.value : "") : true);
    ov.addEventListener("click", e => {
      if (e.target === ov) return cancel();
      const act = e.target.closest("[data-act]");
      if (act) (act.dataset.act === "ok" ? ok : cancel)();
    });
    ov.addEventListener("keydown", e => {
      if (e.key === "Escape") cancel();
      else if (e.key === "Enter") { e.preventDefault(); ok(); }
    });
    (inp || ov.querySelector('[data-act="ok"]')).focus();
    if (inp) inp.select();
  });
}

function ticketModal(opts) {
  const {to = "my-agent", options = [], note = ""} = opts || {};
  const choices = (options.length ? options : [to || "my-agent"])
    .map(o => typeof o === "string" ? {value:o, label:o} : o);
  let selected = choices.some(o => o.value === to) ? to : (choices[0] && choices[0].value) || to || "my-agent";
  return modalShell(`<div class="modal" role="dialog" aria-modal="true">
      <div class="modal-msg">티켓을 진행할 에이전트와 코멘트를 확인합니다.</div>
      <label class="modal-label">에이전트</label>
      <div class="dd modal-dd">
        <button type="button" class="dd-btn"><span class="dd-val"></span><span class="dd-caret"></span></button>
        <div class="dd-menu"></div>
      </div>
      <label class="modal-label">코멘트</label>
      <textarea class="modal-textarea" rows="3" placeholder="작업 지시나 판단 기준을 짧게 남깁니다."></textarea>
      <div class="modal-actions">
        <button type="button" class="modal-btn" data-act="cancel">취소</button>
        <button type="button" class="modal-btn primary" data-act="ok">진행</button>
      </div>
    </div>`, (ov, done) => {
    const dd = ov.querySelector(".modal-dd");
    const textarea = ov.querySelector(".modal-textarea");
    const pick = v => { selected = v; buildDD(dd, choices, selected, pick); textarea.focus(); };
    buildDD(dd, choices, selected, pick);
    textarea.value = note;
    const cancel = () => done(null);
    const ok = () => done({to: selected, note: textarea.value.trim()});
    ov.addEventListener("click", e => {
      if (e.target === ov) return cancel();
      const act = e.target.closest("[data-act]");
      if (act) (act.dataset.act === "ok" ? ok : cancel)();
    });
    ov.addEventListener("keydown", e => {
      if (e.key === "Escape") cancel();
      else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); ok(); }
    });
    dd.querySelector(".dd-btn").focus();
  });
}

// 메시지 필터 패널.
const fwrap = byId("filter-wrap");
function updateFilterIndicator() {
  byId("filterbtn").classList.toggle("active", hasFacetFilters());
  const bits = [];
  if (filterKinds.size) bits.push("종류 " + filterKinds.size);
  if (filterAgents.size) bits.push("참여자 " + filterAgents.size);
  if (filterTasks.size) bits.push("작업 " + filterTasks.size);
  byId("filter-summary").textContent = bits.join(" · ");
}
function buildFilterUI() {
  const parts = [...new Set(["user", ...lastMsgs.flatMap(m => [m.from, m.to])].filter(Boolean))].sort();
  document.querySelectorAll("#fp-kinds [data-kind]").forEach(btn =>
    btn.classList.toggle("on", filterKinds.has(btn.dataset.kind)));
  byId("fp-agents").innerHTML = parts.map(a =>
    `<div class="fp-opt ${filterAgents.has(a) ? "on" : ""}" data-a="${esc(a)}">` +
    `<span class="fp-check"></span><span class="fp-label">${esc(a)}</span></div>`).join("")
    || `<div class="fp-empty">없음</div>`;
  byId("fp-tasks").innerHTML = lastTasks.map(t =>
    `<div class="fp-opt fp-task-opt ${filterTasks.has(t.task_id) ? "on" : ""}" data-t="${esc(t.task_id)}" data-tip="${esc(t.title || "")}">` +
    `<span class="fp-check"></span><span class="fp-task-main"><span>${idPill("task", t.task_id, {}, "idpill-compact")}</span>` +
    `<span class="fp-task-title">${esc(t.title || "")}</span></span></div>`).join("")
    || `<div class="fp-empty">없음</div>`;
}
function syncFilterHighlights() {
  document.querySelectorAll("#tasks .idpill[data-task]").forEach(el =>
    el.classList.toggle("on", filterTasks.has(el.dataset.task)));
  document.querySelectorAll("#completed .completed-card[data-task]").forEach(el =>
    el.classList.toggle("on", filterTasks.has(el.dataset.task)));
  document.querySelectorAll("#agents .agent[data-agent]").forEach(el =>
    el.classList.toggle("on", filterAgents.has(el.dataset.agent)));
}
function afterFilterChange() { updateFilterIndicator(); syncFilterHighlights(); sigMsg = null; renderTimeline(); }
function toggleInSet(set, key, el) {
  if (set.has(key)) { set.delete(key); el.classList.remove("on"); }
  else { set.add(key); el.classList.add("on"); }
  afterFilterChange();
}
byId("filterbtn").addEventListener("click", e => {
  e.stopPropagation();
  if (fwrap.classList.toggle("open")) buildFilterUI();
});
byId("fp-kinds").addEventListener("click", e => {
  const b = e.target.closest("[data-kind]"); if (b) toggleInSet(filterKinds, b.dataset.kind, b);
});
byId("fp-agents").addEventListener("click", e => {
  const o = e.target.closest(".fp-opt"); if (o && o.dataset.a) toggleInSet(filterAgents, o.dataset.a, o);
});
byId("fp-tasks").addEventListener("click", e => {
  const o = e.target.closest(".fp-opt"); if (o && o.dataset.t) toggleInSet(filterTasks, o.dataset.t, o);
});
byId("fp-reset").addEventListener("click", () => {
  filterAgents.clear(); filterTasks.clear(); filterKinds.clear();
  buildFilterUI(); afterFilterChange();
});
// 작업 id 클릭은 메시지 필터를 토글한다.
byId("tasks").addEventListener("click", e => {
  if (handlePanelToggle(e)) return;
  const del = e.target.closest("[data-delete-task]");
  if (del) {
    e.stopPropagation();
    deleteTask(del.dataset.deleteTask);
    return;
  }
  const more = e.target.closest(".todo-more");
  if (more) {
    e.stopPropagation();
    const tid = more.closest(".todo").dataset.task;
    if (taskTextOpen.has(tid)) taskTextOpen.delete(tid); else taskTextOpen.add(tid);
    fitTaskTexts();
    return;
  }
  const id = e.target.closest(".idpill[data-task]");
  if (id && id.dataset.task) { e.stopPropagation(); toggleInSet(filterTasks, id.dataset.task, id); }
});
byId("completed").addEventListener("click", e => {
  if (handlePanelToggle(e)) return;
  const card = e.target.closest(".completed-card");
  if (card && card.dataset.task) { e.stopPropagation(); toggleInSet(filterTasks, card.dataset.task, card); }
});
byId("clear-done").addEventListener("click", clearDone);
// 툴팁.
const tipEl = document.createElement("div"); tipEl.className = "tooltip"; document.body.appendChild(tipEl);
let tipTarget = null;
function normalizeTooltips(root = document) {
  const nodes = [];
  if (root?.nodeType === 1 && root.hasAttribute?.("title")) nodes.push(root);
  root?.querySelectorAll?.("[title]").forEach(el => nodes.push(el));
  for (const el of nodes) {
    const text = el.getAttribute("title");
    if (text && !el.dataset.tip) el.dataset.tip = text;
    el.removeAttribute("title");
  }
}
normalizeTooltips();
new MutationObserver(records => {
  for (const rec of records) {
    if (rec.type === "attributes") normalizeTooltips(rec.target);
    else rec.addedNodes.forEach(node => normalizeTooltips(node));
  }
}).observe(document.body, {subtree:true, childList:true, attributes:true, attributeFilter:["title"]});
function tipVisibleText(el) {
  return (el.textContent || "").replace(/\s+/g, " ").trim();
}
function isTipTextClipped(el) {
  return el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1;
}
function shouldShowTooltip(el, text) {
  if (!text) return false;
  const visible = tipVisibleText(el);
  return visible !== text.trim() || isTipTextClipped(el);
}
document.addEventListener("mouseover", e => {
  normalizeTooltips(e.target);
  const el = e.target.closest("[data-tip]");
  if (!el || el === tipTarget) return;
  const text = el.dataset.tip;
  if (!shouldShowTooltip(el, text)) return;
  tipTarget = el; tipEl.textContent = text; tipEl.classList.add("show");
  const r = el.getBoundingClientRect(), tr = tipEl.getBoundingClientRect();
  const left = Math.max(6, Math.min(r.left + r.width / 2 - tr.width / 2, innerWidth - tr.width - 6));
  let top = r.bottom + 6;
  if (top + tr.height > innerHeight - 6) top = r.top - tr.height - 6;
  tipEl.style.left = left + "px"; tipEl.style.top = Math.max(6, top) + "px";
});
document.addEventListener("mouseout", e => {
  if (tipTarget && !tipTarget.contains(e.relatedTarget)) { tipEl.classList.remove("show"); tipTarget = null; }
});
// 개요 스트립.
const AGENT_STATE_LABEL = {running:"실행 중", waiting:"대기", done:"완료", error:"오류"};
function updateOverview(st) {
  const ag = st.status.agents || {};
  const order = ["running", "waiting", "done", "error"];
  const counts = {};
  for (const n in ag) { const s = ag[n].state; counts[s] = (counts[s] || 0) + 1; }
  const states = order.filter(s => counts[s]).concat(Object.keys(counts).filter(s => !order.includes(s)));
  const agentBits = states.map(s =>
    `<span class="ov-ag" data-tip="${esc((AGENT_STATE_LABEL[s] || s) + " " + counts[s])}">` +
    `<span class="ov-dot ${cls(s)}"></span>${counts[s]}</span>`).join("");
  const tasks = st.tasks || [];
  const working = tasks.filter(t => t.state === "working").length;
  const ticketCount = (st.tickets || st.issues || []).length;
  let last = "";
  if (st.messages.length) { const t = new Date(st.messages[st.messages.length - 1].time).getTime() / 1000; if (!isNaN(t)) last = fmtAge(st.now - t); }
  byId("overview").innerHTML =
    `<span>메시지 ${st.messages_total}</span>` +
    (agentBits ? `<span class="ov-agents">${agentBits}</span>` : "") +
    `<span>작업 ${tasks.length}${working ? " (진행 " + working + ")" : ""}</span>` +
    (ticketCount ? `<span>티켓 ${ticketCount}</span>` : "") +
    (last ? `<span>${esc(last)}</span>` : "");
  fitOverview();
}
// 개요가 넘치면 뒤 세그먼트부터 숨긴다.
function fitOverview() {
  const ov = byId("overview"); if (!ov) return;
  const segs = [...ov.children];
  segs.forEach(s => s.style.display = "");
  for (let i = segs.length - 1; i >= 1 && ov.scrollWidth > ov.clientWidth + 1; i--) segs[i].style.display = "none";
}
window.addEventListener("resize", fitOverview);
window.addEventListener("resize", fitProjectBadge);
// 메시지 검색.
const searchWrap = byId("search-wrap"), searchIn = byId("search-in");
byId("searchbtn").addEventListener("click", e => {
  e.stopPropagation();
  const opening = !searchWrap.classList.contains("open");
  searchWrap.classList.toggle("open", opening);
  if (opening) searchIn.focus();
  else { if (searchQuery) { searchQuery = ""; searchIn.value = ""; afterFilterChange(); } setTimeout(fitOverview, 240); }
});
searchIn.addEventListener("input", () => { searchQuery = searchIn.value.trim().toLowerCase(); afterFilterChange(); });
searchIn.addEventListener("keydown", e => {
  if (e.key === "Escape") { searchWrap.classList.remove("open"); if (searchQuery) { searchQuery = ""; searchIn.value = ""; afterFilterChange(); } }
});
document.addEventListener("click", e => { if (!e.target.closest("#filter-wrap")) fwrap.classList.remove("open"); });

// 메시지의 작업 pill은 작업 패널 항목을 강조한다.
let hlTask = null;
function taskRow(id) {
  return Array.from(document.querySelectorAll("#tasks .todo[data-task]"))
    .find(row => row.dataset.task === id) || null;
}
function highlightTask(id) {
  if (hlTask === id) return;
  clearTaskHighlight(); hlTask = id;
  const row = taskRow(id);
  if (row) { row.classList.add("hl"); row.scrollIntoView({block:"nearest"}); }
}
function clearTaskHighlight() {
  hlTask = null;
  document.querySelectorAll("#tasks .todo.hl").forEach(r => r.classList.remove("hl"));
}
let taskJumpTimer = null;
async function jumpToTask(id) {
  clearTimeout(taskJumpTimer);
  if (hlTask === id) clearTaskHighlight();
  if (!taskRow(id) && !panelExpanded.tasks && (lastTasks || []).some(t => t.task_id === id)) {
    panelExpanded.tasks = true;
    sigTasks = null;
    await refresh();
  }
  highlightTask(id);
  taskJumpTimer = setTimeout(clearTaskHighlight, 1600);
}
const timelineEl = byId("timeline");
// reply 칩은 응답 대상 메시지를 강조한다.
let msgHlTimer = null;
function messageRow(id) {
  return Array.from(document.querySelectorAll("#timeline .msg[data-id]"))
    .find(row => row.dataset.id === id) || null;
}
function highlightMsg(id) {
  const row = messageRow(id);
  if (!row) return;
  row.scrollIntoView({block:"center", behavior:"smooth"});
  document.querySelectorAll(".msg.hlmsg").forEach(r => r.classList.remove("hlmsg"));
  row.classList.add("hlmsg");
  clearTimeout(msgHlTimer);
  msgHlTimer = setTimeout(() => row.classList.remove("hlmsg"), 1600);
}

// 메시지별 답장.
function openReply(id) {
  replyOpenId = (replyOpenId === id) ? null : id;
  replyDraft = "";
  renderTimeline();
  if (replyOpenId) { const i = timelineEl.querySelector(".reply-in"); if (i) i.focus(); }
}
async function sendReply(box) {
  const inp = box.querySelector(".reply-in"), body = inp.value.trim();
  if (!body) return;
  replyOpenId = null; replyDraft = "";
  await post("/api/send", {from:"user", to: box.dataset.to, reply_to: box.dataset.reply, body, kind:"note"});
}
async function deleteMessage(id) {
  if (await modal({message: "이 메시지를 삭제할까요?", confirmText: "삭제", danger: true})) {
    if (replyOpenId === id) replyOpenId = null;
    await post("/api/message-delete", {id});
  }
}
async function writeClipboardText(text) {
  let legacyError = null;
  try {
    const onCopy = e => {
      if (!e.clipboardData) return;
      e.clipboardData.setData("text/plain", text);
      e.preventDefault();
    };
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.left = "0";
    ta.style.width = "1px";
    ta.style.height = "1px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    try { ta.focus({preventScroll: true}); } catch { ta.focus(); }
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    if (document.addEventListener) document.addEventListener("copy", onCopy, true);
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } finally {
      if (document.removeEventListener) document.removeEventListener("copy", onCopy, true);
      ta.remove();
    }
    if (ok) return;
  } catch (err) {
    legacyError = err;
  }
  const clipboard = window.navigator?.clipboard;
  if (clipboard?.writeText) {
    await clipboard.writeText(text);
    return;
  }
  throw legacyError || new Error("copy command failed");
}
function setCopyButtonState(btn, copied) {
  if (!btn) return;
  btn.classList.toggle("copied", copied);
  btn.innerHTML = copied ? ICON_COPY_DONE : ICON_COPY;
  setTip(btn, copied ? "복사됨" : "내용 복사");
  btn.setAttribute("aria-label", copied ? "복사됨" : "내용 복사");
}
async function copyMessage(id, btn) {
  const msg = lastMsgs.find(m => m.id === id);
  const text = msg ? messageCopyText(msg) : "";
  if (!text) return;
  try {
    await writeClipboardText(text);
    if (btn) {
      setCopyButtonState(btn, true);
      setTimeout(() => setCopyButtonState(btn, false), 1000);
    }
  } catch (err) {
    console.warn("message copy failed", err);
    await manualCopyModal(text);
  }
}
function manualCopyModal(text) {
  return modalShell(`<div class="modal copy-modal" role="dialog" aria-modal="true">
      <div class="modal-msg">브라우저가 자동 복사를 허용하지 않아 원문을 선택했습니다. ⌘C로 복사하세요.</div>
      <textarea class="modal-textarea modal-copy-text" readonly></textarea>
      <div class="modal-actions">
        <button type="button" class="modal-btn primary" data-act="ok">닫기</button>
      </div>
    </div>`, (ov, done) => {
    const ta = ov.querySelector(".modal-copy-text");
    ta.value = text;
    ov.addEventListener("click", e => {
      if (e.target === ov || e.target.closest("[data-act='ok']")) done();
    });
    ov.addEventListener("keydown", e => { if (e.key === "Escape") done(); });
    ta.focus();
    ta.select();
  });
}
timelineEl.addEventListener("click", e => {
  const more = e.target.closest("[data-load-more]");
  if (more) { e.stopPropagation(); loadMore(); return; }
  const taskChip = e.target.closest(".idpill[data-task]");
  if (taskChip) { e.stopPropagation(); jumpToTask(taskChip.dataset.task).catch(err => console.warn("task jump failed", err)); return; }
  const replyChip = e.target.closest(".idpill[data-reply]");
  if (replyChip) { e.stopPropagation(); highlightMsg(replyChip.dataset.reply); return; }
  const cp = e.target.closest("[data-copy-message]");
  if (cp) { e.stopPropagation(); copyMessage(cp.dataset.copyMessage, cp); return; }
  const rb = e.target.closest(".msg-reply");
  if (rb) { e.stopPropagation(); openReply(rb.dataset.id); return; }
  const del = e.target.closest("[data-delete-message]");
  if (del) { e.stopPropagation(); deleteMessage(del.dataset.deleteMessage); return; }
  const go = e.target.closest(".reply-go");
  if (go) { e.stopPropagation(); sendReply(go.closest(".reply-box")); }
});
timelineEl.addEventListener("keydown", e => {
  const i = e.target.closest(".reply-in"); if (!i) return;
  const box = i.closest(".reply-box");
  if (box.querySelector(".mention-menu").classList.contains("open")) return;
  if (e.key === "Enter") { e.preventDefault(); sendReply(box); }
  else if (e.key === "Escape") { replyOpenId = null; replyDraft = ""; renderTimeline(); }
});
// 에이전트 패널의 작업 pill은 클릭할 때 작업 항목으로 이동한다.
const agentsEl = byId("agents");

// 작성 상태.
let composeTo = "all", composeKind = "note", composeTask = "";
let toOptions = [{value:"all", label:"all"}], taskOptions = [], lastTasks = [];

// 드롭다운은 작성 패널과 모달이 같은 마크업과 동작을 쓴다.
function buildDD(target, options, current, onPick, placeholder) {
  const dd = typeof target === "string" ? byId(target) : target;
  if (!dd) return;
  if (dd.classList.contains("open")) return;
  const opts = options.map(o => typeof o === "string" ? {value:o, label:o} : o);
  const cur = opts.find(o => o.value === current);
  const valEl = dd.querySelector(".dd-val");
  valEl.textContent = cur ? cur.label : (placeholder || current || "");
  valEl.classList.toggle("placeholder", !cur);
  dd.querySelector(".dd-menu").innerHTML = opts.map(o =>
    `<div class="dd-opt ${o.value === current ? "sel" : ""}" data-v="${esc(o.value)}">` +
    `<span>${esc(o.label)}</span>${o.sub ? `<span class="sub">${esc(o.sub)}</span>` : ""}</div>`
  ).join("") || `<div class="dd-opt muted">없음</div>`;
  dd.querySelectorAll(".dd-opt[data-v]").forEach(el => el.addEventListener("click", ev => {
    ev.stopPropagation(); dd.classList.remove("open"); onPick(el.getAttribute("data-v"));
  }));
}
function pickTo(v) { composeTo = v; buildDD("dd-to", toOptions, composeTo, pickTo); }
// 작업 연결 드롭다운.
function rebuildTaskDD() {
  taskOptions = (composeTask ? [{value:"", label:"연결 해제"}] : [])
    .concat(lastTasks.map(t => ({value:t.task_id, label:t.task_id, sub:t.title || ""})));
  if (composeTask && !lastTasks.some(t => t.task_id === composeTask)) composeTask = "";
  buildDD("dd-task", taskOptions, composeTask, pickTask, "작업 선택");
}
function pickTask(v) { composeTask = v; rebuildTaskDD(); }
function closeDropdownMenus() {
  document.querySelectorAll(".dd.open").forEach(d => d.classList.remove("open"));
}
document.addEventListener("click", e => {
  const btn = e.target.closest(".dd-btn");
  if (btn) {
    e.stopPropagation();
    const dd = btn.closest(".dd"), wasOpen = dd.classList.contains("open");
    closeDropdownMenus();
    if (!wasOpen) dd.classList.add("open");
    return;
  }
  if (!e.target.closest(".dd")) closeDropdownMenus();
});

// kind 세그먼트.
const segEl = byId("seg-kind");
const segThumb = document.createElement("div");
segThumb.className = "seg-thumb";
segEl.insertBefore(segThumb, segEl.firstChild);
function moveSegThumb() {
  const on = segEl.querySelector("button.on");
  if (!on || !on.offsetWidth) return;
  segThumb.style.width = on.offsetWidth + "px";
  segThumb.style.transform = "translateX(" + on.offsetLeft + "px)";
}
segEl.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
  composeKind = b.getAttribute("data-v");
  segEl.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
  moveSegThumb();
}));

// 본문 입력창 높이.
const bodyEl = byId("body");
function growBody() { bodyEl.style.height = "auto"; bodyEl.style.height = Math.min(bodyEl.scrollHeight, 140) + "px"; }

// 파일 멘션 자동완성.
const mentionEl = byId("mention");
function makeMention(inputEl, menuEl, onChange) {
  let items = [], active = -1, start = -1, token = 0;
  const close = () => { menuEl.classList.remove("open"); items = []; active = -1; start = -1; };
  function ctxOf() {
    const text = inputEl.value.slice(0, inputEl.selectionStart);
    const m = text.match(/(?:^|\s)@([^\s@]*)$/);
    return m ? { q: m[1], start: inputEl.selectionStart - m[1].length - 1 } : null;
  }
  async function update() {
    const ctx = ctxOf();
    if (!ctx) { close(); return; }
    const t = ++token; let files = [];
    try { files = (await (await fetch("/api/files?q=" + encodeURIComponent(ctx.q))).json()).files || []; }
    catch { close(); return; }
    if (t !== token) return;
    if (!files.length) { close(); return; }
    items = files; start = ctx.start; active = 0; render();
  }
  function render() {
    menuEl.innerHTML = items.map((f, i) => {
      const cut = f.lastIndexOf("/") + 1;
      return `<div class="mention-opt ${i === active ? "active" : ""}" data-i="${i}">` +
        `<span class="dir">${esc(f.slice(0, cut))}</span><span class="base">${esc(f.slice(cut))}</span></div>`;
    }).join("");
    menuEl.classList.add("open");
    menuEl.querySelectorAll(".mention-opt").forEach(el =>
      el.addEventListener("mousedown", ev => { ev.preventDefault(); insert(+el.dataset.i); }));
    const a = menuEl.querySelector(".mention-opt.active"); if (a) a.scrollIntoView({ block: "nearest" });
  }
  function insert(i) {
    const f = items[i]; if (f == null) return;
    const before = inputEl.value.slice(0, start), after = inputEl.value.slice(inputEl.selectionStart);
    inputEl.value = before + f + " " + after;
    const caret = (before + f + " ").length;
    close(); if (onChange) onChange();
    inputEl.focus(); inputEl.setSelectionRange(caret, caret);
  }
  inputEl.addEventListener("input", () => { if (onChange) onChange(); update(); });
  inputEl.addEventListener("blur", () => setTimeout(close, 150));
  inputEl.addEventListener("keydown", e => {
    if (!menuEl.classList.contains("open") || !items.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); active = (active + 1) % items.length; render(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = (active - 1 + items.length) % items.length; render(); }
    else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); insert(active); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
  });
  return { close, isOpen: () => menuEl.classList.contains("open") };
}
const composeMention = makeMention(bodyEl, mentionEl, growBody);

async function sendMessage() {
  const body = bodyEl.value.trim();
  if (!body) return;
  composeMention.close();
  await post("/api/send", {to: composeTo, kind: composeKind, body, task_id: composeTask});
  bodyEl.value = ""; growBody();
}
byId("compose").addEventListener("submit", e => { e.preventDefault(); sendMessage(); });
bodyEl.addEventListener("keydown", e => {
  if (composeMention.isOpen()) return;
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); sendMessage(); }
});
byId("loopstate").addEventListener("click", toggleLoopPanel);
const stopbarEl = byId("stopbar");
stopbarEl.addEventListener("submit", e => {
  if (e.target.closest("[data-stop-form]")) requestStopFromPanel(e);
});
stopbarEl.addEventListener("click", e => {
  const clear = e.target.closest("[data-clear-stop]");
  if (clear) { e.preventDefault(); clearStop(); }
});
stopbarEl.addEventListener("keydown", e => {
  if (e.key === "Escape") setLoopPanelOpen(false);
});
async function requestStopFromPanel(e) {
  if (e) e.preventDefault();
  const input = byId("stop-reason");
  const reason = (input?.value || "").trim() || "user_stop";
  await post("/api/stop", {reason});
}
// 세션 정리.
const settingsWrap = byId("settings-wrap");
byId("rotatebtn").addEventListener("click", async () => {
  settingsWrap.classList.remove("open");
  if (!await modal({message: "현재 메시지를 archive/로 보관하고 타임라인을 비웁니다. 계속할까요?", confirmText: "보관"})) return;
  const r = await fetch("/api/rotate", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
  if (!r.ok) { await modal({message: "요청 실패: " + await r.text(), cancelText: null}); return; }
  const j = await r.json().catch(() => ({}));
  await modal({message: j.archived ? "메시지를 보관함(archive/)으로 회전했습니다." : "보관할 메시지가 없습니다.", cancelText: null});
  resetSigs(); refresh();
});
byId("clearbtn").addEventListener("click", async () => {
  settingsWrap.classList.remove("open");
  if (await modal({message: "현재 메시지·확인 기록을 비웁니다(작업·에이전트는 유지). 계속할까요?", confirmText: "비우기", danger: true})) post("/api/clear", {});
});
function setInlineFormOpen(form, button, focusEl, open) {
  form.classList.toggle("open", open);
  form.setAttribute("aria-hidden", open ? "false" : "true");
  button.classList.toggle("open", open);
  if (open) focusEl.focus();
}
// 티켓.
const newticketBtn = byId("newticket");
const newticketForm = byId("newticket-form");
const newticketTitle = byId("newticket-title");
function setNewticketOpen(open) {
  setInlineFormOpen(newticketForm, newticketBtn, newticketTitle, open);
}
newticketBtn.addEventListener("click", () => setNewticketOpen(!newticketForm.classList.contains("open")));
newticketForm.addEventListener("submit", async e => {
  e.preventDefault();
  const title = newticketTitle.value.trim();
  if (!title) return;
  newticketTitle.value = ""; setNewticketOpen(false);
  await post("/api/ticket-new", {title});
});
newticketTitle.addEventListener("keydown", e => {
  if (e.key === "Escape") { newticketTitle.value = ""; setNewticketOpen(false); }
});
function defaultAssignee() {
  return RECIPIENT_NAMES.find(n => n !== "user") || AGENT_NAMES.find(n => n !== "user") || "my-agent";
}
async function acceptTicket(id) {
  const picked = await ticketModal({to: defaultAssignee(), options: RECIPIENT_OPTIONS.length ? RECIPIENT_OPTIONS : RECIPIENT_NAMES});
  if (!picked || !picked.to) return;
  await post("/api/ticket-accept", {id, to: picked.to, note: picked.note});
}
async function rejectTicket(id) {
  if (await modal({message: "이 티켓을 삭제할까요?", confirmText: "삭제", danger: true})) {
    await post("/api/ticket-reject", {id});
  }
}
byId("tickets").addEventListener("click", e => {
  if (handlePanelToggle(e)) return;
  const accept = e.target.closest("[data-accept-ticket]");
  if (accept) { acceptTicket(accept.dataset.acceptTicket); return; }
  const reject = e.target.closest("[data-reject-ticket]");
  if (reject) rejectTicket(reject.dataset.rejectTicket);
});
// 새 작업.
const newtaskBtn = byId("newtask");
const newtaskForm = byId("newtask-form");
const newtaskTitle = byId("newtask-title");
function setNewtaskOpen(open) {
  setInlineFormOpen(newtaskForm, newtaskBtn, newtaskTitle, open);
}
newtaskBtn.addEventListener("click", () => setNewtaskOpen(!newtaskForm.classList.contains("open")));
newtaskForm.addEventListener("submit", async e => {
  e.preventDefault();
  const title = newtaskTitle.value.trim();
  if (!title) return;
  newtaskTitle.value = ""; setNewtaskOpen(false);
  await post("/api/task-new", {title, assign: []});
});
newtaskTitle.addEventListener("keydown", e => {
  if (e.key === "Escape") { newtaskTitle.value = ""; setNewtaskOpen(false); }
});
function setTaskState(id, state) { post("/api/task-state", {id, state}); }
function deleteTask(id) { post("/api/task-delete", {id}); }
async function deleteAgent(agent) {
  if (await modal({message: `에이전트 '${agent}' 상태를 지울까요?`, confirmText: "제거", danger: true})) {
    post("/api/agent-delete", {agent});
  }
}
async function clearStop() {
  if (await modal({message: "정지 요청을 해제할까요?", confirmText: "해제"})) post("/api/clear-stop", {});
}
agentsEl.addEventListener("click", e => {
  if (handlePanelToggle(e)) return;
  const del = e.target.closest("[data-delete-agent]");
  if (del) { e.stopPropagation(); deleteAgent(del.dataset.deleteAgent); return; }
  const chip = e.target.closest(".idpill[data-task]");
  if (chip) { e.stopPropagation(); jumpToTask(chip.dataset.task).catch(err => console.warn("task jump failed", err)); return; }
  const card = e.target.closest(".agent[data-agent]");
  if (card) { e.stopPropagation(); toggleInSet(filterAgents, card.dataset.agent, card); }
});

// 작업 상태 드롭다운.
function closeTaskStateMenus() {
  document.querySelectorAll(".tdd.open").forEach(d => d.classList.remove("open"));
  openTaskDD = null;
}
document.addEventListener("click", e => {
  const opt = e.target.closest(".tdd-opt");
  if (opt) {
    e.stopPropagation();
    closeTaskStateMenus();
    setTaskState(opt.dataset.task, opt.dataset.state);
    return;
  }
  const btn = e.target.closest(".tdd-btn");
  if (btn) {
    e.stopPropagation();
    const tdd = btn.closest(".tdd"), wasOpen = tdd.classList.contains("open");
    closeTaskStateMenus();
    if (!wasOpen) { tdd.classList.add("open"); openTaskDD = tdd.dataset.task; }
    return;
  }
  closeTaskStateMenus();
});

// 레이아웃 토글.
const sideAutoCollapseMQ = window.matchMedia ? window.matchMedia("(max-width: 720px)") : {matches: false};
let floatingSideDismissed = false;
function isAutoSideMode() {
  return !!sideAutoCollapseMQ.matches;
}
function isSideCollapsedForLayout(autoSide = isAutoSideMode()) {
  return localStorage.getItem("sideCollapsed") === "1" || (autoSide && floatingSideDismissed);
}
function isFloatingSideOpen() {
  return isAutoSideMode() && !isSideCollapsedForLayout();
}
function applyLayout() {
  const autoSide = isAutoSideMode();
  if (!autoSide) floatingSideDismissed = false;
  const side = isSideCollapsedForLayout(autoSide);
  const compose = localStorage.getItem("composeOpen") === "1";
  document.body.classList.toggle("side-collapsed", side);
  document.body.classList.toggle("side-auto-collapsed", autoSide);
  document.body.classList.toggle("compose-open", compose);
  const sideVisible = !side;
  const sideBtn = byId("toggleside");
  sideBtn.classList.toggle("on", sideVisible);
  sideBtn.setAttribute("aria-pressed", sideVisible ? "true" : "false");
  sideBtn.setAttribute("aria-expanded", sideVisible ? "true" : "false");
  sideBtn.dataset.tip = "사이드 패널";
  byId("togglecompose").classList.toggle("on", compose);
  const c = byId("compose");
  if (compose) setTimeout(() => { if (localStorage.getItem("composeOpen") === "1") c.classList.add("expanded"); }, 320);
  else c.classList.remove("expanded");
}
function flip(key) {
  localStorage.setItem(key, localStorage.getItem(key) === "1" ? "0" : "1");
  applyLayout();
}
function toggleSidePanel() {
  const autoSide = isAutoSideMode();
  if (autoSide) {
    if (localStorage.getItem("sideCollapsed") === "1") localStorage.setItem("sideCollapsed", "0");
    else floatingSideDismissed = !floatingSideDismissed;
    applyLayout();
    return;
  }
  floatingSideDismissed = false;
  flip("sideCollapsed");
}
function closeFloatingSidePanel() {
  if (!isFloatingSideOpen()) return false;
  floatingSideDismissed = true;
  applyLayout();
  return true;
}
function isSidePanelInteractionTarget(target) {
  return target instanceof Element && !!target.closest("#side, #toggleside");
}
function closeFloatingSidePanelFromOutside(target) {
  if (!isFloatingSideOpen() || isSidePanelInteractionTarget(target)) return;
  closeFloatingSidePanel();
}
byId("toggleside").addEventListener("click", toggleSidePanel);
document.addEventListener("pointerdown", e => closeFloatingSidePanelFromOutside(e.target), true);
document.addEventListener("focusin", e => closeFloatingSidePanelFromOutside(e.target), true);
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && closeFloatingSidePanel()) e.stopPropagation();
}, true);
byId("togglecompose").addEventListener("click", () => flip("composeOpen"));
byId("closecompose").addEventListener("click", () => {
  localStorage.setItem("composeOpen", "0"); applyLayout();
});
function onSideModeChange() {
  document.body.classList.add("side-mode-switching");
  applyLayout();
  requestAnimationFrame(() => requestAnimationFrame(() => document.body.classList.remove("side-mode-switching")));
}
if (sideAutoCollapseMQ.addEventListener) sideAutoCollapseMQ.addEventListener("change", onSideModeChange);
else if (sideAutoCollapseMQ.addListener) sideAutoCollapseMQ.addListener(onSideModeChange);
applyLayout();

// 테마 선택.
function applyTheme() {
  const t = localStorage.getItem("theme") || "";
  document.body.classList.toggle("theme-light", t === "light");
  document.body.classList.toggle("theme-dark", t === "dark");
  document.querySelectorAll("#theme-row .set-opt").forEach(b => b.classList.toggle("on", b.dataset.theme === t));
}
document.querySelectorAll("#theme-row .set-opt").forEach(b => b.addEventListener("click", () => {
  const v = b.dataset.theme;
  if (v) localStorage.setItem("theme", v); else localStorage.removeItem("theme");
  applyTheme();
}));
applyTheme();
const SIZE_ZOOM = [0.9, 1.0, 1.12, 1.25, 1.4];
const sizeSlider = byId("size-slider");
function applyTextSize() {
  let idx = parseInt(localStorage.getItem("textsize"), 10);
  if (isNaN(idx) || idx < 0 || idx >= SIZE_ZOOM.length) idx = 1;
  const main = document.querySelector("main");
  if (main) main.style.zoom = SIZE_ZOOM[idx];
  sizeSlider.value = idx;
  sizeSlider.style.setProperty("--pct", (idx / (SIZE_ZOOM.length - 1) * 100) + "%");
}
sizeSlider.addEventListener("input", () => { localStorage.setItem("textsize", sizeSlider.value); applyTextSize(); });
applyTextSize();
byId("settingsbtn").addEventListener("click", (e) => { e.stopPropagation(); settingsWrap.classList.toggle("open"); });
document.addEventListener("click", (e) => { if (!e.target.closest("#settings-wrap")) settingsWrap.classList.remove("open"); });
moveSegThumb();
updateFilterIndicator();

// 첫 페인트 뒤 애니메이션을 켠다.
requestAnimationFrame(() => requestAnimationFrame(() => { document.body.classList.remove("no-anim"); moveSegThumb(); }));

refresh(); setInterval(refresh, 2500);
