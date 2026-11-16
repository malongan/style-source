/* style-source 本地编辑器 P0 —— 原生 JS，无外部依赖 */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (v) => String(v == null ? '' : v)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

const S = {
  boot: null, styles: [], shown: 60, selected: null, detail: null,
  form: null, tab: 'basic', newImage: null, changes: [],
  checked: new Set(), importImage: null, importAnalysis: null,
  importFileName: '', batchPlan: null,
  migratePlan: null, replaceImage: null, replacePlan: null,
  normalizeScan: null, normalizePlan: null, historyRecords: [],
  releaseCheck: null,
};

/* ---------------- 访问口令（仅 --lan 模式启用） ---------------- */
const TOKEN_KEY = 'style-editor-token';
let tokenGateOpen = false;
const getToken = () => localStorage.getItem(TOKEN_KEY) || '';
function setToken(v) {
  if (v) localStorage.setItem(TOKEN_KEY, v);
  else localStorage.removeItem(TOKEN_KEY);
}

function showTokenPrompt(msg = '') {
  if (tokenGateOpen) {
    const err = $('#tokenErr');
    if (err && msg) err.textContent = msg;
    return;
  }
  tokenGateOpen = true;
  const gate = document.createElement('div');
  gate.id = 'tokenGate';
  gate.className = 'token-gate';
  gate.innerHTML = `
    <div class="token-card">
      <h2>需要访问口令</h2>
      <p>编辑器已开放局域网访问，读写操作都需要口令。<br>
      口令在启动服务的终端输出里，或本机 <code>tools/editor/.state/lan_token</code>。</p>
      <input id="tokenInput" type="password" placeholder="输入访问口令" autocomplete="off" spellcheck="false">
      <div id="tokenErr" class="token-err">${esc(msg)}</div>
      <div class="token-actions"><button id="tokenSubmit" class="btn primary">进入编辑器</button></div>
      <p class="token-hint">口令只保存在当前浏览器，不会写进仓库；换设备需重新输入。</p>
    </div>`;
  document.body.appendChild(gate);
  const input = $('#tokenInput', gate);
  const submit = async () => {
    const v = input.value.trim();
    if (!v) return;
    const btn = $('#tokenSubmit', gate);
    busy(btn, true, '验证中');
    try {
      const r = await fetch('/api/bootstrap', { headers: { 'X-Editor-Token': v } });
      if (r.status === 401) { $('#tokenErr', gate).textContent = '口令不正确，请重试'; return; }
      if (!r.ok) { $('#tokenErr', gate).textContent = '服务返回 HTTP ' + r.status; return; }
      setToken(v);
      location.reload();
    } catch (e) {
      $('#tokenErr', gate).textContent = '连接失败：' + e.message;
    } finally {
      busy(btn, false);
    }
  };
  $('#tokenSubmit', gate).addEventListener('click', submit);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') submit(); });
  setTimeout(() => input.focus(), 30);
}

function markLanMode() {
  if ($('.lan-tag')) return;
  const tag = document.createElement('span');
  tag.className = 'lan-tag';
  tag.textContent = '局域网 · 需口令';
  tag.title = '点击清除本机保存的口令';
  tag.addEventListener('click', () => { setToken(''); location.reload(); });
  $('.topbar .brand').appendChild(tag);
}

async function api(url, opts = {}) {
  const token = getToken();
  const headers = Object.assign(
    { 'Content-Type': 'application/json' },
    opts.headers || {},
    token ? { 'X-Editor-Token': token } : {});
  const res = await fetch(url, { ...opts, headers });
  const data = await res.json().catch(() => ({ error: '响应不是 JSON' }));
  if (res.status === 401 && data.need_token) {
    setToken('');
    showTokenPrompt(data.error || '请重新输入访问口令');
    throw new Error(data.error || '需要访问口令');
  }
  if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}

let toastTimer;
function toast(msg, kind = '') {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast ' + kind;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4200);
}

function busy(btn, on, text) {
  if (!btn) return;
  if (on) { btn.dataset.old = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>' + text; }
  else { btn.disabled = false; if (btn.dataset.old) btn.innerHTML = btn.dataset.old; }
}

/* ---------------- 启动与列表 ---------------- */
async function init() {
  // 启动图标会带 #t=<口令> 打开；这里吸收入口令并清掉地址栏，免手输
  const m = /[#&]t=([^&]+)/.exec(location.hash || '');
  if (m) {
    setToken(decodeURIComponent(m[1]));
    try { history.replaceState(null, '', location.pathname + location.search); } catch (e) {}
  }
  // 局域网模式先探口令状态：缺口令就拦在入口，避免整页刷 401
  try {
    const st = await fetch('/api/auth/status').then(r => r.json());
    if (st.lan) markLanMode();
    if (st.auth_required && !getToken()) { showTokenPrompt(); return; }
  } catch (e) { /* 旧版服务无此接口，按原流程继续 */ }
  try { await refreshBoot(); }
  catch (e) { toast('启动失败：' + e.message, 'err'); return; }
  await loadStyles();
  await refreshChanges();

  let t;
  $('#search').addEventListener('input', () => { clearTimeout(t); t = setTimeout(loadStyles, 180); });
  $('#category').addEventListener('change', loadStyles);
  $('#btnMore').addEventListener('click', () => { S.shown += 60; renderList(); });
  $('#btnNew').addEventListener('click', () => openNew());
  $('#btnImport').addEventListener('click', openImport);
  $('#btnDrafts').addEventListener('click', openDrafts);
  $('#btnTrash').addEventListener('click', openTrash);
  $('#btnBatch').addEventListener('click', openBatch);
  $('#btnNormalize').addEventListener('click', openNormalize);
  $('#btnMigrate').addEventListener('click', openMigrate);
  $('#btnReplaceImage').addEventListener('click', openReplaceImage);
  $('#btnRebuild').addEventListener('click', rebuild);
  $('#btnRelease').addEventListener('click', openRelease);
  $('#btnChanges').addEventListener('click', openChanges);
  $('#btnSave').addEventListener('click', save);
  $('#btnDelete').addEventListener('click', openDelete);
  $$('.tab').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));
  $('#modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); if (S.selected) save(); }
  });
  document.addEventListener('click', e => {
    const chip = e.target.closest && e.target.closest('#freshChip');
    if (chip) openFreshness();
  });
}

async function refreshBoot() {
  const b = await api('/api/bootstrap');
  S.boot = b;
  const dirty = (b.git && b.git.lines || []).length;
  const f = b.freshness || {};
  const n = (f.changed || []).length + (f.added || []).length + (f.removed || []).length;
  const chip = f.baseline
    ? (f.stale
      ? `<span id="freshChip" class="fresh bad" title="点击查看明细">生成物已过期 · ${n} 处改动</span>`
      : '<span id="freshChip" class="fresh ok" title="点击查看明细">生成物已同步</span>')
    : '<span id="freshChip" class="fresh warn" title="点击查看明细">未建立基线</span>';
  $('#status').innerHTML = `仓库 <b>${esc(b.root)}</b> · ${b.total} 个风格 · ${chip} · ` +
    (dirty ? `<span class="warn">工作区有 ${dirty} 项未提交（工具不会自动 add -A）</span>` : '工作区干净') +
    (b.sandbox ? ' · <span class="warn">沙箱模式</span>' : '');
  $('#draftCount').textContent = b.drafts || 0;
  const sel = $('#category');
  if (sel.options.length <= 1) {
    (b.categories || []).forEach(c => {
      const o = document.createElement('option'); o.value = c; o.textContent = c; sel.appendChild(o);
    });
  }
}

async function loadStyles() {
  const q = encodeURIComponent($('#search').value.trim());
  const cat = encodeURIComponent($('#category').value);
  const r = await api(`/api/styles?q=${q}&cat=${cat}`);
  S.styles = r.styles; S.shown = 60;
  renderList();
}

function renderList() {
  const box = $('#styleList');
  const slice = S.styles.slice(0, S.shown);
  $('#listMeta').textContent = `共 ${S.styles.length} 条 · 已显示 ${slice.length} 条`;
  $('#btnMore').hidden = slice.length >= S.styles.length;
  box.innerHTML = slice.map(s => {
    const thumb = s.thumb
      ? `<img class="thumb" loading="lazy" src="${esc(s.thumb.replace('https://malongan.github.io/style-source/', '/'))}">`
      : `<div class="thumb blank">无图</div>`;
    const flags = [
      s.code ? `<span class="chip">${esc(s.code)}</span>` : '<span class="chip warn">未分配编号</span>',
      s.has_image ? '' : '<span class="chip warn">缺配图</span>',
      s.errors && s.errors.length ? '<span class="chip warn">解析异常</span>' : '',
      s.legacy ? '<span class="chip warn">历史格式</span>' : '',
    ].join('');
    return `<div class="card ${S.selected === s.id ? 'active' : ''}" data-id="${esc(s.id)}">
      <input type="checkbox" class="pick" data-pick="${esc(s.id)}" ${S.checked.has(s.id) ? 'checked' : ''} title="勾选以批量编辑标签">
      ${thumb}<div class="card-txt">
      <div class="card-name">${esc(s.name)}</div>
      <div class="card-sub">${flags} ${esc(s.category)} · ${s.var_count} 变量 · ${s.prompt_len} 字</div>
      <div class="card-sub">${esc(s.id)}</div>
      </div></div>`;
  }).join('') || '<div class="empty">没有匹配的风格</div>';
  $$('.card', box).forEach(c => c.addEventListener('click', () => select(c.dataset.id)));
  $$('.pick', box).forEach(cb => {
    cb.addEventListener('click', e => e.stopPropagation());
    cb.addEventListener('change', () => {
      if (cb.checked) S.checked.add(cb.dataset.pick);
      else S.checked.delete(cb.dataset.pick);
      updatePickBtn();
    });
  });
  updatePickBtn();
}

function updatePickBtn() {
  $('#pickCount').textContent = S.checked.size;
  $('#btnBatch').hidden = S.checked.size === 0;
}

/* ---------------- 编辑 ---------------- */
async function select(id) {
  try {
    S.detail = await api('/api/style/' + encodeURIComponent(id));
    S.selected = id;
    S.form = JSON.parse(JSON.stringify(S.detail.data || {}));
    S.form.id = id;
    S.form.category = S.detail.category;
    renderList();
    renderEditor();
  } catch (e) { toast('读取失败：' + e.message, 'err'); }
}

function renderEditor() {
  $('#empty').hidden = true; $('#editor').hidden = false;
  $('#edCode').textContent = S.detail.code || '（重建后分配编号）';
  $('#edTitle').textContent = S.form.name || S.selected;
  $('#edMeta').textContent = `${S.detail.path} · 分类 ${S.detail.category} · id 与分类已锁定 · 配图 ${S.detail.images.length} 张`;
  $('#pane-basic').innerHTML = basicForm(S.form, false);
  $('#pane-features').innerHTML = featuresPane(S.form.features || []);
  $('#pane-prompt').innerHTML = promptPane(S.form.prompt || '', S.form.variables || []);
  $('#rawText').value = S.detail.text;
  $('#validateOut').textContent = '尚未校验，点「保存」后会显示校验结果';
  bindPaneEvents($('#pane-features'), $('#pane-prompt'));
  switchTab(S.tab);
  $('.workspace').scrollTop = 0;
}

function switchTab(name) {
  S.tab = name;
  $$('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $$('.pane').forEach(p => { p.hidden = p.id !== 'pane-' + name; });
}

function basicForm(d, isNew) {
  const line = (label, key, val, ph = '') =>
    `<div class="field"><label>${label}</label><input data-field="${key}" value="${esc(val || '')}" placeholder="${esc(ph)}"></div>`;
  const area = (label, key, val, rows = 3, ph = '') =>
    `<div class="field"><label>${label}</label><textarea data-field="${key}" rows="${rows}" placeholder="${esc(ph)}">${esc(val || '')}</textarea></div>`;
  const lines = v => Array.isArray(v) ? v.join('\n') : (v || '');
  const idField = isNew
    ? `<div class="grid2">${line('风格 id（snake_case，创建后不可改）', 'id', d.id || '', '如：navy_halftone_poster')}
       <div class="field"><label>分类（创建后不可改）</label><select data-field="category">${(S.boot.categories || []).map(c => `<option value="${c}" ${d.category === c ? 'selected' : ''}>${c}</option>`).join('')}</select></div></div>`
    : `<div class="hint info">身份字段：id <code>${esc(S.selected)}</code> · 分类 <code>${esc(S.detail.category)}</code> · 配图。
       它们不在表单里改，请用上方「改名 / 迁移」或「替换配图」向导，避免编号被重新分配或配图串号。</div>`;
  return idField + `<div class="grid2">
      ${line('名称 *', 'name', d.name)}
      ${line('比例', 'ratio', d.ratio, '如：2:3')}
    </div>
    ${area('一句话摘要 *', 'summary', d.summary, 3)}
    ${area('适用场景', 'scene', d.scene, 2)}
    <div class="grid2">
      ${area('标签 *（每行一个）', 'tags', lines(d.tags), 5)}
      ${area('触发词 *（每行一个）', 'triggers', lines(d.triggers), 5)}
    </div>
    <div class="grid2">
      ${line('来源链接（手工新建可留空）', 'source_url', d.source_url)}
      ${line('来源作者', 'source_author', d.source_author)}
    </div>`;
}

function featuresPane(list) {
  const items = (list || []).map((f, i) => {
    const title = typeof f === 'string' ? f : (f.title || '');
    const desc = typeof f === 'string' ? '' : (f.desc || '');
    return `<div class="item" data-feat="${i}"><div class="item-head"><span>特征 ${i + 1}</span>
      <button class="btn mini" data-del-feat="${i}">删除</button></div>
      <div class="field"><label>标题</label><input data-role="title" value="${esc(title)}"></div>
      <div class="field"><label>描述</label><textarea data-role="desc" rows="3">${esc(desc)}</textarea></div></div>`;
  }).join('');
  return `<div class="hint info">features 是 title + desc 结构，不是纯字符串数组；至少 1 条，每条 desc 会显示在详情页。</div>
    <div id="featList">${items}</div><button class="btn ghost" id="addFeat">+ 添加特征</button>`;
}

function promptPane(prompt, vars) {
  return `<div class="hint">prompt 至少 80 字。每个 <code>{槽位}</code> 都必须在下表中声明（R3），
    表里每条变量也必须逐字出现在 prompt 里（R1）。变量 ≤12 条，每条 desc 必填（R7）。</div>
    <div class="field"><label>提示词 *</label><textarea data-field="prompt" id="promptText" rows="14" style="font:12px/1.7 var(--mono)">${esc(prompt)}</textarea></div>
    <div id="slotState" class="slot-state"></div>
    <div class="section-title">变量（kv_var / style_var / desc）</div>
    <div id="varWrap">${varTable(vars)}</div>
    <div style="margin-top:10px;display:flex;gap:8px">
      <button class="btn ghost" id="addVar">+ 添加变量</button>
      <button class="btn ghost" id="insertSlot">把选中变量插入提示词</button>
    </div>`;
}

function varTable(vars) {
  const rows = (vars || []).map((v, i) => {
    const kv = typeof v === 'string' ? v : (v.kv_var || '');
    const sv = typeof v === 'string' ? ('{' + v + '}') : (v.style_var || '');
    const de = typeof v === 'string' ? '' : (v.desc || '');
    return `<tr data-var="${i}">
      <td><input data-role="kv_var" value="${esc(kv)}" placeholder="中文短名"></td>
      <td><input data-role="style_var" data-old="${esc(sv)}" value="${esc(sv)}" placeholder="{槽位}"></td>
      <td><input data-role="desc" value="${esc(de)}" placeholder="填写说明 + 示例"></td>
      <td><button class="btn mini" data-del-var="${i}">删除</button></td></tr>`;
  }).join('');
  return `<table><thead><tr><th style="width:20%">面板标签 kv_var</th><th style="width:22%">占位符 style_var</th>
    <th>填写说明 desc</th><th style="width:60px"></th></tr></thead><tbody id="varBody">${rows}</tbody></table>`;
}

/* 所有查询都限定在传入的 pane 内：编辑区和新建弹窗会同时存在同名的
   #promptText / #varBody / #slotState，用全局 document 查询会串到另一边。 */
function bindPaneEvents(featPane, promptPaneEl) {
  $('#addFeat', featPane)?.addEventListener('click', () => {
    const cur = collectFeatures(featPane); cur.push({ title: '', desc: '' });
    featPane.innerHTML = featuresPane(cur); bindPaneEvents(featPane, promptPaneEl);
  });
  $$('[data-del-feat]', featPane).forEach(b => b.addEventListener('click', () => {
    const cur = collectFeatures(featPane); cur.splice(+b.dataset.delFeat, 1);
    featPane.innerHTML = featuresPane(cur); bindPaneEvents(featPane, promptPaneEl);
  }));

  const varWrap = $('#varWrap', promptPaneEl);
  $('#addVar', promptPaneEl)?.addEventListener('click', () => {
    const cur = collectVars(promptPaneEl); cur.push({ kv_var: '', style_var: '', desc: '' });
    varWrap.innerHTML = varTable(cur); bindVarEvents(promptPaneEl); updateSlotState(promptPaneEl);
  });
  $('#insertSlot', promptPaneEl)?.addEventListener('click', () => {
    const ta = $('#promptText', promptPaneEl);
    const first = collectVars(promptPaneEl)[0];
    if (!first || !first.style_var) return toast('先填好一条变量的 style_var', 'err');
    const pos = ta.selectionStart ?? ta.value.length;
    ta.value = ta.value.slice(0, pos) + '【' + first.style_var + '】' + ta.value.slice(pos);
    updateSlotState(promptPaneEl);
  });
  $('#promptText', promptPaneEl)?.addEventListener('input', () => updateSlotState(promptPaneEl));
  bindVarEvents(promptPaneEl);
  updateSlotState(promptPaneEl);
}

function bindVarEvents(promptPaneEl) {
  $$('[data-del-var]', promptPaneEl).forEach(b => b.addEventListener('click', () => {
    const cur = collectVars(promptPaneEl);
    const removed = cur.splice(+b.dataset.delVar, 1)[0];
    const ta = $('#promptText', promptPaneEl);
    if (removed && removed.style_var && ta.value.includes(removed.style_var)) {
      ta.value = ta.value.split(removed.style_var).join('');
      toast('已同步移除 prompt 里的 ' + removed.style_var);
    }
    $('#varWrap', promptPaneEl).innerHTML = varTable(cur);
    bindVarEvents(promptPaneEl); updateSlotState(promptPaneEl);
  }));
  $$('input[data-role="style_var"]', promptPaneEl).forEach(inp => inp.addEventListener('change', () => {
    const old = inp.dataset.old;
    const now = inp.value.trim();
    if (old && now && old !== now) {
      const ta = $('#promptText', promptPaneEl);
      if (ta.value.includes(old)) {
        ta.value = ta.value.split(old).join(now);
        toast('prompt 里的占位符已同步：' + old + ' → ' + now);
      }
    }
    inp.dataset.old = now;
    updateSlotState(promptPaneEl);
  }));
  $$('#varBody input', promptPaneEl).forEach(inp =>
    inp.addEventListener('input', () => updateSlotState(promptPaneEl)));
}

function collectFeatures(scope = document) {
  return $$('#featList .item', scope).map(it => ({
    title: $('[data-role="title"]', it).value.trim(),
    desc: $('[data-role="desc"]', it).value.trim(),
  }));
}

function collectVars(scope = document) {
  return $$('#varBody tr', scope).map(tr => ({
    kv_var: $('[data-role="kv_var"]', tr).value.trim(),
    style_var: $('[data-role="style_var"]', tr).value.trim(),
    desc: $('[data-role="desc"]', tr).value.trim(),
  }));
}

function updateSlotState(promptPaneEl = document) {
  const el = $('#slotState', promptPaneEl);
  if (!el) return;
  const prompt = $('#promptText', promptPaneEl)?.value || '';
  const vars = collectVars(promptPaneEl).filter(v => v.style_var);
  const declared = new Set(vars.map(v => v.style_var.replace(/^\{|\}$/g, '')));
  const used = new Set(Array.from(prompt.matchAll(/\{([^{}\n]{1,40})\}/g), m => m[1]));
  const missing = [...declared].filter(x => !used.has(x));
  const undeclared = [...used].filter(x => !declared.has(x));
  const noDesc = vars.filter(v => !v.desc).length;
  const parts = [];
  if (missing.length) parts.push('声明了但 prompt 里没有：' + missing.map(x => '{' + x + '}').join(' '));
  if (undeclared.length) parts.push('prompt 里未声明：' + undeclared.map(x => '{' + x + '}').join(' '));
  if (noDesc) parts.push(noDesc + ' 条变量缺 desc');
  if (vars.length > 12) parts.push('变量超过 12 条');
  if (parts.length) { el.className = 'slot-state bad'; el.textContent = '⚠ ' + parts.join('；'); }
  else { el.className = 'slot-state ok'; el.textContent = `✓ ${vars.length} 条变量与 prompt 槽位对齐，desc 齐全`; }
}

function collectFields(root) {
  const out = {};
  $$('[data-field]', root).forEach(el => {
    const k = el.dataset.field;
    if (['tags', 'triggers'].includes(k)) {
      out[k] = el.value.split(/[\n,，]/).map(x => x.trim()).filter(Boolean);
    } else if (k === 'category' || k === 'id') {
      out[k] = el.value.trim();
    } else {
      out[k] = el.value;
    }
  });
  return out;
}

async function save(btn) {
  if (!S.selected) return;
  const target = btn || $('#btnSave');
  const isRaw = S.tab === 'raw';
  let body;
  if (isRaw) body = { raw: $('#rawText').value };
  else {
    const fields = collectFields($('#pane-basic'));
    fields.features = collectFeatures($('#pane-features'));
    fields.prompt = $('#promptText', $('#pane-prompt')).value;
    fields.variables = collectVars($('#pane-prompt'));
    delete fields.id; delete fields.category;   // P0 锁定
    body = { fields };
  }
  busy(target, true, '校验中…');
  try {
    const r = await api('/api/style/' + encodeURIComponent(S.selected), {
      method: 'PUT', body: JSON.stringify(body),
    });
    if (!r.ok) {
      $('#validateOut').textContent = (r.error || '') + '\n\n' + (r.validation ? JSON.stringify(r.validation, null, 2) : '');
      switchTab('validate');
      toast(r.error || '保存失败', 'err');
      return;
    }
    $('#validateOut').textContent =
      `✅ 校验通过\n\nvalidate_style (--require-desc):\n${r.validation?.validate?.output || ''}\n\nlint_hygiene (--strict):\n${r.validation?.hygiene?.output || ''}\n\n--- diff ---\n${r.diff || '（无改动）'}`;
    toast(r.changed ? '已保存，校验通过（只改了目标字段）' : '没有改动', 'ok');
    await refreshBoot(); await refreshChanges();
    await select(S.selected);
    switchTab(r.changed ? 'validate' : S.tab);
  } catch (e) { toast('保存失败：' + e.message, 'err'); }
  finally { busy(target, false); }
}

/* ---------------- 新建 ---------------- */
function openNew(prefill) {
  S.newImage = null;
  const d = Object.assign(
    { category: 'creative', tags: [], triggers: [], features: [], variables: [] },
    prefill || {});
  showModal(prefill ? '从草稿继续：' + (d.name || d.id || '未命名') : '自定义新建风格文件', `
    <div class="hint info">新建会同时生成 yaml + full/thumb 两张 WebP；编号在「重建生成物」后自动分配。
    查重会在写文件之前跑。<b>没配图也可以先「存为草稿」</b>——草稿不进 styles/，不影响校验。</div>
    <div id="newBasic">${basicForm(d, true)}</div>
    <div class="section-title">配图（正式入库必需，草稿可留空）</div>
    <div class="preview-box"><img id="newPreview" src="" alt="预览" hidden>
      <div><input type="file" id="newFile" accept="image/*"><div class="hint" style="margin-top:8px">图片会转成最长边 1000 的 WebP + 400 缩略图，文件名按 md5 前 8 位锚定。</div></div></div>
    <div class="section-title">摘要 / 提示词 / 特征 / 变量</div>
    ${promptNewPane(d.prompt || '', d.variables || [])}
    <div id="newFeat">${featuresPane(d.features || [])}</div>
    <div class="section-title">查重（写文件之前）</div>
    <div id="newDup" class="hint">尚未查重</div>
  `, [
    { label: '先查重', cls: '', fn: checkNew },
    { label: '存为草稿', cls: '', fn: saveAsDraft },
    { label: '创建', cls: 'primary', fn: create },
  ]);
  $('#newFile').addEventListener('change', ev => {
    const f = ev.target.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      S.newImage = { name: f.name, data: rd.result };
      const img = $('#newPreview'); img.src = rd.result; img.hidden = false;
    };
    rd.readAsDataURL(f);
  });
  bindPaneEvents($('#newFeat'), $('#newPrompt'));
}

function promptNewPane(prompt = '', vars = []) {
  return `<div id="newPrompt">
    <div class="field"><label>提示词 *（≥80 字）</label><textarea data-field="prompt" id="promptText" rows="10" style="font:12px/1.7 var(--mono)">${esc(prompt)}</textarea></div>
    <div id="slotState" class="slot-state"></div>
    <div class="section-title">变量</div>
    <div id="varWrap">${varTable(vars)}</div>
    <div style="margin-top:10px;display:flex;gap:8px">
      <button class="btn ghost" id="addVar">+ 添加变量</button>
      <button class="btn ghost" id="insertSlot">把选中变量插入提示词</button>
    </div></div>`;
}

function newFormData() {
  const f = collectFields($('#newBasic'));
  f.summary = $('[data-field="summary"]', $('#newBasic')).value;
  f.scene = $('[data-field="scene"]', $('#newBasic')).value;
  f.prompt = $('#promptText', $('#newPrompt')).value;
  f.variables = collectVars($('#newPrompt'));
  f.features = collectFeatures($('#newFeat'));
  return f;
}

async function checkNew(btn) {
  const f = newFormData();
  busy(btn, true, '查重中…');
  try {
    const r = await api('/api/style/check-new', {
      method: 'POST', body: JSON.stringify({ id: f.id, source_url: f.source_url, prompt: f.prompt }),
    });
    const out = Object.entries(r.checks || {}).map(([k, v]) => `[${k}] ${v.output}`).join('\n\n');
    $('#newDup').textContent = out || '无结果';
    $('#newDup').className = 'hint ' + (r.blocked ? '' : 'info');
    toast(r.blocked ? '查重命中，请勿重复创建' : '查重通过', r.blocked ? 'err' : 'ok');
  } catch (e) { toast('查重失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

async function create(btn) {
  const style = newFormData();
  if (!style.id) return toast('先填 id', 'err');
  if (!S.newImage) return toast('先上传 1 张配图', 'err');
  busy(btn, true, '创建中…');
  try {
    const r = await api('/api/style', {
      method: 'POST', body: JSON.stringify({ style, image: S.newImage }),
    });
    if (!r.ok) {
      const msg = r.error || (r.errors || []).join('\n');
      toast(msg, 'err');
      $('#newDup').textContent = msg + (r.checks ? '\n\n' + JSON.stringify(r.checks, null, 2) : '');
      return;
    }
    toast('创建成功：' + r.id + '，记得点「重建生成物」', 'ok');
    closeModal();
    await refreshBoot(); await loadStyles(); await refreshChanges();
    await select(r.id);
  } catch (e) { toast('创建失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

/* ---------------- P1：草稿 / 导入 / 批量 / 回收区 / 新鲜度 ---------------- */
async function saveAsDraft(btn) {
  const style = newFormData();
  busy(btn, true, '保存中…');
  try {
    const r = await api('/api/draft', {
      method: 'POST', body: JSON.stringify({ id: style.id || '', style }),
    });
    if (!r.ok) return toast(r.error || '保存失败', 'err');
    toast('草稿已保存：' + r.id + '（不进 styles/，无需配图）', 'ok');
    closeModal(); await refreshBoot();
  } catch (e) { toast('保存草稿失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

function bindImagePicker(fileId, previewId, key) {
  const input = $(fileId), img = $(previewId);
  if (!input) return;
  input.addEventListener('change', ev => {
    const f = ev.target.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      S[key] = { name: f.name, data: rd.result };
      if (img) { img.src = rd.result; img.hidden = false; }
    };
    rd.readAsDataURL(f);
  });
}

/* ---- 导入现成 YAML ---- */
function openImport() {
  S.importImage = null; S.importAnalysis = null; S.importFileName = '';
  const cats = (S.boot.categories || []).map(c => `<option value="${c}">${c}</option>`).join('');
  showModal('导入现成 YAML 文件', `
    <div class="hint info">先解析并<b>在写文件之前查重</b>，再补 1 张配图正式入库。
    「规范化」按本库模板重渲染（推荐，校验最稳）；「保真」保留原文注释与字段顺序，只改 id / 分类 / 配图注释。</div>
    <div class="grid2">
      <div class="field"><label>选择 .yaml 文件</label><input type="file" id="importFile" accept=".yaml,.yml,.txt"></div>
      <div class="field"><label>文件名（自动填，用于推断 id）</label><input id="importFilename" placeholder="可留空"></div>
    </div>
    <div class="field"><label>YAML 全文（也可直接粘贴）</label>
      <textarea id="importYaml" class="raw" style="min-height:200px" spellcheck="false" placeholder="把 .yaml 内容粘贴到这里"></textarea></div>
    <div class="grid2">
      <div class="field"><label>导入方式</label><select id="importMode">
        <option value="normalized">规范化（按本库模板重渲染，推荐）</option>
        <option value="faithful">保真（保留原文与注释）</option></select></div>
      <div class="field"><label>覆盖 id（可选）</label><input id="importId" placeholder="留空则用文件内 id 或文件名"></div>
    </div>
    <div class="field"><label>覆盖分类（可选）</label><select id="importCat"><option value="">用文件内 category</option>${cats}</select></div>
    <div class="section-title">配图（正式入库必需）</div>
    <div class="preview-box"><img id="importPreview" src="" alt="预览" hidden>
      <div><input type="file" id="importImageFile" accept="image/*">
        <div class="hint" style="margin-top:8px">与新建一致：md5 前 8 位锚定，生成 full + thumb 两张 WebP。</div></div></div>
    <div class="section-title">检查结果</div>
    <div id="importResult" class="hint">尚未检查</div>
  `, [
    { label: '检查', cls: '', fn: importCheck },
    { label: '导入', cls: 'primary', fn: importCommit },
    { label: '关闭', cls: '', fn: closeModal },
  ]);
  $('#importFile').addEventListener('change', ev => {
    const f = ev.target.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      $('#importYaml').value = rd.result;
      $('#importFilename').value = f.name;
      S.importFileName = f.name;
      toast('已读入 ' + f.name + '，点「检查」', 'ok');
    };
    rd.readAsText(f);
  });
  bindImagePicker('#importImageFile', '#importPreview', 'importImage');
}

function importFormData() {
  return {
    text: $('#importYaml').value,
    filename: $('#importFilename').value,
    mode: $('#importMode').value,
    id: $('#importId').value.trim(),
    category: $('#importCat').value,
  };
}

function renderImportResult(r) {
  const s = r.summary || {};
  const dup = r.dup || {};
  const dupOut = Object.entries(dup.checks || {}).map(([k, v]) => `[${k}] ${v.output}`).join('\n');
  const errHtml = (r.errors || []).length
    ? `<div class="hint"><b>阻断项（${r.errors.length}）</b><br>${r.errors.map(esc).join('<br>')}</div>` : '';
  const warnHtml = (r.warnings || []).length
    ? `<div class="hint info"><b>提示（${r.warnings.length}）</b><br>${r.warnings.map(esc).join('<br>')}</div>` : '';
  $('#importResult').innerHTML = `
    ${errHtml}${warnHtml}
    <div class="hint ${r.ok && !dup.blocked ? 'info' : ''}">解析结果：
      <code>${esc(r.id || '—')}</code> / <code>${esc(r.category || '—')}</code> ·
      ${esc(s.name || '未命名')} · prompt ${s.prompt_len} 字 ·
      tags ${s.tags} / triggers ${s.triggers} / features ${s.features} / variables ${s.variables}<br>
      查重：<b>${dup.blocked ? '命中，禁止导入' : '通过'}</b></div>
    ${dupOut ? `<pre class="pre" style="max-height:150px">${esc(dupOut)}</pre>` : ''}
    <div class="section-title">候选文本预览（${esc(r.mode === 'faithful' ? '保真' : '规范化')}）</div>
    <pre class="pre" style="max-height:260px">${esc((r.candidate || '').slice(0, 4000))}</pre>`;
}

async function importCheck(btn) {
  const f = importFormData();
  if (!f.text.trim()) return toast('先选文件或粘贴 YAML', 'err');
  busy(btn, true, '解析与查重中…');
  try {
    const r = await api('/api/import/check', { method: 'POST', body: JSON.stringify(f) });
    S.importAnalysis = r;
    renderImportResult(r);
    toast(r.ok ? '检查通过，可以导入' : '检查未通过，请看阻断项', r.ok ? 'ok' : 'err');
  } catch (e) { toast('检查失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

async function importCommit(btn) {
  if (!S.importImage) return toast('导入必须上传 1 张配图', 'err');
  const f = importFormData();
  if (!f.text.trim()) return toast('先选文件或粘贴 YAML', 'err');
  busy(btn, true, '导入中…');
  try {
    const r = await api('/api/import/commit', {
      method: 'POST', body: JSON.stringify(Object.assign({}, f, { image: S.importImage })),
    });
    if (!r.ok) {
      const msg = r.error || (r.errors || []).join('\n');
      toast(msg, 'err');
      $('#importResult').innerHTML = `<div class="hint"><b>导入失败</b><br>${esc(msg)}</div>` +
        (r.errors || []).map(esc).join('<br>');
      return;
    }
    toast('导入成功：' + r.id + '，记得点「重建生成物」', 'ok');
    closeModal();
    await refreshBoot(); await loadStyles(); await refreshChanges();
    await select(r.id);
  } catch (e) { toast('导入失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

/* ---- 草稿箱 ---- */
async function openDrafts() {
  const r = await api('/api/drafts');
  const items = r.drafts.map(d => `<div class="change-item">
    <b>${esc(d.name)}</b> <span style="color:var(--muted)">${esc(d.id)} · ${esc(d.category || '未选分类')} · prompt ${d.prompt_len} 字 · ${esc(d.saved_at)}</span>
    <div style="margin-top:7px;display:flex;gap:6px">
      <button class="btn mini" data-draft-load="${esc(d.id)}">载入新建向导</button>
      <button class="btn mini" data-draft-pub="${esc(d.id)}">补全配图并入库</button>
      <button class="btn mini" data-draft-del="${esc(d.id)}">删除草稿</button>
    </div></div>`).join('') || '<p class="hint info">草稿箱为空。在「新建风格」里点「存为草稿」即可，不需要配图。</p>';
  showModal('草稿箱（无图 · 不参与校验）', `
    <div class="hint info">草稿存在 <code>tools/editor/.drafts/</code>（已 gitignore），不在 styles/ 里，
    所以 preflight / CI 完全看不到它。补全配图后才会走与新建一样的查重与校验链路。</div>${items}`,
    [{ label: '关闭', cls: 'primary', fn: closeModal }]);
  $$('[data-draft-load]').forEach(b => b.addEventListener('click', async () => {
    const d = await api('/api/draft/' + encodeURIComponent(b.dataset.draftLoad));
    openNew(d.style || {});
  }));
  $$('[data-draft-pub]').forEach(b => b.addEventListener('click', () => draftPublish(b.dataset.draftPub)));
  $$('[data-draft-del]').forEach(b => b.addEventListener('click', async () => {
    const r = await api('/api/draft/' + encodeURIComponent(b.dataset.draftDel), { method: 'DELETE' });
    toast(r.ok ? '草稿已删除' : r.error, r.ok ? 'ok' : 'err');
    await refreshBoot(); openDrafts();
  }));
}

function draftPublish(id) {
  S.publishImage = null;
  showModal('补全配图并入库：' + id, `
    <div class="hint info">选 1 张图后会走与「新建」完全相同的链路：写文件前查重 → 转 WebP →
    validate_style + lint_hygiene 校验 → 落盘；成功后草稿自动删除，失败整体回滚。</div>
    <div class="preview-box"><img id="publishPreview" src="" alt="预览" hidden>
      <div><input type="file" id="publishFile" accept="image/*"></div></div>
    <div id="publishResult" class="hint">尚未入库</div>`, [
    { label: '返回草稿箱', cls: '', fn: openDrafts },
    { label: '正式入库', cls: 'primary', fn: btn => draftPublishDo(btn, id) },
  ]);
  bindImagePicker('#publishFile', '#publishPreview', 'publishImage');
}

async function draftPublishDo(btn, id) {
  if (!S.publishImage) return toast('先选 1 张配图', 'err');
  busy(btn, true, '入库中…');
  try {
    const r = await api('/api/draft/' + encodeURIComponent(id) + '/publish', {
      method: 'POST', body: JSON.stringify({ image: S.publishImage }),
    });
    if (!r.ok) {
      const msg = r.error || (r.errors || []).join('\n');
      $('#publishResult').textContent = msg;
      return toast(msg, 'err');
    }
    toast('草稿已入库：' + r.id, 'ok');
    closeModal();
    await refreshBoot(); await loadStyles(); await refreshChanges();
    await select(r.id);
  } catch (e) { toast('入库失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

/* ---- 回收区 ---- */
async function openTrash() {
  const r = await api('/api/trash');
  const items = r.batches.map(b => `<div class="change-item">
    <b>${esc(b.batch)}</b> <span style="color:var(--muted)">${esc(b.style_id)} · ${esc(b.code || '未分配')} ·
    ${b.moved.length} 个文件 · ${esc(b.time)}</span>
    <div style="margin-top:7px;display:flex;gap:6px">
      <button class="btn mini" data-trash-show="${esc(b.batch)}">详情</button>
      <button class="btn mini" data-trash-restore="${esc(b.batch)}">一键还原</button>
      <button class="btn mini" data-trash-purge="${esc(b.batch)}">彻底删除</button>
    </div></div>`).join('') || '<p class="hint info">回收区为空</p>';
  showModal('回收区', `
    <div class="hint info">删除时不 rm，而是把 yaml + 配图移进 <code>tools/editor/.trash/&lt;批次&gt;/</code>
    并写 manifest。还原会把文件移回原位并恢复时间戳条目；彻底删除不可撤销（Git 仍是最后一道保险）。</div>${items}`,
    [{ label: '关闭', cls: 'primary', fn: closeModal }]);
  $$('[data-trash-show]').forEach(b => b.addEventListener('click', () => trashShow(b.dataset.trashShow)));
  $$('[data-trash-restore]').forEach(b => b.addEventListener('click', () => trashRestore(b.dataset.trashRestore)));
  $$('[data-trash-purge]').forEach(b => b.addEventListener('click', () => trashPurgeConfirm(b.dataset.trashPurge)));
}

async function trashShow(batch) {
  const d = await api('/api/trash/' + encodeURIComponent(batch));
  const files = (d.moved || []).map(m => `${m.from} → ${m.to}`).join('\n');
  showModal('批次详情：' + batch, `
    <div class="hint info">${esc(d.note || '')}</div>
    <ul class="impact-list">
      <li>风格：<code>${esc(d.style_id)}</code> / <code>${esc(d.code || '未分配')}</code></li>
      <li>删除时间：<code>${esc(d.time)}</code></li>
      <li>仍在回收区的文件：<b>${d.files_present}/${(d.moved || []).length}</b></li>
      <li>时间戳条目：${d.timestamp ? '<code>' + esc(d.timestamp) + '</code>' : '无'}</li>
    </ul>
    <div class="section-title">移走的文件</div><pre class="pre" style="max-height:180px">${esc(files)}</pre>
    <div class="section-title">yaml 原文</div><pre class="pre" style="max-height:300px">${esc((d.yaml_text || '').slice(0, 6000))}</pre>`, [
    { label: '返回回收区', cls: '', fn: openTrash },
    { label: '一键还原', cls: 'primary', fn: () => trashRestore(batch) },
  ]);
}

async function trashRestore(batch) {
  const r = await api('/api/restore', { method: 'POST', body: JSON.stringify({ batch }) });
  toast(r.ok ? '已还原 ' + r.restored.length + ' 个文件' : r.error, r.ok ? 'ok' : 'err');
  if (!r.ok) return;
  closeModal();
  await refreshBoot(); await loadStyles(); await refreshChanges();
}

async function trashPurgeConfirm(batch) {
  const d = await api('/api/trash/' + encodeURIComponent(batch));
  showModal('⚠ 彻底删除批次', `
    <div class="hint"><b>此操作不可撤销。</b>将永久删除回收批次 <code>${esc(batch)}</code>
    下的 ${d.files_present} 个文件与 manifest。若该删除尚未提交到 Git，仍可用 git 找回。</div>
    <pre class="pre" style="max-height:200px">${esc((d.moved || []).map(m => m.to).join('\n'))}</pre>`, [
    { label: '取消，返回回收区', cls: '', fn: openTrash },
    { label: '确认彻底删除', cls: 'danger', fn: async btn => {
      busy(btn, true, '删除中…');
      try {
        const r = await api('/api/trash/' + encodeURIComponent(batch) + '?confirm=1', { method: 'DELETE' });
        toast(r.ok ? '批次已彻底删除' : r.error, r.ok ? 'ok' : 'err');
        await refreshChanges(); openTrash();
      } catch (e) { toast('删除失败：' + e.message, 'err'); }
      finally { busy(btn, false); }
    } },
  ]);
}

/* ---- 批量标签编辑 ---- */
function openBatch() {
  const ids = [...S.checked];
  if (!ids.length) return toast('先在左侧勾选风格', 'err');
  S.batchPlan = null;
  showModal(`批量编辑（已选 ${ids.length} 条）`, `
    <div class="hint info">只改 <code>tags</code> 或 <code>triggers</code> 一个字段，其他字段、
    注释与 prompt 一律保持原样；列表项会跟随各文件原有的引号写法（无引号 / 双引号），
    所以正常情况下 diff 只增删必要的行。应用前会跑一次全库
    <code>validate_all --strict --require-desc</code> 与 <code>lint_hygiene --strict</code>，
    任一失败整体回滚。</div>
    <div class="grid2">
      <div class="field"><label>字段</label><select id="batchField">
        <option value="tags">tags 标签</option><option value="triggers">triggers 触发词</option></select></div>
      <div class="field"><label>动作</label><select id="batchAction">
        <option value="add">追加值（自动去重）</option>
        <option value="remove">删除指定值</option>
        <option value="replace_all">整体替换为这些值</option>
        <option value="replace_value">把某个值替换成另一个值</option></select></div>
    </div>
    <div class="field"><label>值（每行一个；「替换某个值」时第 1 行=原值、第 2 行=新值）</label>
      <textarea id="batchValues" rows="4" placeholder="例如：复古"></textarea></div>
    <div class="hint">已选：${esc(ids.slice(0, 8).join('、'))}${ids.length > 8 ? ' 等 ' + ids.length + ' 条' : ''}</div>
    <div class="section-title">预览</div><div id="batchResult" class="hint">尚未预览</div>`, [
    { label: '预览 diff', cls: '', fn: batchPreview },
    { label: '应用到磁盘', cls: 'primary', fn: batchApply },
    { label: '清空选择', cls: '', fn: () => { S.checked.clear(); updatePickBtn(); closeModal(); } },
  ]);
}

function batchParams(dry) {
  return {
    ids: [...S.checked],
    field: $('#batchField').value,
    action: $('#batchAction').value,
    values: $('#batchValues').value.split(/[\n,，]/).map(x => x.trim()).filter(Boolean),
    dry_run: dry,
  };
}

function renderBatchResult(r) {
  const plans = r.plans || [];
  const diffs = plans.map(p => `<div class="change-item"><b>${esc(p.id)}</b>
    <span style="color:var(--muted)">${esc(p.path)}</span>
    <pre class="pre" style="max-height:150px;margin-top:6px">${esc(p.diff)}</pre></div>`).join('');
  $('#batchResult').innerHTML = `
    <div class="hint ${r.ok ? 'info' : ''}">${r.rolled_back ? '<b>校验失败，已全部回滚</b><br>' : ''}
      ${esc(r.error || '')} ${r.note ? esc(r.note) : ''}<br>
      选中 ${r.selected || r.changed || plans.length} 条 · 将改动 <b>${plans.length}</b> 条 ·
      跳过 ${(r.skipped || []).length} 条（值没变化）</div>
    ${(r.errors || []).length ? `<div class="hint">${r.errors.map(esc).join('<br>')}</div>` : ''}
    ${diffs || '<p class="hint">没有任何字段会变化</p>'}
    ${r.validation ? `<pre class="pre" style="max-height:160px">${esc((r.validation.validate_all?.output || '') + '\n' + (r.validation.lint_hygiene?.output || ''))}</pre>` : ''}`;
}

async function batchPreview(btn) {
  busy(btn, true, '计算中…');
  try {
    const r = await api('/api/batch/tags', { method: 'POST', body: JSON.stringify(batchParams(true)) });
    S.batchPlan = r;
    renderBatchResult(r);
    toast(r.ok ? `预览完成：${(r.plans || []).length} 条会变化` : r.error, r.ok ? 'ok' : 'err');
  } catch (e) { toast('预览失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

async function batchApply(btn) {
  if (!S.batchPlan) return toast('先点「预览 diff」', 'err');
  busy(btn, true, '写入与全库校验中…');
  try {
    const r = await api('/api/batch/tags', { method: 'POST', body: JSON.stringify(batchParams(false)) });
    renderBatchResult(r);
    if (!r.ok) return toast(r.error || '应用失败，已回滚', 'err');
    toast(`已改动 ${r.changed} 条，全库校验通过`, 'ok');
    S.checked.clear(); updatePickBtn();
    await refreshBoot(); await loadStyles(); await refreshChanges();
  } catch (e) { toast('应用失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

/* ---- 生成物过期状态 ---- */
async function openFreshness() {
  const f = await api('/api/freshness');
  const files = [...(f.changed || []), ...(f.added || []), ...(f.removed || [])];
  showModal('生成物状态', `
    <div class="hint ${f.stale ? '' : 'info'}">${esc(f.note || '')}</div>
    <ul class="impact-list">
      <li>基线：${f.baseline ? '已建立 · ' + esc(f.snapshot_time) : '未建立（按文件修改时间粗判）'}</li>
      <li>yaml 总数：${f.total}</li>
      <li>新增 ${(f.added || []).length} · 删除 ${(f.removed || []).length} · 修改 ${(f.changed || []).length}</li>
    </ul>
    <div class="section-title">变动文件</div>
    <div class="paths" style="font:11px/1.8 var(--mono);color:var(--muted)">${files.map(esc).join('<br>') || '（无）'}</div>`, [
    { label: '标记为已同步', cls: '', fn: async btn => {
      busy(btn, true, '写基线…');
      try {
        await api('/api/freshness/snapshot', { method: 'POST', body: '{}' });
        toast('已写入内容基线', 'ok'); closeModal(); await refreshBoot();
      } catch (e) { toast('失败：' + e.message, 'err'); }
      finally { busy(btn, false); }
    } },
    { label: '重建生成物', cls: 'primary', fn: rebuild },
  ]);
}

/* ---------------- 删除 / 回收区 / 变更中心 ---------------- */
async function openDelete() {
  if (!S.selected) return;
  const imp = await api('/api/impact/' + encodeURIComponent(S.selected) + '?dry_run=1');
  const i = imp.impact;
  showModal('删除风格：' + S.selected, `
    <div class="hint">yaml 与配图会一起移入回收区（可一键还原）；时间戳条目会清理；
    编号 <b>不回收</b>，避免旧链接指向新风格。生成物需在删除后点「重建」。</div>
    <ul class="impact-list">
      <li>源文件：<code>${esc(i.yaml)}</code></li>
      <li>配图 ${i.images.length} 张：${i.images.map(x => '<code>' + esc(x) + '</code>').join(' ')}</li>
      <li>时间戳条目：${i.timestamp_entry ? '有，将清理' : '无'}</li>
      <li>编号：<code>${esc(i.code || '未分配')}</code>（保留空洞，不重用）</li>
      <li>生成物需重建：${i.generated.length} 个文件（styles.json / gallery / 索引等）</li>
      <li>线上链接将失效：<code>${esc(i.online_url || '—')}</code></li>
    </ul>`, [
    { label: '取消', cls: '', fn: closeModal },
    { label: '确认删除并移入回收区', cls: 'danger', fn: doDelete },
  ]);
}

async function doDelete(btn) {
  busy(btn, true, '处理中…');
  try {
    const r = await api('/api/style/' + encodeURIComponent(S.selected) + '?dry_run=0', { method: 'DELETE' });
    if (!r.ok) return toast(r.error, 'err');
    toast('已移入回收区：' + r.batch, 'ok');
    closeModal();
    S.selected = null; S.detail = null;
    $('#editor').hidden = true; $('#empty').hidden = false;
    await refreshBoot(); await loadStyles(); await refreshChanges();
  } catch (e) { toast('删除失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

/* ---------------- 发布前检查（纯只读） ---------------- */
async function openRelease() {
  let r;
  try { r = await api('/api/release/check'); }
  catch (e) { return toast('发布检查失败：' + e.message, 'err'); }
  S.releaseCheck = r;
  const lv = { ok: '已就绪', warn: '注意', fail: '待处理', info: '说明' };
  const checks = r.checks.map(c => `<div class="rel-item">
      <span class="rel-level ${c.level}">${lv[c.level] || esc(c.level)}</span>
      <div class="rel-text"><b>${esc(c.title)}</b>
        ${c.detail ? `<div class="rel-detail">${esc(c.detail)}</div>` : ''}
        ${c.action ? `<div class="rel-action">建议：${esc(c.action)}</div>` : ''}
      </div></div>`).join('');
  const paths = (title, arr) => `<div class="section-title">${esc(title)}（${arr.length}）</div>
    <div class="rel-paths">${arr.length ? arr.map(esc).join('<br>') : '（无）'}</div>`;
  const cmds = r.commands.map((s, i) => `
    <div class="section-title">${esc(s.title)}</div>
    <pre class="cmd rel-cmd">${esc(s.cmd)}</pre>
    ${s.note ? `<div class="rel-note">${esc(s.note)}</div>` : ''}
    <button class="btn mini" data-copyrel="${i}">复制此步</button>`).join('');
  const g = r.git;
  const summary = `<div class="rel-summary ${r.ready ? 'ok' : 'fail'}">
      <b>${esc(r.summary)}</b>
      <div>分支 ${esc(g.branch)} · HEAD ${esc(g.head)} · 落后 ${g.behind} / 领先 ${g.ahead} ·
      本次会话 ${r.session_changes} 次写操作 · 生成物 ${r.freshness.stale ? '已过期' : '已同步'}</div>
    </div>`;
  showModal('发布前检查', `
    ${summary}
    <div class="hint info">${esc(r.note)}</div>
    <div class="section-title">检查项（${r.counts.ok} 就绪 / ${r.counts.warn} 注意 / ${r.counts.fail} 待处理）</div>
    ${checks}
    ${paths('待提交源文件', r.groups.source)}
    ${paths('生成物改动', r.groups.generated)}
    ${paths('其它改动 / 未跟踪（不进建议命令）', r.groups.other)}
    <div class="section-title">建议命令 · 按顺序自行复制执行</div>
    <div style="margin-bottom:10px"><button class="btn mini" id="copyAllRel">复制全部命令</button></div>
    ${cmds}
  `, [
    { label: '关闭', cls: '', fn: closeModal },
    { label: '重新检查', cls: '', fn: openRelease },
    { label: '重建生成物', cls: 'primary', fn: rebuild },
  ]);
  $$('[data-copyrel]').forEach(b => b.addEventListener('click', () => {
    const i = +b.dataset.copyrel;
    navigator.clipboard.writeText(r.commands[i].cmd)
      .then(() => toast('已复制第 ' + (i + 1) + ' 步', 'ok'));
  }));
  $('#copyAllRel').addEventListener('click', () => {
    const all = r.commands.map(s => '# ' + s.title + '\n' + s.cmd).join('\n\n');
    navigator.clipboard.writeText(all).then(() => toast('已复制全部命令', 'ok'));
  });
}

async function refreshChanges() {
  try {
    const r = await api('/api/changes');
    S.changes = r.changes;
    $('#changeCount').textContent = r.changes.length;
  } catch (e) { /* ignore */ }
}

async function openChanges() {
  await refreshChanges();
  const trash = await api('/api/trash');
  const items = S.changes.map((c, i) => `<div class="change-item">
    <span class="op">${esc(c.op)}</span><b>${esc(c.id || '—')}</b> <span style="color:var(--muted)">${esc(c.time)}</span>
    <div class="paths">${c.paths.map(esc).join('<br>')}</div></div>`).join('') || '<p class="hint info">本次会话还没有改动</p>';
  const batches = trash.batches.map(b => `<div class="change-item"><b>${esc(b.batch)}</b>
    <span style="color:var(--muted)">${esc(b.style_id)} · ${b.moved.length} 个文件</span>
    <div style="margin-top:6px"><button class="btn mini" data-restore="${esc(b.batch)}">一键还原</button></div></div>`).join('') || '<p class="hint info">回收区为空</p>';
  const allPaths = [...new Set(S.changes.flatMap(c => c.paths))];
  const cmd = allPaths.length ? 'git add ' + allPaths.join(' ') : '# 本次会话无改动';
  showModal('变更中心', `
    <div class="hint info">工具不会自动 git add -A / commit / push。下面是本次会话产生的精确路径；
    「重建生成物」后再把这些生成物一起加入提交。</div>
    <div class="section-title">本次会话操作</div>${items}
    <div class="section-title">建议的暂存命令（按需复制）</div>
    <div class="cmd" id="gitCmd">${esc(cmd)}</div>
    <div style="margin-top:8px"><button class="btn mini" id="copyCmd">复制命令</button></div>
    <div class="section-title">回收区（可还原）</div>${batches}
    <div class="section-title">生成物清单</div>
    <div class="paths" style="font:11px/1.8 var(--mono);color:var(--muted)">${(await api('/api/changes')).generated.map(esc).join('<br>')}</div>
  `, [
    { label: '历史对比', cls: '', fn: openHistory },
    { label: '发布检查', cls: '', fn: openRelease },
    { label: '关闭', cls: '', fn: closeModal },
    { label: '重建生成物', cls: 'primary', fn: rebuild },
  ]);
  $('#copyCmd').addEventListener('click', () => {
    navigator.clipboard.writeText($('#gitCmd').textContent).then(() => toast('已复制', 'ok'));
  });
  $$('[data-restore]').forEach(b => b.addEventListener('click', async () => {
    const r = await api('/api/restore', { method: 'POST', body: JSON.stringify({ batch: b.dataset.restore }) });
    toast(r.ok ? '已还原 ' + r.restored.length + ' 个文件' : r.error, r.ok ? 'ok' : 'err');
    if (!r.ok) return;
    closeModal(); await refreshBoot(); await loadStyles(); await refreshChanges();
  }));
}

async function rebuild(btn) {
  busy(btn, true, '跑 9 项闸门…');
  try {
    const r = await api('/api/rebuild', { method: 'POST', body: '{}' });
    toast(r.ok ? '重建完成，preflight 全绿' : '重建有问题，请看输出', r.ok ? 'ok' : 'err');
    showModal('重建生成物 · preflight 输出', `<pre class="pre">${esc(r.output || '')}</pre>`,
      [{ label: '关闭', cls: 'primary', fn: closeModal }]);
    await refreshBoot(); await loadStyles(); await refreshChanges();
  } catch (e) { toast('重建失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

/* ---------------- P2：改名迁移 / 替换配图 / 格式体检 / 历史对比 ---------------- */

/* ---- 改名 / 改分类迁移向导 ---- */
function openMigrate() {
  if (!S.selected) return toast('先在左侧选一个风格', 'err');
  S.migratePlan = null;
  const cats = (S.boot.categories || []).map(c =>
    `<option value="${c}" ${c === S.detail.category ? 'selected' : ''}>${c}</option>`).join('');
  showModal('改名 / 改分类迁移：' + S.selected, `
    <div class="hint info">这是一次「身份迁移」，不是改一个字段：yaml 路径与 id/category、
      <code># 配图</code> 注释、2 张配图的文件名前缀、<code>style_numbers.json</code> 与
      <code>style_timestamps.json</code> 的 key 会一起改，<b>编号随 key 保留</b>。
      先出完整影响面，再原子应用；任一校验失败整体回滚。改完必须点「重建生成物」。</div>
    <div class="grid2">
      <div class="field"><label>新 id（snake_case）</label><input id="mgNewId" value="${esc(S.selected)}"></div>
      <div class="field"><label>新分类</label><select id="mgNewCat">${cats}</select></div>
    </div>
    <div class="section-title">影响面预览</div>
    <div id="mgResult" class="hint">填好新 id / 分类后点「检查影响面」</div>`, [
    { label: '检查影响面', cls: '', fn: migrateCheck },
    { label: '取消', cls: '', fn: closeModal },
    { label: '应用到磁盘', cls: 'primary', fn: migrateApply },
  ]);
}

function migrateParams() {
  return {
    id: S.selected,
    new_id: $('#mgNewId').value.trim(),
    new_category: $('#mgNewCat').value,
  };
}

function renderMigrate(r) {
  const errs = (r.errors || []).length
    ? `<div class="hint"><b>阻断项</b><br>${r.errors.map(esc).join('<br>')}</div>` : '';
  const warns = (r.warnings || []).length
    ? `<div class="hint info"><b>提示</b><br>${r.warnings.map(esc).join('<br>')}</div>` : '';
  const o = r.old || {}, n = r.new || {}, meta = r.metadata || {};
  const renames = (r.renames || []).map(x =>
    `<li><code>${esc(x.from)}</code> → <code>${esc(x.to)}</code></li>`).join('');
  $('#mgResult').innerHTML = `${errs}${warns}
    <div class="hint ${r.ok ? 'info' : ''}">${r.ok ? '✓ 检查通过，可以应用' : '检查未通过，请看上方阻断项'}</div>
    <ul class="impact-list">
      <li>yaml：<code>${esc(o.path)}</code> → <code>${esc(n.path)}</code></li>
      <li>编号：<b>${esc(o.code || '未分配')}</b> → 保持不变${meta.kept_number ? '（key 迁移）' : ''}</li>
      <li>线上链接：<code>${esc(r.online_url || '—')}</code>（保号后仍有效）</li>
      <li>配图重命名：${(r.renames || []).length} 张</li>
      <li>元数据 key 迁移：style_numbers ${meta.numbers ? '是' : '否'} ·
        style_timestamps ${meta.timestamps ? '是' : '否'}</li>
      <li>生成物需重建：${(r.generated || []).length} 个文件</li>
    </ul>
    ${renames ? `<div class="pre" style="max-height:150px"><ul class="impact-list">${renames}</ul></div>` : ''}
    <div class="section-title">yaml 差异</div>
    <pre class="pre" style="max-height:260px">${esc(r.yaml_diff || '（无）')}</pre>
    <div class="hint">${esc(r.note || '')}</div>`;
}

async function migrateCheck(btn) {
  busy(btn, true, '计算中…');
  try {
    const r = await api('/api/migrate/check', { method: 'POST', body: JSON.stringify(migrateParams()) });
    S.migratePlan = r;
    renderMigrate(r);
    toast(r.ok ? '影响面检查通过' : '检查未通过', r.ok ? 'ok' : 'err');
  } catch (e) { toast('检查失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

function migrateApply() {
  const r = S.migratePlan;
  if (!r || !r.ok) return toast('先点「检查影响面」并通过', 'err');
  const p = migrateParams();
  showModal('确认迁移', `
    <div class="hint"><b>${esc(p.id)} → ${esc(p.new_id)}</b>（${esc(r.old.category)} → ${esc(p.new_category)}）<br>
    将改动 ${(r.renames || []).length + 2} 个源文件 + ${Object.values(r.metadata || {}).filter(Boolean).length ? '元数据 key' : '无元数据'}，
    编号 <b>${esc(r.old.code || '未分配')}</b> 保持不变。失败会自动整体回滚。</div>
    <div class="hint info">${esc(r.note || '')}</div>`, [
    { label: '返回向导', cls: '', fn: openMigrate },
    { label: '确认迁移', cls: 'primary', fn: async btn => {
      busy(btn, true, '迁移与校验中…');
      try {
        const out = await api('/api/migrate/commit', { method: 'POST', body: JSON.stringify(p) });
        if (!out.ok) {
          toast(out.error || '迁移失败', 'err');
          $('#modalBox .modal-body').innerHTML =
            `<div class="hint"><b>迁移失败${out.rolled_back ? '，已整体回滚' : ''}</b><br>${esc(out.error || '')}</div>`;
          return;
        }
        toast(`已迁移到 ${out.new_id}，编号 ${r.old.code} 保留；请重建生成物`, 'ok');
        closeModal();
        await refreshBoot(); await loadStyles(); await refreshChanges();
        await select(out.new_id);
      } catch (e) { toast('迁移失败：' + e.message, 'err'); }
      finally { busy(btn, false); }
    } },
  ]);
}

/* ---- 替换配图 ---- */
function openReplaceImage() {
  if (!S.selected) return toast('先在左侧选一个风格', 'err');
  S.replaceImage = null; S.replacePlan = null;
  showModal('替换配图：' + S.selected, `
    <div class="hint info">旧图会<b>整体移入回收区</b>（可一键还原），新图按 md5 前 8 位生成
      full + thumb 两张 WebP，yaml 的 <code># 配图</code> 注释同步更新。
      失败整体回滚；改完必须点「重建生成物」更新 styles.json 里的图片 URL。</div>
    <div class="preview-box"><img id="rpPreview" src="" alt="新图预览" hidden>
      <div><input type="file" id="rpFile" accept="image/*">
        <div class="hint" style="margin-top:8px">先点「检查影响面」看旧图清单与新文件名；
        若新图与原图内容相同会提示无需替换。</div></div></div>
    <div class="section-title">影响面</div>
    <div id="rpResult" class="hint">尚未检查</div>`, [
    { label: '检查影响面', cls: '', fn: replaceCheck },
    { label: '取消', cls: '', fn: closeModal },
    { label: '确认替换', cls: 'primary', fn: replaceApply },
  ]);
  bindImagePicker('#rpFile', '#rpPreview', 'replaceImage');
}

async function replaceCheck(btn) {
  busy(btn, true, '检查中…');
  try {
    const r = await api('/api/image/check', {
      method: 'POST', body: JSON.stringify({ id: S.selected, image: S.replaceImage }),
    });
    S.replacePlan = r;
    const old = (r.old_images || []).map(x => `<li><code>${esc(x)}</code></li>`).join('');
    const fresh = (r.new_images || []).map(x => `<li><code>${esc(x)}</code></li>`).join('');
    $('#rpResult').innerHTML = `
      <div class="hint ${r.ok && !r.unchanged ? 'info' : ''}">
        ${r.ok ? (r.unchanged ? '新图与原图内容一致，无需替换' : '✓ 可以替换') : '检查未通过'}<br>
        ${(r.errors || []).map(esc).join('<br>')}</div>
      ${(r.warnings || []).length ? `<div class="hint info">${r.warnings.map(esc).join('<br>')}</div>` : ''}
      <ul class="impact-list">
        <li>原图尺寸：${r.source_size ? esc(r.source_size.join(' × ')) : '未上传新图'}</li>
        <li>yaml：<code>${esc(r.yaml)}</code> 的配图注释${r.yaml_will_change ? '会更新' : '会补上'}</li>
      </ul>
      <div class="section-title">移入回收区的旧图（${(r.old_images || []).length}）</div>
      <div class="pre" style="max-height:140px"><ul class="impact-list">${old || '<li>无</li>'}</ul></div>
      ${fresh ? `<div class="section-title">新图</div><div class="pre"><ul class="impact-list">${fresh}</ul></div>` : ''}
      <div class="hint">${esc(r.note || '')}</div>`;
    toast(r.ok ? '检查完成' : '检查未通过', r.ok ? 'ok' : 'err');
  } catch (e) { toast('检查失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

function replaceApply() {
  if (!S.replaceImage) return toast('先选 1 张新配图', 'err');
  if (!S.replacePlan || !S.replacePlan.ok) return toast('先点「检查影响面」', 'err');
  if (S.replacePlan.unchanged) return toast('内容一致，无需替换', 'err');
  showModal('确认替换配图', `
    <div class="hint"><b>${esc(S.selected)}</b> 的 ${(S.replacePlan.old_images || []).length} 张旧图会移入回收区，
    并写入 2 张新 WebP。此操作会产生一个可还原的回收批次。</div>`, [
    { label: '返回', cls: '', fn: openReplaceImage },
    { label: '确认替换', cls: 'primary', fn: async btn => {
      busy(btn, true, '转换与校验中…');
      try {
        const r = await api('/api/image/replace', {
          method: 'POST', body: JSON.stringify({ id: S.selected, image: S.replaceImage }),
        });
        if (!r.ok) return toast(r.error || '替换失败', 'err');
        toast('配图已替换：' + r.batch + '；请重建生成物', 'ok');
        closeModal();
        await refreshBoot(); await loadStyles(); await refreshChanges();
        await select(S.selected);
      } catch (e) { toast('替换失败：' + e.message, 'err'); }
      finally { busy(btn, false); }
    } },
  ]);
}

/* ---- 历史格式规范化 ---- */
const ISSUE_LABELS = {
  code: 'code 死字段', preview: 'preview 旧字段', missing_id: '缺 id',
  missing_preview_comment: '缺配图注释', stale_preview_comment: '配图注释失效',
  str_features: 'features 字符串数组', str_variables: 'variables 字符串数组',
  extra_keys: '非标准顶层键', unindented_lists: '顶格列表',
  parse_error: 'YAML 解析异常',
};

async function openNormalize() {
  if (!S.normalizeScan) S.normalizeScan = await api('/api/normalize/scan');
  const s = S.normalizeScan;
  const chips = Object.entries(s.issues || {}).map(([k, v]) =>
    `<span class="chip" title="${esc(ISSUE_LABELS[k] || k)}">${esc(ISSUE_LABELS[k] || k)} ${v}</span>`).join(' ');
  const opts = Object.entries(s.options || {}).map(([k, o]) => `
    <label class="opt-row ${o.risk}">
      <input type="checkbox" data-norm-opt="${esc(k)}" ${o.default ? 'checked' : ''}>
      <span><b>${esc(o.label)}</b> <span class="risk ${o.risk}">${o.risk === 'safe' ? '零风险' : o.risk === 'medium' ? '需预览' : '高风险'}</span>
      <small>${esc(o.note)}</small></span></label>`).join('');
  showModal('历史格式规范化 · 体检', `
    <div class="hint info">${esc(s.note || '')}</div>
    <div class="section-title">体检结果：${s.affected}/${s.total} 个文件有历史写法</div>
    <div id="normIssues">${chips || '全库格式已统一'}</div>
    <div class="section-title">修复选项</div><div id="normOptions">${opts}</div>
    <div class="grid2">
      <div class="field"><label>应用范围</label><select id="normScope">
        <option value="all">全部有问题的文件</option>
        <option value="vigo">仅 vigo_cookbook</option>
        <option value="checked">仅左侧勾选的风格</option></select></div>
      <div class="field"><label>最多处理（防止一次改太多）</label><select id="normLimit">
        <option value="20">前 20 个</option><option value="50">前 50 个</option>
        <option value="0">全部</option></select></div>
    </div>
    <div class="section-title">逐文件 diff 预览</div>
    <div id="normResult" class="hint">选好选项后点「预览 diff」</div>`, [
    { label: '预览 diff', cls: '', fn: normalizePreview },
    { label: '取消', cls: '', fn: closeModal },
    { label: '应用到磁盘', cls: 'primary', fn: normalizeApply },
  ]);
}

function normParams() {
  const scope = $('#normScope').value;
  const limit = +$('#normLimit').value;
  let ids = (S.normalizeScan.files || []).map(f => f.id);
  if (scope === 'vigo') ids = (S.normalizeScan.files || [])
    .filter(f => f.category === 'vigo_cookbook').map(f => f.id);
  if (scope === 'checked') ids = [...S.checked];
  if (limit > 0) ids = ids.slice(0, limit);
  const options = {};
  $$('[data-norm-opt]').forEach(el => { options[el.dataset.normOpt] = el.checked; });
  return { ids, options };
}

function renderNormResult(r) {
  const plans = r.plans || [];
  const diffs = plans.slice(0, 12).map(p => `<div class="change-item">
    <b>${esc(p.id)}</b> <span style="color:var(--muted)">${esc(p.path)} · ${esc((p.changes || []).join('、'))}</span>
    <pre class="pre" style="max-height:170px;margin-top:6px">${esc(p.diff)}</pre></div>`).join('');
  $('#normResult').innerHTML = `
    <div class="hint ${r.ok && !r.rolled_back ? 'info' : ''}">
      ${r.rolled_back ? '<b>全库校验失败，已整体回滚</b><br>' : ''}
      ${esc(r.error || r.note || '')}<br>
      选中 ${r.selected || plans.length} 个 · 将改动 <b>${r.changed ?? plans.length}</b> 个文件
      ${plans.length > 12 ? `（下面只显示前 12 条 diff）` : ''}</div>
    ${(r.errors || []).length ? `<div class="hint">${r.errors.map(esc).join('<br>')}</div>` : ''}
    ${diffs || '<p class="hint">按当前选项没有文件需要改动</p>'}`;
}

async function normalizePreview(btn) {
  const p = normParams();
  if (!p.ids.length) return toast('应用范围内没有文件', 'err');
  busy(btn, true, '计算中…');
  try {
    const r = await api('/api/normalize/preview', { method: 'POST', body: JSON.stringify(p) });
    S.normalizePlan = r;
    renderNormResult(r);
    toast(r.ok ? `预览完成：${r.changed} 个文件会变化` : '预览未通过', r.ok ? 'ok' : 'err');
  } catch (e) { toast('预览失败：' + e.message, 'err'); }
  finally { busy(btn, false); }
}

function normalizeApply() {
  const p = normParams();
  const plan = S.normalizePlan;
  if (!plan || !plan.ok) return toast('先点「预览 diff」并通过', 'err');
  if (!plan.changed) return toast('没有文件需要改动', 'err');
  const danger = Object.entries(plan.options || {}).filter(([k, v]) =>
    v && (S.normalizeScan.options[k] || {}).risk === 'danger');
  showModal('确认应用规范化', `
    <div class="hint"><b>将写入 ${plan.changed} 个源文件</b>，随后跑一次全库
      <code>validate_all --strict --require-desc</code> + <code>lint_hygiene --strict</code>，
      任一失败整体回滚。</div>
    ${danger.length ? `<div class="hint"><b>已勾选高风险项：</b>${danger.map(x => esc(x[0])).join('、')}
      —— 会删除历史信息，请确认已看过 diff。</div>` : ''}
    <div class="hint info">只改源文件；生成物在点「重建生成物」后才会更新。</div>`, [
    { label: '返回体检', cls: '', fn: openNormalize },
    { label: '确认应用', cls: 'primary', fn: async btn => {
      busy(btn, true, '写入与全库校验中…');
      try {
        const r = await api('/api/normalize/apply', { method: 'POST', body: JSON.stringify(p) });
        if (!r.ok) return toast(r.error || '应用失败', 'err');
        toast(`已规范化 ${r.changed} 个文件，全库校验通过`, 'ok');
        S.normalizeScan = null;
        closeModal();
        await refreshBoot(); await loadStyles(); await refreshChanges();
        if (S.selected) await select(S.selected);
      } catch (e) { toast('应用失败：' + e.message, 'err'); }
      finally { busy(btn, false); }
    } },
  ]);
}

/* ---- 变更历史对比 ---- */
async function openHistory() {
  let r;
  try { r = await api('/api/history'); }
  catch (e) { return toast('读取历史失败：' + e.message, 'err'); }
  S.historyRecords = r.records || [];
  const items = S.historyRecords.map(h => `<div class="change-item">
    <span class="op">${esc(h.op)}</span><b>${esc(h.style_id || '—')}</b>
    <span style="color:var(--muted)">${esc(h.time)} · ${h.changed} 个源文件 ·
      配图 +${h.images_added}/-${h.images_removed}</span>
    <div class="paths">${h.paths.slice(0, 4).map(esc).join('<br>')}${h.paths.length > 4 ? `<br>… 共 ${h.paths.length} 个` : ''}</div>
    <div style="margin-top:7px"><button class="btn mini" data-hist-show="${esc(h.op_id)}">查看 diff</button></div>
  </div>`).join('') || '<p class="hint info">还没有历史记录。保存 / 新建 / 迁移 / 规范化等写操作会自动留痕。</p>';
  showModal('变更历史对比', `
    <div class="hint info">每次写操作前后自动做一次源文件快照，存在
      <code>tools/editor/.state/history.json</code>（已 gitignore），跨会话保留最近 120 条。
      「还原该文件」只在文件此后<b>没有被再次改动</b>时才允许，且会跑一次单文件校验。</div>
    <div class="section-title">操作时间线（${S.historyRecords.length}）</div>
    <div id="histList">${items}</div>
    <div id="histDetail"></div>`, [
    { label: '清空历史', cls: '', fn: historyClear },
    { label: '返回变更中心', cls: '', fn: openChanges },
    { label: '关闭', cls: 'primary', fn: closeModal },
  ]);
  $$('[data-hist-show]').forEach(b =>
    b.addEventListener('click', () => historyShow(b.dataset.histShow)));
}

async function historyShow(opId) {
  const d = await api('/api/history/' + encodeURIComponent(opId));
  const files = (d.files || []).map(f => `
    <div class="change-item"><b>${esc(f.path)}</b>
      <span class="risk ${f.kind === 'modified' ? 'safe' : 'medium'}">${esc(f.kind)}</span>
      ${d.revertable && f.kind === 'modified'
        ? `<button class="btn mini" data-hist-revert="${esc(opId)}" data-hist-path="${esc(f.path)}">还原该文件</button>` : ''}
      <pre class="pre" style="max-height:200px;margin-top:6px">${esc(f.diff)}</pre></div>`).join('');
  const imgs = [...(d.images_added || []).map(x => '+ ' + x),
                ...(d.images_removed || []).map(x => '- ' + x)].join('\n');
  $('#histDetail').innerHTML = `
    <div class="section-title">${esc(d.op)} · ${esc(d.time)}</div>
    ${d.note ? `<div class="hint">${esc(d.note)}</div>` : ''}
    ${imgs ? `<div class="section-title">配图变化</div><pre class="pre" style="max-height:120px">${esc(imgs)}</pre>` : ''}
    <div class="section-title">逐文件差异（${(d.files || []).length}）</div>${files || '<p class="hint">无源文件变化</p>'}`;
  $$('[data-hist-revert]').forEach(b => b.addEventListener('click', () =>
    historyRevert(b.dataset.histRevert, b.dataset.histPath)));
  $('#histDetail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function historyRevert(opId, path) {
  showModal('确认还原单个文件', `
    <div class="hint"><code>${esc(path)}</code> 会还原到该操作之前的版本。<br>
    如果此后又被编辑过，或还原后校验不通过，都会拒绝 / 回滚。</div>`, [
    { label: '取消', cls: '', fn: openHistory },
    { label: '确认还原', cls: 'primary', fn: async btn => {
      busy(btn, true, '还原中…');
      try {
        const r = await api('/api/history/revert', {
          method: 'POST', body: JSON.stringify({ op_id: opId, path }),
        });
        toast(r.ok ? '已还原：' + path : r.error, r.ok ? 'ok' : 'err');
        closeModal();
        await refreshBoot(); await loadStyles(); await refreshChanges();
        if (S.selected) await select(S.selected);
      } catch (e) { toast('还原失败：' + e.message, 'err'); }
      finally { busy(btn, false); }
    } },
  ]);
}

function historyClear() {
  showModal('清空变更历史', `
    <div class="hint"><b>只清空历史记录</b>，不会改动任何风格文件、生成物或回收区。
    已提交的内容仍可用 Git 追溯。</div>`, [
    { label: '取消', cls: '', fn: openHistory },
    { label: '确认清空', cls: 'danger', fn: async btn => {
      busy(btn, true, '清空中…');
      try {
        const r = await api('/api/history/clear', {
          method: 'POST', body: JSON.stringify({ confirm: true }),
        });
        toast(r.ok ? '历史已清空' : r.error, r.ok ? 'ok' : 'err');
        openHistory();
      } catch (e) { toast('清空失败：' + e.message, 'err'); }
      finally { busy(btn, false); }
    } },
  ]);
}

/* ---------------- 模态 ---------------- */
function showModal(title, html, buttons) {
  $('#modalBox').innerHTML = `<div class="modal-head"><h2>${esc(title)}</h2><button class="close" id="modalClose">×</button></div>
    <div class="modal-body">${html}</div>
    <div class="modal-foot">${buttons.map((b, i) => `<button class="btn ${b.cls}" data-mbtn="${i}">${esc(b.label)}</button>`).join('')}</div>`;
  $('#modal').hidden = false;
  $('#modalClose').addEventListener('click', closeModal);
  buttons.forEach((b, i) => {
    const el = $(`[data-mbtn="${i}"]`);
    el.addEventListener('click', () => b.fn(el));
  });
}
function closeModal() { $('#modal').hidden = true; }

init();
