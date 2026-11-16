#!/usr/bin/env python3
"""P2 · 历史格式规范化（体检 → 分级预览 → 应用，全库校验失败整体回滚）。

库里 51 个 vigo_cookbook 与一批早期文件用的是另一套写法：顶格 `-` 列表、
`code: ''` 死字段、`preview:` 旧字段、features 是字符串数组、首行没有 id、
没有 # 配图 注释。它们**当前全部能通过 CI**，所以规范化不是纠错，而是收敛格式。

因此这里的定位是「体检 + 可选项」，不是一键重写：
  - 零语义风险的项默认开（删死字段 code / 补 id / 修正配图注释）
  - 会改变详情页展示或产生大 diff 的项默认关（features 结构化 / 统一缩进 /
    删旧 preview 字段 / 删历史额外键）
  - 每个文件先出逐条 diff 预览，应用时跑一次全库校验，任一失败整体回滚
"""
from __future__ import annotations

import difflib
import glob
import json
import os
import re
import tempfile

import image_pipeline
import ops
import yaml_patch
import yaml_template

PREVIEW_COMMENT_RE = re.compile(r'^#\s*配图[:：].*$', re.M)
TOP_KEY_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):')
CANONICAL_KEYS = set(yaml_template.FIELD_ORDER)
LIST_KEYS = ('tags', 'triggers', 'features', 'variables')

OPTIONS = {
    'drop_code': {'label': '删除 code 死字段', 'risk': 'safe', 'default': True,
                  'note': '编号由 generate_data.py 重算，yaml 里写了也是死代码'},
    'add_id': {'label': '补 id 字段', 'risk': 'safe', 'default': True,
               'note': '按文件名补一行 id，插在首行标题注释之后'},
    'fix_preview_comment': {'label': '修正 # 配图 注释', 'risk': 'safe', 'default': True,
                            'note': '缺失则补，指向的文件不存在则改为实际配图名'},
    'drop_preview': {'label': '删除 preview 旧字段', 'risk': 'medium', 'default': False,
                     'note': '仅在确认所有风格都有本地 WebP 后才建议开'},
    'structure_features': {'label': 'features 字符串 → title/desc', 'risk': 'medium',
                           'default': False,
                           'note': '会改变详情页展示；按 **标题** — 描述 尝试拆分，拆不开就整串进 title'},
    'normalize_lists': {'label': '统一列表缩进为 2 空格', 'risk': 'medium', 'default': False,
                        'note': '纯格式但 diff 很大；混合缩进的文件会跳过并标注'},
    'drop_extra_keys': {'label': '删除非标准顶层键', 'risk': 'danger', 'default': False,
                        'note': 'source / derived_from / variables_guide 等历史信息会被丢掉'},
}


def _atomic_write(fp: str, text: str):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(fp), prefix='.norm-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
        os.replace(tmp, fp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _diff(old: str, new: str, label: str) -> str:
    return ''.join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=label + ' (before)', tofile=label + ' (after)', n=2))


def _style_files() -> list:
    return sorted(p for p in glob.glob(ops.path('styles', '*', '*.yaml'))
                  if not os.path.basename(p).startswith('_'))


def _blocks(text: str) -> list:
    """[(key, start, end, lines)]，用来按顶层区块安全地做局部文本手术。"""
    lines = text.split('\n')
    marks = yaml_patch._marks(lines)
    out = []
    for j, (i, key) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
        out.append((key, i, end, lines))
    return out


def _drop_simple_scalar(text: str, key: str) -> tuple:
    """只删单行的标量顶层字段；块标量 / 列表字段一律不动，避免误删内容。"""
    m = re.search(r'^%s:[ \t]*(.*)$' % re.escape(key), text, re.M)
    if not m:
        return text, False
    raw = m.group(1).strip()
    if raw.startswith(('|', '>', '[', '{')):
        return text, False
    lines = text.split('\n')
    idx = next(i for i, l in enumerate(lines) if re.match(r'^%s:' % re.escape(key), l))
    del lines[idx]
    # 顺手收掉因此产生的连续空行（只收一行）
    if idx < len(lines) and idx > 0 and not lines[idx].strip() and not lines[idx - 1].strip():
        del lines[idx]
    return '\n'.join(lines), True


def _insert_id(text: str, sid: str) -> str:
    lines = text.split('\n')
    idx = 0
    while idx < len(lines) and (lines[idx].startswith('#') or not lines[idx].strip()):
        idx += 1
    lines.insert(idx, 'id: %s' % sid)
    if idx + 1 < len(lines) and lines[idx + 1].strip():
        lines.insert(idx + 1, '')
    return '\n'.join(lines)


def _fix_comment(text: str, sid: str) -> tuple:
    imgs = image_pipeline.find_images(sid, ops.images_dir())
    full = next((n for n in imgs if not n.endswith('.thumb.webp')), None)
    if not full:
        return text, False
    want = '# 配图: images/styles_previews/%s' % full
    m = PREVIEW_COMMENT_RE.search(text)
    if m:
        if full in m.group(0):
            return text, False
        return PREVIEW_COMMENT_RE.sub(want, text), True
    return text.rstrip('\n') + '\n\n' + want + '\n', True


def _split_feature(s: str) -> dict:
    """把 `**标题** — 描述` 拆成 title/desc；拆不开就整串当 title，不丢内容。"""
    s = str(s).strip()
    m = re.match(r'^\*{0,2}(.+?)\*{0,2}\s*(?:—|--|–|-|：|:)\s+(.+)$', s)
    if m and len(m.group(1).strip()) >= 2:
        title = m.group(1).strip().strip('*').strip()
        desc = m.group(2).strip()
        return {'title': title, 'desc': desc}
    return {'title': s, 'desc': ''}


def _indent_lists(text: str) -> tuple:
    """把顶格 `- ` 列表区块整体右移 2 空格；混合缩进的区块跳过。"""
    lines = text.split('\n')
    out = list(lines)
    changed = 0
    skipped = []
    for key, start, end, _ in _blocks(text):
        if key not in LIST_KEYS:
            continue
        seg = lines[start + 1:end]
        top_items = [i for i, l in enumerate(seg) if re.match(r'^- ', l)]
        indented_items = [i for i, l in enumerate(seg) if re.match(r'^ {2,}- ', l)]
        if top_items and indented_items:
            skipped.append(key)
            continue
        if not top_items:
            continue
        first = min(top_items)
        for k in range(first, len(seg)):
            l = seg[k]
            if not l.strip():
                continue  # 空行不缩进；后面若还有列表项会继续处理
            if l.startswith('#') or TOP_KEY_RE.match(l):
                break     # 顶层注释 / 下一个字段不属于本列表，别把它缩进
            if not (l.startswith('- ') or l.startswith(' ')):
                break
            idx = start + 1 + k
            out[idx] = '  ' + l
        changed += 1
    return '\n'.join(out), changed, skipped


def _drop_extra_keys(text: str) -> tuple:
    keys = yaml_patch.top_keys(text)
    extra = [k for k in keys if k not in CANONICAL_KEYS]
    removed = []
    for k in extra:
        text, hit = _drop_simple_scalar(text, k)
        if hit:
            removed.append(k)
    return text, removed


# ---------------- 体检 ----------------
def scan() -> dict:
    issues = {}
    files = []
    for fp in _style_files():
        sid = os.path.basename(fp)[:-5]
        rel = os.path.relpath(fp, ops.root())
        cat = os.path.basename(os.path.dirname(fp))
        with open(fp, encoding='utf-8') as fh:
            text = fh.read()
        try:
            data = yaml_patch.parse(text)
        except Exception as exc:
            files.append({'id': sid, 'path': rel, 'category': cat,
                          'issues': ['parse_error'], 'parse_error': str(exc)})
            issues['parse_error'] = issues.get('parse_error', 0) + 1
            continue
        keys = yaml_patch.top_keys(text)
        found = []
        if 'code' in keys:
            found.append('code')
        if 'preview' in keys:
            found.append('preview')
        if 'id' not in keys:
            found.append('missing_id')
        if not PREVIEW_COMMENT_RE.search(text):
            found.append('missing_preview_comment')
        feats = data.get('features') or []
        if isinstance(feats, list) and feats and all(isinstance(x, str) for x in feats):
            found.append('str_features')
        variables = data.get('variables') or []
        if isinstance(variables, list) and variables and all(isinstance(x, str) for x in variables):
            found.append('str_variables')
        if any(k not in CANONICAL_KEYS for k in keys):
            found.append('extra_keys')
        if re.search(r'^- ', text, re.M):
            found.append('unindented_lists')
        m = PREVIEW_COMMENT_RE.search(text)
        if m:
            name = m.group(0).split('/')[-1].strip()
            if name and not os.path.isfile(ops.path('images', 'styles_previews', name)):
                found.append('stale_preview_comment')
        for k in found:
            issues[k] = issues.get(k, 0) + 1
        if found:
            files.append({'id': sid, 'path': rel, 'category': cat, 'issues': found})
    return {
        'ok': True, 'total': len(_style_files()), 'affected': len(files),
        'issues': issues, 'files': files, 'options': OPTIONS,
        'note': ('这些历史写法当前都能通过 CI，规范化只收敛格式、不改变风格内容。'
                 '默认只勾零风险项；应用前务必看逐文件 diff，应用后会自动跑一次全库校验。'),
    }


# ---------------- 预览 ----------------
def _build_candidate(text: str, sid: str, options: dict) -> tuple:
    notes = []
    if options.get('drop_code'):
        text, hit = _drop_simple_scalar(text, 'code')
        if hit:
            notes.append('删除 code')
    if options.get('drop_preview'):
        text, hit = _drop_simple_scalar(text, 'preview')
        if hit:
            notes.append('删除 preview')
    if options.get('add_id') and 'id' not in yaml_patch.top_keys(text):
        text = _insert_id(text, sid)
        notes.append('补 id')
    if options.get('fix_preview_comment'):
        text, hit = _fix_comment(text, sid)
        if hit:
            notes.append('修正配图注释')
    if options.get('structure_features'):
        try:
            data = yaml_patch.parse(text)
            feats = data.get('features') or []
            if isinstance(feats, list) and feats and all(isinstance(x, str) for x in feats):
                text = yaml_patch.replace_field(text, 'features',
                                                [_split_feature(x) for x in feats])
                notes.append('features 结构化')
        except Exception as exc:
            notes.append('features 结构化跳过：%s' % exc)
    if options.get('normalize_lists'):
        text, n, skipped = _indent_lists(text)
        if n:
            notes.append('统一 %d 个列表区块缩进' % n)
        if skipped:
            notes.append('混合缩进跳过：%s' % ', '.join(skipped))
    if options.get('drop_extra_keys'):
        text, extra = _drop_extra_keys(text)
        if extra:
            notes.append('删除额外键 %s' % ', '.join(extra))
    return text, notes


def preview(ids: list, options: dict) -> dict:
    ids = list(dict.fromkeys(str(i) for i in (ids or [])))
    if not ids:
        return {'ok': False, 'error': '没有选中文件'}
    opts = {k: bool(options.get(k, v['default'])) for k, v in OPTIONS.items()}
    plans, errors = [], []
    for sid in ids:
        fp = ops.find_style_file(sid)
        if not fp:
            errors.append('%s：找不到文件' % sid)
            continue
        rel = os.path.relpath(fp, ops.root())
        with open(fp, encoding='utf-8') as fh:
            old = fh.read()
        new, notes = _build_candidate(old, sid, opts)
        if new == old:
            continue
        try:
            parsed = yaml_patch.parse(new)
        except Exception as exc:
            errors.append('%s：候选文本 YAML 解析失败 %s' % (sid, exc))
            continue
        if parsed.get('id') and parsed['id'] != sid:
            errors.append('%s：候选文本 id 与文件名不一致' % sid)
            continue
        plans.append({'id': sid, 'path': rel, 'old_text': old, 'new_text': new,
                      'changes': notes, 'diff': _diff(old, new, rel)})
    if errors:
        return {'ok': False, 'errors': errors, 'options': opts,
                'plans': [{k: p[k] for k in ('id', 'path', 'changes', 'diff')} for p in plans]}
    public = [{k: p[k] for k in ('id', 'path', 'changes', 'diff')} for p in plans]
    return {'ok': True, 'dry_run': True, 'options': opts, 'plans': public,
            'selected': len(ids), 'changed': len(plans),
            'note': '预览不写盘；应用时全部写入后跑一次全库校验，失败整体回滚'}


# ---------------- 应用 ----------------
def apply(ids: list, options: dict) -> dict:
    r = preview(ids, options)
    if not r['ok']:
        return r
    # preview 返回的是脱敏后的 plans，这里重新算一遍拿全文，不信任前端
    plans = []
    for p in r['plans']:
        fp = ops.path(p['path'])
        with open(fp, encoding='utf-8') as fh:
            old = fh.read()
        new, notes = _build_candidate(old, p['id'], r['options'])
        if new != old:
            plans.append({'id': p['id'], 'path': p['path'],
                          'old_text': old, 'new_text': new,
                          'changes': notes, 'diff': _diff(old, new, p['path'])})
    if not plans:
        return {'ok': True, 'changed': 0, 'note': '没有文件需要改动'}

    for p in plans:
        _atomic_write(ops.path(p['path']), p['new_text'])
    v = ops.run([ops.PY, 'scripts/validate_all.py', '--strict', '--require-desc'], timeout=180)
    h = ops.run([ops.PY, 'scripts/lint_hygiene.py', '--strict'], timeout=180)
    if not (v['ok'] and h['ok']):
        for p in plans:
            _atomic_write(ops.path(p['path']), p['old_text'])
        ops.invalidate()
        return {'ok': False, 'rolled_back': True,
                'error': '全库校验未通过，已整体回滚',
                'validation': {'validate_all': v, 'lint_hygiene': h},
                'plans': r['plans']}
    ops.invalidate()
    return {'ok': True, 'changed': len(plans), 'options': r['options'],
            'plans': r['plans'],
            'paths': [p['path'] for p in plans],
            'validation': {'validate_all': v, 'lint_hygiene': h},
            'note': '规范化只改源文件；生成物在点「重建生成物」后才会更新'}
