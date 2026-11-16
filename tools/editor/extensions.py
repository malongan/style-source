#!/usr/bin/env python3
"""P1 扩展：YAML 导入 / 无图草稿 / 批量标签 / 回收区 / 生成物过期检测。

与 P0 相同的三条原则：
  - 不重写任何校验规则，一律 subprocess 调 scripts/ 下的既有脚本
  - 写盘一律「先算好 → 全部写入 → 跑校验 → 失败整体回滚」
  - 草稿 / 回收区 / 快照都在 tools/editor/ 下，不进 styles/，不参与 preflight

路径全部通过 ops.path() 运行时求值，支持 STYLE_SOURCE_ROOT 沙箱。
"""
from __future__ import annotations

import base64
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone

import image_pipeline
import ops
import yaml_patch
import yaml_template

SAFE_ID_RE = re.compile(r'^[a-z][a-z0-9_]{2,79}$')
SAFE_BATCH_RE = re.compile(r'^[\w.\-]+$')
PREVIEW_COMMENT_RE = re.compile(r'^#\s*配图[:：].*$', re.M)
BATCH_FIELDS = ('tags', 'triggers')
BATCH_ACTIONS = ('add', 'remove', 'replace_all', 'replace_value')


# ---------------- 通用小工具 ----------------
def _editor_dir(name: str) -> str:
    d = ops.path('tools', 'editor', name)
    os.makedirs(d, exist_ok=True)
    return d


def _atomic_write(fp: str, text: str):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(fp), prefix='.editor-', suffix='.tmp')
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
    return sorted(
        p for p in glob.glob(ops.path('styles', '*', '*.yaml'))
        if not os.path.basename(p).startswith('_')
    )


# ---------------- 1. YAML 导入 ----------------
def _slug_from_filename(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename or ''))[0]
    stem = re.sub(r'[^a-z0-9_]', '_', stem.lower()).strip('_')
    return stem


def analyze_import(text: str, filename: str = '', mode: str = 'normalized',
                   override_id: str = '', override_category: str = '') -> dict:
    """只解析、不写盘。返回字段摘要、错误、警告、两种候选文本与写前查重结果。"""
    result = {'ok': False, 'mode': mode, 'filename': filename}
    try:
        data = yaml_patch.parse(text)
    except Exception as exc:
        result['errors'] = ['YAML 解析失败：%s' % exc]
        return result

    keys = yaml_patch.top_keys(text)
    sid = (override_id or str(data.get('id') or '') or _slug_from_filename(filename)).strip()
    cat = (override_category or str(data.get('category') or '')).strip()

    errors = []
    warnings = []
    if not SAFE_ID_RE.match(sid):
        errors.append('id 不合法或缺失：%r（需要小写字母开头、只含 a-z/0-9/_ 的 3–80 位 snake_case；'
                      '可在下方手工指定）' % sid)
    if cat not in yaml_template.VALID_CATEGORIES:
        errors.append('分类不合法或缺失：%r（需在下方选择）' % cat)

    style = {}
    for key in yaml_template.FIELD_ORDER:
        if key in ('id', 'category'):
            continue
        if data.get(key) is not None:
            style[key] = data[key]
    style['id'] = sid
    style['category'] = cat

    # 历史形态：variables / features 是字符串数组时，规范化会丢失 desc，必须显式提示
    for key in ('variables', 'features'):
        raw = data.get(key) or []
        if isinstance(raw, list) and any(isinstance(v, str) for v in raw):
            warnings.append('%s 是旧式字符串数组（%d 项），规范化后无法自动补 desc；'
                            '建议用「保真导入」或在导入后逐条补齐' % (key, len(raw)))

    unknown = [k for k in keys if k not in yaml_template.FIELD_ORDER and k not in
               ('preview', 'code', 'name_cn', 'created_at', 'verified_at',
                'source', 'derived_from', 'variables_guide')]
    extra = [k for k in keys if k not in yaml_template.FIELD_ORDER]
    if extra:
        warnings.append('源文件含 %d 个非标准顶层键（%s）；「规范化导入」会丢弃它们，'
                        '「保真导入」会原样保留' % (len(extra), ', '.join(extra)))
    if 'code' in keys:
        warnings.append('源文件写了 code: —— 编号由 generate_data.py 重算，属死字段；规范化会去掉')
    if unknown:
        warnings.append('完全未知的顶层键：%s' % ', '.join(unknown))
    if not str(data.get('source_url') or '').strip():
        warnings.append('来源链接为空，导入后将失去 URL 查重能力（库里已有多条先例）')

    errors += yaml_template.check_form(style)

    faithful = text
    if 'id' in keys and data.get('id') != sid:
        faithful = yaml_patch.replace_field(faithful, 'id', sid)
    if 'category' in keys and data.get('category') != cat:
        faithful = yaml_patch.replace_field(faithful, 'category', cat)
    if not faithful.endswith('\n'):
        faithful += '\n'
    normalized = yaml_template.render(style, '')

    dup = ops.check_new(sid, str(data.get('source_url') or ''),
                        str(data.get('prompt') or '')) if sid else {'blocked': False, 'checks': {}}
    if ops.find_style_file(sid):
        errors.append('风格 %s 已存在，不能重复导入' % sid)
    if image_pipeline.find_images(sid, ops.images_dir()):
        errors.append('已存在同名配图（孤儿图），请先处理再导入')

    result.update({
        'ok': not errors and not dup['blocked'],
        'id': sid, 'category': cat, 'errors': errors, 'warnings': warnings,
        'style': style, 'top_keys': keys, 'dup': dup,
        'candidates': {'faithful': faithful, 'normalized': normalized},
        'candidate': normalized if mode == 'normalized' else faithful,
        'summary': {
            'name': data.get('name', ''),
            'prompt_len': len(str(data.get('prompt') or '').strip()),
            'tags': len(data.get('tags') or []),
            'triggers': len(data.get('triggers') or []),
            'features': len(data.get('features') or []),
            'variables': len(data.get('variables') or []),
        },
    })
    return result


def commit_import(text: str, filename: str, mode: str, override_id: str,
                  override_category: str, image: dict) -> dict:
    """写盘导入。前端只传原文与覆盖项，字段一律在后端重新解析，不信任前端结构。"""
    a = analyze_import(text, filename, mode, override_id, override_category)
    if not a['ok']:
        return {'ok': False, 'error': '导入检查未通过', 'errors': a['errors'],
                'warnings': a['warnings'], 'dup': a.get('dup')}
    sid, cat = a['id'], a['category']
    if not image.get('data'):
        return {'ok': False, 'error': '导入必须上传 1 张配图（--strict 要求 full + thumb 齐全）'}
    try:
        raw = base64.b64decode(image['data'].split(',')[-1])
    except Exception:
        return {'ok': False, 'error': '图片解码失败'}

    written = []
    yaml_fp = None
    try:
        meta = image_pipeline.convert_bytes(raw, sid, ops.images_dir())
        written += [ops.path('images', 'styles_previews', meta['full']),
                    ops.path('images', 'styles_previews', meta['thumb'])]
        final = a['candidate']
        if mode == 'faithful':
            if 'preview' in a['top_keys']:
                final = yaml_patch.replace_field(final, 'preview', meta['full_rel'])
            comment = '# 配图: %s' % meta['full_rel']
            if PREVIEW_COMMENT_RE.search(final):
                final = PREVIEW_COMMENT_RE.sub(comment, final)
            else:
                final = final.rstrip('\n') + '\n\n' + comment + '\n'
        else:
            final = yaml_template.render(a['style'], meta['full_rel'])
        yaml_patch.parse(final)

        yaml_fp = ops.path('styles', cat, sid + '.yaml')
        _atomic_write(yaml_fp, final)
        rel = os.path.relpath(yaml_fp, ops.root())
        v = ops.validate_single(rel)
        if not v['ok']:
            raise RuntimeError('导入文件校验未通过：%s\n%s' % (
                v['validate']['output'][-600:], v['hygiene']['output'][-400:]))
        ops.timestamps_add(sid, datetime.now().astimezone().isoformat(timespec='seconds'))
        ops.invalidate()
        paths = [rel, meta['full_rel'], meta['thumb_rel'], 'data/style_timestamps.json']
        return {
            'ok': True, 'id': sid, 'path': rel, 'mode': mode, 'images': meta,
            'validation': v, 'warnings': a['warnings'],
            'diff': _diff('', final, rel), 'paths': paths,
            'hint': '编号将在点「重建生成物」后自动分配；提交前请核对生成物 diff',
        }
    except Exception as exc:
        for fp in written:
            if os.path.exists(fp):
                os.remove(fp)
        if yaml_fp and os.path.exists(yaml_fp):
            os.remove(yaml_fp)
        ops.timestamps_remove(sid)
        ops.invalidate()
        return {'ok': False, 'error': str(exc), 'rolled_back': True}


# ---------------- 2. 无图草稿区 ----------------
def draft_dir() -> str:
    return _editor_dir('.drafts')


def _draft_fp(draft_id: str) -> str:
    if not SAFE_BATCH_RE.match(draft_id):
        raise ValueError('非法草稿 id')
    return os.path.join(draft_dir(), draft_id + '.json')


def list_drafts() -> list:
    out = []
    for fp in sorted(glob.glob(os.path.join(draft_dir(), '*.json')), reverse=True):
        try:
            with open(fp, encoding='utf-8') as fh:
                d = json.load(fh)
            style = d.get('style') or {}
            out.append({
                'id': d.get('id') or os.path.basename(fp)[:-5],
                'name': style.get('name') or '（未命名）',
                'category': style.get('category') or '',
                'prompt_len': len(str(style.get('prompt') or '').strip()),
                'saved_at': d.get('saved_at', ''),
                'note': d.get('note', ''),
            })
        except Exception:
            pass
    return out


def get_draft(draft_id: str) -> dict:
    fp = _draft_fp(draft_id)
    if not os.path.isfile(fp):
        raise FileNotFoundError('找不到草稿 %s' % draft_id)
    with open(fp, encoding='utf-8') as fh:
        return json.load(fh)


def save_draft(style: dict, draft_id: str = '') -> dict:
    did = (draft_id or str(style.get('id') or '') or
           'draft-' + datetime.now().strftime('%Y%m%d-%H%M%S')).strip()
    if not SAFE_BATCH_RE.match(did):
        return {'ok': False, 'error': '草稿 id 非法（只允许字母数字、下划线、点、连字符）'}
    sid = str(style.get('id') or '').strip()
    if sid and ops.find_style_file(sid):
        return {'ok': False, 'error': '风格 %s 已是正式条目，草稿不能覆盖' % sid}
    payload = {
        'id': did, 'style': style,
        'saved_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'note': '无图草稿：不进 styles/，不参与校验；补全配图后才能正式入库',
    }
    fp = _draft_fp(did)
    _atomic_write(fp, json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return {'ok': True, 'id': did, 'path': os.path.relpath(fp, ops.root())}


def delete_draft(draft_id: str) -> dict:
    fp = _draft_fp(draft_id)
    if not os.path.isfile(fp):
        return {'ok': False, 'error': '找不到草稿'}
    os.remove(fp)
    return {'ok': True, 'id': draft_id}


# ---------------- 3. 批量标签编辑 ----------------
def batch_tags(ids: list, field: str, action: str, values: list,
               dry_run: bool = True) -> dict:
    """只改 tags / triggers 一个字段；全库校验一次，任一失败整体回滚。"""
    if field not in BATCH_FIELDS:
        return {'ok': False, 'error': '只允许批量改 tags / triggers'}
    if action not in BATCH_ACTIONS:
        return {'ok': False, 'error': '未知批量动作'}
    vals = [str(v).strip() for v in values if str(v).strip()]
    if not vals and action != 'replace_all':
        return {'ok': False, 'error': '请填写至少一个值'}
    if action == 'replace_value' and len(vals) < 2:
        return {'ok': False, 'error': '「替换某个值」需要填两个值：原值、新值'}
    ids = list(dict.fromkeys(str(i) for i in ids))
    if not ids:
        return {'ok': False, 'error': '没有选中风格'}

    plans, errors, skipped = [], [], []
    for sid in ids:
        try:
            info = ops.read_style(sid)
        except Exception as exc:
            errors.append('%s：%s' % (sid, exc))
            continue
        cur = info['data'].get(field) or []
        if not isinstance(cur, list):
            errors.append('%s：%s 不是数组，跳过' % (sid, field))
            continue
        if action == 'add':
            new = cur + [v for v in vals if v not in cur]
        elif action == 'remove':
            new = [v for v in cur if str(v) not in vals]
        elif action == 'replace_all':
            new = vals[:]
        else:
            old_v, new_v = vals[0], vals[1]
            new = [new_v if str(v) == old_v else v for v in cur]
        if new == cur:
            skipped.append(sid)
            continue
        try:
            new_text = yaml_patch.replace_field(info['text'], field, new)
            yaml_patch.parse(new_text)
        except Exception as exc:
            errors.append('%s：生成文本失败 %s' % (sid, exc))
            continue
        plans.append({
            'id': sid, 'path': info['path'], 'old_text': info['text'],
            'new_text': new_text, 'old': cur, 'new': new,
            'diff': _diff(info['text'], new_text, info['path']),
        })
    if errors:
        return {'ok': False, 'errors': errors, 'plans': [
            {k: p[k] for k in ('id', 'path', 'diff', 'old', 'new')} for p in plans]}

    public = [{k: p[k] for k in ('id', 'path', 'diff', 'old', 'new')} for p in plans]
    if dry_run:
        return {'ok': True, 'dry_run': True, 'plans': public,
                'skipped': skipped, 'selected': len(ids), 'changed': len(plans),
                'note': '预览不写盘；确认后逐个写入并跑一次全库校验，失败整体回滚'}

    for p in plans:
        _atomic_write(ops.path(p['path']), p['new_text'])
    v = ops.run([ops.PY, 'scripts/validate_all.py', '--strict', '--require-desc'], timeout=180)
    h = ops.run([ops.PY, 'scripts/lint_hygiene.py', '--strict'], timeout=180)
    if not (v['ok'] and h['ok']):
        for p in plans:
            _atomic_write(ops.path(p['path']), p['old_text'])
        ops.invalidate()
        return {'ok': False, 'rolled_back': True, 'plans': public,
                'error': '全库校验未通过，已全部回滚',
                'validation': {'validate_all': v, 'lint_hygiene': h}}
    ops.invalidate()
    return {'ok': True, 'changed': len(plans), 'skipped': skipped,
            'plans': public, 'validation': {'validate_all': v, 'lint_hygiene': h},
            'paths': [p['path'] for p in plans]}


# ---------------- 4. 回收区详情与彻底删除 ----------------
def trash_root() -> str:
    return ops.path('tools', 'editor', '.trash')


def trash_detail(batch: str) -> dict:
    if not SAFE_BATCH_RE.match(batch):
        raise ValueError('非法批次名')
    mf = os.path.join(trash_root(), batch, 'manifest.json')
    if not os.path.isfile(mf):
        raise FileNotFoundError('找不到回收批次 %s' % batch)
    with open(mf, encoding='utf-8') as fh:
        manifest = json.load(fh)
    yaml_text = ''
    for item in manifest.get('moved', []):
        if item['from'].endswith('.yaml'):
            fp = ops.path(item['to'])
            if os.path.isfile(fp):
                with open(fp, encoding='utf-8') as fh:
                    yaml_text = fh.read()
            break
    manifest['yaml_text'] = yaml_text
    manifest['files_present'] = sum(
        1 for i in manifest.get('moved', []) if os.path.isfile(ops.path(i['to'])))
    return manifest


def trash_purge(batch: str, confirm: bool) -> dict:
    if not SAFE_BATCH_RE.match(batch):
        return {'ok': False, 'error': '非法批次名'}
    if not confirm:
        return {'ok': False, 'error': '彻底删除需要显式确认（confirm=1）'}
    dest = os.path.join(trash_root(), batch)
    if not os.path.isdir(dest):
        return {'ok': False, 'error': '找不到回收批次'}
    try:
        detail = trash_detail(batch)
    except Exception:
        detail = {}
    shutil.rmtree(dest)
    return {'ok': True, 'batch': batch,
            'removed_files': len(detail.get('moved', [])),
            'note': '已从回收区彻底删除；Git 仍是最后一道保险'}


# ---------------- 5. 生成物过期检测（内容摘要快照） ----------------
def snapshot_fp() -> str:
    return os.path.join(_editor_dir('.state'), 'snapshot.json')


def yaml_digest() -> dict:
    out = {}
    for fp in _style_files():
        with open(fp, 'rb') as fh:
            out[os.path.relpath(fp, ops.root())] = hashlib.sha256(fh.read()).hexdigest()
    return out


def write_snapshot() -> dict:
    files = yaml_digest()
    payload = {
        'time': datetime.now().astimezone().isoformat(timespec='seconds'),
        'total': len(files), 'files': files,
        'note': '上一次「重建生成物」时的 yaml 内容摘要；用于判断此后是否有源文件被改动',
    }
    _atomic_write(snapshot_fp(), json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return {'ok': True, 'time': payload['time'], 'total': len(files)}


def _generated_ts() -> float:
    try:
        with open(ops.path('data', 'styles.json'), encoding='utf-8') as fh:
            s = json.load(fh).get('meta', {}).get('generated', '')
        return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(
            tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


def freshness() -> dict:
    cur = yaml_digest()
    try:
        with open(snapshot_fp(), encoding='utf-8') as fh:
            snap = json.load(fh)
        base = snap.get('files') or {}
    except Exception:
        base = None

    if base is None:
        # 没建立基线时退化为 mtime 比较；只做提示，不假装精确
        gen = _generated_ts()
        newest = max((os.path.getmtime(ops.path(p)) for p in cur), default=0)
        stale = bool(gen and newest > gen + 1)
        return {
            'baseline': False, 'stale': stale, 'total': len(cur),
            'changed': [], 'added': [], 'removed': [],
            'snapshot_time': '', 'generated': gen or None,
            'note': '尚未建立内容基线，当前按文件修改时间粗判；点「标记为已同步」或重建一次即可建立',
        }
    added = sorted(set(cur) - set(base))
    removed = sorted(set(base) - set(cur))
    changed = sorted(k for k in set(cur) & set(base) if cur[k] != base[k])
    return {
        'baseline': True, 'stale': bool(added or removed or changed),
        'total': len(cur), 'added': added, 'removed': removed, 'changed': changed,
        'snapshot_time': snap.get('time', ''),
        'note': ('生成物已过期：%d 个源文件有变动，请点「重建生成物」' % (len(added) + len(removed) + len(changed))
                 if (added or removed or changed) else '生成物与源文件一致'),
    }
