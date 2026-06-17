const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const cls = s => String(s ?? "").replace(/[^a-zA-Z0-9_-]/g, "_");
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

// 스레딩 칩 아이콘 (task 연결 / 응답 대상)
const ICON_TASK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/></svg>`;
const ICON_REPLY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 7l-5 5 5 5"/><path d="M4 12h11a5 5 0 0 1 5 5v1"/></svg>`;
const ICON_EMPTY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 11.3a8 8 0 0 1-8.6 8 8.7 8.7 0 0 1-3.6-.8L3.5 20l1.5-4.8a8 8 0 0 1-.8-3.6 8 8 0 0 1 8-7.6 8 8 0 0 1 8.3 7.3z"/></svg>`;
const ICON_LOCK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>`;
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
    return `<span class="ackchip ackall" title="전체 확인: ${esc(ackers.join(", "))}">${ICON_DBLCHECK}</span>`;
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
  return `<span class="chip security ${cls(level)}" title="${esc(level)}">${ICON_LOCK}<span>${esc(level)}</span></span>`;
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
  s = s.replace(/\*\*([^\n]+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^\s*][^\n*]*?)\*(?!\*)/g, "$1<em>$2</em>");
  s = s.replace(/\[([^\]]+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  s = s.replace(/^\s*#{1,3}\s+(.+)$/gm, '<div class="md-h">$1</div>');
  s = s.replace(/^\s*[-*]\s+(.+)$/gm, '<div class="md-li">$1</div>');
  for (let i = keep.length - 1; i >= 0; i--) s = s.split("@@KTEX" + i + "@@").join(keep[i]);
  s = s.replace(/\n+(<(?:div class="md-|pre class="md-))/g, "$1");
  s = s.replace(/(<\/(?:div|pre)>)\n+/g, "$1");
  return s;
}
function renderMsg(m, acks) {
  if (m._decode_error) return `<div class="card msg"><div class="body">${esc(m._decode_error)}</div></div>`;
  const ackers = acks[m.id] || [];
  const body = m.body || "";
  const subject = m.subject || "";
  const bodyHtml = body ? `<div class="body">${renderBody(body)}</div>` : "";
  const refsHtml = (m.refs || []).length ? `<div class="refs">${m.refs.flatMap(r => r.split(",")).map(s => s.trim()).filter(Boolean).map(renderRef).join("")}</div>` : "";
  const metaBits = [`<span class="mid">${esc(m.id)}</span>`];
  if (m.task_id) metaBits.push(`<span class="chip threadchip" data-task="${esc(m.task_id)}">${ICON_TASK}${esc(m.task_id)}</span>`);
  if (m.reply_to) metaBits.push(`<span class="chip threadchip" data-reply="${esc(m.reply_to)}">${ICON_REPLY}${esc(m.reply_to)}</span>`);
  const metaHtml = `<div class="msg-meta">${metaBits.join("")}</div>`;
  let content;
  if (subject) {
    content = `<details data-msgid="${esc(m.id)}" ${expanded.has(m.id) ? "open" : ""}>
         <summary><span class="subject">${esc(subject)}</span><span class="disc-caret"></span></summary>
         <div class="detail">${bodyHtml}${refsHtml}${metaHtml}</div>
       </details>`;
  } else {
    content = `${bodyHtml.replace('class="body"', 'class="body nosubj"')}${refsHtml}${metaHtml}`;
  }
  const canReply = m.from && m.from !== "user";
  const replyBtn = canReply ? `<button class="msg-act msg-reply" type="button" data-id="${esc(m.id)}" title="답장" aria-label="답장">${ICON_REPLY}</button>` : "";
  const deleteBtn = `<button class="msg-act msg-del" type="button" data-delete-message="${esc(m.id)}" title="삭제" aria-label="삭제">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13"/></svg>
  </button>`;
  const replyBox = (canReply && replyOpenId === m.id) ? `<div class="reply-box" data-to="${esc(m.from)}" data-reply="${esc(m.id)}"><div class="reply-row"><input class="reply-in" type="text" placeholder="${esc(m.from)}에게 답장…"><button class="reply-go" type="button">보내기</button></div><div class="mention-menu"></div></div>` : "";
  return `<div class="card msg" data-id="${esc(m.id)}">
    <div class="head">
      <span class="route">${esc(m.from)} → ${esc(m.to)}</span>
      <span class="chip kind ${cls(m.kind)}">${esc(m.kind)}</span>
      ${securityChip(m)}
      <span>${fmtTime(m.time)}</span>
      ${renderAcks(ackers, m.from)}
      <span class="msg-actions">${replyBtn}${deleteBtn}</span>
    </div>
    ${content}
    ${replyBox}
  </div>`;
}

let TASK_STATES = [];
let openTaskDD = null;
const TASK_SHOW = 3;
let taskShowAll = false;
const TICKET_SHOW = 3;
let ticketShowAll = false;
const taskTextOpen = new Set();
const STATE_LABEL = {submitted:"대기", working:"진행 중", input_required:"확인 필요",
                     completed:"완료", failed:"오류", canceled:"취소"};
function renderTicket(ticket) {
  const id = ticket.issue_id || ticket.ticket_id;
  const refs = (ticket.refs || []).length
    ? `<div class="todo-desc">${ticket.refs.flatMap(r => r.split(",")).map(s => s.trim()).filter(Boolean).map(renderRef).join("")}</div>`
    : "";
  return `<div class="todo ticket" data-ticket="${esc(id)}">
    <span class="todo-mark submitted"></span>
    <div class="todo-body">
      <div class="todo-text">${esc(ticket.title || "(제목 없음)")}</div>
      ${ticket.body ? `<div class="todo-desc">${esc(ticket.body)}</div>` : ""}
      ${refs}
      <div class="todo-meta"><code class="todo-id">${esc(id)}</code>${securityChip(ticket)}<span>${fmtTime(ticket.created_at)}</span></div>
    </div>
    <div class="todo-actions">
      <button type="button" class="todo-run" title="진행" aria-label="진행" data-accept-ticket="${esc(id)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 6.5"/></svg>
      </button>
      <button type="button" class="todo-del" title="삭제" aria-label="삭제" data-reject-ticket="${esc(id)}">
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
    ? `<div class="todo-desc${taskTextOpen.has(t.task_id) ? "" : " clamp"}">${esc(t.note)}</div><button type="button" class="todo-more" hidden>더보기</button>`
    : "";
  return `<div class="todo ${cls(t.state)}" data-task="${esc(t.task_id)}">
    <span class="todo-mark ${cls(t.state)}"></span>
    <div class="todo-body">
      <div class="todo-text">${esc(t.title || "(제목 없음)")}</div>
      ${descHtml}
      <div class="todo-meta"><code class="todo-id ${filterTasks.has(t.task_id) ? "on" : ""}" data-task="${esc(t.task_id)}">${esc(t.task_id)}</code>${securityChip(t)}<span class="todo-time" data-c="${c}" data-u="${u}" data-s="${esc(t.state)}"></span>${assignStr ? `<span class="todo-rest">${assignStr}</span>` : ""}</div>
    </div>
    <div class="todo-actions">
      <button type="button" class="todo-del" title="삭제" aria-label="삭제" data-delete-task="${esc(t.task_id)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13"/></svg>
      </button>
      <div class="tdd ${openTaskDD === t.task_id ? "open" : ""}" data-task="${esc(t.task_id)}">
        <button type="button" class="tdd-btn">${esc(STATE_LABEL[t.state] || t.state)}<span class="dd-caret"></span></button>
        <div class="tdd-menu">${opts}</div>
      </div>
    </div>
  </div>`;
}

function renderAgent(name, a) {
  return `<div class="card agent" data-hb="${a.heartbeat || ""}">
    <div class="name">${esc(name)} <span class="state ${cls(a.state)}">${esc(a.state)}</span></div>
    ${a.task ? `<div class="task"><span class="chip threadchip" data-task="${esc(a.task)}">${ICON_TASK}${esc(a.task)}</span></div>` : ""}
    ${a.note ? `<div class="note">${esc(a.note)}</div>` : ""}
    <div class="beat"><span class="age"></span></div>
    <div class="agent-actions">
      <button type="button" class="todo-del" title="제거" aria-label="제거" data-delete-agent="${esc(name)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13"/></svg>
      </button>
    </div>
  </div>`;
}
function updateAgentAges(now) {
  for (const card of document.querySelectorAll("#agents .agent")) {
    const beat = card.querySelector(".beat"), ageEl = card.querySelector(".age");
    if (!ageEl) continue;
    const hb = parseFloat(card.dataset.hb);
    if (isNaN(hb)) { ageEl.textContent = "활동 없음"; beat.classList.add("stale"); continue; }
    const age = now - hb, stale = age > 900;
    beat.classList.toggle("stale", stale);
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
function expandTasks() { taskShowAll = true; sigTasks = null; refresh(); }
function collapseTasks() { taskShowAll = false; sigTasks = null; refresh(); }
function expandTickets() { ticketShowAll = true; sigTickets = null; refresh(); }
function collapseTickets() { ticketShowAll = false; sigTickets = null; refresh(); }
async function clearDone() {
  const done = (lastTasks || []).filter(t => t.state === "completed");
  if (!done.length) return;
  if (!await modal({message: `완료된 작업 ${done.length}개를 지울까요?`, confirmText: "지우기", danger: true})) return;
  for (const t of done) await fetch("/api/task-delete", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: t.task_id})});
  resetSigs(); await refresh();
}

// 섹션별 시그니처가 바뀔 때만 다시 그린다.
let sigStop = null, sigMsg = null, sigTickets = null, sigTasks = null, sigAgents = null, sigDD = null;
function resetSigs() { sigStop = sigMsg = sigTickets = sigTasks = sigAgents = sigDD = null; }

// 최근 N건을 불러온다.
let msgLimit = 100, pinScroll = false;
function loadMore() { msgLimit += 100; pinScroll = true; sigMsg = null; refresh(); }

// 메시지 필터.
let filterAgents = new Set(), filterTasks = new Set(), searchQuery = "";
let lastMsgs = [], lastAcks = {}, lastHidden = 0;
function filterSig() { return [...filterAgents].sort().join(",") + "|" + [...filterTasks].sort().join(",") + "|" + searchQuery; }
function passesFilter(m) {
  if (filterAgents.size && !filterAgents.has(m.from) && !filterAgents.has(m.to)) return false;
  if (filterTasks.size && !filterTasks.has(m.task_id)) return false;
  if (searchQuery && !(((m.subject || "") + " " + (m.body || "")).toLowerCase().includes(searchQuery))) return false;
  return true;
}
function renderTimeline() {
  const tl = document.getElementById("timeline");
  const prevH = tl.scrollHeight, prevY = tl.scrollTop;
  const msgs = lastMsgs.filter(passesFilter);
  let html;
  if (!msgs.length) html = `<div class="empty-state">${ICON_EMPTY}<span>메시지 없음</span></div>`;
  else {
    html = msgs.slice().reverse().map(m => renderMsg(m, lastAcks)).join("");
    if (!filterAgents.size && !filterTasks.size && !searchQuery && lastHidden > 0)
      html += `<button type="button" class="load-more" onclick="loadMore()">이전 메시지 ${lastHidden}개</button>`;
  }
  tl.innerHTML = html;
  if (window.renderMathInElement) renderMathInElement(tl, {delimiters:[{left:"$$",right:"$$",display:true},{left:"$",right:"$",display:false}], throwOnError:false, ignoredClasses:["md-code","md-pre"]});
  if (replyOpenId) { const box = tl.querySelector(".reply-box"); if (box) { const inp = box.querySelector(".reply-in"); inp.value = replyDraft; makeMention(inp, box.querySelector(".mention-menu"), () => { replyDraft = inp.value; }); } }
  if (pinScroll) { tl.scrollTop = prevY; pinScroll = false; }
  else if (prevY > 50) tl.scrollTop = prevY + (tl.scrollHeight - prevH);
}
document.getElementById("timeline").addEventListener("toggle", e => {
  const d = e.target.closest("details[data-msgid]");
  if (d) onToggle(d.dataset.msgid, d.open);
}, true);

async function refresh() {
  let st;
  try { st = await (await fetch("/api/state?limit=" + msgLimit)).json(); }
  catch { document.getElementById("refreshed").textContent = "서버 연결 끊김"; return; }
  document.getElementById("refreshed").textContent = "";
  STATE_ROOT = st.root || "";
  const proj = document.getElementById("project");
  if (STATE_ROOT && proj.dataset.tip !== STATE_ROOT) {
    proj.textContent = STATE_ROOT.split("/").filter(Boolean).pop() || STATE_ROOT;
    proj.dataset.tip = STATE_ROOT;   // 전체 경로는 커스텀 툴팁으로
  }
  AGENT_NAMES = Object.keys(st.status.agents || {}).sort();
  TASK_STATES = st.task_states || [];

  // 정지 배너
  const stopSig = JSON.stringify(st.stop || null);
  if (stopSig !== sigStop) {
    sigStop = stopSig;
    const bar = document.getElementById("stopbar");
    if (st.stop) {
      bar.style.display = "block";
      bar.innerHTML = `정지 요청: ${esc(st.stop.by)} · ${esc(st.stop.reason)}` +
        (st.stop.detail ? ` · ${esc(JSON.stringify(st.stop.detail))}` : "") +
        ` <button class="btn" style="margin-left:10px" onclick="clearStop()">해제</button>`;
    } else bar.style.display = "none";
  }

  const acks = {};
  for (const r of st.acks) (acks[r.id] = acks[r.id] || []).push(r.agent);
  lastMsgs = st.messages; lastAcks = acks;
  lastHidden = Math.max(0, (st.messages_total || st.messages.length) - st.messages.length);
  updateOverview(st);
  const msgSig = JSON.stringify(st.messages) + "|" + JSON.stringify(st.acks) + "|" + lastHidden + "|" + filterSig();
  if (msgSig !== sigMsg) { sigMsg = msgSig; renderTimeline(); }

  const tickets = (st.tickets || st.issues || []).slice().sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  const ticketSig = JSON.stringify(tickets) + "|" + ticketShowAll;
  if (ticketSig !== sigTickets) {
    sigTickets = ticketSig;
    const shownTickets = ticketShowAll ? tickets : tickets.slice(0, TICKET_SHOW);
    const moreTickets = tickets.length - shownTickets.length;
    let ih = shownTickets.map(renderTicket).join("") || `<div class="todo muted" style="padding:8px">티켓 없음</div>`;
    if (moreTickets > 0) ih += `<button type="button" class="todo-expand" onclick="expandTickets()">티켓 ${moreTickets}개 더 보기<span class="exp-caret down"></span></button>`;
    else if (ticketShowAll && tickets.length > TICKET_SHOW) ih += `<button type="button" class="todo-expand" onclick="collapseTickets()">접기<span class="exp-caret up"></span></button>`;
    document.getElementById("tickets").innerHTML = ih;
  }

  const tasks = (st.tasks || []).slice().sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  const taskSig = JSON.stringify(tasks) + "|" + taskShowAll;
  if (taskSig !== sigTasks) {
    sigTasks = taskSig;
    const shown = taskShowAll ? tasks : tasks.slice(0, TASK_SHOW);
    const moreN = tasks.length - shown.length;
    let th = shown.map(renderTask).join("") || `<div class="todo muted" style="padding:8px">작업 없음</div>`;
    if (moreN > 0) th += `<button type="button" class="todo-expand" onclick="expandTasks()">작업 ${moreN}개 더 보기<span class="exp-caret down"></span></button>`;
    else if (taskShowAll && tasks.length > TASK_SHOW) th += `<button type="button" class="todo-expand" onclick="collapseTasks()">접기<span class="exp-caret up"></span></button>`;
    document.getElementById("tasks").innerHTML = th;
    fitTaskTexts();
  }
  document.getElementById("clear-done").hidden = !tasks.some(t => t.state === "completed");
  updateTaskTimes(st.now);

  const agents = st.status.agents || {};
  const agentSig = JSON.stringify(AGENT_NAMES.map(n => [n, agents[n].state, agents[n].task, agents[n].note, agents[n].updated_at]));
  if (agentSig !== sigAgents) {
    sigAgents = agentSig;
    document.getElementById("agents").innerHTML =
      AGENT_NAMES.map(n => renderAgent(n, agents[n])).join("") ||
      `<div class="card agent muted">등록된 에이전트 없음</div>`;
  }
  updateAgentAges(st.now);

  lastTasks = tasks;
  const cards = st.cards || {};
  const recipients = [...new Set([...AGENT_NAMES, ...Object.keys(cards)])].sort();
  RECIPIENT_NAMES = recipients.filter(n => n && n !== "all");
  const ddSig = JSON.stringify(recipients) + "|" + JSON.stringify(tasks.map(t => [t.task_id, t.title])) + "|" + composeTo + "|" + composeTask;
  if (ddSig !== sigDD) {
    sigDD = ddSig;
    toOptions = recipients.map(n => ({value:n, label:n, sub:(cards[n] && cards[n].name && cards[n].name !== n) ? cards[n].name : ""}))
      .concat({value:"all", label:"all (전체)"});
    RECIPIENT_OPTIONS = toOptions.filter(o => o.value && o.value !== "all");
    if (!toOptions.some(o => o.value === composeTo)) composeTo = toOptions.length ? toOptions[0].value : "all";
    buildDD("dd-to", toOptions, composeTo, pickTo);
    rebuildTaskDD();
  }
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

// 모달은 input이면 문자열/null, 아니면 true/false를 반환한다.
function modal(opts) {
  const {message = "", input = false, value = "", confirmText = "확인", cancelText = "취소", danger = false} = opts || {};
  return new Promise(resolve => {
    let settled = false;
    const ov = document.createElement("div");
    ov.className = "modal-ov";
    ov.innerHTML = `<div class="modal" role="dialog" aria-modal="true">
      <div class="modal-msg"></div>
      ${input ? `<input class="modal-input" type="text">` : ""}
      <div class="modal-actions">
        ${cancelText ? `<button type="button" class="modal-btn" data-act="cancel">${esc(cancelText)}</button>` : ""}
        <button type="button" class="modal-btn ${danger ? "danger" : "primary"}" data-act="ok">${esc(confirmText)}</button>
      </div>
    </div>`;
    ov.querySelector(".modal-msg").textContent = message;
    const inp = ov.querySelector(".modal-input");
    if (inp) inp.value = value;
    document.body.appendChild(ov);
    requestAnimationFrame(() => ov.classList.add("show"));
    function done(val) { if (settled) return; settled = true; ov.classList.remove("show"); setTimeout(() => ov.remove(), 160); resolve(val); }
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
  return new Promise(resolve => {
    let settled = false;
    const ov = document.createElement("div");
    ov.className = "modal-ov";
    ov.innerHTML = `<div class="modal" role="dialog" aria-modal="true">
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
    </div>`;
    const dd = ov.querySelector(".modal-dd");
    const textarea = ov.querySelector(".modal-textarea");
    const pick = v => { selected = v; buildDD(dd, choices, selected, pick); textarea.focus(); };
    buildDD(dd, choices, selected, pick);
    textarea.value = note;
    document.body.appendChild(ov);
    requestAnimationFrame(() => ov.classList.add("show"));
    function done(val) { if (settled) return; settled = true; ov.classList.remove("show"); setTimeout(() => ov.remove(), 160); resolve(val); }
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
const fwrap = document.getElementById("filter-wrap");
function updateFilterIndicator() {
  document.getElementById("filterbtn").classList.toggle("active", filterAgents.size > 0 || filterTasks.size > 0);
  const bits = [];
  if (filterAgents.size) bits.push("참여자 " + filterAgents.size);
  if (filterTasks.size) bits.push("작업 " + filterTasks.size);
  document.getElementById("filter-summary").textContent = bits.join(" · ");
}
function buildFilterUI() {
  const parts = [...new Set(["user", ...lastMsgs.flatMap(m => [m.from, m.to])].filter(Boolean))].sort();
  document.getElementById("fp-agents").innerHTML = parts.map(a =>
    `<div class="fp-opt ${filterAgents.has(a) ? "on" : ""}" data-a="${esc(a)}"><span class="fp-check"></span><span class="fp-label">${esc(a)}</span></div>`).join("")
    || `<div class="fp-empty">없음</div>`;
  document.getElementById("fp-tasks").innerHTML = lastTasks.map(t =>
    `<div class="fp-opt ${filterTasks.has(t.task_id) ? "on" : ""}" data-t="${esc(t.task_id)}" title="${esc(t.title || "")}"><span class="fp-check"></span><code class="fp-id">${esc(t.task_id)}</code><span class="fp-title">${esc(t.title || "")}</span></div>`).join("")
    || `<div class="fp-empty">없음</div>`;
}
function afterFilterChange() { updateFilterIndicator(); sigMsg = null; renderTimeline(); }
function toggleInSet(set, key, el) {
  if (set.has(key)) { set.delete(key); el.classList.remove("on"); }
  else { set.add(key); el.classList.add("on"); }
  afterFilterChange();
}
document.getElementById("filterbtn").addEventListener("click", e => {
  e.stopPropagation();
  if (fwrap.classList.toggle("open")) buildFilterUI();
});
document.getElementById("fp-agents").addEventListener("click", e => {
  const o = e.target.closest(".fp-opt"); if (o && o.dataset.a) toggleInSet(filterAgents, o.dataset.a, o);
});
document.getElementById("fp-tasks").addEventListener("click", e => {
  const o = e.target.closest(".fp-opt"); if (o && o.dataset.t) toggleInSet(filterTasks, o.dataset.t, o);
});
document.getElementById("fp-reset").addEventListener("click", () => {
  filterAgents.clear(); filterTasks.clear();
  buildFilterUI(); afterFilterChange();
});
// 작업 id 클릭은 메시지 필터를 토글한다.
document.getElementById("tasks").addEventListener("click", e => {
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
  const id = e.target.closest(".todo-id");
  if (id && id.dataset.task) { e.stopPropagation(); toggleInSet(filterTasks, id.dataset.task, id); }
});
document.getElementById("clear-done").addEventListener("click", clearDone);
// 툴팁.
const tipEl = document.createElement("div"); tipEl.className = "tooltip"; document.body.appendChild(tipEl);
let tipTarget = null;
document.addEventListener("mouseover", e => {
  const el = e.target.closest("[title],[data-tip]");
  if (!el || el === tipTarget) return;
  if (el.hasAttribute("title")) { el.dataset.tip = el.getAttribute("title"); el.removeAttribute("title"); }
  const text = el.dataset.tip;
  if (!text) return;
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
const STATE_COLOR = {running:"var(--running)", waiting:"var(--waiting)", done:"var(--done)", error:"var(--error)"};
const AGENT_STATE_LABEL = {running:"실행 중", waiting:"대기", done:"완료", error:"오류"};
function updateOverview(st) {
  const ag = st.status.agents || {};
  const order = ["running", "waiting", "done", "error"];
  const counts = {};
  for (const n in ag) { const s = ag[n].state; counts[s] = (counts[s] || 0) + 1; }
  const states = order.filter(s => counts[s]).concat(Object.keys(counts).filter(s => !order.includes(s)));
  const agentBits = states.map(s =>
    `<span class="ov-ag" data-tip="${esc((AGENT_STATE_LABEL[s] || s) + " " + counts[s])}"><span class="ov-dot" style="background:${STATE_COLOR[s] || "var(--circle)"}"></span>${counts[s]}</span>`).join("");
  const tasks = st.tasks || [];
  const working = tasks.filter(t => t.state === "working").length;
  const ticketCount = (st.tickets || st.issues || []).length;
  let last = "";
  if (st.messages.length) { const t = new Date(st.messages[st.messages.length - 1].time).getTime() / 1000; if (!isNaN(t)) last = fmtAge(st.now - t); }
  document.getElementById("overview").innerHTML =
    `<span>메시지 ${st.messages_total}</span>` +
    (agentBits ? `<span class="ov-agents">${agentBits}</span>` : "") +
    `<span>작업 ${tasks.length}${working ? " (진행 " + working + ")" : ""}</span>` +
    (ticketCount ? `<span>티켓 ${ticketCount}</span>` : "") +
    (last ? `<span>${esc(last)}</span>` : "");
  fitOverview();
}
// 개요가 넘치면 뒤 세그먼트부터 숨긴다.
function fitOverview() {
  const ov = document.getElementById("overview"); if (!ov) return;
  const segs = [...ov.children];
  segs.forEach(s => s.style.display = "");
  for (let i = segs.length - 1; i >= 1 && ov.scrollWidth > ov.clientWidth + 1; i--) segs[i].style.display = "none";
}
window.addEventListener("resize", fitOverview);
// 메시지 검색.
const searchWrap = document.getElementById("search-wrap"), searchIn = document.getElementById("search-in");
document.getElementById("searchbtn").addEventListener("click", e => {
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
function highlightTask(id) {
  if (hlTask === id) return;
  clearTaskHighlight(); hlTask = id;
  const row = document.querySelector(`#tasks .todo[data-task="${id}"]`);
  if (row) { row.classList.add("hl"); row.scrollIntoView({block:"nearest"}); }
}
function clearTaskHighlight() {
  hlTask = null;
  document.querySelectorAll("#tasks .todo.hl").forEach(r => r.classList.remove("hl"));
}
const timelineEl = document.getElementById("timeline");
timelineEl.addEventListener("mouseover", e => {
  const chip = e.target.closest(".threadchip[data-task]");
  if (chip) highlightTask(chip.dataset.task);
});
timelineEl.addEventListener("mouseout", e => {
  const chip = e.target.closest(".threadchip[data-task]");
  if (!chip) return;
  if (e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest(".threadchip[data-task]") === chip) return;
  clearTaskHighlight();
});
// reply 칩은 응답 대상 메시지를 강조한다.
let msgHlTimer = null;
function highlightMsg(id) {
  const row = document.querySelector(`#timeline .msg[data-id="${id}"]`);
  if (!row) return;
  row.scrollIntoView({block:"center", behavior:"smooth"});
  document.querySelectorAll(".msg.hlmsg").forEach(r => r.classList.remove("hlmsg"));
  row.classList.add("hlmsg");
  clearTimeout(msgHlTimer);
  msgHlTimer = setTimeout(() => row.classList.remove("hlmsg"), 1600);
}
timelineEl.addEventListener("click", e => {
  const chip = e.target.closest(".threadchip[data-reply]");
  if (chip) highlightMsg(chip.dataset.reply);
});
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
timelineEl.addEventListener("click", e => {
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
// 에이전트 패널의 작업 pill도 작업 항목을 강조한다.
const agentsHoverEl = document.getElementById("agents");
agentsHoverEl.addEventListener("mouseover", e => {
  const chip = e.target.closest(".threadchip[data-task]");
  if (chip) highlightTask(chip.dataset.task);
});
agentsHoverEl.addEventListener("mouseout", e => {
  const chip = e.target.closest(".threadchip[data-task]");
  if (!chip) return;
  if (e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest(".threadchip[data-task]") === chip) return;
  clearTaskHighlight();
});

// 작성 상태.
let composeTo = "all", composeKind = "note", composeTask = "";
let toOptions = [{value:"all", label:"all"}], taskOptions = [], lastTasks = [];

// 드롭다운은 작성 패널과 모달이 같은 마크업과 동작을 쓴다.
function buildDD(target, options, current, onPick, placeholder) {
  const dd = typeof target === "string" ? document.getElementById(target) : target;
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
  dd.querySelectorAll(".dd-opt[data-v]").forEach(el => el.onclick = ev => {
    ev.stopPropagation(); dd.classList.remove("open"); onPick(el.getAttribute("data-v"));
  });
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
document.addEventListener("click", e => {
  const btn = e.target.closest(".dd-btn");
  if (btn) {
    e.stopPropagation();
    const dd = btn.closest(".dd"), wasOpen = dd.classList.contains("open");
    document.querySelectorAll(".dd.open").forEach(d => d.classList.remove("open"));
    if (!wasOpen) dd.classList.add("open");
    return;
  }
  if (!e.target.closest(".dd")) document.querySelectorAll(".dd.open").forEach(d => d.classList.remove("open"));
});

// kind 세그먼트.
const segEl = document.getElementById("seg-kind");
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
const bodyEl = document.getElementById("body");
function growBody() { bodyEl.style.height = "auto"; bodyEl.style.height = Math.min(bodyEl.scrollHeight, 140) + "px"; }

// 파일 멘션 자동완성.
const mentionEl = document.getElementById("mention");
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
    menuEl.innerHTML = items.map((f, i) => { const cut = f.lastIndexOf("/") + 1;
      return `<div class="mention-opt ${i === active ? "active" : ""}" data-i="${i}"><span class="dir">${esc(f.slice(0, cut))}</span><span class="base">${esc(f.slice(cut))}</span></div>`; }).join("");
    menuEl.classList.add("open");
    menuEl.querySelectorAll(".mention-opt").forEach(el => el.onmousedown = ev => { ev.preventDefault(); insert(+el.dataset.i); });
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
document.getElementById("compose").addEventListener("submit", e => { e.preventDefault(); sendMessage(); });
bodyEl.addEventListener("keydown", e => {
  if (composeMention.isOpen()) return;
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); sendMessage(); }
});
document.getElementById("stopbtn").addEventListener("click", async () => {
  document.getElementById("settings-wrap").classList.remove("open");
  const reason = await modal({message:"정지 요청을 보내면 에이전트 협업 루프가 멈춥니다. 사유 (선택):", input:true, value:"user_stop", confirmText:"요청", danger:true});
  if (reason === null) return;
  post("/api/stop", {reason: reason.trim() || "user_stop"});
});
// 세션 정리.
document.getElementById("rotatebtn").addEventListener("click", async () => {
  document.getElementById("settings-wrap").classList.remove("open");
  if (!await modal({message: "현재 메시지를 archive/로 보관하고 타임라인을 비웁니다. 계속할까요?", confirmText: "보관"})) return;
  const r = await fetch("/api/rotate", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
  if (!r.ok) { await modal({message: "요청 실패: " + await r.text(), cancelText: null}); return; }
  const j = await r.json().catch(() => ({}));
  await modal({message: j.archived ? "메시지를 보관함(archive/)으로 회전했습니다." : "보관할 메시지가 없습니다.", cancelText: null});
  resetSigs(); refresh();
});
document.getElementById("clearbtn").addEventListener("click", async () => {
  document.getElementById("settings-wrap").classList.remove("open");
  if (await modal({message: "현재 메시지·확인 기록을 비웁니다(작업·에이전트는 유지). 계속할까요?", confirmText: "비우기", danger: true})) post("/api/clear", {});
});
// 티켓.
const newticketBtn = document.getElementById("newticket");
const newticketForm = document.getElementById("newticket-form");
const newticketTitle = document.getElementById("newticket-title");
function setNewticketOpen(open) {
  newticketForm.hidden = !open;
  newticketBtn.classList.toggle("open", open);
  if (open) newticketTitle.focus();
}
newticketBtn.addEventListener("click", () => setNewticketOpen(newticketForm.hidden));
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
document.getElementById("tickets").addEventListener("click", e => {
  const accept = e.target.closest("[data-accept-ticket]");
  if (accept) { acceptTicket(accept.dataset.acceptTicket); return; }
  const reject = e.target.closest("[data-reject-ticket]");
  if (reject) rejectTicket(reject.dataset.rejectTicket);
});
// 새 작업.
const newtaskBtn = document.getElementById("newtask");
const newtaskForm = document.getElementById("newtask-form");
const newtaskTitle = document.getElementById("newtask-title");
function setNewtaskOpen(open) {
  newtaskForm.hidden = !open;
  newtaskBtn.classList.toggle("open", open);
  if (open) newtaskTitle.focus();
}
newtaskBtn.addEventListener("click", () => setNewtaskOpen(newtaskForm.hidden));
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
async function deleteAgent(agent) { if (await modal({message: `에이전트 '${agent}' 상태를 지울까요?`, confirmText: "제거", danger: true})) post("/api/agent-delete", {agent}); }
async function clearStop() { if (await modal({message: "정지 요청을 해제할까요?", confirmText: "해제"})) post("/api/clear-stop", {}); }
document.getElementById("agents").addEventListener("click", e => {
  const del = e.target.closest("[data-delete-agent]");
  if (del) deleteAgent(del.dataset.deleteAgent);
});

// 작업 상태 드롭다운.
document.addEventListener("click", e => {
  const opt = e.target.closest(".tdd-opt");
  if (opt) {
    e.stopPropagation();
    openTaskDD = null; setTaskState(opt.dataset.task, opt.dataset.state);
    return;
  }
  const btn = e.target.closest(".tdd-btn");
  if (btn) {
    e.stopPropagation();
    const tdd = btn.closest(".tdd"), wasOpen = tdd.classList.contains("open");
    document.querySelectorAll(".tdd.open").forEach(d => d.classList.remove("open"));
    openTaskDD = null;
    if (!wasOpen) { tdd.classList.add("open"); openTaskDD = tdd.dataset.task; }
    return;
  }
  document.querySelectorAll(".tdd.open").forEach(d => d.classList.remove("open")); openTaskDD = null;
});

// 레이아웃 토글.
function applyLayout() {
  const side = localStorage.getItem("sideCollapsed") === "1";
  const compose = localStorage.getItem("composeOpen") === "1";
  document.body.classList.toggle("side-collapsed", side);
  document.body.classList.toggle("compose-open", compose);
  document.getElementById("toggleside").classList.toggle("on", !side);
  document.getElementById("togglecompose").classList.toggle("on", compose);
  const c = document.getElementById("compose");
  if (compose) setTimeout(() => { if (localStorage.getItem("composeOpen") === "1") c.classList.add("expanded"); }, 320);
  else c.classList.remove("expanded");
}
function flip(key) {
  localStorage.setItem(key, localStorage.getItem(key) === "1" ? "0" : "1");
  applyLayout();
}
document.getElementById("toggleside").addEventListener("click", () => flip("sideCollapsed"));
document.getElementById("togglecompose").addEventListener("click", () => flip("composeOpen"));
document.getElementById("closecompose").addEventListener("click", () => {
  localStorage.setItem("composeOpen", "0"); applyLayout();
});
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
const sizeSlider = document.getElementById("size-slider");
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
const setwrap = document.getElementById("settings-wrap");
document.getElementById("settingsbtn").addEventListener("click", (e) => { e.stopPropagation(); setwrap.classList.toggle("open"); });
document.addEventListener("click", (e) => { if (!e.target.closest("#settings-wrap")) setwrap.classList.remove("open"); });
moveSegThumb();
updateFilterIndicator();

// 첫 페인트 뒤 애니메이션을 켠다.
requestAnimationFrame(() => requestAnimationFrame(() => { document.body.classList.remove("no-anim"); moveSegThumb(); }));

refresh(); setInterval(refresh, 2500);
