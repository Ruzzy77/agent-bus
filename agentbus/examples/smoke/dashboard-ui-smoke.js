#!/usr/bin/env node
// Dashboard rendering and UI contract checks used by publish-smoke.sh.
// Keep these checks at the behavior/contract level where possible so dashboard
// refactors do not fail merely because internal function names or declaration
// ordering changed.
const fs = require('fs');
const vm = require('vm');

const src = fs.readFileSync('agentbus/static/dashboard.js', 'utf8');
const dashboardHtml = fs.readFileSync('agentbus/static/dashboard.html', 'utf8');
const dashboardCss = fs.readFileSync('agentbus/static/dashboard.css', 'utf8');

function assert(ok, message) {
  if (!ok) throw new Error(message);
}

function exportBefore(marker, exportsSource, globals = {}) {
  const end = src.indexOf(marker);
  assert(end >= 0, `${marker} marker not found`);
  const ctx = {...globals};
  vm.createContext(ctx);
  vm.runInContext(src.slice(0, end) + '\n' + exportsSource, ctx);
  return ctx;
}

function cssBlocks(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return [...dashboardCss.matchAll(new RegExp('(^|\\n)\\s*' + escaped + '\\s*\\{([^}]+)\\}', 'gs'))].map(m => m[2]);
}

function cssBlock(selector, label = selector) {
  const block = cssBlocks(selector)[0] || '';
  assert(block, `CSS rule missing for ${label}`);
  return block;
}

function cssRuleContaining(fragment) {
  const idx = dashboardCss.indexOf(fragment);
  assert(idx >= 0, `CSS rule containing ${fragment} missing`);
  const prevOpen = dashboardCss.lastIndexOf('{', idx);
  const prevClose = dashboardCss.lastIndexOf('}', idx);
  const start = prevOpen > prevClose ? prevOpen : dashboardCss.indexOf('{', idx);
  const end = dashboardCss.indexOf('}', start);
  assert(start >= 0 && end > start, `CSS rule around ${fragment} malformed`);
  return dashboardCss.slice(start + 1, end);
}

function decls(block) {
  const out = {};
  for (const part of block.split(';')) {
    const idx = part.indexOf(':');
    if (idx < 0) continue;
    out[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
  }
  return out;
}

function assertDecl(selector, prop, predicate, message) {
  const value = decls(cssBlock(selector))[prop] || '';
  assert(predicate(value), message || `${selector} ${prop} contract failed: ${value}`);
  return value;
}

function assertSelectorContains(selector, needles) {
  const block = cssBlock(selector);
  for (const needle of needles) assert(block.includes(needle), `${selector} missing ${needle}`);
  return block;
}

function htmlHasId(id) {
  return new RegExp(`\\bid=["']${id}["']`).test(dashboardHtml);
}

function assertOrder(before, after, message) {
  const a = dashboardHtml.indexOf(before);
  const b = dashboardHtml.indexOf(after);
  assert(a >= 0 && b >= 0 && a < b, message);
}

// Render helpers: markdown tables, copy payloads, stop banner labels/actions.
const ctx = exportBefore(
  'function renderMsg(',
  'this.renderBody = renderBody; this.messageCopyText = messageCopyText; ' +
    'this.renderStopBanner = renderStopBanner; this.stopDetailText = stopDetailText; ' +
    'this.securityChip = securityChip;'
);
const tableHtml = ctx.renderBody([
  '| 판단 출처 | 처리 | 근거 | 파일 |',
  '| --- | --- | --- | --- |',
  '| Codex lead | 통과 | 긴 설명은 텍스트 열로 넓게 잡혀야 한다 | agentbus/static/dashboard.js |',
].join('\n'));
assert(src.includes('const byId = id => document.getElementById(id);'), 'byId helper must call document.getElementById directly');
assert(!src.includes('const byId = id => byId(id);'), 'byId helper must not recurse');
assert(tableHtml.includes('<table class="md-table"'), 'markdown table did not render');
assert(tableHtml.includes('--md-cols:4;--md-min:'), 'markdown table column metrics missing');
assert(tableHtml.includes('<th class="md-align-left md-col-short">판단 출처</th>'), 'source markdown table column overclassified');
assert(tableHtml.includes('<th class="md-align-left md-col-short">처리</th>'), 'short markdown table column missing');
assert(tableHtml.includes('<th class="md-align-left md-col-text">근거</th>'), 'text markdown table column missing');
assert(tableHtml.includes('<th class="md-align-left md-col-path">파일</th>'), 'path markdown table column missing');
assert(tableHtml.includes('<td class="md-align-left md-col-short">통과</td>'), 'markdown table cell missing');
assert(!ctx.securityChip({sensitivity:'confidential'}).includes('data-tip='), 'visible security label should not duplicate tooltip text');
assert(src.includes('function shouldShowTooltip') && src.includes('function normalizeTooltips'), 'tooltip normalization/suppression helpers missing');
const copied = ctx.messageCopyText({subject:'제목', body:'본문\n둘째 줄', refs:['a.md,b.md']});
assert(copied === '제목\n\n본문\n둘째 줄\n\nRefs:\na.md\nb.md', 'message copy text mismatch');
const stopHtml = ctx.renderStopBanner({by:'codex-lead', reason:'loop_closed', detail:'plain detail', time:'2026-01-01T00:00:00Z'});
assert(stopHtml.includes('class="stop-inner"') && stopHtml.includes('class="stop-label">루프 종료됨</span>'), 'loop-closed stop banner structure missing');
assert(stopHtml.includes('plain detail') && !stopHtml.includes('&quot;plain detail&quot;'), 'stop banner string detail was JSON quoted');
assert(!stopHtml.includes('>닫기</button>') && !stopHtml.includes('class="stop-dismiss"') && !stopHtml.includes('class="btn"'), 'loop-closed stop banner should not carry a close action');
const requestStopHtml = ctx.renderStopBanner({by:'user', reason:'user_stop', detail:'pause'});
assert(requestStopHtml.includes('class="stop-label">정지 요청됨</span>'), 'active stop request label missing');
assert(requestStopHtml.includes('class="stop-action stop-clear"') && requestStopHtml.includes('>해제</button>'), 'active stop request clear action missing');
const openStopHtml = ctx.renderStopBanner(null);
assert(openStopHtml.includes('class="stop-inner stop-form"') && openStopHtml.includes('class="stop-label">루프 열림</span>'), 'open loop stop request form missing');
assert(openStopHtml.includes('id="stop-reason"') && openStopHtml.includes('>요청</button>') && openStopHtml.includes('data-tip="정지 사유를 입력하면 협업 루프에 정지 요청을 보냅니다."'), 'open loop stop request control missing');
assert(ctx.stopDetailText({a:1}) === '{"a":1}', 'stop banner object detail mismatch');

// Message and ID-pill rendering contracts.
const ctx2 = exportBefore(
  'let TASK_STATES',
  'this.html = renderMsg({' +
    'id:"m-copy", from:"agent", to:"user", kind:"note", ' +
    'time:"2026-01-01T00:00:00Z", task_id:"t-1", reply_to:"m-prev", ' +
    'subject:"제목", body:"본문"' +
  '}, {}); ' +
  'this.issue = idPill("issue", "i-1", {"data-ticket":"i-1"});'
);
assert(ctx2.html.includes('data-copy-message="m-copy"'), 'message copy button missing');
assert(ctx2.html.indexOf('data-copy-message="m-copy"') < ctx2.html.indexOf('class="msg-act msg-reply"'), 'message copy button is not first action');
assert(ctx2.html.indexOf('class="msg-actions"') < ctx2.html.indexOf('<div class="head">'), 'message actions are not rendered as header overlay');
assert(ctx2.html.includes('class="chip idpill idpill-message" data-id-kind="message" data-message="m-copy"'), 'message id pill missing');
assert(ctx2.html.includes('class="chip idpill idpill-task" data-id-kind="task" data-task="t-1"'), 'task id pill missing');
assert(ctx2.html.includes('class="chip idpill idpill-reply" data-id-kind="reply" data-reply="m-prev"'), 'reply id pill missing');
assert(ctx2.issue.includes('class="chip idpill idpill-issue"') && ctx2.issue.includes('data-ticket="i-1"'), 'issue id pill missing');
assert(!ctx2.html.includes('threadchip'), 'old id chip class leaked into message render');
const panelExports = `
this.panelActions = Object.keys(PANEL_TOGGLE_ACTIONS).sort();
this.panelHtml = renderPanelToggle("agents_more", "에이전트 2개 더 보기", "down");
const panelListOpts = {
  limit: 2,
  renderItem: x => \`<i>\${x}</i>\`,
  emptyHtml: "empty",
  moreAction: "tasks_more",
  lessAction: "tasks_less",
  moreLabel: n => \`작업 \${n}개 더 보기\`,
};
this.panelListMore = renderPanelList(["a", "b", "c"], {...panelListOpts, expanded: false});
this.panelListLess = renderPanelList(["a", "b", "c"], {...panelListOpts, expanded: true});
`;
const panelCtx = exportBefore(
  'async function clearDone',
  panelExports,
  {window: {addEventListener() {}}}
);
assert(panelCtx.panelActions.join(',') === 'agents_less,agents_more,completed_less,completed_more,tasks_less,tasks_more,tickets_less,tickets_more', 'panel toggle action map mismatch');
assert(panelCtx.panelHtml.includes('data-panel-toggle="agents_more"') && panelCtx.panelHtml.includes('에이전트 2개 더 보기') && panelCtx.panelHtml.includes('exp-caret down'), 'panel toggle render contract missing');
assert(panelCtx.panelListMore === '<i>a</i><i>b</i><button type="button" class="todo-expand" data-panel-toggle="tasks_more">작업 1개 더 보기<span class="exp-caret down"></span></button>', 'panel list collapsed render contract missing');
assert(panelCtx.panelListLess === '<i>a</i><i>b</i><i>c</i><button type="button" class="todo-expand" data-panel-toggle="tasks_less">접기<span class="exp-caret up"></span></button>', 'panel list expanded render contract missing');
for (const oldToken of ['threadchip', 'todo-id', 'assess-task-id', 'beat.stale']) {
  assert(!src.includes(oldToken), `old dashboard token still present: ${oldToken}`);
}

// HTML-level UI contracts.
assert(htmlHasId('loopstate') && !htmlHasId('stopbtn'), 'loop status toggle did not replace settings stop button');
assert(dashboardHtml.includes('세션 메시지') && dashboardHtml.includes('class="set-actions"') && dashboardHtml.includes('보관') && dashboardHtml.includes('비우기'), 'settings session message action row missing');
assert(dashboardHtml.includes('class="set-label"') && dashboardHtml.includes('aria-label="시스템 테마"') && dashboardHtml.includes('aria-label="메시지 보관"'), 'settings icon-label action controls missing');
assertOrder('id="seg-kind"', 'id="dd-to"', 'compose kind selector should precede recipient selector');
assert(!src.includes('label:"all (전체)"') && !dashboardHtml.includes('all (전체)'), 'compose all label regression');
assert(htmlHasId('fp-kinds') && dashboardHtml.includes('필터 해제'), 'filter kind controls missing');
assert(!dashboardHtml.includes(' title=') && !src.includes(' title=') && !src.includes('.title ='), 'native title tooltip source leaked');
assert(!dashboardHtml.includes('newtask-form" hidden') && !dashboardHtml.includes('newticket-form" hidden'), 'animated panel forms should not use hidden attribute');
assert(!dashboardHtml.includes(' onclick=') && !dashboardHtml.includes(' onsubmit=') && !src.includes('onclick=') && !src.includes('onsubmit='), 'inline dashboard event handler leaked');

// CSS-level contracts. These check semantic properties instead of exact rule text.
assertDecl('.msg', 'position', v => v === 'relative', 'message card must anchor overlay actions');
const msgActions = decls(cssBlock('.msg-actions'));
assert(msgActions.position === 'absolute' && msgActions.top && msgActions.right, 'message actions must be positioned as overlay');
assert((msgActions.background || '').includes('transparent') && (msgActions['backdrop-filter'] || '').includes('blur'), 'message action overlay should use translucent blur background');
assert(!('border' in msgActions) && !('box-shadow' in msgActions), 'message action overlay should not use card chrome');
assert(!dashboardCss.includes('.msg:focus-within .msg-actions'), 'message action overlay should not stick for whole-card focus');
assert(cssRuleContaining('.msg:has(.msg-act:focus-visible) .msg-actions').includes('pointer-events:auto'), 'message action overlay focus rule missing');
for (const selector of ['.msg.hlmsg', '.todo.hl', '.assessment.on', '.agent.on']) {
  assert((decls(cssBlock(selector))['box-shadow'] || '').includes('0 0 0 1px'), `${selector} should use thin highlight ring`);
}
for (const selector of ['.card', '.todo', '.assessment', '.agent']) {
  assert((decls(cssBlock(selector)).transition || '').includes('background'), `${selector} transition missing`);
}
for (const selector of ['.filter-pop', '.settings-pop', '.ackmore-pop', '.tdd-menu', '.mention-menu', '.dd-menu']) {
  const d = decls(cssBlock(selector));
  assert(d.position === 'absolute' && d.opacity === '0' && d.visibility === 'hidden' && d['pointer-events'] === 'none' && (d.transform || '').includes('translateY'), `popover animation contract missing for ${selector}`);
  assert(!('display' in d && d.display === 'none'), `popover ${selector} should not use display:none`);
}
assertDecl('.filter-pop', 'display', v => v === 'flex', 'filter popover should be flex container');
assertDecl('.filter-pop', 'flex-direction', v => v === 'column', 'filter popover should stack sections');
assertDecl('.filter-pop', 'overflow', v => v === 'hidden', 'filter popover outer scroll should be hidden');
assertDecl('.filter-pop', 'max-height', v => v.includes('100vh'), 'filter popover should respect viewport height');
assertDecl('#fp-agents', 'overflow', v => v === 'auto', 'agent filter list should scroll internally');
assertDecl('#fp-tasks', 'overflow', v => v === 'auto', 'task filter list should scroll internally');
assertDecl('#stopbar', 'display', v => v === 'grid', 'stopbar should use grid open-close animation');
assertDecl('#stopbar', 'grid-template-rows', v => v === '0fr', 'closed stopbar row height mismatch');
assertDecl('#stopbar.open', 'grid-template-rows', v => v === '1fr', 'open stopbar row height mismatch');
assertDecl(
  '#stopbar.loop-open, #stopbar.loop-closed',
  'background',
  v => v === 'var(--hover)',
  'closed/open loop stopbar should not flash error color'
);
assertDecl(
  'body.side-collapsed main, body.side-auto-collapsed main',
  'grid-template-columns',
  v => v.includes('0px'),
  'side collapse should remove side column'
);
assertDecl('body.side-collapsed main, body.side-auto-collapsed main', 'gap', v => v === '0', 'side collapse should remove grid gap');
assertSelectorContains('.stop-inner', ['display:flex', 'overflow:hidden', 'width:100%']);
assertDecl('.stop-form', 'display', v => v === 'grid', 'open loop form should use grid layout');
assertDecl(
  '.stop-form',
  'grid-template-columns',
  v => v.includes('minmax') && v.includes('auto'),
  'open loop form should keep input and button on control row'
);
assertDecl('.stop-form .stop-copy', 'grid-column', v => v === '1 / -1', 'open loop explanatory text should occupy first row');
const project = decls(cssBlock('.project'));
assert((project['font-family'] || '').includes('ui-monospace') && project.flex === 'none' && (project['max-width'] || '').includes('24vw'), 'project badge sizing contract missing');
assertDecl('.project.project-hidden', 'display', v => v === 'none', 'project badge should hide rather than shrink when topbar is tight');
assert(!dashboardCss.includes('@media (max-width: 760px) { .project { display:none; } }'), 'project badge should be hidden by fit logic, not a fixed media query');
assertDecl('.overview .ov-dot', 'background', v => v === 'var(--circle)', 'overview dots should have a CSS default color');
assertDecl('.overview .ov-dot.running', 'background', v => v === 'var(--running)', 'overview running dot color missing');
assertDecl('.overview .ov-dot.waiting', 'background', v => v === 'var(--waiting)', 'overview waiting dot color missing');
assert(!src.includes('STATE_COLOR') && !src.includes('style="background:${'), 'overview state color should not use inline style rendering');
const floatingSide = decls(cssBlock('body.side-auto-collapsed:not(.side-collapsed) #side'));
assert(floatingSide.position === 'absolute' && (floatingSide.width || '').includes('min(300px') && parseInt(floatingSide['z-index'] || '999', 10) < 60, 'floating side panel layout/z-index contract missing');
assert((floatingSide.transition || '').includes('.28s'), 'floating side panel should match panel animation duration');
assertDecl(
  'body.side-mode-switching main, body.side-mode-switching #side',
  'transition',
  v => v === 'none',
  'side mode switch should suppress replay animation'
);

// JS interaction sentinels that still need source-level coverage until dashboard.js is modularized.
for (const needle of [
  'function fitProjectBadge()',
  'window.addEventListener("resize", fitProjectBadge)',
  'function toggleLoopPanel()',
  'function requestStopFromPanel',
  'filterKinds',
  'fp-task-opt',
  'function normalizeTooltips',
  'new MutationObserver',
  'window.matchMedia ? window.matchMedia("(max-width: 720px)")',
  'document.body.classList.toggle("side-auto-collapsed", autoSide)',
  'function closeFloatingSidePanelFromOutside',
  'document.addEventListener("pointerdown", e => closeFloatingSidePanelFromOutside(e.target), true)',
  'document.addEventListener("focusin", e => closeFloatingSidePanelFromOutside(e.target), true)',
  'function onSideModeChange()',
  'sideAutoCollapseMQ.addEventListener("change", onSideModeChange)',
  'bar.classList.add("open")',
  'function setInlineFormOpen',
  'setInlineFormOpen(newtaskForm, newtaskBtn, newtaskTitle, open)',
  'setInlineFormOpen(newticketForm, newticketBtn, newticketTitle, open)',
]) {
  assert(src.includes(needle), `dashboard interaction sentinel missing: ${needle}`);
}
assert(!src.includes('bar.style.display') && !src.includes('addEventListener("click", () => flip("sideCollapsed"))') && !src.includes('플로팅 패널'), 'old layout interaction source leaked');

// Clipboard fallback behavior when the modern Clipboard API is present but denied.
const clipStart = src.indexOf('async function writeClipboardText');
const clipEnd = src.indexOf('async function copyMessage');
assert(clipStart >= 0 && clipEnd > clipStart, 'clipboard function marker not found');
let fallbackUsed = false, appended = null, removed = false, focused = false;
const textarea = {
  value: '', style: {},
  setAttribute() {},
  focus() { focused = true; },
  select() {},
  setSelectionRange() {},
  remove() { removed = true; },
};
const ctx3 = {
  window: { navigator: { clipboard: { writeText: async () => { throw new Error('denied'); } } } },
  document: {
    body: { appendChild(node) { appended = node; } },
    createElement(tag) { if (tag !== 'textarea') throw new Error('unexpected element'); return textarea; },
    execCommand(cmd) { fallbackUsed = cmd === 'copy'; return fallbackUsed; },
  },
  Error,
};
vm.createContext(ctx3);
vm.runInContext(src.slice(clipStart, clipEnd) + '\nthis.writeClipboardText = writeClipboardText;', ctx3);
ctx3.writeClipboardText('copy fallback').then(() => {
  assert(fallbackUsed && appended && removed && focused && textarea.value === 'copy fallback', 'clipboard fallback did not run with modern API present');
}).catch(err => {
  console.error(err);
  process.exit(1);
});
