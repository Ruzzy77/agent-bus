#!/usr/bin/env node
// Dashboard rendering and UI contract checks used by publish-smoke.sh.
// Keep these checks at the behavior/contract level where possible so dashboard
// refactors do not fail merely because internal function names or declaration
// ordering changed.
const fs = require('fs');
const vm = require('vm');

const primitiveSrc = fs.readFileSync('agentbus/static/dashboard-primitives.js', 'utf8');
const src = fs.readFileSync('agentbus/static/dashboard.js', 'utf8');
const dashboardHtml = fs.readFileSync('agentbus/static/dashboard.html', 'utf8');
const dashboardCss = fs.readFileSync('agentbus/static/dashboard.css', 'utf8');

function assert(ok, message) {
  if (!ok) throw new Error(message);
}

function makeDashboardContext(globals = {}) {
  const ctx = {...globals};
  if (!ctx.window) ctx.window = {};
  vm.createContext(ctx);
  vm.runInContext(primitiveSrc, ctx);
  return ctx;
}

function exportBefore(marker, exportsSource, globals = {}) {
  const end = src.indexOf(marker);
  assert(end >= 0, `${marker} marker not found`);
  const ctx = makeDashboardContext(globals);
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
    'this.securityMark = securityMark; ' +
    'this.compact = [fmtCompactCount(999), fmtCompactCount(1200), fmtCompactCount(10400)]; ' +
    'this.age = [fmtAge(89), fmtAge(5400), fmtAge(90000)]; ' +
    'this.dur = [fmtDur(59), fmtDur(5400), fmtDur(142560), fmtDur(171000)];'
);
const tableHtml = ctx.renderBody([
  '| 판단 출처 | 처리 | 근거 | 파일 |',
  '| --- | --- | --- | --- |',
  '| Codex lead | 통과 | 긴 설명은 텍스트 열로 넓게 잡혀야 한다 | agentbus/static/dashboard.js |',
].join('\n'));
assert(primitiveSrc.includes('const byId = id => document.getElementById(id);'), 'byId helper must call document.getElementById directly');
assert(!primitiveSrc.includes('const byId = id => byId(id);'), 'byId helper must not recurse');
assert(tableHtml.includes('<table class="md-table"'), 'markdown table did not render');
assert(tableHtml.includes('--md-cols:4;--md-min:'), 'markdown table column metrics missing');
assert(tableHtml.includes('<th class="md-align-left md-col-short">판단 출처</th>'), 'source markdown table column overclassified');
assert(tableHtml.includes('<th class="md-align-left md-col-short">처리</th>'), 'short markdown table column missing');
assert(tableHtml.includes('<th class="md-align-left md-col-text">근거</th>'), 'text markdown table column missing');
assert(tableHtml.includes('<th class="md-align-left md-col-path">파일</th>'), 'path markdown table column missing');
assert(tableHtml.includes('<td class="md-align-left md-col-short">통과</td>'), 'markdown table cell missing');
const restrictedMark = ctx.securityMark({sensitivity:'restricted'});
assert(restrictedMark.includes('class="security-mark restricted"'), 'security marker should render lock-only marker style');
assert(restrictedMark.includes('data-tip="보안 처리됨"') && restrictedMark.includes('aria-label="보안 처리됨"'), 'security marker should expose short text through tooltip/accessibility only');
assert(!restrictedMark.includes('<span>restricted</span>') && !restrictedMark.includes('<span>보안') && !restrictedMark.includes('class="tag security'), 'security marker should not render a text pill');
assert(ctx.compact.join(',') === '999,1.2K,10K' && ctx.age.join(',') === '방금,2시간 전,1일 전' && ctx.dur.join(',') === '1분 미만,1.5시간,1일 16시간,2일', 'overview compact/time formatting mismatch');
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
assert(openStopHtml === '', 'open loop status should not render a stop request panel');
assert(ctx.stopDetailText({a:1}) === '{"a":1}', 'stop banner object detail mismatch');

// Message and ID-pill rendering contracts.
const ctx2 = exportBefore(
  'let TASK_STATES',
  'this.html = renderMsg({' +
    'id:"m-copy", from:"agent", to:"user", kind:"note", ' +
    'time:"2026-01-01T00:00:00Z", task_id:"t-1", reply_to:"m-prev", ' +
    'subject:"제목", body:"본문", refs:["README.md","agentbus/static/dashboard.js"]' +
  '}, {}); ' +
  'replyOpenId = "m-copy"; this.replyHtml = renderMsg({' +
    'id:"m-copy", from:"agent", to:"user", kind:"note", ' +
    'time:"2026-01-01T00:00:00Z", subject:"제목", body:"본문"' +
  '}, {}); ' +
  'this.issue = idPill("issue", "i-1", {"data-ticket":"i-1"});'
);
assert(ctx2.html.includes('data-copy-message="m-copy"'), 'message copy button missing');
assert(ctx2.html.includes('class="tag kind note"'), 'message kind should use flat semantic tag style');
assert(ctx2.html.indexOf('data-copy-message="m-copy"') < ctx2.html.indexOf('class="msg-act msg-reply"'), 'message copy button is not first action');
assert(ctx2.html.indexOf('class="msg-actions inline-actions"') < ctx2.html.indexOf('<div class="head">'), 'message actions are not rendered as header overlay');
assert(ctx2.html.includes('class="chip idpill idpill-message" data-id-kind="message" data-message="m-copy"'), 'message id pill missing');
assert(ctx2.html.includes('class="chip idpill idpill-task" data-id-kind="task" data-task="t-1"'), 'task id pill missing');
assert(ctx2.html.includes('class="chip idpill idpill-reply" data-id-kind="reply" data-reply="m-prev"'), 'reply id pill missing');
assert(ctx2.issue.includes('class="chip idpill idpill-issue"') && ctx2.issue.includes('data-ticket="i-1"'), 'issue id pill missing');
assert(ctx2.html.includes('<details class="refs-expander"><summary><span class="refs-label">참조 2개<span class="refs-caret"></span></span></summary>') && !ctx2.html.includes('<details class="refs-expander" open'), 'message refs should render collapsed expander');
assert(ctx2.replyHtml.includes('class="iconbtn send reply-go"') && ctx2.replyHtml.includes('aria-label="보내기"') && !ctx2.replyHtml.includes('>보내기</button>'), 'reply send should use the same icon button grammar as compose send');
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
this.panelEmptyHtml = panelEmpty("등록된 에이전트 없음");
this.skillHtml = renderSkill({skill_id:"skill-alpha", name:"skill-alpha", state:"active", pending:{check:1}, warnings:["review"]});
this.filterAgents = new Set();
this.agentHtml = renderAgent("codex", {state:"waiting", heartbeat:123, task:"t-demo-review", note:"runner docs"});
this.ticketHtml = renderTicket({issue_id:"i-demo", title:"ticket", body:"body", refs:["README.md","agentbus/static/dashboard.js","agentbus/static/dashboard.css"], created_at:"2026-06-18T12:00:00Z"});
AGENT_NAMES = ["reviewer"];
this.bridgeProfileHtml = renderBridgeProfile({name:"a2a-reviewer", source:"package", event:"message.created", matcher:"reviewer", matcherTargets:["reviewer"], matcherKinds:["request", "report", "note"], handler:"a2a", handlerType:"http", protocol:"a2a", hasExecution:true, envCount:1, state:"ready"}, {hasPosition:true, failureCount:0, positionUpdatedAt:"2026-06-18T12:00:00Z"});
this.bridgeMissingHtml = renderBridgeProfile({name:"ghost-profile", source:"local", event:"message.created", matcher:"ghost", matcherTargets:["ghost"], handler:"monitor", handlerType:"monitor", state:"ready"}, {});
this.bridgeFailureHtml = renderBridgeProfile({name:"a2a-reviewer", source:"package", event:"message.created", matcher:"reviewer", matcherTargets:["reviewer"], handler:"a2a", handlerType:"http", hasExecution:true, state:"ready"}, {failureCount:1});
this.bridgeInboundHtml = renderBridgeGateway({name:"A2A inbound", protocol:"a2a", endpoint:"http://127.0.0.1:8791/a2a/rpc", state:"ready", access:"local only"});
this.bridgeAgentHtml = renderBridgeProfile({name:"claude-runner-inbox", source:"package", event:"message.created", matcherTargets:["reviewer"], handler:"claude", handlerType:"agent", provider:"claude", state:"ready"}, {});
this.bridgeAnyTargetHtml = renderBridgeProfile({name:"openai-compatible-messages", source:"package", event:"message.created", matcherTargets:[], handler:"openai-compatible", handlerType:"openai-compatible", state:"ready"}, {});
this.bridgePrefixedRuntime = bridgeRuntimeForProfile(new Map([["teammate/a2a-reviewer", {failureCount:2}]]), "a2a-reviewer");
this.bridgeFailureRank = bridgeRuntimeRank({failureCount:1}, {state:"ready"});
this.bridgeReadyRank = bridgeRuntimeRank({}, {state:"ready"});
`;
const panelCtx = exportBefore(
  'async function clearDone',
  panelExports,
  {window: {addEventListener() {}}}
);
assert(panelCtx.panelActions.join(',') === 'agents_less,agents_more,bridge_gateways_less,bridge_gateways_more,bridge_profiles_less,bridge_profiles_more,completed_less,completed_more,skills_less,skills_more,tasks_less,tasks_more,tickets_less,tickets_more', 'panel toggle action map mismatch');
assert(panelCtx.panelHtml.includes('data-panel-toggle="agents_more"') && panelCtx.panelHtml.includes('에이전트 2개 더 보기') && panelCtx.panelHtml.includes('exp-caret down'), 'panel toggle render contract missing');
assert(panelCtx.panelListMore === '<i>a</i><i>b</i><button type="button" class="todo-expand" data-panel-toggle="tasks_more">작업 1개 더 보기<span class="exp-caret down"></span></button>', 'panel list collapsed render contract missing');
assert(panelCtx.panelListLess === '<i>a</i><i>b</i><i>c</i><button type="button" class="todo-expand" data-panel-toggle="tasks_less">접기<span class="exp-caret up"></span></button>', 'panel list expanded render contract missing');
assert(panelCtx.panelEmptyHtml === '<div class="panel-empty">등록된 에이전트 없음</div>', 'side panel empty state should use neutral empty row');
assert(!panelCtx.agentHtml.includes('data-delete-agent'), 'agent cards should not expose a delete action without runner ownership');
assert(panelCtx.ticketHtml.includes('<details class="refs-expander"><summary><span class="refs-label">참조 3개<span class="refs-caret"></span></span></summary>') && !panelCtx.ticketHtml.includes('<details class="refs-expander" open'), 'ticket refs should render collapsed expander');
assert(panelCtx.ticketHtml.includes('class="todo-actions inline-actions"') && panelCtx.ticketHtml.includes('class="msg-act todo-run"') && panelCtx.ticketHtml.includes('class="msg-act msg-del todo-del"'), 'ticket actions should reuse inline action controls');
assert((panelCtx.skillHtml.match(/skill-alpha/g) || []).length === 1 && panelCtx.skillHtml.includes('근거 확인 1') && panelCtx.skillHtml.includes('주의 1건'), 'skill card should not repeat its title in metadata');
assert(panelCtx.skillHtml.includes('todo-mark status-mark input_required health-mark') && panelCtx.skillHtml.includes('<svg') && !panelCtx.skillHtml.includes('skill-state'), 'skill card should reuse shared lucide status marker');
assert(panelCtx.bridgeProfileHtml.includes('a2a-reviewer') && panelCtx.bridgeProfileHtml.includes('bridge-time') && panelCtx.bridgeProfileHtml.includes('data-position-time="2026-06-18T12:00:00Z"') && panelCtx.bridgeProfileHtml.includes('A2A') && panelCtx.bridgeProfileHtml.includes('data-agent="reviewer"') && panelCtx.bridgeProfileHtml.includes('idpill-compact bridge-target') && panelCtx.bridgeProfileHtml.includes('새 메시지') && panelCtx.bridgeProfileHtml.includes('bridge-kind') && panelCtx.bridgeProfileHtml.includes('request, report, note') && !panelCtx.bridgeProfileHtml.includes('request</code><span class="route-sep">') && !panelCtx.bridgeProfileHtml.includes('target reviewer') && !panelCtx.bridgeProfileHtml.includes('bridge-source') && !panelCtx.bridgeProfileHtml.includes('tracked'), 'bridge profile card contract missing');
assert(panelCtx.bridgeProfileHtml.includes('todo-mark status-mark completed health-mark') && panelCtx.bridgeFailureHtml.includes('todo-mark status-mark failed health-mark'), 'bridge cards should reuse shared lucide status marker');
assert(panelCtx.bridgeMissingHtml.includes('bridge-target-missing') && panelCtx.bridgeMissingHtml.includes('aria-disabled="true"') && !panelCtx.bridgeMissingHtml.includes('data-agent="ghost"'), 'missing bridge target should render as disabled reference');
assert(panelCtx.bridgeFailureHtml.includes('failure') && panelCtx.bridgeFailureHtml.includes('오류 1건'), 'bridge failure status should be folded into profile card');
assert(panelCtx.bridgePrefixedRuntime.failureCount === 2 && panelCtx.bridgeFailureRank < panelCtx.bridgeReadyRank, 'prefixed bridge runtime state should attach to local profile and sort first');
assert(panelCtx.bridgeInboundHtml.includes('A2A inbound') && panelCtx.bridgeInboundHtml.includes('/a2a/rpc') && !panelCtx.bridgeInboundHtml.includes('handler-inbound'), 'bridge gateway card contract missing');
assert(panelCtx.bridgeAgentHtml.includes('claude-cli') && !panelCtx.bridgeAgentHtml.includes('>claude</span>'), 'agent bridge handler should show cli runner label');
assert(panelCtx.bridgeAnyTargetHtml.includes('OpenAI Compatible') && panelCtx.bridgeAnyTargetHtml.includes('>-</span>'), 'openai-compatible/no-target bridge display mismatch');
for (const oldToken of ['threadchip', 'todo-id', 'beat.stale']) {
  assert(!src.includes(oldToken), `old dashboard token still present: ${oldToken}`);
}

// HTML-level UI contracts.
assertOrder('/static/dashboard-primitives.js', '/static/dashboard.js', 'dashboard primitives should load before dashboard runtime');
assert(src.includes('window.AgentBusDashboardPrimitives') && primitiveSrc.includes('renderRefsExpander'), 'dashboard primitive module contract missing');
assert(htmlHasId('loopstate') && !htmlHasId('stopbtn'), 'loop status toggle did not replace settings stop button');
assert(dashboardHtml.includes('세션 메시지') && dashboardHtml.includes('class="set-actions"') && dashboardHtml.includes('보관') && dashboardHtml.includes('비우기'), 'settings session message action row missing');
assert(dashboardHtml.includes('class="set-label"') && dashboardHtml.includes('aria-label="시스템 테마"') && dashboardHtml.includes('aria-label="메시지 보관"'), 'settings icon-label action controls missing');
assert(htmlHasId('compose-kind') && htmlHasId('kind-token') && htmlHasId('compose-meta-chips'), 'inline compose controls missing');
assert(dashboardHtml.includes('data-v="task"') && dashboardHtml.includes('data-v="ticket"') && dashboardHtml.includes('data-v="stop"'), 'lead management compose kinds missing');
assert(!htmlHasId('closecompose') && dashboardHtml.includes('class="iconbtn send compose-send"'), 'compose should keep send inside the input field and remove the close button');
assert(!htmlHasId('seg-kind') && !htmlHasId('dd-to') && !htmlHasId('dd-task') && !htmlHasId('compose-policy'), 'old compose dropdown controls should stay removed');
assert(src.includes('function makeComposePalette') && src.includes('mode:"security"') && src.includes('mode:"agent"') && src.includes('mode:"task"'), 'compose slash palette contract missing');
assert(!htmlHasId('dd-ticket-sensitivity') && !htmlHasId('dd-task-sensitivity'), 'side panel task/ticket sensitivity controls should stay removed');
assert(src.includes('sensitivity: composeSensitivity') && !src.includes('ticketSensitivity') && !src.includes('taskSensitivity'), 'dashboard write payloads should route sensitivity through compose only');
assert(!src.includes('label:"all (전체)"') && !dashboardHtml.includes('all (전체)'), 'compose all label regression');
assert(htmlHasId('fp-kinds') && dashboardHtml.includes('필터 해제'), 'filter kind controls missing');
assert(src.includes('function filterAgentKey') && src.includes('filterAgents.has(filterAgentKey(m.from))'), 'participant filter should canonicalize agent names and ids');
assert(htmlHasId('skills') && dashboardHtml.includes('스킬'), 'skill side panel missing');
assert(htmlHasId('side-tab-work') && htmlHasId('side-tab-agent') && htmlHasId('side-tab-bridge') && htmlHasId('side-work') && htmlHasId('side-agent') && htmlHasId('side-bridge'), 'side panel tabs missing');
assert(htmlHasId('bridge-profiles') && htmlHasId('bridge-gateways') && !htmlHasId('bridges'), 'bridge side panel should use profile and gateway lists');
assert(dashboardHtml.includes('class="side-tabbar"') && dashboardHtml.includes('class="side-scroll"') && dashboardHtml.includes('class="side-tab-thumb"') && dashboardHtml.includes('class="side-tab-icon"'), 'side panel tab bar/thumb/icons missing');
assertOrder('id="side-tab-work"', 'id="side-tab-agent"', 'side tab order should be work then agent');
assertOrder('id="side-tab-agent"', 'id="side-tab-bridge"', 'bridge tab should follow agent tab');
assertOrder('id="side-work"', 'id="side-agent"', 'side panel content order should be work then agent');
assert(!dashboardHtml.includes(' title=') && !src.includes(' title=') && !src.includes('.title ='), 'native title tooltip source leaked');
assert(!htmlHasId('newtask') && !htmlHasId('newticket') && !dashboardHtml.includes('newtask-form') && !dashboardHtml.includes('newticket-form'), 'side panel creation controls should stay removed');
assert(!dashboardHtml.includes(' onclick=') && !dashboardHtml.includes(' onsubmit=') && !src.includes('onclick=') && !src.includes('onsubmit='), 'inline dashboard event handler leaked');

// CSS-level contracts. These check semantic properties instead of exact rule text.
assertDecl('.msg', 'position', v => v === 'relative', 'message card must anchor overlay actions');
const msgActions = decls(cssBlock('.msg-actions'));
assert(msgActions.position === 'absolute' && msgActions.top && msgActions.right, 'message actions must be positioned as overlay');
const inlineActions = decls(cssBlock('.inline-actions'));
assert((inlineActions.background || '').includes('var(--overlay-bg)') && dashboardCss.includes('--overlay-bg:color-mix') && (inlineActions['backdrop-filter'] || '').includes('blur'), 'inline action overlay should use translucent blur background');
assert(!('border' in inlineActions) && !('box-shadow' in inlineActions), 'inline action overlay should not use card chrome');
assert(!dashboardCss.includes('.msg:focus-within .msg-actions'), 'message action overlay should not stick for whole-card focus');
assert(cssRuleContaining('.msg:has(.msg-act:focus-visible) .msg-actions').includes('pointer-events:auto'), 'message action overlay focus rule missing');
for (const selector of ['.msg.hlmsg', '.todo.hl', '.summary-card.on, .summary-card.hl']) {
  assert((decls(cssBlock(selector))['box-shadow'] || '').includes('var(--selected-ring)'), `${selector} should use thin highlight ring`);
}
for (const selector of ['.card', '.todo', '.summary-card']) {
  const transition = decls(cssBlock(selector)).transition || '';
  assert(transition.includes('background') || transition.includes('var(--transition-card)'), `${selector} transition missing`);
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
assert(cssBlocks('#side').some(block => decls(block).overflow === 'hidden'), 'side panel should keep tabs outside the scrolling content');
assertDecl('.side-tabbar', 'position', v => v === 'relative', 'side tab bar should stay fixed outside side panel scrolling');
assertDecl('.side-tabbar', 'background', v => v === 'var(--bg)', 'side tab bar should mask panel content below');
assertDecl('.side-tabbar', 'flex', v => v === '0 0 auto' || v === 'none', 'side tab bar should not shrink under long panel content');
assert((decls(cssBlock('.side-tabbar')).padding || '') === '12px 2px 9px 0', 'side tab bar should match timeline toolbar height');
assertDecl('.side-scroll', 'overflow-y', v => v === 'auto', 'side panel content should own vertical scrolling');
assertDecl('.side-scroll', 'flex', v => v.includes('auto'), 'side panel scroll body should fill remaining panel height');
assertDecl('.side-tabs', 'display', v => v === 'flex', 'side tabs should use sliding segmented layout');
assertDecl('.side-tabs', 'position', v => v === 'relative', 'side tabs should anchor sliding thumb inside tab bar');
assertDecl('.side-tab-panel', 'flex', v => v === '0 0 auto' || v === 'none', 'side tab panel content should define the side scroll height');
assertDecl('.side-tabs', 'height', v => v === '32px', 'side tab container height should stay compact across active labels');
assert(!('width' in decls(cssBlock('.side-tabs'))), 'side tab container should stretch with side panel width');
assert(!('align-self' in decls(cssBlock('.side-tabs'))), 'side tab container should keep default stretch alignment');
assertDecl('.side-tabs button', 'flex', v => v === '1 1 0', 'side tab buttons should keep equal widths across selected labels');
assertDecl('.side-tabs button', 'height', v => v === '26px', 'side tab buttons should keep compact fixed height across active labels');
assertDecl('.side-tab-thumb', 'position', v => v === 'absolute', 'side tab thumb should slide under active tab');
assertDecl('.side-tab-thumb', 'background', v => v === 'var(--segment-thumb)', 'side tab thumb should use visible segmented thumb background');
assertDecl('.side-tab-thumb', 'transition', v => v === 'none', 'side tab thumb should not animate during resize/layout updates');
assertDecl('.side-tabs.side-tabs-animate .side-tab-thumb', 'transition', v => v === 'var(--transition-thumb)', 'side tab click animation contract missing');
assertDecl('.side-tab-panel', 'display', v => v === 'flex', 'side tab panels should preserve section stack');
assertDecl('.side-tab-panel[hidden]', 'display', v => v === 'none', 'inactive side tab panel should be hidden');
assertDecl('.panel-title', 'min-height', v => v === '30px', 'side panel section headings should share action-row height');
assertDecl('.panel-empty', 'color', v => v === 'var(--dim)', 'side panel empty rows should use muted text');
const sidePadding = cssBlocks('#side').map(block => decls(block).padding).find(Boolean) || '';
assert(sidePadding === '0', 'side panel should not put scroll padding above fixed tabs');
const sideScrollPadding = decls(cssBlock('.side-scroll')).padding || '';
assert(sideScrollPadding.includes('44px'), 'side panel scroll body should keep bottom breathing room');
const floatingSidePadding = decls(cssBlock('body.side-auto-collapsed:not(.side-collapsed) #side')).padding || '';
assert(floatingSidePadding.startsWith('0 '), 'floating side panel should keep fixed tabs at the top edge');
assertSelectorContains('#skills, #bridge-profiles, #bridge-gateways', ['display:flex', 'gap:8px']);
assertDecl('.bridge-head', 'align-items', v => v === 'flex-start', 'bridge card header should top-align status pill');
assertDecl('.health-mark', 'margin-left', v => v === 'auto', 'health marker should keep right alignment');
assertDecl('.todo-mark svg', 'stroke-width', v => v === '2.15', 'status marker should use shared lucide stroke weight');
assertDecl('.todo-mark.completed', 'color', v => v === 'var(--done)', 'completed task marker should use shared status color');
assertDecl('.todo-mark.input_required', 'color', v => v === 'var(--waiting)', 'warning task marker should use shared status color');
assertDecl('.tdot svg', 'width', v => v === '14px', 'state menu marker should reuse compact lucide status icon');
assertSelectorContains('.todo:hover .todo-actions, .todo-actions:has(.tdd.open), .todo:has(.todo-actions :focus-visible) .todo-actions', ['pointer-events:auto', 'transform:translateY(0)']);
assert(!dashboardCss.includes('.todo-run:hover') && !dashboardCss.includes('.todo-del:hover'), 'todo actions should use shared icon hover styles');
assertDecl('.reply-go.iconbtn.send', 'width', v => v === '34px', 'reply send icon button should stay compact');
assertDecl('.refs-expander summary', 'display', v => v === 'block', 'reference expander summary should align as a block row');
assertDecl('.refs-label', 'display', v => v === 'inline-flex', 'reference expander label should stay compact');
assertDecl('.refs-caret', 'opacity', v => v === '0', 'reference expander caret should stay hidden until hover/open');
assertDecl('.refs-caret', 'width', v => v === '5px', 'reference expander caret should stay small');
assertDecl('.refs-caret', 'transform', v => v.includes('translateY(-2px)'), 'reference expander caret should align with the label baseline');
assertDecl('.refs-expander[open] .refs-caret', 'opacity', v => v === '1', 'reference expander caret should stay visible when open');
assertDecl('.bridge-time', 'color', v => v === 'var(--mid)', 'bridge processed time should use secondary text color');
assertSelectorContains('.inline-actions', ['pointer-events:none', 'backdrop-filter:saturate(180%) blur(12px)']);
assert(!dashboardCss.includes('.agent-actions'), 'agent card should not keep unused delete overlay styles');
assert(!cssBlocks('.agent-head').some(block => block.includes('padding-right')) && !cssBlocks('.agent-meta').some(block => block.includes('padding-right')), 'agent card should not reserve layout space for delete overlay');
assertDecl('.tag', 'background', v => v === 'transparent', 'semantic tags should stay flatter than ID pills');
assertDecl('.tag', 'border-radius', v => v === 'var(--radius-xs)', 'semantic tags should not reuse pill radius');
assertDecl('.kind.report', 'color', v => v === 'var(--done)', 'report tag should use design state color');
assertDecl('.security-mark', 'color', v => v === 'var(--security)', 'security marker should use dedicated security color');
assertDecl('.security-mark.internal', 'color', v => v === 'var(--security-muted)', 'internal security marker should use gray security color');
assert(dashboardCss.includes('--apple-yellow:#fdbc00') && dashboardCss.includes('--apple-gray:#818186'), 'Apple-style semantic colors should be available as tokens');
assertDecl('.compose-chip.security.internal', 'color', v => v === 'var(--security)', 'internal compose security chip should keep security color');
assertDecl('.compose-chip.security.restricted', 'color', v => v === 'var(--error)', 'restricted compose security chip should use error color');
assertDecl('.compose-chip button svg', 'color', v => v === 'currentColor', 'compose chip close icon should inherit neutral button color');
assertDecl('.bridge-dir', 'color', v => v === 'var(--ink)', 'bridge handler labels should use one neutral color');
assert(cssRuleContaining('.idpill.on[data-agent]:hover').includes('color:#fff'), 'selected agent pill hover should keep readable text');
assertSelectorContains('.bridge-target-missing', ['text-decoration:line-through', 'cursor:default']);
assert(src.includes('async function jumpToAgent') && src.includes('jumpToAgent(agent.dataset.agent)'), 'bridge agent target should jump to agent card');
assert(!src.includes('toggleInSet(filterAgents, agent.dataset.agent, agent);'), 'bridge agent target should not toggle message participant filter');
assertSelectorContains('.stop-inner', ['display:flex', 'overflow:hidden', 'width:100%']);
assert(!dashboardCss.includes('.stop-form') && !dashboardCss.includes('.stop-reason') && !src.includes('data-stop-form'), 'stop request form should not remain in dashboard UI');
assert(!src.includes('data-tip="정지 사유를 입력하면 협업 루프에 정지 요청을 보냅니다."'), 'visible stop helper text should not repeat itself as a tooltip');
const project = decls(cssBlock('.project'));
assert((project['font-family'] || '').includes('ui-monospace') && project.flex === 'none' && (project['max-width'] || '').includes('24vw'), 'project badge sizing contract missing');
assertDecl('.project.project-hidden', 'display', v => v === 'none', 'project badge should hide rather than shrink when topbar is tight');
assert(!dashboardCss.includes('@media (max-width: 760px) { .project { display:none; } }'), 'project badge should be hidden by fit logic, not a fixed media query');
assertDecl('.compose-kind.open .kind-token', 'opacity', v => v === '0', 'compose kind token should yield to expanded inline tags');
assertDecl('.kind-pop button.on', 'background', v => v === 'var(--hover)', 'compose kind menu should use the tag selected background');
assertDecl('.kind-pop', 'white-space', v => v === 'nowrap', 'compose kind popover should keep kind labels on one line');
assertDecl('.kind-pop button', 'white-space', v => v === 'nowrap', 'compose kind buttons should not wrap Korean labels');
assertDecl('.filter-kind', 'display', v => v === 'flex', 'filter kind selector should render as a segmented control');
assertDecl('.filter-kind', 'background', v => v === 'var(--hover)', 'filter kind selector should have a segmented track');
assertDecl('.filter-kind button', 'border', v => v === '0', 'filter kind buttons should not fall back to native button styling');
assertDecl('.filter-kind button', 'white-space', v => v === 'nowrap', 'filter kind labels should stay on one line');
assertDecl('.filter-kind button', 'height', v => v === '26px', 'filter kind selected border should keep vertical breathing room');
assertDecl('.filter-kind', 'overflow', v => v === 'visible', 'filter kind selected shadow should not clip against the track');
assertDecl('.filter-kind button', 'margin', v => v === '0', 'filter kind buttons should stay centered in the track');
assertDecl('.filter-kind button.on', 'background', v => v === 'var(--segment-thumb)', 'selected filter kind should read as the active segment');
assertDecl('.filter-kind button.on', 'color', v => v === 'var(--accent)', 'selected filter kind should use the active filter color');
assertDecl('.fp-opt', 'display', v => v === 'grid', 'filter participant/task rows should reuse palette item layout');
assertDecl('.fp-opt', 'grid-template-columns', v => v === 'auto minmax(0, auto) minmax(0, 1fr)', 'filter rows should keep check, main, and meta text columns');
assertDecl('.fp-main', 'font-weight', v => v === '500', 'filter row main text should match slash palette hierarchy');
assertDecl('.fp-meta', 'color', v => v === 'var(--dim)', 'filter row meta text should match slash palette hierarchy');
assert(src.includes('class="fp-main"') && src.includes('class="fp-meta"'), 'filter rows should render main/meta text like slash palette rows');
assert(!src.includes('fp-task-main') && !src.includes('fp-task-title'), 'old two-line task filter row should stay removed');
assertDecl('.composer-field', 'display', v => v === 'grid', 'compose field should own the inline send layout');
assertDecl('.compose-send', 'grid-column', v => v === '2', 'compose send should sit inside the field on the right');
assertDecl('.compose-send', 'align-self', v => v === 'end', 'compose send should align to the bottom of the field');
assertDecl('.compose-input-row', 'align-items', v => v === 'center', 'single-line compose row should center the token and text');
assertDecl('.composer-field.compose-multiline .compose-input-row', 'align-items', v => v === 'flex-start', 'multiline compose row should grow downward from the same top edge');
assertDecl('.compose-input-row', 'min-height', v => v === '28px', 'single-line compose row should align with the compact send button');
assertDecl('.compose-token-row', 'min-height', v => v === '28px', 'compose kind token row should match the compact input row');
assertDecl('#compose textarea', 'min-height', v => v === '28px', 'compose textarea should keep the single-line row centered');
assertDecl('.compose-send.iconbtn.send', 'width', v => v === '28px', 'compose send button should stay compact inside the field');
assertDecl('.compose-send.iconbtn.send svg', 'width', v => v === '17px', 'compose send icon should scale with the compact button');
assertDecl('.composer-field:has(.compose-meta-chips:empty)', 'row-gap', v => v === '0', 'single-line compose field should not reserve metadata gap');
assertDecl('.composer-field:has(.compose-meta-chips:empty) .compose-send', 'grid-row', v => v === '1', 'single-line compose send should align to the input row');
assertDecl('.composer-field:has(.compose-meta-chips:empty):not(.compose-multiline) .compose-send', 'align-self', v => v === 'center', 'single-line compose send should center in the input row');
assert(src.includes('classList.toggle("compose-multiline"'), 'compose field should track multiline state for alignment');
assert(!dashboardCss.includes('#compose #closecompose'), 'compose close button styles should stay removed');
assert(dashboardCss.includes('--segment-thumb:#3a3a3c'), 'dark theme should brighten segmented thumb background');
assertDecl('.overview .ov-dot', 'background', v => v === 'var(--circle)', 'overview dots should have a CSS default color');
assertDecl('.overview .ov-dot.running', 'background', v => v === 'var(--running)', 'overview running dot color missing');
assertDecl('.overview .ov-dot.waiting', 'background', v => v === 'var(--waiting)', 'overview waiting dot color missing');
assert(src.includes('<span>완료 ${fmtCompactCount(completed)}</span>') && !src.includes('(진행 '), 'overview should show section counts, not working-state detail');
assert(!src.includes('STATE_COLOR') && !src.includes('style="background:${'), 'overview state color should not use inline style rendering');
const floatingSide = decls(cssBlock('body.side-auto-collapsed:not(.side-collapsed) #side'));
assert(floatingSide.position === 'absolute' && (floatingSide.width || '').includes('min(300px') && floatingSide['z-index'] === 'var(--z-side-floating)', 'floating side panel layout/z-index contract missing');
assert((floatingSide.transition || '').includes('var(--transition-panel-open)'), 'floating side panel should match panel animation duration');
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
  'filterKinds',
  'class="fp-main"',
  'function normalizeTooltips',
  'new MutationObserver',
  'window.matchMedia ? window.matchMedia("(max-width: 720px)")',
  'document.body.classList.toggle("side-auto-collapsed", autoSide)',
  'function closeFloatingSidePanelFromOutside',
  'document.addEventListener("pointerdown", e => closeFloatingSidePanelFromOutside(e.target), true)',
  'document.addEventListener("focusin", e => closeFloatingSidePanelFromOutside(e.target), true)',
  'function onSideModeChange()',
  'sideAutoCollapseMQ.addEventListener("change", onSideModeChange)',
  'function setSideTab',
  'function moveSideTabThumb',
  'function syncSideTabThumbAfterLayout',
  'let sideTabAnimTimer = null',
  'let sideTabSyncTimer = null',
  'if (tabsWidth < 80 || on.offsetWidth < 40) return',
  'tabs.classList.toggle("side-tabs-animate", animate)',
  'animate = animate === true',
  'window.addEventListener("resize", syncSideTabThumbAfterLayout)',
  'if (sideVisible) syncSideTabThumbAfterLayout()',
  'byId("side-tab-work").addEventListener("click", () => setSideTab("work", true, true))',
  'byId("side-tab-agent").addEventListener("click", () => setSideTab("agent", true, true))',
  'byId("side-tab-bridge").addEventListener("click", () => setSideTab("bridge", true, true))',
  'byId("bridge-profiles").addEventListener("click", e => {',
  'setSideTab(sideTab, false)',
  'byId("force-stopbtn")?.addEventListener("click", async () => {',
  'const LEAD_REQUEST_KINDS = new Set(["task", "ticket", "stop"])',
  'LEAD_AGENT_ID = AGENT_NAMES.find(id => isLeadAgent(agents[id] || {})) || ""',
  'if (LEAD_REQUEST_KINDS.has(kind)) composeKind = "note"',
]) {
  assert(src.includes(needle), `dashboard interaction sentinel missing: ${needle}`);
}
assert(!src.includes('bar.style.display') && !src.includes('addEventListener("click", () => flip("sideCollapsed"))') && !src.includes('플로팅 패널'), 'old layout interaction source leaked');
assert(!src.includes('SIDE_TAB_PILL_WIDTH'), 'side tab thumb should fill the active tab slot rather than use a fixed pill width');

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
