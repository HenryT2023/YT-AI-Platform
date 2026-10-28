'use strict';

const STUDIO_BASE = /^\/studio(?:\/|$)/.test(location.pathname) ? '/studio' : '';
const studioUrl = path => `${STUDIO_BASE}${path}`;

// All untrusted text enters the DOM through textContent. SVG previews are
// server-sanitized responses displayed as images, never active DOM fragments.
const $ = (selector, root = document) => root.querySelector(selector);
const node = (tag, attrs = {}, ...children) => {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') element.className = value;
    else if (key === 'text') element.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') element.addEventListener(key.slice(2), value);
    else if (key === 'checked') element.checked = Boolean(value);
    else if (key === 'value') element.value = value;
    else if (key === 'required' || key === 'disabled' || key === 'hidden') element[key] = Boolean(value);
    else element.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
};
const clear = element => element.replaceChildren();
const text = (tag, value, className) => node(tag, {text: value, class: className});
const button = (label, action, className = 'button button-secondary', attrs = {}) => node('button', {type: 'button', class: className, onclick: action, ...attrs}, label);
const badge = (label, tone = 'neutral') => text('span', label, `badge ${tone}`);
const domainLabels = {humanities: '人文文化', nature: '自然生态', craft: '工艺与文创', project: '项目资料'};
const reviewLabels = {draft: '待核验', source_checked: '已核对出处', approved: '已审阅', disputed: '有争议', retired: '已停用'};
const designLabels = {draft: '稿样待审', needs_revision: '待修改', approved: '本版已审', source_changed: '关联知识已更新'};
const purposeLabels = {print_block: '木刻印版', decorative: '装饰图样', undecided: '用途待定'};
const kindLabels = {fact: '事实陈述', interpretation: '解释与创作', requirement: '项目要求'};
const routes = {qa: '文化问答', dashboard: '工作室概览', knowledge: '文化知识与来源', designs: '木刻稿样', reviews: '审阅与反馈'};
const toneFor = status => ['approved', 'source_checked'].includes(status) ? 'green' : ['disputed', 'needs_revision', 'source_changed'].includes(status) ? 'red' : 'gold';
const state = {status: null, sources: [], knowledge: [], designs: [], candidates: [], design: null, route: 'qa', loadErrors: {}, issues: [], issuesLoaded: false, issuesError: '', qaSourceFilter: '', qaSourceSearch: '', askBusy: false, askError: '', loaded: false, question: '', answer: null, knowledgeSearch: '', domainFilter: '', statusFilter: '', designIsNew: false};
let previewTimer;
let previewSequence = 0;
let previewObjectUrl;
let historicalObjectUrl;
let routeSequence = 0;

function friendlyError(detail, fallback) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => typeof item === 'string' ? item : item.msg || '输入格式不正确').join('；');
  return fallback;
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== 'GET') {
    headers.set('X-Yantian-Local', '1');
    headers.set('Content-Type', 'application/json');
  }
  let response;
  try { response = await fetch(studioUrl(path), {...options, headers, credentials: 'same-origin'}); }
  catch { throw new Error('暂时无法连接本地工作室。请确认本地服务仍在运行，输入内容已保留。'); }
  if (!response.ok) {
    let body;
    try { body = await response.json(); } catch { body = {}; }
    const fallback = response.status === 409 ? '这份资料已有新版本，请刷新后核对。当前输入已保留。' : `操作未完成（${response.status}），请检查输入后重试。`;
    throw new Error(friendlyError(body.detail, fallback));
  }
  if (options.responseType === 'text') return response.text();
  return response.json();
}
function toast(message, kind = 'error') {
  const item = node('div', {class: `toast ${kind}`, role: kind === 'error' ? 'alert' : 'status'}, text('span', message));
  item.append(button('×', () => item.remove(), '', {'aria-label': '关闭提示'}));
  $('#toasts').append(item);
  setTimeout(() => item.remove(), kind === 'error' ? 11000 : 5500);
}
async function submitWith(form, action) {
  const submit = form.querySelector('[type=submit]');
  if (submit.disabled) return;
  const original = submit.textContent;
  submit.disabled = true; submit.textContent = '正在保存…';
  try { await action(); } catch (error) { toast(error.message); }
  finally { submit.disabled = false; submit.textContent = original; }
}
function dateLabel(value) {
  if (!value) return '时间未记录';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai'}).format(date);
}
function safeLink(url, label, className = '') {
  if (!url) return text('span', label || '本地来源，无公开链接', `muted ${className}`);
  try {
    const parsed = new URL(url);
    if (!['https:', 'http:'].includes(parsed.protocol)) return text('span', '链接格式待核对', 'muted');
    return node('a', {href: parsed.href, target: '_blank', rel: 'noopener noreferrer', class: className}, label || '打开原始来源 ↗');
  } catch { return text('span', '来源链接待核对', 'muted'); }
}
function notice(title, content, tone = '') {
  return node('div', {class: `notice ${tone}`}, text('span', tone === 'warm' ? '◇' : '◌', 'notice-icon'), node('div', {}, text('strong', title), text('p', content)));
}
function emptyState(title, description, action) {
  return node('div', {class: 'empty'}, text('span', '·', 'empty-symbol'), text('h3', title), text('p', description), action);
}
function pageHead(eyebrow, title, description, actions = []) {
  return node('div', {class: 'page-head'}, node('div', {}, text('div', eyebrow, 'eyebrow'), text('h1', title), text('p', description)), actions.length ? node('div', {class: 'head-actions'}, actions) : null);
}
function sectionHeading(title, action) { return node('div', {class: 'section-heading'}, text('h2', title), action); }
function field(label, control, hint) {
  const tag = ['INPUT', 'TEXTAREA', 'SELECT'].includes(control.tagName) ? 'label' : 'div';
  return node(tag, {class: 'field'}, text('span', label), control, hint ? text('small', hint) : null);
}
function input(name, value = '', attrs = {}) { return node('input', {name, value, ...attrs}); }
function select(name, options, value = '', attrs = {}) {
  const result = node('select', {name, ...attrs});
  for (const [key, label] of options) result.append(node('option', {value: key}, label));
  result.value = value;
  return result;
}
function textarea(name, value = '', attrs = {}) { return node('textarea', {name, value, ...attrs}); }
function checkbox(name, label, description, checked = false) {
  return node('label', {class: 'checkbox-label'}, input(name, 'on', {type: 'checkbox', checked}), node('span', {}, label, description ? text('span', description, 'check-description') : null));
}
function syncSidebarAccessibility() { $('#sidebar').inert = window.matchMedia('(max-width: 780px)').matches && !$('#sidebar').classList.contains('open'); }
function closeMenu() {
  $('#sidebar').classList.remove('open'); $('#mobile-shade').hidden = true;
  $('#menu-toggle').setAttribute('aria-expanded', 'false');
  syncSidebarAccessibility();
}
function navigate(route) { location.hash = route; if (state.route === route) render(); }
async function reloadData() {
  const entries = [['status', '/api/status'], ['sources', '/api/sources'], ['knowledge', '/api/knowledge'], ['designs', '/api/designs'], ['candidates', '/api/learning-candidates']];
  const results = await Promise.allSettled([...entries.map(([, path]) => api(path)), api('/api/issues')]);
  const errors = [];
  results.slice(0, entries.length).forEach((result, index) => {
    const key = entries[index][0];
    if (result.status === 'fulfilled') { state[key] = result.value; delete state.loadErrors[key]; }
    else { state.loadErrors[key] = result.reason.message; errors.push(result.reason.message); }
  });
  const issuesResult = results[entries.length];
  state.issuesLoaded = issuesResult.status === 'fulfilled';
  state.issues = state.issuesLoaded && Array.isArray(issuesResult.value) ? issuesResult.value : [];
  state.issuesError = state.issuesLoaded ? '' : issuesResult.reason.message;
  state.loaded = true;
  if (errors.length) toast(errors[0]);
  if (state.status?.version) $('#sidebar-version').textContent = `V${state.status.version}`;
}
async function loadDesign(id) {
  if (!id) { state.design = null; return null; }
  const design = await api(`/api/designs/${encodeURIComponent(id)}`);
  state.design = design; state.designIsNew = false;
  return design;
}
function recentDesignsCard() {
  const content = node('div', {class: 'card card-pad'}, sectionHeading('稿样手记', button('全部稿样 ↗', () => navigate('designs'), 'text-button')));
  if (!state.designs.length) content.append(emptyState('第一份稿样，等你落笔', '从原创几何、叶片或波纹开始一份设计练习。', button('创建稿样', startNewDesign, 'button button-secondary button-small')));
  else {
    const list = node('div', {class: 'summary-list'});
    state.designs.slice(0, 3).forEach(design => list.append(node('div', {class: 'summary-item'}, text('h3', design.title), text('p', `${purposeLabels[design.purpose] || '用途待确认'} · 第 ${design.version} 版`), node('div', {class: 'badge-row'}, badge(designLabels[design.status] || design.status, toneFor(design.status)), button('打开稿样 →', async () => { try { await loadDesign(design.id); navigate('designs'); } catch (error) { toast(error.message); } }, 'text-button')))));
    content.append(list);
  }
  return content;
}
function renderDashboard(main) {
  main.append(pageHead('YANTIAN · STUDIO / 01', '让地方知识，成为可用的智慧', '从一份有出处的资料，到一张可编辑的稿样，再到一次真实的审阅。这里保存每一步的来处与修改。'));
  const counts = state.status?.counts;
  const stats = [['sources', '资料来源', '建立知识的证据起点'], ['knowledge', '知识条目', '区分事实、解释与要求'], ['designs', '木刻稿样', '原创练习，保存不可变版本'], ['reviews', '审阅记录', '意见绑定具体图样版本']];
  main.append(node('div', {class: 'stats'}, stats.map(([key, title, description]) => node('div', {class: 'card stat'}, node('div', {class: 'stat-label'}, title, text('span', '↗')), text('div', counts?.[key] ?? '—', 'stat-value'), text('div', description, 'stat-detail')))));
  main.append(notice('当前为本地证据检索工作室', '问答从可用知识中检索并摘录，保留出处与范围。尚未连接大模型、尚未训练专属权重；机器接口未启用。'));
  const modules = [
    ['knowledge', '▤', '文化知识', '整理人文、自然、工艺与项目资料，让地域、来源和使用范围保持清楚。', '管理知识与来源'],
    ['qa', '◌', '出处问答', '带着问题查找本地知识。能回答的给出证据，缺少的保留缺口。', '开始一次查证'],
    ['designs', '◇', '木刻稿样', '从设计意图到可编辑 SVG，保留尺寸、镜像选择和每次修改。', '进入稿样工作区'],
    ['reviews', '✓', '审阅与反馈', '在具体版本上留下文化、权利和工艺意见，积累待审学习候选。', '查看审阅与反馈']
  ];
  const modulePanel = node('section', {}, sectionHeading('四个工作入口', text('span', '从资料到作品', 'small muted')), node('div', {class: 'module-grid'}, modules.map(([route, icon, title, description, link], index) => node('a', {class: 'module-card', href: `#${route}`}, node('div', {class: 'module-top'}, text('span', icon, 'module-icon'), text('span', `0${index + 1}`, 'module-index')), text('h3', title), text('p', description), node('div', {class: 'module-link'}, link, text('span', '→'))))));
  main.append(node('div', {class: 'home-grid'}, modulePanel, recentDesignsCard()));
  main.append(node('div', {class: 'workflow'}, text('b', '工作路径'), '登记来源', text('span', '→', ''), '核对知识', text('span', '→'), '创作稿样', text('span', '→'), '按版审阅', text('span', '→'), '保留反馈'));
}

function sourceCard(source) {
  return node('div', {class: 'source-item'}, text('div', sourceName(source), 'source-title'), text('p', `地域 / 适用范围：${source.scope || '未记录'}`), node('div', {class: 'badge-row mt-16'}, badge(({public: '公开资料', local: '本地资料', oral: '口述资料', project: '项目资料'})[source.source_kind] || source.source_kind), badge(source.rights_scope === 'internal' ? '限内部使用' : '权利待确认', source.rights_scope === 'internal' ? 'green' : 'gold')), source.locator ? text('p', `定位：${locatorLabel(source.locator)}`) : null, node('div', {class: 'mt-16'}, safeLink(source.url, source.url ? '查看来源 ↗' : '本地来源 · 无公开链接')), source.id ? sourceReadButton(source.id) : null);
}
function renderKnowledge(main) {
  main.append(pageHead('COLLECTION / 02', '文化知识', '把事实、解释和项目要求分别保存。核对出处仅表示资料已核对，不自动证明其属于严田的在地事实。', [button('＋ 登记来源', openSourceEditor, 'button button-secondary'), button('＋ 添加知识', () => openKnowledgeEditor())]));
  const search = input('knowledge_search', state.knowledgeSearch, {type: 'search', placeholder: '搜索标题、内容、地域或来源', 'aria-label': '搜索知识'});
  const domains = select('domain_filter', [['', '全部领域'], ...Object.entries(domainLabels)], state.domainFilter, {'aria-label': '筛选知识领域'});
  const statuses = select('status_filter', [['', '全部状态'], ...Object.entries(reviewLabels)], state.statusFilter, {'aria-label': '筛选核验状态'});
  const list = node('div', {class: 'knowledge-list'});
  const count = text('span', '', 'small muted');
  function updateList() {
    clear(list);
    const query = state.knowledgeSearch.toLocaleLowerCase();
    const items = state.knowledge.filter(item => (!state.domainFilter || item.domain === state.domainFilter) && (!state.statusFilter || item.review_status === state.statusFilter) && `${item.title} ${item.content} ${item.region_scope} ${item.source?.title || ''}`.toLocaleLowerCase().includes(query));
    count.textContent = `${items.length} 条知识`;
    if (!items.length) { list.append(emptyState('没有匹配的知识', '可以更换筛选条件，或先登记来源，再添加知识。', button('添加知识', () => openKnowledgeEditor(), 'button button-secondary button-small'))); return; }
    for (const item of items) {
      list.append(node('article', {class: 'card knowledge-card'}, node('div', {class: 'knowledge-card-top'}, node('div', {}, node('div', {class: 'badge-row'}, badge(domainLabels[item.domain] || item.domain), badge(reviewLabels[item.review_status] || item.review_status, toneFor(item.review_status))), node('h3', {class: 'mt-16'}, item.title)), item.evidence_type === 'document_statement' ? sourceReadButton(item.source_id, '查看原文') : button('编辑', () => openKnowledgeEditor(item), 'button button-quiet button-small')), text('p', item.content, 'knowledge-content'), node('div', {class: 'knowledge-meta'}, `范围：${item.region_scope || '未记录'}`, `${item.evidence_type === 'document_statement' ? '资料记载 · 待事实复核' : kindLabels[item.kind] || item.kind} · v${item.version}`, item.rights_scope === 'internal' ? '限内部使用' : '使用权利待确认'), node('div', {class: 'knowledge-source'}, text('span', '↳'), safeLink(item.source?.url, item.source?.title || state.sources.find(source => source.id === item.source_id)?.title || '来源待确认')), text('span', `定位：${locatorLabel(item.locator)}`, 'source-scope')));
    }
  }
  search.addEventListener('input', () => { state.knowledgeSearch = search.value; updateList(); });
  domains.addEventListener('change', () => { state.domainFilter = domains.value; updateList(); });
  statuses.addEventListener('change', () => { state.statusFilter = statuses.value; updateList(); });
  const body = node('section', {}, node('div', {class: 'toolbar'}, node('div', {class: 'search-wrap'}, text('span', '⌕', 'search-icon'), search), domains, statuses), node('div', {class: 'section-heading'}, count), list);
  const sources = node('div', {class: 'card card-pad'}, sectionHeading('来源簿', badge(`${state.sources.length} 份`)));
  if (state.sources.length) sources.append(...state.sources.map(sourceCard));
  else sources.append(text('p', '还没有来源。先记录资料的来处与适用范围。', 'small'));
  const aside = node('aside', {class: 'source-sidebar'}, sources, node('div', {class: 'side-note'}, text('strong', '地域与证据，分别记清'), '中华文化背景、徽州区域资料和严田在地事实各有适用范围。区域性材料不能直接变成严田起源、历史或非遗身份的证明。'));
  main.append(node('div', {class: 'knowledge-layout'}, body, aside)); updateList();
}
function openDialog(title, description, form) {
  const dialog = $('#editor-dialog'); const content = $('#dialog-content'); clear(content);
  content.append(node('div', {class: 'dialog-header'}, text('h2', title, ''), button('×', () => dialog.close(), 'icon-button', {'aria-label': '关闭窗口'})), node('div', {class: 'dialog-body'}, text('p', description, 'dialog-description'), form));
  content.querySelector('h2').id = 'dialog-title';
  dialog.showModal();
}
function dialogActions(form, label) { form.append(node('div', {class: 'form-actions'}, node('button', {type: 'submit', class: 'button'}, label), button('取消', () => $('#editor-dialog').close(), 'button button-quiet'))); }
function openSourceEditor() {
  const form = node('form');
  form.append(field('来源标题 *', input('title', '', {required: true, maxlength: 200, placeholder: '资料名称、文件名或口述主题'})), field('来源链接', input('url', '', {type: 'url', placeholder: 'https://…；本地资料可以留空'}), '仅登记链接，不会主动抓取远程内容。'), node('div', {class: 'form-row'}, field('来源类型 *', select('source_kind', [['project', '项目资料'], ['public', '公开资料'], ['local', '本地资料'], ['oral', '口述资料']], 'project')), field('使用范围 *', select('rights_scope', [['unknown', '权利待确认'], ['internal', '限内部使用']], 'unknown'))), field('地域 / 适用范围 *', input('scope', '', {required: true, placeholder: '如：徽州区域；严田具体对象；某一时期'})), field('原件定位', input('locator', '', {placeholder: '页码、段落、表名或受控记录引用'})));
  dialogActions(form, '保存来源');
  form.addEventListener('submit', event => { event.preventDefault(); submitWith(form, async () => { await api('/api/sources', {method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(form)))}); await reloadData(); $('#editor-dialog').close(); render(); toast('来源已登记。接下来可以添加有出处的知识。', 'success'); }); });
  openDialog('登记资料来源', '保留标题、范围与定位；请勿填入私人联系方式、访问令牌或私有连接信息。', form);
}
function openKnowledgeEditor(item = null) {
  if (item?.evidence_type === 'document_statement') { openSourceDetails(item.source_id); return; }
  if (!state.sources.length) { toast('先登记一份来源，再添加知识。'); openSourceEditor(); return; }
  const form = node('form');
  form.append(field('知识标题 *', input('title', item?.title || '', {required: true, maxlength: 200})), field('知识正文 *', textarea('content', item?.content || '', {required: true, rows: 5, placeholder: '记录有依据的内容；艺术联想和待核验内容请明确标记。'})), field('资料来源 *', select('source_id', state.sources.map(source => [source.id, `${source.title} · ${source.scope || '范围待记'}`]), item?.source_id || state.sources[0].id, {required: true})), field('原件定位 *', input('locator', item?.locator || '', {required: true, placeholder: '可反查的页、段、表、记录引用'})), field('地域 / 时期 / 适用范围 *', input('region_scope', item?.region_scope || '', {required: true, placeholder: '按证据填写，不将区域共性直接标为严田事实'})), node('div', {class: 'form-row'}, field('知识领域 *', select('domain', Object.entries(domainLabels), item?.domain || 'humanities')), field('陈述性质 *', select('kind', Object.entries(kindLabels), item?.kind || 'fact'))), node('div', {class: 'form-row'}, field('核验状态 *', select('review_status', Object.entries(reviewLabels), item?.review_status || 'draft')), field('使用范围 *', select('rights_scope', [['unknown', '权利待确认'], ['internal', '限内部使用']], item?.rights_scope || 'unknown'))), notice('核对的是出处', '“已核对出处”不表示已证明严田归属，也不等同于工艺师审核。编辑会保存为新版本。', 'neutral'));
  dialogActions(form, item ? `保存为新版本（当前 v${item.version}）` : '保存知识');
  form.addEventListener('submit', event => { event.preventDefault(); submitWith(form, async () => {
    const payload = Object.fromEntries(new FormData(form)); if (item) payload.base_version = item.version;
    await api(item ? `/api/knowledge/${encodeURIComponent(item.id)}` : '/api/knowledge', {method: item ? 'PUT' : 'POST', body: JSON.stringify(payload)});
    await reloadData(); $('#editor-dialog').close(); render(); toast(item ? '知识新版本已保存。关联稿样需要按新来源重新核对。' : '知识条目已保存。', 'success');
  }); });
  openDialog(item ? '编辑知识条目' : '添加知识条目', '不同来源、解释和争议应分别记录。历史版本保留，未核验内容不用于确定性回答。', form);
}

const issueLabels = {missing: '缺资料', disputed: '有争议', unreadable: '原件待读取', verification: '待事实复核', rights: '使用范围待核'};
function sourceName(source) {
  const value = source?.filename || source?.title || '来源未记录';
  return String(value).split(/[\\/]/).filter(Boolean).pop() || '本地资料';
}
function locatorLabel(value) {
  if (!value || /(?:file:\/\/|\/Users\/|\/home\/|^[A-Za-z]:[\\/])/.test(String(value))) return '文件内定位未记录';
  return String(value);
}
function sourceForId(id) { return state.sources.find(source => source.id === id); }
function issueCard(issue, compact = false) {
  if (typeof issue === 'string') return text('li', issue, 'issue-plain');
  const card = node('article', {class: `issue-card ${issue.kind === 'disputed' ? 'disputed' : ''}`}, node('div', {class: 'badge-row'}, badge(issueLabels[issue.kind] || '待核事项', issue.kind === 'disputed' ? 'red' : 'gold'), issue.scope ? text('span', issue.scope, 'small muted') : null), text('h3', issue.title || '待确认事项'), text('p', issue.description || '请核对原始资料，并记录确认结论。'));
  if (issue.source_ids?.length) card.append(node('div', {class: 'issue-sources'}, issue.source_ids.map(id => button(sourceName(sourceForId(id)), () => openSourceDetails(id), 'text-button'))));
  if (!compact && issue.topics?.length) card.append(text('div', `相关主题：${issue.topics.join(' · ')}`, 'citation-detail'));
  return card;
}
function sourceReadButton(id, label = '查看原文选段 →') {
  return button(label, () => openSourceDetails(id), 'text-button', {'aria-label': `${label}：${sourceName(sourceForId(id))}`});
}
async function openSourceDetails(id) {
  const body = node('div', {class: 'source-reader', 'aria-live': 'polite'}, text('p', '正在读取来源与原文选段…', 'small muted'));
  openDialog('来源与原文选段', '只读查看本次入库的本地摘录。资料记载、事实复核与使用许可分别保留。', body);
  try {
    const result = await api(`/api/sources/${encodeURIComponent(id)}`);
    if (!body.isConnected) return;
    clear(body);
    const source = result.source || result;
    body.append(text('h3', sourceName(source)), node('div', {class: 'badge-row mt-16'}, badge(source.local_use_scope === 'local_excerpt_only' ? '仅本地摘录查阅' : source.rights_scope === 'internal' ? '限内部使用' : '使用范围待核', 'gold'), badge(source.fact_verification === 'verified' ? '已有事实复核记录' : '未经事实复核', source.fact_verification === 'verified' ? 'green' : 'gold')), text('p', `地域 / 时期：${source.region_scope || source.scope || '待核'}${source.temporal_scope ? ` · ${source.temporal_scope}` : ''}`, 'reader-meta'), text('p', `来源版本：${source.version || '未记录'} · 训练使用许可：${source.training_rights === 'approved' ? '已登记许可' : '待确认'}`, 'reader-meta'));
    if (source.sha256) body.append(node('details', {class: 'reader-fingerprint'}, text('summary', '核对文件指纹'), text('p', source.sha256, 'mono')));
    if (source.url) body.append(safeLink(source.url, '查看已登记的公开链接 ↗'));
    const passages = result.passages || [];
    body.append(sectionHeading('原文选段', badge(`${passages.length} 段`)));
    if (!passages.length) body.append(notice('尚无可读的原文选段', '当前仅有来源登记。需补原件与文件内定位后，才能逐段查证。', 'warm'));
    for (const passage of passages) body.append(node('article', {class: 'reader-passage'}, text('h3', passage.section_title || locatorLabel(passage.locator)), text('div', `定位：${locatorLabel(passage.locator)}`, 'citation-detail'), text('blockquote', passage.text || '这段原文尚未读取。'), passage.sha256 ? node('details', {class: 'reader-fingerprint'}, text('summary', '段落指纹'), text('p', passage.sha256, 'mono')) : null));
    if (result.issues?.length) body.append(sectionHeading('此来源的待核事项'), ...result.issues.map(issue => issueCard(issue, true)));
  } catch (error) {
    if (!body.isConnected) return;
    clear(body); body.append(notice('来源暂时无法读取', error.message, 'warm'), button('重试读取', () => openSourceDetails(id), 'button button-secondary mt-16'));
  }
}
function qaCoverage() {
  const localSources = state.sources.filter(source => source.filename || source.document_key);
  const disputes = state.issues.filter(issue => issue.kind === 'disputed');
  const missing = state.issues.filter(issue => ['missing', 'unreadable'].includes(issue.kind));
  const card = node('section', {class: 'card qa-coverage'}, node('div', {class: 'section-heading'}, text('h2', '本机资料覆盖'), button('刷新资料', async () => { await reloadData(); render(); }, 'text-button')));
  const counts = [[state.loadErrors.sources ? '—' : localSources.length, '已入库本地文件'], [state.loadErrors.knowledge ? '—' : state.knowledge.length, '知识条目'], [state.issuesLoaded ? disputes.length : '—', '争议事项'], [state.issuesLoaded ? missing.length : '—', '资料缺口']];
  card.append(node('div', {class: 'coverage-stats'}, counts.map(([count, label]) => node('div', {}, text('strong', count), text('span', label)))));
  card.append(text('p', '以下为已入库范围；本机未入库文件不在检索范围内。', 'small muted'));
  if (state.loadErrors.sources || state.loadErrors.knowledge) card.append(notice('资料覆盖暂未完整更新', '部分清单未读取成功，数量暂记为未知。请刷新资料后重试。', 'warm'));
  const search = input('qa_source_search', state.qaSourceSearch, {type: 'search', placeholder: '按文件名查找', 'aria-label': '按文件名查找来源'});
  const filter = select('qa_source_filter', [['', '全部来源'], ['local', '本地文件'], ['disputed', '关联争议'], ['unverified', '待事实复核']], state.qaSourceFilter, {'aria-label': '筛选资料状态'});
  const list = node('div', {class: 'qa-source-list'});
  function showSources() {
    clear(list);
    const disputedIds = new Set(disputes.flatMap(issue => issue.source_ids || []));
    const sources = state.sources.filter(source => sourceName(source).toLowerCase().includes(state.qaSourceSearch.toLowerCase()) && (!state.qaSourceFilter || state.qaSourceFilter === 'local' && (source.filename || source.document_key) || state.qaSourceFilter === 'disputed' && disputedIds.has(source.id) || state.qaSourceFilter === 'unverified' && source.fact_verification !== 'verified'));
    if (!sources.length) list.append(text('p', '没有匹配来源。可以更换筛选条件。', 'small muted'));
    sources.forEach(source => list.append(node('article', {class: 'qa-source-item'}, text('h3', sourceName(source)), node('div', {class: 'badge-row'}, badge(source.filename || source.document_key ? '本地文件' : '来源登记'), badge(disputedIds.has(source.id) ? '关联争议' : source.fact_verification === 'verified' ? '有复核记录' : '待事实复核', disputedIds.has(source.id) ? 'red' : 'gold')), text('p', source.scope || source.region_scope || '适用范围待核'), sourceReadButton(source.id))));
  }
  search.addEventListener('input', () => { state.qaSourceSearch = search.value; showSources(); });
  filter.addEventListener('change', () => { state.qaSourceFilter = filter.value; showSources(); });
  card.append(node('div', {class: 'qa-source-controls'}, search, filter), list); showSources(); return card;
}
function qaIssues() {
  const card = node('section', {class: 'card qa-issues'}, sectionHeading('缺失与争议', state.issuesLoaded ? badge(`${state.issues.length} 项待核`) : badge('暂未读取', 'gold')));
  if (!state.issuesLoaded) card.append(notice('待核清单暂时无法读取', state.issuesError || '请刷新资料后重试。当前问答仍保留自身的证据限制。', 'warm'));
  else if (!state.issues.length) card.append(text('p', '本次入库尚未登记待核事项。这不表示所有资料已经完成复核。', 'small muted'));
  else {
    const list = node('div', {class: 'qa-issue-list'});
    const filter = select('qa_issue_filter', [['', '全部待核事项'], ...Object.entries(issueLabels)], '', {'aria-label': '筛选缺失与争议类别'});
    function showIssues() { clear(list); const issues = state.issues.filter(issue => !filter.value || issue.kind === filter.value); if (!issues.length) list.append(text('p', '此类别暂无已登记事项。', 'small muted')); else issues.forEach(issue => list.append(issueCard(issue, true))); }
    filter.addEventListener('change', showIssues); card.append(filter, list); showIssues();
  }
  return card;
}
function renderAsk(main) {
  main.append(pageHead('YANTIAN · CULTURE / 01', '从严田资料里，找到有出处的回答', '先读本机已入库的资料，再看原文和不同记载。缺少依据的地方，明确留下待补与待核。'));
  const primary = node('section', {class: 'qa-primary', 'aria-label': '文化问答'});
  const form = node('form', {class: 'card ask-form'});
  const question = textarea('question', state.question, {id: 'culture-question', required: true, maxlength: 4000, placeholder: '例如：严田村什么时候建村？', 'aria-label': '输入文化问题', rows: 3});
  question.addEventListener('input', () => { state.question = question.value; });
  const submit = node('button', {type: 'submit', class: 'button', disabled: state.askBusy}, state.askBusy ? '正在查找…' : '查找资料与出处 →');
  const answers = node('div', {id: 'qa-answer', 'aria-live': 'polite', 'aria-busy': String(state.askBusy)});
  function showAnswer() {
    clear(answers); answers.setAttribute('aria-busy', String(state.askBusy));
    if (state.askBusy) answers.append(node('div', {class: 'qa-loading', role: 'status'}, text('strong', '正在查找本地资料…'), text('p', '逐条保留文件、段落与原文。')));
    else if (state.askError) answers.append(node('div', {class: 'qa-error', role: 'alert'}, notice('这次查找未完成', state.askError, 'warm'), text('p', '问题已保留，可以直接重试。', 'small muted')));
    else if (state.answer) answers.append(answerCard(state.answer));
    else answers.append(emptyState('先问一个具体问题', '可以查村史、地名、建筑与文化。结果是本地资料摘录；有争议时并列记载，资料不足时说明缺口。'));
  }
  form.append(node('label', {for: 'culture-question', class: 'qa-question-label'}, '想了解严田的什么？'), question, node('div', {class: 'ask-form-bottom'}, text('span', '本地资料检索与摘录 · 尚未接入生成式模型', 'small'), submit));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (state.askBusy) return;
    const value = question.value.trim(); if (!value) { question.focus(); return; }
    state.question = value; state.askBusy = true; state.askError = ''; submit.disabled = true; submit.textContent = '正在查找…'; showAnswer();
    try { state.answer = await api('/api/ask', {method: 'POST', body: JSON.stringify({question: value})}); }
    catch (error) { state.askError = error.message; }
    finally { state.askBusy = false; submit.disabled = false; submit.textContent = '查找资料与出处 →'; if (primary.isConnected) showAnswer(); else if (state.route === 'qa') render(); }
  });
  primary.append(form, node('div', {class: 'question-chips', 'aria-label': '示例问题'}, ['严田村什么时候建村？', '严田和严溪是什么关系？', '秩叙堂有哪些木雕？'].map(value => button(value, () => { question.value = value; state.question = value; question.focus(); }, 'chip'))), answers);
  showAnswer();
  const aside = node('aside', {class: 'qa-aside', 'aria-label': '资料覆盖与待核事项'}, qaCoverage(), qaIssues());
  main.append(node('div', {class: 'qa-layout'}, primary, aside));
}
function answerCard(answer) {
  const isDocument = answer.evidence_state === 'document_statement';
  const disputed = Boolean(answer.disputed || answer.issues?.some(issue => issue.kind === 'disputed'));
  const answerText = answer.citations?.length && answer.mode === 'extractive' ? String(answer.answer || '').split('\n\n')[0] : answer.answer;
  const title = answer.status !== 'answered' ? '现有资料还不足' : disputed ? '找到不同记载，暂不合并为结论' : isDocument ? '找到可查证的资料记载' : '找到可引用的知识条目';
  const card = node('section', {class: 'card answer-card', 'aria-label': '查证结果'}, text('div', `查证问题：${answer.question || state.question}`, 'answer-question'), node('div', {class: 'section-heading'}, text('h2', title), badge(disputed ? '有争议' : isDocument ? '资料记载' : '本地摘录', disputed ? 'red' : 'gold')), text('div', answerText || '当前未找到足以回答此问题的资料。', 'answer-text'));
  if (isDocument) card.append(notice('资料记载 · 未经事实复核', '以下原文能证明资料如何记载；是否符合史实、是否适用于严田具体对象，仍需核对。', 'warm'));
  if (answer.limitations?.length) card.append(node('ul', {class: 'limitations'}, answer.limitations.map(value => text('li', value))));
  if (answer.citations?.length) card.append(sectionHeading('逐条引用与出处', badge(`${answer.citations.length} 条`)), node('div', {class: 'citation-grid'}, answer.citations.map((citation, index) => {
    const source = citation.source || sourceForId(citation.source_id);
    const fromDocument = citation.evidence_type === 'document_statement' || citation.passage_id || isDocument;
    const item = node('article', {class: 'citation-card'}, node('div', {class: 'badge-row'}, badge(`出处 ${index + 1}`, 'green'), badge(fromDocument ? '文档原文' : `知识 v${citation.knowledge_version || '未记录'}`), badge(fromDocument && citation.fact_verification !== 'verified' ? '待事实复核' : reviewLabels[citation.review_status] || '核验状态未记录', toneFor(citation.review_status))), text('h3', citation.title || '原文选段'), text('div', `文件：${sourceName({filename: citation.filename || source?.filename, title: citation.source_title || source?.title})}`, 'citation-detail'), text('blockquote', citation.excerpt || ''), text('div', `定位：${locatorLabel(citation.locator)}`, 'citation-detail'), text('div', `范围：${citation.region_scope || source?.region_scope || source?.scope || '未记录'}`, 'citation-detail'), text('div', `来源版本：${citation.source_version || source?.version || '未记录'} · ${source?.local_use_scope === 'local_excerpt_only' || fromDocument ? '仅本地摘录查阅' : source?.rights_scope === 'internal' ? '限内部使用' : '使用范围待核'}`, 'citation-detail'));
    if (citation.source_id) item.append(sourceReadButton(citation.source_id));
    else if (citation.url) item.append(safeLink(citation.url, '查看已登记的公开链接 ↗'));
    if (citation.source_sha256 || citation.passage_sha256) item.append(node('details', {class: 'reader-fingerprint'}, text('summary', '核对引用指纹'), citation.source_sha256 ? text('p', `文件：${citation.source_sha256}`, 'mono') : null, citation.passage_sha256 ? text('p', `段落：${citation.passage_sha256}`, 'mono') : null));
    return item;
  })));
  if (answer.issues?.length) card.append(sectionHeading('与本题有关的争议与待核'), ...answer.issues.map(issue => issueCard(issue)));
  if (answer.gaps?.length) card.append(sectionHeading('还需要补充什么'), node('div', {class: 'answer-gaps'}, answer.gaps.map(gap => typeof gap === 'string' ? text('p', gap) : issueCard(gap))));
  return card;
}

function startNewDesign() { state.design = null; state.designIsNew = true; navigate('designs'); }
function defaultDesign() { return {title: '', purpose: 'undecided', label: '', width_mm: 160, height_mm: 120, motif: 'geometric', mirror_choice: 'unconfirmed', knowledge_ids: [], note: ''}; }
function designPayload(form) {
  const data = new FormData(form);
  const payload = {title: data.get('title'), purpose: data.get('purpose'), label: data.get('label'), width_mm: Number(data.get('width_mm')), height_mm: Number(data.get('height_mm')), motif: data.get('motif'), mirror_choice: data.get('mirror_choice'), knowledge_ids: data.getAll('knowledge_ids'), note: data.get('note') || ''};
  if (data.get('use_custom_svg') === 'on') payload.svg = data.get('svg') || '';
  return payload;
}
function renderDesigns(main) {
  main.append(pageHead('WOODCUT WORKSHOP / 04', '木刻稿样', '保留设计意图和每次修改。几何、叶片与波纹均为原创设计练习，不标作历史纹样。', [button('＋ 新建稿样', startNewDesign)]));
  const current = state.design || defaultDesign(); const isSaved = Boolean(state.design?.id);
  const designList = node('div', {class: 'design-list'});
  if (!state.designs.length) designList.append(text('p', '还没有稿样。填写右侧设计意图，保存第一版。', 'small muted'));
  for (const design of state.designs) designList.append(node('button', {type: 'button', class: `design-list-item ${state.design?.id === design.id ? 'selected' : ''}`, onclick: async () => { try { await loadDesign(design.id); render(); } catch (error) { toast(error.message); } }}, text('span', ({geometric: '◇', leaf: '❧', wave: '≈'})[design.motif] || '◇', 'draft-thumb'), text('strong', design.title), text('small', `v${design.version} · ${design.width_mm || '—'} × ${design.height_mm || '—'} mm`), badge(designLabels[design.status] || design.status, toneFor(design.status))));
  const listPanel = node('aside', {class: 'card design-list-panel'}, text('div', `${state.designs.length} 份稿样 · 本地保存`, 'design-list-head'), designList);
  const previewSurface = node('div', {class: 'preview-surface'}, node('div', {class: 'preview-placeholder'}, text('span', '◇'), '填写设计意图，查看稿样预览'));
  const previewState = text('span', isSaved ? '已保存版本' : '实时预览 · 尚未保存');
  const versionSelect = select('preview_version', isSaved ? (current.versions || [{version: current.version}]).map(version => [String(version.version), `第 ${version.version} 版${version.version === current.version ? ' · 当前' : ' · 历史'}`]) : [['draft', '未保存稿样']], isSaved ? String(current.version) : 'draft', {'aria-label': '选择预览历史版本'});
  const dimensionLabel = text('span', `${current.width_mm} × ${current.height_mm} mm`);
  const download = node('a', {class: 'text-button', href: isSaved ? studioUrl(`/api/designs/${encodeURIComponent(current.id)}/svg?version=${current.version}`) : '#', download: true}, '↓ 下载当前 SVG');
  if (!isSaved) { download.removeAttribute('href'); download.textContent = '保存后可下载 SVG'; download.setAttribute('aria-disabled', 'true'); }
  const previewPanel = node('section', {}, node('div', {class: 'card preview-card'}, node('div', {class: 'preview-toolbar'}, previewState, versionSelect), previewSurface, node('div', {class: 'preview-caption'}, node('div', {}, dimensionLabel, text('p', '设计尺寸 · 非设备加工能力')), download)), node('div', {class: 'preview-note'}, '手工稿样与审阅阶段。机器接口仅预留，本版不启动设备，也不生成加工参数。'), isSaved ? notice(designLabels[current.status] || '稿样待审', `当前 v${current.version}。审阅只对精确版本有效；每次保存新版本后，原批准不沿用。`, current.status === 'approved' ? '' : 'neutral') : null);
  const form = node('form', {class: 'card inspector'});
  form.append(sectionHeading(isSaved ? `编辑稿样 · v${current.version}` : '一份新的稿样', badge(isSaved ? '新版本保存' : '原创练习', 'green')));
  form.append(field('稿样名称 *', input('title', current.title, {required: true, maxlength: 120, placeholder: '给这份练习取一个名字'})), field('制作用途 *', select('purpose', Object.entries(purposeLabels), current.purpose)), field('图样文字', input('label', current.label || '', {maxlength: 30, placeholder: '可留空，最多 30 字'})), node('div', {class: 'form-row'}, field('宽度 / mm *', input('width_mm', current.width_mm, {type: 'number', required: true, min: 30, max: 500, step: '.1'})), field('高度 / mm *', input('height_mm', current.height_mm, {type: 'number', required: true, min: 30, max: 500, step: '.1'}))));
  const motifs = node('div', {class: 'motif-options'}, [['geometric', '◇', '几何'], ['leaf', '❧', '叶片'], ['wave', '≈', '波纹']].map(([value, symbol, label]) => node('label', {class: 'motif-option'}, input('motif', value, {type: 'radio', checked: current.motif === value, required: true}), text('span', symbol, 'motif-symbol'), label)));
  form.append(field('原创图案', motifs), field('镜像选择 *', select('mirror_choice', [['unconfirmed', '尚未确认'], ['yes', '镜像图样'], ['no', '不镜像']], current.mirror_choice), '印版用途须明确镜像选择，待确认时不能批准。'));
  const picker = node('div', {class: 'knowledge-picker'});
  if (!state.knowledge.length) picker.append(text('p', '没有可关联知识。原创设计练习可先不关联。', 'small muted'));
  for (const knowledge of state.knowledge) picker.append(node('label', {class: 'checkbox-label'}, input('knowledge_ids', knowledge.id, {type: 'checkbox', checked: current.knowledge_ids?.includes(knowledge.id)}), node('span', {}, knowledge.title, text('span', `${knowledge.region_scope} · v${knowledge.version} · ${reviewLabels[knowledge.review_status] || knowledge.review_status}`, 'check-description'))));
  form.append(field('关联知识（可选）', picker, '关联不代表已获得商用权；审阅时重新核对可用状态。'), field('设计意图 / 修改说明', textarea('note', current.note || '', {rows: 3, placeholder: '用途、受众、文化解释与本次修改的理由'})));
  const custom = checkbox('use_custom_svg', '使用编辑后的 SVG 源码', '开启后以源码为图样；保存前由后端清洗与检查。');
  const svgCode = textarea('svg', current.svg || '', {class: 'svg-editor', spellcheck: 'false', 'aria-label': '安全 SVG 源码编辑', placeholder: '可编辑 SVG，禁止脚本、事件、外链和外部资源。'});
  form.append(node('details', {}, text('summary', '展开安全 SVG 源码编辑'), node('div', {class: 'mt-16'}, custom), svgCode), node('div', {class: 'form-actions'}, node('button', {type: 'submit', class: 'button full-width'}, isSaved ? `保存为第 ${Number(current.version) + 1} 版` : '保存第一版稿样')));
  if (isSaved) form.append(button('前往本版审阅 →', () => navigate('reviews'), 'button button-secondary full-width mt-16'));
  main.append(node('div', {class: 'design-layout'}, listPanel, previewPanel, form));
  function showSvg(svg, historical = false) {
    if (!previewSurface.isConnected) return;
    const imageUrl = URL.createObjectURL(new Blob([svg], {type: 'image/svg+xml'}));
    if (historical) { if (historicalObjectUrl) URL.revokeObjectURL(historicalObjectUrl); historicalObjectUrl = imageUrl; }
    else { if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl); previewObjectUrl = imageUrl; }
    previewSurface.replaceChildren(node('img', {src: imageUrl, alt: `${current.title || '原创木刻练习'}的 SVG 稿样预览`}));
  }
  if (current.svg) showSvg(current.svg);
  const updatePreview = async () => {
    const sequence = ++previewSequence;
    const payload = designPayload(form);
    if (!Number.isFinite(payload.width_mm) || !Number.isFinite(payload.height_mm) || payload.width_mm < 30 || payload.width_mm > 500 || payload.height_mm < 30 || payload.height_mm > 500) { previewState.textContent = '尺寸须为 30–500 mm'; return; }
    payload.title = payload.title.trim() || '未命名稿样';
    previewState.textContent = '正在检查预览…';
    try {
      const result = await api('/api/designs/preview', {method: 'POST', body: JSON.stringify(payload)});
      if (sequence !== previewSequence || !form.isConnected) return;
      if (!result.svg) throw new Error('预览未返回有效 SVG。');
      showSvg(result.svg); previewState.textContent = '实时预览 · 尚未保存';
      dimensionLabel.textContent = `${payload.width_mm} × ${payload.height_mm} mm`;
      versionSelect.value = isSaved ? String(current.version) : 'draft';
      if (!$('[name=use_custom_svg]', form).checked) svgCode.value = result.svg;
      if (isSaved) { download.textContent = `↓ 下载已保存 v${current.version}`; }
    } catch (error) {
      if (sequence !== previewSequence || !form.isConnected) return;
      previewState.textContent = '预览未更新 · 输入已保留';
      previewState.title = error.message;
      if (payload.svg) toast(error.message);
    }
  };
  form.addEventListener('input', () => { clearTimeout(previewTimer); previewTimer = setTimeout(updatePreview, 450); });
  form.addEventListener('change', () => { clearTimeout(previewTimer); previewTimer = setTimeout(updatePreview, 100); });
  versionSelect.addEventListener('change', async () => {
    if (!isSaved) return;
    clearTimeout(previewTimer); ++previewSequence;
    const version = versionSelect.value; previewState.textContent = `读取第 ${version} 版…`;
    try {
      const svg = await api(`/api/designs/${encodeURIComponent(current.id)}/svg?version=${encodeURIComponent(version)}`, {responseType: 'text'});
      if (!previewSurface.isConnected) return;
      showSvg(svg, true); previewState.textContent = Number(version) === current.version ? '已保存的当前版本' : '历史版本 · 仅预览';
      download.href = studioUrl(`/api/designs/${encodeURIComponent(current.id)}/svg?version=${encodeURIComponent(version)}`); download.textContent = `↓ 下载 v${version} SVG`;
    } catch (error) { toast(error.message); previewState.textContent = '版本读取未完成'; }
  });
  form.addEventListener('submit', event => { event.preventDefault(); submitWith(form, async () => {
    const payload = designPayload(form); if (isSaved) payload.base_version = current.version;
    const saved = await api(isSaved ? `/api/designs/${encodeURIComponent(current.id)}` : '/api/designs', {method: isSaved ? 'PUT' : 'POST', body: JSON.stringify(payload)});
    state.design = saved; state.designIsNew = false; await reloadData(); render(); toast(`稿样第 ${saved.version} 版已保存。${isSaved ? '旧审阅保留，当前版本需要重新审阅。' : '现在可以下载 SVG 或提交本版审阅。'}`, 'success');
  }); });
  if (!current.svg) setTimeout(updatePreview, 50);
}

function reviewHistory(design) {
  const card = node('section', {class: 'card card-pad review-history'}, sectionHeading('审阅留痕', badge(`${design?.reviews?.length || 0} 条`)));
  if (!design?.reviews?.length) { card.append(text('p', '尚无审阅。所有意见按图样版本保留，不自动产生工艺师身份认证。', 'history-empty')); return card; }
  [...design.reviews].reverse().forEach(review => card.append(node('article', {class: 'history-item'}, node('div', {class: 'badge-row'}, badge(review.decision === 'approve' ? '同意本版' : '请求修改', review.decision === 'approve' ? 'green' : 'red'), badge(`v${review.version}`), badge(review.version === design.version ? '当前版本意见' : '历史版本 · 不适用当前', review.version === design.version ? 'green' : 'neutral')), text('p', review.comment, 'history-comment'), text('div', `${review.reviewer_role}（本地申报岗位） · ${dateLabel(review.created_at)}`, 'history-meta'), text('div', `图样指纹：${review.design_hash || '未记录'}`, 'mono muted'))));
  return card;
}
function renderReviews(main) {
  main.append(pageHead('REVIEW & REFLECTION / 05', '每次修改，都值得留下', '审阅绑定精确图样版本。岗位由审阅者本地申报，不能视为独立核验的工艺师身份；反馈仅进入待审学习候选。'));
  if (!state.designs.length) {
    main.append(emptyState('先准备一份可审阅的稿样', '保存图样后，才能对它的文化依据、使用权利与工艺表达留下意见。', button('创建第一份稿样 →', startNewDesign))); renderCandidates(main); return;
  }
  const design = state.design;
  if (!design) { main.append(text('p', '正在读取稿样…', 'small muted')); return; }
  const choose = select('review_design', state.designs.map(item => [item.id, `${item.title} · v${item.version}`]), design.id, {'aria-label': '选择要审阅的稿样'});
  choose.addEventListener('change', async () => { try { await loadDesign(choose.value); render(); } catch (error) { toast(error.message); } });
  const surface = node('div', {class: 'preview-surface'});
  if (design.svg) {
    const url = URL.createObjectURL(new Blob([design.svg], {type: 'image/svg+xml'}));
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl); previewObjectUrl = url;
    surface.append(node('img', {src: url, alt: `待审阅稿样：${design.title}，第 ${design.version} 版`}));
  }
  const left = node('section', {}, node('div', {class: 'card review-preview'}, sectionHeading('本次审阅对象', badge(designLabels[design.status] || design.status, toneFor(design.status))), choose, surface, node('div', {class: 'review-info'}, `精确版本：v${design.version}`, `${design.width_mm} × ${design.height_mm} mm`, purposeLabels[design.purpose] || '用途待定'), text('div', `图样指纹：${design.hash}`, 'mono muted'), node('div', {class: 'form-actions'}, button('编辑稿样', () => navigate('designs'), 'button button-secondary button-small'), node('a', {class: 'button button-quiet button-small', href: studioUrl(`/api/designs/${encodeURIComponent(design.id)}/svg?version=${design.version}`), download: true}, '下载 SVG'))), reviewHistory(design));
  const form = node('form', {class: 'card review-form'});
  form.append(sectionHeading('留下本版审阅意见', badge(`v${design.version}`, 'green')), notice('请确认你实际核对过的内容', '以下确认均不默认勾选。若有缺口，可请求修改；同意本版需要三项确认、明确用途及有效关联知识。', 'neutral'), field('申报岗位 / 审阅角色 *', input('reviewer_role', '', {required: true, maxlength: 120, placeholder: '填写你的实际岗位或审阅角色'}), '仅为本地申报，不自动证明专业资质或传承人身份。'), node('div', {class: 'review-checks'}, checkbox('culture', '文化依据与表达已核对', '原创练习也需确认未被误称为传统纹样或严田史实。'), checkbox('rights', '当前使用范围与权利已核对', '核对素材来源、改编方式与本次使用许可。'), checkbox('craft', '本版工艺表达已核对', '核对用途、镜像、文字、尺寸和可编辑图样。')), field('审阅决定 *', select('decision', [['', '请选择审阅决定'], ['revise', '请求修改'], ['approve', '同意本版']], '', {required: true})), field('具体意见 *', textarea('comment', '', {required: true, rows: 5, maxlength: 6000, placeholder: '写明已核对内容、需要修改的细节，或本版可以通过的依据。'})), node('button', {type: 'submit', class: 'button full-width'}, '保存本版审阅意见'), text('p', '保存意见会产生待审学习候选，不会自动训练模型。', 'small muted mt-16'));
  form.addEventListener('submit', event => { event.preventDefault(); submitWith(form, async () => {
    const data = new FormData(form); const payload = {version: design.version, reviewer_role: data.get('reviewer_role'), decision: data.get('decision'), comment: data.get('comment'), confirmations: {culture: data.has('culture'), rights: data.has('rights'), craft: data.has('craft')}};
    const result = await api(`/api/designs/${encodeURIComponent(design.id)}/reviews`, {method: 'POST', body: JSON.stringify(payload)});
    state.design = result.design; await reloadData(); render(); toast('审阅意见已保存，精确版本与历史记录已保留。', 'success');
  }); });
  main.append(node('div', {class: 'review-layout'}, left, form)); renderCandidates(main);
}
function renderCandidates(main) {
  const card = node('section', {class: 'card card-pad feedback-list'}, sectionHeading('待审学习候选', badge(`${state.candidates.length} 条 · 未训练`, 'gold')), text('p', '来自真实审阅意见的候选记录，使用权利仍待确认。候选积累不代表训练完成。', 'small'));
  if (!state.candidates.length) card.append(text('p', '保存审阅意见后，候选会显示在这里。', 'history-empty'));
  [...state.candidates].reverse().forEach(candidate => {
    const design = state.designs.find(item => item.id === candidate.design_id);
    card.append(node('article', {class: 'candidate'}, node('div', {}, node('div', {class: 'badge-row'}, badge('待人工审阅', 'gold'), badge('训练权利未知'), text('small', `${design?.title || '关联稿样'} · v${candidate.design_version}`)), text('p', candidate.comment), text('small', `${dateLabel(candidate.created_at)} · 未进入训练`)), button('查看稿样 →', async () => { try { await loadDesign(candidate.design_id); navigate('designs'); } catch (error) { toast(error.message); } }, 'button button-quiet button-small')));
  });
  main.append(card);
}

async function render() {
  const sequence = ++routeSequence; clearTimeout(previewTimer); ++previewSequence;
  const hashRoute = location.hash.slice(1);
  const route = hashRoute === 'ask' ? 'qa' : hashRoute;
  state.route = Object.hasOwn(routes, route) ? route : 'qa';
  for (const link of document.querySelectorAll('[data-route]')) { const active = link.dataset.route === state.route; link.classList.toggle('active', active); if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current'); }
  $('#page-crumb').textContent = routes[state.route]; document.title = `${routes[state.route]} · 严田文明工作室`; closeMenu();
  if (['designs', 'reviews'].includes(state.route) && !state.design && state.designs.length && !(state.route === 'designs' && state.designIsNew)) {
    try { await loadDesign(state.designs[0].id); } catch (error) { toast(error.message); }
    if (sequence !== routeSequence) return;
  }
  const main = $('#main'); clear(main);
  ({dashboard: renderDashboard, knowledge: renderKnowledge, qa: renderAsk, designs: renderDesigns, reviews: renderReviews})[state.route](main);
}

$('#menu-toggle').addEventListener('click', () => { const open = !$('#sidebar').classList.contains('open'); $('#sidebar').classList.toggle('open', open); $('#mobile-shade').hidden = !open; $('#menu-toggle').setAttribute('aria-expanded', String(open)); syncSidebarAccessibility(); });
$('#mobile-shade').addEventListener('click', closeMenu);
window.matchMedia('(max-width: 780px)').addEventListener('change', syncSidebarAccessibility);
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
$('#editor-dialog').addEventListener('click', event => { if (event.target === $('#editor-dialog')) { const bounds = event.target.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.target.close(); } });
window.addEventListener('hashchange', () => { render(); window.scrollTo({top: 0, behavior: 'instant'}); });
window.addEventListener('beforeunload', () => { if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl); if (historicalObjectUrl) URL.revokeObjectURL(historicalObjectUrl); });
$('.export-button').href = studioUrl('/api/export');
$('#os-return').hidden = !STUDIO_BASE;
(async () => { await reloadData(); await render(); })();
