const {
  esc, cls, byId, fmtTime, fmtAge, fmtDur, fmtCompactCount, icon, hydrateIcons,
  setTip, idPill, statusMark, healthMark, setRefRoot, splitRefs, renderRefsExpander, securityMark,
  ICON_REPLY, ICON_EMPTY, ICON_COPY, ICON_COPY_DONE, ICON_TRASH, ICON_SEND, ICON_CHECK, ICON_DBLCHECK, ICON_X, ICON_UNLOCK,
} = window.AgentBusDashboardPrimitives;

hydrateIcons();

function fitProjectBadge() {
  const header = document.querySelector("header");
  const proj = byId("project");
  if (!header || !proj || !proj.textContent) return;
  proj.classList.remove("project-hidden");
  if (header.scrollWidth > header.clientWidth + 1) proj.classList.add("project-hidden");
}

// 펼친 메시지 상태를 유지한다.
const expanded = new Set();
function onToggle(id, open) { if (open) expanded.add(id); else expanded.delete(id); }
let replyOpenId = null, replyDraft = "";

let AGENT_NAMES = [];
let AGENT_LABELS = {};
let AUTH_AGENT_NAMES = new Set();
let VIEWER_AUTH = {authenticated:false, name:""};
let KEY_CONTEXT = {schemaVersion:"agentbus.key-context.v1", body:"", revision:0};
let keyContextCompact = typeof localStorage !== "undefined" && localStorage.getItem("keyContextCompact") === "1";
let RECIPIENT_NAMES = [];
let RECIPIENT_OPTIONS = [];
let LEAD_AGENT_ID = "";
let composeToTouched = false;

let STATE_ROOT = "";

const KIND_LABEL = {note:"메모", request:"요청", report:"보고", task:"작업", ticket:"티켓", stop:"정지", ack:"확인"};
function kindLabel(kind) { return KIND_LABEL[String(kind || "")] || String(kind || ""); }

const ICON_RUNNER_PROFILE = icon("bridge", {class:"agent-profile-icon-svg"});
const ICON_RUNNER_MISSING = icon("circle-help", {class:"agent-profile-icon-svg"});

function agentLabel(id) {
  const key = String(id || "");
  if (AGENT_LABELS[key]) return AGENT_LABELS[key];
  return /^a-[0-9a-f]{6,}$/i.test(key) ? "삭제됨" : key;
}
function agentIdForRef(ref) {
  const key = String(ref || "");
  if (AGENT_NAMES.includes(key)) return key;
  return AGENT_NAMES.find(id => AGENT_LABELS[id] === key) || "";
}
function agentDisplay(ref) {
  const key = String(ref || "");
  const id = agentIdForRef(key);
  if (id) return agentLabel(id);
  return /^a-[0-9a-f]{6,}$/i.test(key) ? "삭제됨" : key;
}
function agentPill(ref, attrs = {}, extraClass = "") {
  const id = agentIdForRef(ref);
  return idPill("agent", id ? agentLabel(id) : "삭제됨", attrs, extraClass);
}
function agentLabelSig() {
  return AGENT_NAMES.map(id => [id, AGENT_LABELS[id] || id]);
}
function isLeadAgent(a = {}) {
  return String(a.role || "") === "lead";
}
function runnerProfileName(a = {}) {
  return String(a.runnerProfile || "").trim();
}
function renderAgentBadges(a = {}) {
  const lead = isLeadAgent(a) ? `<span class="code-pill agent-lead-badge">lead</span>` : "";
  const profile = runnerProfileName(a);
  const profileMark = profile
    ? `<span class="agent-profile-mark" data-tip="${esc(profile)}" aria-label="${esc(profile)}">${ICON_RUNNER_PROFILE}</span>`
    : (isLeadAgent(a) ? "" : `<span class="agent-profile-mark missing" data-tip="프로필 없음" aria-label="프로필 없음">${ICON_RUNNER_MISSING}</span>`);
  return lead + profileMark;
}

function renderAcks(ackers, sender) {
  if (!ackers.length) return "";
  const expected = AGENT_NAMES.filter(a => a !== sender);
  if (expected.length > 0 && expected.every(a => ackers.includes(a))) {
    return `<span class="ackchip ackall" data-tip="전체 확인: ${esc(ackers.map(agentLabel).join(", "))}">${ICON_DBLCHECK}</span>`;
  }
  const shown = ackers.slice(0, 2).map(a => `<span class="ackchip">${ICON_CHECK}${esc(agentLabel(a))}</span>`).join("");
  const hidden = ackers.slice(2);
  if (!hidden.length) return shown;
  const pop = hidden.map(a => `<span>${ICON_CHECK}${esc(agentLabel(a))}</span>`).join("");
  return shown + `<span class="ackchip ackmore" tabindex="0">+${hidden.length}<span class="ackmore-pop">${pop}</span></span>`;
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
  return "루프 진행 중";
}

function renderStopBanner(stop) {
  if (!stop) return "";
  const mode = loopStatusMode(stop);
  const label = loopStatusLabel(stop);
  const detail = stopDetailText(stop?.detail);
  const closed = mode === "closed";
  const meta = [stop?.by, stop?.reason].filter(Boolean).join(" · ");
  const time = stop?.time ? fmtTime(stop.time) : "";
  const detailHtml = detail ? `<span class="stop-detail">${esc(detail)}</span>` : "";
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
  return renderRefsExpander(refs);
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
      <input class="reply-in" type="text" placeholder="${esc(agentLabel(m.from))}에게 답장…">
      <button class="iconbtn send reply-go" type="button" data-tip="보내기" aria-label="보내기">${ICON_SEND}</button>
    </div>
    <div class="mention-menu"></div>
  </div>`;
}
function renderMsg(m, acks) {
  if (m._decode_error) return `<div class="card msg"><div class="body">${esc(m._decode_error)}</div></div>`;
  const ackers = acks[m.id] || [];
  const canReply = m.from && m.from !== "user";
  return `<div class="card msg" data-id="${esc(m.id)}">
    <span class="msg-actions inline-actions">${renderMessageActions(m, canReply)}</span>
    <div class="head">
      <span class="route">${esc(agentLabel(m.from))} → ${esc(agentLabel(m.to))}</span>
      <span class="tag kind ${cls(m.kind)}">${esc(kindLabel(m.kind))}</span>
      ${securityMark(m)}
      <span>${fmtTime(m.time)}</span>
      ${renderAcks(ackers, m.from)}
    </div>
    ${renderMessageContent(m)}
    ${renderReplyBox(m, canReply)}
  </div>`;
}

let TASK_STATES = [];
let openTaskDD = null;
const PANEL_LIMIT = {tasks: 3, tickets: 3, completed: 3, skills: 3, agents: 3, bridgeProfiles: 3, bridgeGateways: 3};
const panelExpanded = {tasks: false, tickets: false, completed: false, skills: false, agents: false, bridgeProfiles: false, bridgeGateways: false};
const SIDE_TABS = ["work", "agent", "bridge"];
const storedSideTab = typeof localStorage !== "undefined" ? localStorage.getItem("sideTab") : "";
let sideTab = SIDE_TABS.includes(storedSideTab) ? storedSideTab : "work";
const taskTextOpen = new Set();
const STATE_LABEL = {submitted:"대기", working:"진행 중", input_required:"확인 필요",
                     completed:"완료", failed:"오류", canceled:"취소"};
const AGENT_STATE_LABEL = {running:"진행 중", waiting:"대기", done:"완료", error:"오류"};
const SKILL_EVIDENCE_LABEL = {grounding:"근거", check:"확인", gap:"빈틈", risk:"위험"};
const BRIDGE_EVENT_LABEL = {
  "message.created": "새 메시지",
  "message.deleted": "메시지 삭제",
  "message.acked": "메시지 확인",
  "message.delivered": "메시지 전달",
  "task.created": "새 작업",
  "task.state": "작업 상태",
  "task.deleted": "작업 삭제",
  "ticket.created": "새 티켓",
  "ticket.accepted": "티켓 진행",
  "ticket.rejected": "티켓 종료",
};
const BRIDGE_ACCESS_LABEL = {"local only": "로컬", "local origin": "로컬 요청"};
function skillHealth(s) {
  if (s.state === "active" && !(s.warnings || []).length) return "ok";
  if (s.state === "invalid" || s.state === "broken") return "problem";
  return "warning";
}
function bridgeHealth(state) {
  if (state === "failure" || state === "invalid") return "problem";
  if (state === "needs_config" || state === "unknown") return "warning";
  return "ok";
}
function agentHealth(a) {
  if (a.state === "error") return "problem";
  if (!a.heartbeat) return "warning";
  return "ok";
}
const HEALTH_LABEL = {ok:"정상", warning:"주의", problem:"오류"};
function bridgeEventLabel(value) {
  return String(value || "").split(/\s*,\s*/).filter(Boolean)
    .map(v => BRIDGE_EVENT_LABEL[v] || v).join(", ");
}
function bridgeAccessLabel(value) {
  const key = String(value || "").trim();
  return BRIDGE_ACCESS_LABEL[key] || key;
}
let sideTabAnimTimer = null;
let sideTabSyncTimer = null;
function moveSideTabThumb(animate = false) {
  animate = animate === true;
  const tabs = byId("side-tabs");
  const thumb = tabs?.querySelector(".side-tab-thumb");
  const on = tabs?.querySelector("button.on");
  if (!tabs || !thumb || !on) return;
  const tabsWidth = tabs.getBoundingClientRect().width;
  if (tabsWidth < 80 || on.offsetWidth < 40) return;
  clearTimeout(sideTabAnimTimer);
  tabs.classList.toggle("side-tabs-animate", animate);
  if (animate) void thumb.offsetWidth;
  thumb.style.width = on.offsetWidth + "px";
  thumb.style.transform = "translateX(" + on.offsetLeft + "px)";
  if (animate) sideTabAnimTimer = setTimeout(() => tabs.classList.remove("side-tabs-animate"), 280);
}
function syncSideTabThumbAfterLayout() {
  clearTimeout(sideTabSyncTimer);
  requestAnimationFrame(() => {
    moveSideTabThumb(false);
    requestAnimationFrame(() => moveSideTabThumb(false));
  });
  sideTabSyncTimer = setTimeout(() => moveSideTabThumb(false), 320);
}
function updateViewerAuthUi(viewer = {}) {
  VIEWER_AUTH = {authenticated:!!viewer.authenticated, name:String(viewer.name || "")};
  const state = byId("viewer-auth-state");
  const btn = byId("viewer-authbtn");
  if (!state || !btn) return;
  state.innerHTML = VIEWER_AUTH.authenticated
    ? `<span class="code-pill">${esc(VIEWER_AUTH.name || "사용자")}</span>`
    : "꺼짐";
  state.classList.toggle("on", VIEWER_AUTH.authenticated);
  btn.classList.toggle("on", VIEWER_AUTH.authenticated);
  btn.setAttribute("aria-label", VIEWER_AUTH.authenticated ? "보안 보기 로그아웃" : "사용자 인증");
  const label = btn.querySelector(".set-label");
  if (label) label.textContent = VIEWER_AUTH.authenticated ? "로그아웃" : "인증";
}

function setSideTab(tab, persist = true, animate = false) {
  sideTab = SIDE_TABS.includes(tab) ? tab : "work";
  if (persist && typeof localStorage !== "undefined") localStorage.setItem("sideTab", sideTab);
  for (const name of SIDE_TABS) {
    const on = sideTab === name;
    const btn = byId(`side-tab-${name}`);
    const panel = byId(`side-${name}`);
    if (btn) {
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    }
    if (panel) panel.hidden = !on;
  }
  moveSideTabThumb(animate);
}
function renderTicket(ticket) {
  const id = ticket.issue_id || ticket.ticket_id;
  const refsHtml = renderRefsExpander(ticket.refs || []);
  return `<div class="todo ticket" data-ticket="${esc(id)}">
    ${statusMark("submitted", "대기")}
    <div class="todo-body">
      <div class="todo-text">${esc(ticket.title || "(제목 없음)")}</div>
      ${ticket.body ? `<div class="todo-desc">${esc(ticket.body)}</div>` : ""}
      ${refsHtml}
      <div class="todo-meta">
        ${idPill(ticket.issue_id ? "issue" : "ticket", id, {"data-ticket": id}, "idpill-compact")}
        ${securityMark(ticket)}
        <span>${fmtTime(ticket.created_at)}</span>
      </div>
    </div>
    <div class="todo-actions inline-actions">
      <button type="button" class="msg-act todo-run" data-tip="진행" aria-label="진행" data-accept-ticket="${esc(id)}">
        ${ICON_CHECK}
      </button>
      <button type="button" class="msg-act msg-del todo-del" data-tip="삭제" aria-label="삭제" data-reject-ticket="${esc(id)}">
        ${ICON_X}
      </button>
    </div>
  </div>`;
}
function renderTask(t) {
  const assignStr = (t.assign || []).length ? t.assign.map(a => esc(agentDisplay(a))).join(", ") : "";
  const c = t.created_at ? new Date(t.created_at).getTime() / 1000 : "";
  const u = t.updated_at ? new Date(t.updated_at).getTime() / 1000 : "";
  const opts = TASK_STATES.map(s =>
    `<button type="button" class="tdd-opt ${s === t.state ? "sel" : ""}" data-task="${esc(t.task_id)}" data-state="${esc(s)}">` +
    `${statusMark(s, STATE_LABEL[s] || s, "tdot")}${STATE_LABEL[s] || s}</button>`).join("");
  const descHtml = t.note
    ? `<div class="todo-desc${taskTextOpen.has(t.task_id) ? "" : " clamp"}">${esc(t.note)}</div>` +
      `<button type="button" class="todo-more" hidden>더보기</button>`
    : "";
  return `<div class="todo ${cls(t.state)}" data-task="${esc(t.task_id)}">
    ${statusMark(t.state, STATE_LABEL[t.state] || t.state)}
    <div class="todo-body">
      <div class="todo-text">${esc(t.title || "(제목 없음)")}</div>
      ${descHtml}
      <div class="todo-meta">
        ${idPill("task", t.task_id, {"data-task": t.task_id}, `idpill-compact${filterTasks.has(t.task_id) ? " on" : ""}`)}
        ${securityMark(t)}
        <span class="todo-time" data-c="${c}" data-u="${u}" data-s="${esc(t.state)}"></span>
        ${assignStr ? `<span class="todo-rest">${assignStr}</span>` : ""}
      </div>
    </div>
    <div class="todo-actions inline-actions">
      <button type="button" class="msg-act msg-del todo-del" data-tip="삭제" aria-label="삭제" data-delete-task="${esc(t.task_id)}">${ICON_TRASH}</button>
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
  return `<div class="summary-card completed-card ${filterTasks.has(t.task_id) ? "on" : ""}" data-task="${esc(t.task_id)}">
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

function renderAgentAuth(name) {
  if (!AUTH_AGENT_NAMES.has(name)) return "";
  return `<span class="security-mark agent-auth" data-tip="보안 권한" aria-label="보안 권한">${ICON_UNLOCK}</span>`;
}
function agentStateText(a = {}) {
  const state = String(a.state || "");
  return AGENT_STATE_LABEL[state] || (state ? state : "확인 필요");
}
function agentStateMark(a = {}) {
  const state = String(a.state || "");
  const marker = {running:"working", waiting:"submitted", done:"completed", error:"failed"}[state] || "input_required";
  return statusMark(marker, agentStateText(a), "agent-state-mark");
}
function renderAgent(name, a) {
  const task = a.task ? idPill("task", a.task, {"data-task": a.task}, "agent-task") : "";
  const display = agentLabel(name);
  const stateText = agentStateText(a);
  return `<div class="summary-card agent ${filterAgents.has(name) ? "on" : ""}" data-agent="${esc(name)}" data-hb="${a.heartbeat || ""}">
    <div class="summary-head agent-head">
      <span class="summary-title agent-name"><span class="agent-name-text">${esc(display)}</span>${renderAgentBadges(a)}</span>
      <span class="agent-status">
        <span class="beat"><span class="age"></span></span>
        <span class="agent-status-sep" aria-hidden="true">·</span>
        ${stateText ? `<span class="agent-state-text">${esc(stateText)}</span>` : ""}
        ${renderAgentAuth(name)}
        ${agentStateMark(a)}
      </span>
    </div>
    ${a.note ? `<div class="agent-note">${esc(a.note)}</div>` : ""}
    <div class="summary-meta agent-meta">${idPill("agent", name, {}, "idpill-compact")}${task}</div>
  </div>`;
}
function renderSkill(s) {
  const pending = s.pending || {};
  const pendingBits = ["grounding", "check", "gap", "risk"].filter(k => pending[k]).map(k => `${SKILL_EVIDENCE_LABEL[k]} ${pending[k]}`);
  const warn = (s.warnings || []).length;
  const health = skillHealth(s);
  const meta = [
    pendingBits.length ? `<span>근거 ${esc(pendingBits.join(", "))}</span>` : "",
    warn ? `<span>주의 ${esc(warn)}건</span>` : "",
  ].filter(Boolean).join("");
  return `<div class="summary-card skill-card">
    <div class="summary-head">
      <span class="summary-title">${esc(s.name || s.skill_id || "(이름 없음)")}</span>
      ${healthMark(health, HEALTH_LABEL[health])}
    </div>
    ${s.description ? `<div class="skill-desc">${esc(s.description)}</div>` : ""}
    ${meta ? `<div class="summary-meta">${meta}</div>` : ""}
  </div>`;
}
function bridgeRuntimeState(p, runtime = {}) {
  if ((runtime.failureCount || 0) > 0) return "failure";
  if (p.state && p.state !== "ready") return p.state;
  return "ready";
}
function bridgeDisplayHandler(p) {
  const raw = p.handler || p.handlerType || "monitor";
  if (p.handlerType === "agent") {
    const provider = raw.replace(/^agent\s+/, "");
    return provider ? `${provider}-cli` : "agent-cli";
  }
  if (p.handlerType === "http" && p.protocol === "a2a") return "A2A";
  if (p.handlerType === "http") return "HTTP";
  if (p.handlerType === "openai-compatible") return "OpenAI Compatible";
  return raw;
}
function bridgeTargetPills(targets = []) {
  const cleaned = (targets || []).filter(Boolean);
  if (!cleaned.length) return `<span class="bridge-target-muted">-</span>`;
  return cleaned.map(t => {
    const agentId = agentIdForRef(t);
    const exists = !!agentId;
    const attrs = exists ? {"data-agent": agentId} : {"aria-disabled": "true"};
    const extra = exists ? "idpill-compact bridge-target" : "idpill-compact bridge-target bridge-target-missing";
    return exists ? agentPill(agentId, attrs, extra) : idPill("agent", "삭제됨", attrs, extra);
  }).join("");
}
function bridgeMatcherLine(p) {
  const bits = [];
  if (p.event) bits.push(`<span class="bridge-event">${esc(bridgeEventLabel(p.event))}</span>`);
  const kinds = (p.matcherKinds || []).filter(Boolean);
  if (kinds.length) bits.push(`<code class="bridge-kind">${esc(kinds.join(", "))}</code>`);
  const extras = [...(p.matcherActors || []), ...(p.matcherObjectTypes || []), ...(p.matcherObjectIds || [])].filter(Boolean);
  if (extras.length) bits.push(`<span>${esc(extras.join(", "))}</span>`);
  if (!bits.length && p.matcher) bits.push(`<span>${esc(p.matcher)}</span>`);
  return bits.join("");
}
function renderBridgeProfile(p, runtime = {}) {
  const warnings = p.warnings || [];
  const state = bridgeRuntimeState(p, runtime);
  const health = bridgeHealth(state);
  const positionTime = runtime.positionUpdatedAt
    ? `<span class="bridge-time" data-position-time="${esc(runtime.positionUpdatedAt)}"></span>`
    : "";
  const meta = [
    runtime.failureCount ? `오류 ${runtime.failureCount}건` : "",
    state === "needs_config" ? "설정 필요" : "",
    warnings.length ? `주의 ${warnings.length}건` : "",
  ].filter(Boolean);
  const handlerClass = `handler-${p.handlerType || p.protocol || "monitor"}`;
  const matcherLine = bridgeMatcherLine(p);
  return `<div class="summary-card bridge-card ${cls(state)}">
    <div class="summary-head bridge-head">
      <span class="summary-title bridge-title">${esc(p.name || "(이름 없음)")}${positionTime ? " " + positionTime : ""}</span>
      ${healthMark(health, HEALTH_LABEL[health])}
    </div>
    <div class="bridge-route bridge-route-main">
      <span class="bridge-dir ${cls(handlerClass)}">${esc(bridgeDisplayHandler(p))}</span>
      <span class="bridge-arrow">→</span>
      <span class="bridge-targets">${bridgeTargetPills(p.matcherTargets || [])}</span>
    </div>
    ${matcherLine ? `<div class="bridge-route bridge-route-matcher">${matcherLine}</div>` : ""}
    ${meta.length ? `<div class="summary-meta bridge-extra-meta">${meta.map(v => `<span>${esc(v)}</span>`).join("")}</div>` : ""}
  </div>`;
}
function renderBridgeGateway(g) {
  const meta = [g.protocol || "", bridgeAccessLabel(g.access)].filter(Boolean);
  const state = g.state || "ready";
  const health = bridgeHealth(state);
  return `<div class="summary-card bridge-card gateway ${cls(state)}">
    <div class="summary-head">
      <span class="summary-title">${esc(g.name || "게이트웨이")}</span>
      ${healthMark(health, HEALTH_LABEL[health])}
    </div>
    <div class="bridge-route">
      <span>${esc(g.endpoint || "-")}</span>
    </div>
    <div class="summary-meta">${meta.map(v => `<span>${esc(v)}</span>`).join("")}</div>
  </div>`;
}
function bridgeRuntimeForProfile(statusByName, name) {
  return statusByName.get(name) || statusByName.get(`teammate/${name}`) || statusByName.get(`bridge/${name}`) || {};
}
function bridgeRuntimeRank(runtime = {}, profile = {}) {
  if ((runtime.failureCount || 0) > 0) return 0;
  if (profile.state && profile.state !== "ready") return 1;
  if ((profile.warnings || []).length) return 2;
  if (runtime.positionUpdatedAt) return 3;
  return 4;
}
function updateAgentAges(now) {
  for (const card of document.querySelectorAll("#agents .agent")) {
    const beat = card.querySelector(".beat"), ageEl = card.querySelector(".age"), sep = card.querySelector(".agent-status-sep");
    if (!beat || !ageEl) continue;
    const hb = parseFloat(card.dataset.hb);
    const hasBeat = !isNaN(hb);
    beat.hidden = !hasBeat;
    if (sep) sep.hidden = !hasBeat;
    if (!hasBeat) { ageEl.textContent = ""; continue; }
    const age = now - hb;
    ageEl.textContent = fmtAge(age);
  }
}
function updateBridgeAges(now) {
  for (const el of document.querySelectorAll(".bridge-time[data-position-time]")) {
    const t = new Date(el.dataset.positionTime).getTime() / 1000;
    el.textContent = isNaN(t) ? el.dataset.positionTime : fmtAge(now - t);
  }
}
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
window.addEventListener("resize", syncSideTabThumbAfterLayout);
function invalidatePanelSig(panel) {
  if (panel === "tickets") sigTickets = null;
  else if (panel === "tasks") sigTasks = null;
  else if (panel === "completed") sigCompleted = null;
  else if (panel === "skills") sigSkills = null;
  else if (panel === "agents") sigAgents = null;
  else if (panel === "bridgeProfiles" || panel === "bridgeGateways") sigBridges = null;
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
  skills_more: () => setPanelExpanded("skills", true),
  skills_less: () => setPanelExpanded("skills", false),
  agents_more: () => setPanelExpanded("agents", true),
  agents_less: () => setPanelExpanded("agents", false),
  bridge_profiles_more: () => setPanelExpanded("bridgeProfiles", true),
  bridge_profiles_less: () => setPanelExpanded("bridgeProfiles", false),
  bridge_gateways_more: () => setPanelExpanded("bridgeGateways", true),
  bridge_gateways_less: () => setPanelExpanded("bridgeGateways", false),
};
function renderPanelToggle(action, label, dir) {
  return `<button type="button" class="todo-expand" data-panel-toggle="${esc(action)}">` +
    `${esc(label)}<span class="exp-caret ${cls(dir)}"></span></button>`;
}
function panelEmpty(label) {
  return `<div class="panel-empty">${esc(label)}</div>`;
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
let sigStop = null, sigMsg = null, sigTickets = null, sigTasks = null, sigCompleted = null, sigKeyContext = null, sigSkills = null, sigAgents = null, sigBridges = null, sigDD = null;
function resetSigs() { sigStop = sigMsg = sigTickets = sigTasks = sigCompleted = sigKeyContext = sigSkills = sigAgents = sigBridges = sigDD = null; }
function sig(...parts) { return JSON.stringify(parts); }

let loopPanelOpen = false;
function syncLoopPanelKey() {
  if (loopPanelOpen) {
    loopPanelOpen = false;
    sigStop = null;
  }
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
  const label = loopStatusLabel(stop);
  if (btn.dataset.loopMode !== mode) {
    btn.innerHTML = `<span class="loop-route" aria-hidden="true">
      <span class="loop-road"></span>
      <span class="loop-bus">${icon("bus")}</span>
    </span><span class="sr-only">${esc(label)}</span>`;
    btn.dataset.loopMode = mode;
  } else {
    const text = btn.querySelector(".sr-only");
    if (text) text.textContent = label;
  }
  btn.setAttribute("aria-label", label);
  setLoopModeClasses(btn, mode);
  btn.classList.remove("on");
  btn.removeAttribute("aria-expanded");
  setTip(btn, label);
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
function filterAgentKey(ref) {
  return agentIdForRef(ref) || String(ref || "");
}
function passesFilter(m) {
  if (filterAgents.size && !filterAgents.has(filterAgentKey(m.from)) && !filterAgents.has(filterAgentKey(m.to))) return false;
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
  setRefRoot(STATE_ROOT);
  const proj = byId("project");
  if (STATE_ROOT && proj.dataset.tip !== STATE_ROOT) {
    proj.textContent = STATE_ROOT.split("/").filter(Boolean).pop() || STATE_ROOT;
    proj.dataset.tip = STATE_ROOT;   // 전체 경로는 커스텀 툴팁으로
  }
  fitProjectBadge();
}
function updateStopPanel(stop) {
  const stopPanelSig = sig(stop || null, false);
  if (stopPanelSig === sigStop) return;
  sigStop = stopPanelSig;
  const bar = byId("stopbar");
  bar.classList.remove("open");
  bar.innerHTML = "";
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
    emptyHtml: panelEmpty("티켓 없음"),
    moreAction: "tickets_more",
    lessAction: "tickets_less",
    moreLabel: n => `티켓 ${n}개 더 보기`,
  });
}
function updateTaskPanel(tasks, now) {
  const taskSig = sig(tasks, panelExpanded.tasks, agentLabelSig());
  if (taskSig !== sigTasks) {
    sigTasks = taskSig;
    byId("tasks").innerHTML = renderPanelList(tasks, {
      expanded: panelExpanded.tasks,
      limit: PANEL_LIMIT.tasks,
      renderItem: renderTask,
      emptyHtml: panelEmpty("작업 없음"),
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
  if (completedSig === sigCompleted) return;
  sigCompleted = completedSig;
  byId("completed").innerHTML = renderPanelList(completed, {
    expanded: panelExpanded.completed,
    limit: PANEL_LIMIT.completed,
    renderItem: t => renderCompletedTask(t, reportsByTask.get(t.task_id)),
    emptyHtml: panelEmpty("완료 작업 없음"),
    moreAction: "completed_more",
    lessAction: "completed_less",
    moreLabel: n => `완료 ${n}개 더 보기`,
  });
}
function updateSkillPanel(skills) {
  skills = skills || [];
  const section = byId("skills-section");
  if (section) section.hidden = skills.length === 0;
  const skillSig = sig(skills, panelExpanded.skills);
  if (skillSig === sigSkills) return;
  sigSkills = skillSig;
  byId("skills").innerHTML = renderPanelList(skills, {
    expanded: panelExpanded.skills,
    limit: PANEL_LIMIT.skills,
    renderItem: renderSkill,
    emptyHtml: panelEmpty("로컬 스킬 없음"),
    moreAction: "skills_more",
    lessAction: "skills_less",
    moreLabel: n => `스킬 ${n}개 더 보기`,
  });
}
function updateAgentPanel(agents, now) {
  const agentSig = sig(AGENT_NAMES.map(n => [n, AGENT_LABELS[n], agents[n].state, agents[n].task, agents[n].note, agents[n].updated_at, agents[n].role, agents[n].runnerProfile, agents[n].runnerProfileSource, AUTH_AGENT_NAMES.has(n)]), panelExpanded.agents);
  if (agentSig !== sigAgents) {
    sigAgents = agentSig;
    byId("agents").innerHTML = renderPanelList(AGENT_NAMES, {
      expanded: panelExpanded.agents,
      limit: PANEL_LIMIT.agents,
      renderItem: n => renderAgent(n, agents[n]),
      emptyHtml: panelEmpty("등록된 에이전트 없음"),
      moreAction: "agents_more",
      lessAction: "agents_less",
      moreLabel: n => `에이전트 ${n}개 더 보기`,
    });
  }
  updateAgentAges(now);
}
function updateBridgePanel(profiles, bridges, gateways, now) {
  profiles = profiles || [];
  bridges = bridges || [];
  gateways = gateways || [];
  const bridgeSig = sig(profiles, bridges, gateways, AGENT_NAMES, agentLabelSig(), panelExpanded.bridgeProfiles, panelExpanded.bridgeGateways);
  if (bridgeSig === sigBridges) { updateBridgeAges(now); return; }
  sigBridges = bridgeSig;
  const statusByName = new Map(bridges.map(row => [row.name, row]));
  const profilesForDisplay = [...profiles].sort((a, b) => {
    const ar = bridgeRuntimeForProfile(statusByName, a.name);
    const br = bridgeRuntimeForProfile(statusByName, b.name);
    return bridgeRuntimeRank(ar, a) - bridgeRuntimeRank(br, b) || String(a.name || "").localeCompare(String(b.name || ""));
  });
  byId("bridge-profiles").innerHTML = renderPanelList(profilesForDisplay, {
    expanded: panelExpanded.bridgeProfiles,
    limit: PANEL_LIMIT.bridgeProfiles,
    renderItem: profile => renderBridgeProfile(profile, bridgeRuntimeForProfile(statusByName, profile.name)),
    emptyHtml: panelEmpty("프로필 없음"),
    moreAction: "bridge_profiles_more",
    lessAction: "bridge_profiles_less",
    moreLabel: n => `프로필 ${n}개 더 보기`,
  });
  byId("bridge-gateways").innerHTML = renderPanelList(gateways, {
    expanded: panelExpanded.bridgeGateways,
    limit: PANEL_LIMIT.bridgeGateways,
    renderItem: renderBridgeGateway,
    emptyHtml: panelEmpty("게이트웨이 없음"),
    moreAction: "bridge_gateways_more",
    lessAction: "bridge_gateways_less",
    moreLabel: n => `게이트웨이 ${n}개 더 보기`,
  });
  updateBridgeAges(now);
}

function renderKeyContext(doc) {
  doc = doc || {};
  const body = String(doc.body || "");
  const signature = sig(body, doc.updatedAt, doc.updatedBy, doc.revision);
  if (signature === sigKeyContext) return;
  sigKeyContext = signature;
  KEY_CONTEXT = {
    schemaVersion: doc.schemaVersion || "agentbus.key-context.v1",
    body,
    updatedAt: doc.updatedAt || "",
    updatedBy: doc.updatedBy || "",
    revision: Number(doc.revision || 0),
  };
  const card = byId("key-context-card");
  const bodyEl = byId("key-context-body");
  const metaEl = byId("key-context-meta");
  bodyEl.textContent = body || "현재 Key Context가 없습니다.";
  bodyEl.classList.toggle("empty", !body);
  metaEl.textContent = KEY_CONTEXT.updatedAt ? fmtTime(KEY_CONTEXT.updatedAt) : "";
  card.classList.toggle("empty", !body);
  updateKeyContextLayout();
}

function updateKeyContextLayout() {
  const card = byId("key-context-card");
  const btn = byId("toggle-key-context-lines");
  if (!card || !btn) return;
  card.classList.toggle("compact", keyContextCompact);
  const label = keyContextCompact ? "펼치기" : "접기";
  btn.setAttribute("aria-label", label);
  setTip(btn, label);
}

function toggleKeyContextLines() {
  keyContextCompact = !keyContextCompact;
  try { localStorage.setItem("keyContextCompact", keyContextCompact ? "1" : "0"); } catch {}
  updateKeyContextLayout();
}

function updateComposeOptions(cards, tasks) {
  lastTasks = tasks;
  const recipients = [...new Set([...AGENT_NAMES, ...Object.keys(cards)])].sort();
  RECIPIENT_NAMES = recipients.filter(n => n && n !== "all");
  const defaultTo = LEAD_AGENT_ID || "all";
  const ddSig = sig(recipients.map(n => [n, agentLabel(n)]), tasks.map(t => [t.task_id, t.title]), composeTo, composeTask, defaultTo, composeToTouched);
  if (ddSig === sigDD) return;
  sigDD = ddSig;
  toOptions = recipients.map(n => ({value:n, label:agentLabel(n), sub:(cards[n] && cards[n].name && cards[n].name !== n) ? cards[n].name : ""}))
    .concat({value:"all", label:"전체"});
  RECIPIENT_OPTIONS = toOptions.filter(o => o.value && o.value !== "all");
  if (!composeToTouched) composeTo = "all";
  if (composeToTouched && !toOptions.some(o => o.value === composeTo)) {
    composeTo = "all";
    composeToTouched = false;
  }
  if (composeTask && !lastTasks.some(t => t.task_id === composeTask)) composeTask = "";
  renderComposeTokens();
}

async function refresh() {
  let st;
  try { st = await (await fetch("/api/state?limit=" + msgLimit)).json(); }
  catch { byId("refreshed").textContent = "서버 연결 끊김"; return; }
  byId("refreshed").textContent = "";
  updateProjectRoot(st.root);
  const agents = st.status.agents || {};
  AGENT_NAMES = Object.keys(agents).sort((a, b) => {
    const la = String((agents[a] && (agents[a].name || agents[a].displayName)) || a);
    const lb = String((agents[b] && (agents[b].name || agents[b].displayName)) || b);
    return la.localeCompare(lb) || a.localeCompare(b);
  });
  AGENT_LABELS = Object.fromEntries(AGENT_NAMES.map(id => [id, String((agents[id] && (agents[id].name || agents[id].displayName)) || id)]));
  LEAD_AGENT_ID = AGENT_NAMES.find(id => isLeadAgent(agents[id] || {})) || "";
  AUTH_AGENT_NAMES = new Set(((st.auth && st.auth.agents) || [])
    .filter(row => row && row.canReadRestricted && row.agent)
    .map(row => String(row.agent)));
  updateViewerAuthUi(st.viewer || {});
  TASK_STATES = st.task_states || [];
  syncLoopPanelKey();
  updateLoopStateButton(st.stop);
  updateStopPanel(st.stop);
  renderKeyContext(st.key_context || st.keyContext || {});

  updateMessagePanel(st, ackIndex(st.acks));
  updateTicketPanel(byCreatedDesc(st.tickets || st.issues));
  const tasks = byCreatedDesc(st.tasks);
  updateTaskPanel(tasks, st.now);
  const taskReports = (st.task_reports || []).slice();
  updateCompletedPanel(tasks, taskReports);
  updateSkillPanel(st.skills || []);
  updateAgentPanel(agents, st.now);
  updateBridgePanel(st.bridge_profiles || [], st.bridges || [], st.bridge_gateways || [], st.now);
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
    hydrateIcons(ov);
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

function keyContextModal() {
  return modalShell(`<div class="modal key-context-modal" role="dialog" aria-modal="true" aria-labelledby="key-context-modal-title">
      <div class="modal-title" id="key-context-modal-title">Key Context 편집</div>
      <div class="modal-note-row">
        <div class="modal-note">이 작업 흐름을 어떤 관점에서 이어갈지 남깁니다.</div>
        <button class="modal-help" type="button" aria-label="작성 기준" data-tip="- 상태나 메시지 요약보다, 이 흐름을 이해하고 판단할 기준을 중심으로 씁니다.
- 사용자와 조율한 의도, 관점, 판단 기준을 남깁니다.
- 이어지는 작업에서 참고할 배경과 판단 이유를 남깁니다."><span data-icon="circle-help"></span></button>
      </div>
      <textarea class="modal-textarea key-context-editor" spellcheck="false" placeholder="현재 작업 흐름에서 중요하게 볼 사용자 의도, 작업 배경, 방향성을 적습니다."></textarea>
      <div class="modal-actions">
        <button type="button" class="modal-btn" data-act="cancel">취소</button>
        <button type="button" class="modal-btn primary" data-act="ok">저장</button>
      </div>
    </div>`, (ov, done) => {
    const textarea = ov.querySelector(".key-context-editor");
    textarea.value = KEY_CONTEXT.body || "";
    const cancel = () => done(null);
    const ok = () => done(textarea.value);
    ov.addEventListener("click", e => {
      if (e.target === ov) return cancel();
      const act = e.target.closest("[data-act]");
      if (act) (act.dataset.act === "ok" ? ok : cancel)();
    });
    ov.addEventListener("keydown", e => {
      if (e.key === "Escape") cancel();
      else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); ok(); }
    });
    textarea.focus();
  });
}

async function editKeyContext() {
  const body = await keyContextModal();
  if (body == null) return;
  const r = await fetch("/api/key-context", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({body, by:"user", revision:KEY_CONTEXT.revision}),
  });
  if (!r.ok) {
    await modal({message: "저장 실패: " + await r.text(), cancelText: null});
    return;
  }
  resetSigs();
  await refresh();
}

function viewerAuthModal() {
  return modalShell(`<div class="modal" role="dialog" aria-modal="true">
      <div class="modal-title">보안 보기</div>
      <label class="modal-label">사용자</label>
      <input class="modal-input" data-field="viewer" type="text" autocomplete="username" placeholder="operator">
      <label class="modal-label">토큰</label>
      <input class="modal-input" data-field="token" type="password" autocomplete="current-password">
      <div class="modal-actions">
        <button type="button" class="modal-btn" data-act="cancel">취소</button>
        <button type="button" class="modal-btn primary" data-act="ok">인증</button>
      </div>
    </div>`, (ov, done) => {
    const viewer = ov.querySelector('[data-field="viewer"]');
    const token = ov.querySelector('[data-field="token"]');
    const cancel = () => done(null);
    const ok = () => done({viewer:(viewer.value || "").trim(), token:token.value || ""});
    ov.addEventListener("click", e => {
      if (e.target === ov) return cancel();
      const act = e.target.closest("[data-act]");
      if (act) (act.dataset.act === "ok" ? ok : cancel)();
    });
    ov.addEventListener("keydown", e => {
      if (e.key === "Escape") cancel();
      else if (e.key === "Enter") { e.preventDefault(); ok(); }
    });
    viewer.focus();
  });
}

function ticketModal(opts) {
  const {to = "my-agent", options = [], note = ""} = opts || {};
  const choices = (options.length ? options : [to || "my-agent"])
    .map(o => typeof o === "string" ? {value:o, label:o} : o);
  let selected = choices.some(o => o.value === to) ? to : (choices[0] && choices[0].value) || to || "my-agent";
  return modalShell(`<div class="modal" role="dialog" aria-modal="true">
      <div class="modal-title">티켓 진행</div>
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
  const parts = [...new Set([...AGENT_NAMES, "user", ...lastMsgs.flatMap(m => [filterAgentKey(m.from), filterAgentKey(m.to)])].filter(Boolean))]
    .sort((a, b) => agentLabel(a).localeCompare(agentLabel(b)) || String(a).localeCompare(String(b)));
  document.querySelectorAll("#fp-kinds [data-kind]").forEach(btn =>
    btn.classList.toggle("on", filterKinds.has(btn.dataset.kind)));
  byId("fp-agents").innerHTML = parts.map(a =>
    `<div class="fp-opt ${filterAgents.has(a) ? "on" : ""}" data-a="${esc(a)}">` +
    `<span class="fp-check"></span><span class="fp-main">${esc(agentLabel(a))}</span>` +
    `<span class="fp-meta">${agentLabel(a) === a ? "" : esc(a)}</span></div>`).join("")
    || `<div class="fp-empty">없음</div>`;
  byId("fp-tasks").innerHTML = lastTasks.map(t =>
    `<div class="fp-opt ${filterTasks.has(t.task_id) ? "on" : ""}" data-t="${esc(t.task_id)}">` +
    `<span class="fp-check"></span><span class="fp-main">${esc(t.task_id)}</span>` +
    `<span class="fp-meta">${esc(t.title || "")}</span></div>`).join("")
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
byId("skills").addEventListener("click", e => { handlePanelToggle(e); });
byId("bridge-gateways").addEventListener("click", e => { handlePanelToggle(e); });
byId("bridge-profiles").addEventListener("click", e => {
  if (handlePanelToggle(e)) return;
  const agent = e.target.closest(".idpill[data-agent]");
  if (agent && agent.dataset.agent) { e.stopPropagation(); jumpToAgent(agent.dataset.agent).catch(err => console.warn("agent jump failed", err)); }
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
  const completed = tasks.filter(t => t.state === "completed").length;
  const ticketCount = (st.tickets || st.issues || []).length;
  let last = "";
  if (st.messages.length) { const t = new Date(st.messages[st.messages.length - 1].time).getTime() / 1000; if (!isNaN(t)) last = fmtAge(st.now - t); }
  byId("overview").innerHTML =
    `<span>메시지 ${fmtCompactCount(st.messages_total)}</span>` +
    (agentBits ? `<span class="ov-agents">${agentBits}</span>` : "") +
    `<span>작업 ${fmtCompactCount(tasks.length)}</span>` +
    (completed ? `<span>완료 ${fmtCompactCount(completed)}</span>` : "") +
    (ticketCount ? `<span>티켓 ${fmtCompactCount(ticketCount)}</span>` : "") +
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
  setSideTab("work");
  if (hlTask === id) clearTaskHighlight();
  if (!taskRow(id) && !panelExpanded.tasks && (lastTasks || []).some(t => t.task_id === id)) {
    panelExpanded.tasks = true;
    sigTasks = null;
    await refresh();
  }
  highlightTask(id);
  taskJumpTimer = setTimeout(clearTaskHighlight, 1600);
}
let hlAgent = null, agentJumpTimer = null;
function agentRow(id) {
  return Array.from(document.querySelectorAll("#agents .agent[data-agent]"))
    .find(row => row.dataset.agent === id) || null;
}
function clearAgentHighlight() {
  hlAgent = null;
  document.querySelectorAll("#agents .agent.hl").forEach(r => r.classList.remove("hl"));
}
function highlightAgent(id) {
  if (hlAgent === id) return;
  clearAgentHighlight(); hlAgent = id;
  const row = agentRow(id);
  if (row) { row.classList.add("hl"); row.scrollIntoView({block:"nearest"}); }
}
async function jumpToAgent(id) {
  if (!AGENT_NAMES.includes(id)) return;
  clearTimeout(agentJumpTimer);
  setSideTab("agent", true, true);
  if (hlAgent === id) clearAgentHighlight();
  if (!agentRow(id) && !panelExpanded.agents) {
    panelExpanded.agents = true;
    sigAgents = null;
    await refresh();
  }
  highlightAgent(id);
  agentJumpTimer = setTimeout(clearAgentHighlight, 1600);
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
  let copyFallbackError = null;
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
    copyFallbackError = err;
  }
  const clipboard = window.navigator?.clipboard;
  if (clipboard?.writeText) {
    await clipboard.writeText(text);
    return;
  }
  throw copyFallbackError || new Error("copy command failed");
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
const SENSITIVITY_OPTIONS = [
  {value:"normal", label:"일반"},
  {value:"internal", label:"내부"},
  {value:"restricted", label:"제한"},
];
const COMPOSE_COMMANDS = [
  {command:"agent", icon:"agent", main:"/agent", meta:"에이전트"},
  {command:"task", icon:"list", main:"/task", meta:"작업"},
  {command:"security", icon:"lock", main:"/security", meta:"보안"},
];
const COMPOSE_COMMAND_NAMES = COMPOSE_COMMANDS.map(c => c.command);
const COMPOSE_COMMAND_PATTERN = COMPOSE_COMMAND_NAMES.join("|");
let composeTo = "all", composeKind = "note", composeTask = "";
let composeSensitivity = "normal";
let toOptions = [{value:"all", label:"전체"}], lastTasks = [];

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
    `<button type="button" class="dd-opt ${o.value === current ? "sel" : ""}" data-v="${esc(o.value)}">` +
    `<span>${esc(o.label)}</span>${o.sub ? `<span class="sub">${esc(o.sub)}</span>` : ""}</button>`
  ).join("") || `<div class="dd-empty muted">없음</div>`;
  dd.querySelectorAll(".dd-opt[data-v]").forEach(el => el.addEventListener("click", ev => {
    ev.stopPropagation(); dd.classList.remove("open"); onPick(el.getAttribute("data-v"));
  }));
}
function optionLabel(options, value) {
  const found = options.find(o => (typeof o === "string" ? o : o.value) === value);
  return found ? (typeof found === "string" ? found : found.label) : value;
}

function composeTaskTitle(taskId) {
  return (lastTasks.find(t => t.task_id === taskId) || {}).title || "";
}
function renderComposeTokens() {
  const label = byId("kind-token-label");
  if (label) label.textContent = kindLabel(composeKind);
  const kindToken = byId("kind-token");
  if (kindToken) kindToken.className = `compose-token kind-token tag kind ${cls(composeKind || "note")}`;
  document.querySelectorAll("#kind-pop button[data-v]").forEach(btn => btn.classList.toggle("on", btn.dataset.v === composeKind));
  const meta = byId("compose-meta-chips");
  if (!meta) return;
  const chips = [];
  if (composeToTouched && composeTo && composeTo !== "all") {
    chips.push({kind:"agent", icon:"agent", label:agentLabel(composeTo), tip:composeTo, clear:"agent"});
  }
  if (composeTask) {
    chips.push({kind:"task", icon:"list", label:composeTask, tip:composeTaskTitle(composeTask), clear:"task"});
  }
  if (composeSensitivity && composeSensitivity !== "normal") {
    chips.push({kind:`security ${cls(composeSensitivity)}`, icon:"lock", label:optionLabel(SENSITIVITY_OPTIONS, composeSensitivity), tip:"보안", clear:"security"});
  }
  meta.innerHTML = chips.map(c =>
    `<span class="compose-chip ${esc(c.kind)}" ${c.tip ? `data-tip="${esc(c.tip)}"` : ""}>` +
    `${icon(c.icon)}<span class="chip-main">${esc(c.label)}</span>` +
    `<button type="button" data-clear-compose="${esc(c.clear)}" aria-label="제거">${icon("x")}</button></span>`
  ).join("");
}

function buildPolicyDDs() {
  renderComposeTokens();
}
function closeDropdownMenus() {
  document.querySelectorAll(".dd.open").forEach(d => d.classList.remove("open"));
}
function closeKindMenu() {
  const wrap = byId("compose-kind");
  if (!wrap) return;
  wrap.classList.remove("open");
  byId("kind-token")?.setAttribute("aria-expanded", "false");
}
document.addEventListener("click", e => {
  const clear = e.target.closest("[data-clear-compose]");
  if (clear) {
    e.preventDefault(); e.stopPropagation();
    const what = clear.dataset.clearCompose;
    if (what === "agent") { composeTo = "all"; composeToTouched = false; }
    else if (what === "task") composeTask = "";
    else if (what === "security") composeSensitivity = "normal";
    renderComposeTokens();
    return;
  }
  const kindToken = e.target.closest("#kind-token");
  if (kindToken) {
    e.preventDefault(); e.stopPropagation();
    closeDropdownMenus();
    const wrap = byId("compose-kind");
    if (!wrap) return;
    const open = !wrap.classList.contains("open");
    wrap.classList.toggle("open", open);
    kindToken.setAttribute("aria-expanded", open ? "true" : "false");
    return;
  }
  const kindButton = e.target.closest("#kind-pop button[data-v]");
  if (kindButton) {
    e.preventDefault(); e.stopPropagation();
    composeKind = kindButton.dataset.v;
    renderComposeTokens();
    closeKindMenu();
    return;
  }
  const btn = e.target.closest(".dd-btn");
  if (btn) {
    e.stopPropagation();
    const dd = btn.closest(".dd"), wasOpen = dd.classList.contains("open");
    closeDropdownMenus();
    closeKindMenu();
    if (!wasOpen) dd.classList.add("open");
    return;
  }
  if (!e.target.closest(".dd")) closeDropdownMenus();
  if (!e.target.closest("#compose-kind")) closeKindMenu();
});

// 본문 입력창 높이.
const bodyEl = byId("body");
function growBody() {
  bodyEl.style.height = "auto";
  const height = Math.min(bodyEl.scrollHeight, 140);
  bodyEl.style.height = height + "px";
  bodyEl.closest(".composer-field")?.classList.toggle("compose-multiline", height > 34 || bodyEl.value.includes("\n"));
}

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
function makeComposePalette(inputEl, menuEl, onChange) {
  let items = [], active = -1, start = -1, token = 0, mode = "";
  const close = () => { menuEl.classList.remove("open"); items = []; active = -1; start = -1; mode = ""; };
  function slashCtx(before, pos) {
    const command = before.match(/(^|\s)\/([a-zA-Z]*)$/);
    if (command && !COMPOSE_COMMAND_NAMES.includes(command[2].toLowerCase())) {
      return {mode:"command", q:command[2].toLowerCase(), start:pos - command[2].length - 1};
    }
    const exact = before.match(new RegExp(`(^|\\s)\\/(${COMPOSE_COMMAND_PATTERN})(?:\\s+([^\\n/]*))?$`, "i"));
    if (!exact) return null;
    const leading = exact[1] || "";
    return {
      mode:exact[2].toLowerCase(),
      q:String(exact[3] || "").trim().toLowerCase(),
      start:pos - exact[0].length + leading.length,
    };
  }
  function ctxOf() {
    const pos = inputEl.selectionStart;
    const before = inputEl.value.slice(0, pos);
    const file = before.match(/(?:^|\s)@([^\s@]*)$/);
    if (file) return {mode:"file", q:file[1], start:pos - file[1].length - 1};
    return slashCtx(before, pos);
  }
  function commandItems(q) {
    return COMPOSE_COMMANDS
      .map(it => ({...it, mode:"command"}))
      .filter(it => !q || it.command.startsWith(q));
  }
  function slashItems(ctx) {
    if (ctx.mode === "command") return commandItems(ctx.q);
    if (ctx.mode === "agent") {
      return RECIPIENT_OPTIONS.map(o => ({
        mode:"agent", value:o.value, icon:"agent", main:agentLabel(o.value), meta:o.value,
      }));
    }
    if (ctx.mode === "task") {
      return lastTasks.map(t => ({
        mode:"task", value:t.task_id, icon:"list", main:t.task_id, meta:t.title || "",
      }));
    }
    return SENSITIVITY_OPTIONS.map(o => ({
      mode:"security", value:o.value, icon:o.value === "normal" ? "message" : "lock",
      main:o.label, meta:o.value === "normal" ? "" : "보안",
    }));
  }
  function filterItems(list, q) {
    if (!q) return list;
    return list.filter(it => `${it.main || ""} ${it.meta || ""}`.toLowerCase().includes(q));
  }
  async function update() {
    const ctx = ctxOf();
    if (!ctx) { close(); return; }
    const t = ++token; let next = [];
    if (ctx.mode === "file") {
      try {
        const files = (await (await fetch("/api/files?q=" + encodeURIComponent(ctx.q))).json()).files || [];
        next = files.map(f => {
          const cut = f.lastIndexOf("/") + 1;
          return {mode:"file", value:f, icon:"message", main:f.slice(cut), meta:f.slice(0, cut)};
        });
      } catch { close(); return; }
    } else {
      next = filterItems(slashItems(ctx), ctx.q);
    }
    if (t !== token) return;
    if (!next.length) { close(); return; }
    items = next; start = ctx.start; mode = ctx.mode; active = 0; render();
  }
  function render() {
    menuEl.innerHTML = items.map((it, i) =>
      `<div class="mention-opt ${i === active ? "active" : ""}" data-i="${i}">` +
      `<span class="mention-icon">${icon(it.icon || "message")}</span>` +
      `<span class="mention-main">${esc(it.main || it.value || "")}</span>` +
      `<span class="mention-meta">${esc(it.meta || "")}</span></div>`
    ).join("");
    menuEl.classList.add("open");
    menuEl.querySelectorAll(".mention-opt").forEach(el =>
      el.addEventListener("mousedown", ev => { ev.preventDefault(); insert(+el.dataset.i); }));
    const a = menuEl.querySelector(".mention-opt.active"); if (a) a.scrollIntoView({ block: "nearest" });
  }
  function replaceToken(text, caretOffset = text.length) {
    const before = inputEl.value.slice(0, start), after = inputEl.value.slice(inputEl.selectionStart);
    inputEl.value = before + text + after;
    const caret = before.length + caretOffset;
    if (onChange) onChange();
    inputEl.focus(); inputEl.setSelectionRange(caret, caret);
  }
  function removeCommandText() {
    replaceToken("", 0);
  }
  function insert(i) {
    const it = items[i]; if (!it) return;
    if (it.mode === "file") {
      replaceToken(it.value + " ");
      close();
      return;
    }
    if (it.mode === "command") {
      replaceToken("/" + it.command + " ");
      update();
      return;
    }
    if (it.mode === "agent") { composeTo = it.value; composeToTouched = true; }
    else if (it.mode === "task") composeTask = it.value;
    else if (it.mode === "security") composeSensitivity = it.value;
    removeCommandText();
    renderComposeTokens();
    close();
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
const composeMention = makeComposePalette(bodyEl, mentionEl, growBody);

const LEAD_REQUEST_KINDS = new Set(["task", "ticket", "stop"]);
function messageSubjectForKind(kind, body) {
  if (!LEAD_REQUEST_KINDS.has(kind)) return "";
  return body.split(/\r?\n/).map(s => s.trim()).find(Boolean) || kindLabel(kind);
}
async function sendMessage() {
  let body = bodyEl.value.trim();
  if (!body && composeKind === "stop") body = "정지 요청";
  if (!body) return;
  composeMention.close();
  const kind = composeKind;
  const target = (!composeToTouched && LEAD_AGENT_ID) ? LEAD_AGENT_ID : (composeTo || LEAD_AGENT_ID || "all");
  const ok = await post("/api/send", {
    to: target, kind, subject: messageSubjectForKind(kind, body), body, task_id: composeTask,
    sensitivity: composeSensitivity,
  });
  if (!ok) return;
  bodyEl.value = "";
  if (LEAD_REQUEST_KINDS.has(kind)) composeKind = "note";
  if (!composeToTouched) composeTo = "all";
  growBody();
  renderComposeTokens();
}
byId("compose").addEventListener("submit", e => { e.preventDefault(); sendMessage(); });
bodyEl.addEventListener("keydown", e => {
  if (composeMention.isOpen()) return;
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); sendMessage(); }
});
byId("toggle-key-context-lines").addEventListener("click", toggleKeyContextLines);
byId("edit-key-context").addEventListener("click", editKeyContext);
const stopbarEl = byId("stopbar");
stopbarEl.addEventListener("click", e => {
  const clear = e.target.closest("[data-clear-stop]");
  if (clear) { e.preventDefault(); clearStop(); }
});
// 세션 정리.
const settingsWrap = byId("settings-wrap");
byId("rotatebtn").addEventListener("click", async () => {
  settingsWrap.classList.remove("open");
  if (!await modal({message: "현재 메시지를 보관하고 타임라인을 비울까요?", confirmText: "보관"})) return;
  const r = await fetch("/api/rotate", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
  if (!r.ok) { await modal({message: "요청 실패: " + await r.text(), cancelText: null}); return; }
  const j = await r.json().catch(() => ({}));
  await modal({message: j.archived ? "메시지를 보관했습니다." : "보관할 메시지가 없습니다.", cancelText: null});
  resetSigs(); refresh();
});
byId("clearbtn").addEventListener("click", async () => {
  settingsWrap.classList.remove("open");
  if (await modal({message: "메시지와 확인 기록을 비울까요? 작업과 에이전트는 유지됩니다.", confirmText: "비우기", danger: true})) post("/api/clear", {});
});
byId("force-stopbtn")?.addEventListener("click", async () => {
  settingsWrap.classList.remove("open");
  if (!await modal({message: "루프를 강제 정지할까요?", confirmText: "강제 정지", danger: true})) return;
  await post("/api/force-stop", {reason:"force_stop"});
});
byId("viewer-authbtn").addEventListener("click", async () => {
  settingsWrap.classList.remove("open");
  if (VIEWER_AUTH.authenticated) {
    await post("/api/viewer-logout", {});
    return;
  }
  const creds = await viewerAuthModal();
  if (!creds) return;
  if (!creds.viewer || !creds.token) {
    await modal({message:"사용자와 토큰을 입력하세요.", cancelText:null});
    return;
  }
  const r = await fetch("/api/viewer-login", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(creds),
  });
  if (!r.ok) {
    await modal({message:"인증 실패", cancelText:null});
    return;
  }
  resetSigs();
  await refresh();
});
// 티켓.
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
// 작업.
function setTaskState(id, state) { post("/api/task-state", {id, state}); }
async function deleteTask(id) {
  if (await modal({message: "이 작업을 삭제할까요?", confirmText: "삭제", danger: true})) {
    post("/api/task-delete", {id});
  }
}
async function clearStop() {
  if (await modal({message: "정지 요청을 해제할까요?", confirmText: "해제"})) post("/api/clear-stop", {});
}
agentsEl.addEventListener("click", e => {
  if (handlePanelToggle(e)) return;
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
  if (sideVisible) syncSideTabThumbAfterLayout();
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
  return target instanceof Element && !!target.closest("#side, #toggleside, .modal-ov");
}
function closeFloatingSidePanelFromOutside(target) {
  if (!isFloatingSideOpen() || isSidePanelInteractionTarget(target)) return;
  closeFloatingSidePanel();
}
byId("toggleside").addEventListener("click", toggleSidePanel);
byId("side-tab-work").addEventListener("click", () => setSideTab("work", true, true));
byId("side-tab-agent").addEventListener("click", () => setSideTab("agent", true, true));
byId("side-tab-bridge").addEventListener("click", () => setSideTab("bridge", true, true));
document.addEventListener("pointerdown", e => closeFloatingSidePanelFromOutside(e.target), true);
document.addEventListener("focusin", e => closeFloatingSidePanelFromOutside(e.target), true);
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && closeFloatingSidePanel()) e.stopPropagation();
}, true);
byId("togglecompose").addEventListener("click", () => flip("composeOpen"));
function onSideModeChange() {
  document.body.classList.add("side-mode-switching");
  applyLayout();
  requestAnimationFrame(() => requestAnimationFrame(() => document.body.classList.remove("side-mode-switching")));
}
if (sideAutoCollapseMQ.addEventListener) sideAutoCollapseMQ.addEventListener("change", onSideModeChange);
else if (sideAutoCollapseMQ.addListener) sideAutoCollapseMQ.addListener(onSideModeChange);
setSideTab(sideTab, false);
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
  moveSideTabThumb();
}
sizeSlider.addEventListener("input", () => { localStorage.setItem("textsize", sizeSlider.value); applyTextSize(); });
applyTextSize();
byId("settingsbtn").addEventListener("click", (e) => { e.stopPropagation(); settingsWrap.classList.toggle("open"); });
document.addEventListener("click", (e) => { if (!e.target.closest("#settings-wrap")) settingsWrap.classList.remove("open"); });
buildPolicyDDs();
updateFilterIndicator();

// 첫 페인트 뒤 애니메이션을 켠다.
requestAnimationFrame(() => requestAnimationFrame(() => { document.body.classList.remove("no-anim"); moveSideTabThumb(); }));

refresh(); setInterval(refresh, 2500);
