#!/usr/bin/env python3
"""P2 · 变更历史对比（跨会话持久化的写操作快照）。

设计要点：
  - 不在每个业务函数里手工传 before/after：用 capture() 包住一次写操作，
    进入/退出各做一次「全库源文件快照」，自动 diff 出真正变化的文件。
    这样 P0/P1 已有的所有写入路径（包括 extensions 内部写盘）都能被覆盖，
    而且「写入后校验失败自动回滚」的操作因为前后一致，不会留下假记录。
  - 只快照源文件：styles/**/*.yaml + data/style_numbers.json +
    data/style_timestamps.json + 配图文件名清单。
    styles.json / gallery.* 是生成物且体积大，交给「重建生成物」和 Git 管。
  - 快照全文存 .state/history.json（已 gitignore），支持「查看 diff」与
    「按文件还原到操作前」；还原会先确认磁盘内容仍等于操作后版本，避免覆盖后续编辑。
"""
from __future__ import annotations

import contextlib
import difflib
import glob
import json
import os
import tempfile
from datetime import datetime

import ops

STATE_DIR_NAME = '.state'
HISTORY_FILE = 'history.json'
MAX_RECORDS = 120
MAX_ENTRY_CHARS = 1_500_000
TRACKED_DATA = ('data/style_numbers.json', 'data/style_timestamps.json')


def _editor_dir(name: str) -> str:
    d = ops.path('tools', 'editor', name)
    os.makedirs(d, exist_ok=True)
    return d


def history_fp() -> str:
    return os.path.join(_editor_dir(STATE_DIR_NAME), HISTORY_FILE)


def _read_text(fp: str) -> str:
    try:
        with open(fp, encoding='utf-8') as fh:
            return fh.read()
    except Exception:
        return ''


def snapshot() -> dict:
    files = {}
    for fp in sorted(glob.glob(ops.path('styles', '*', '*.yaml'))):
        if os.path.basename(fp).startswith('_'):
            continue
        files[os.path.relpath(fp, ops.root())] = _read_text(fp)
    for rel in TRACKED_DATA:
        fp = ops.path(rel)
        if os.path.isfile(fp):
            files[rel] = _read_text(fp)
    imgs = []
    d = ops.images_dir()
    if os.path.isdir(d):
        imgs = sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n)))
    return {'files': files, 'images': imgs}


def _diff(old: str, new: str, label: str) -> str:
    return ''.join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=label + ' (before)', tofile=label + ' (after)', n=2))


def _build(op: str, style_id: str, before: dict, after: dict, extra: dict) -> dict | None:
    bf, af = before['files'], after['files']
    paths = sorted(set(bf) | set(af))
    changes = []
    for rel in paths:
        old, new = bf.get(rel), af.get(rel)
        if old == new:
            continue
        changes.append({
            'path': rel,
            'kind': 'added' if old is None else 'removed' if new is None else 'modified',
            'before': old, 'after': new,
            'diff': _diff(old or '', new or '', rel),
        })
    img_added = sorted(set(after['images']) - set(before['images']))
    img_removed = sorted(set(before['images']) - set(after['images']))
    if not changes and not img_added and not img_removed:
        return None
    size = sum(len(c['before'] or '') + len(c['after'] or '') for c in changes)
    full_text = size <= MAX_ENTRY_CHARS
    if not full_text:
        # 极端批量操作只留 diff，避免运行时文件膨胀；明确标记不可还原
        for c in changes:
            c.pop('before', None)
            c.pop('after', None)
    now = datetime.now().astimezone()
    entry = {
        'op_id': now.strftime('%Y%m%d-%H%M%S') + '-' + op + '-' + str(now.microsecond)[:4],
        'op': op, 'style_id': style_id,
        'time': now.isoformat(timespec='seconds'),
        'extra': extra or {},
        'files': changes,
        'images_added': img_added, 'images_removed': img_removed,
        'revertable': full_text,
        'note': ('单条快照过大，只保存 diff，不能按文件还原' if not full_text else ''),
    }
    return entry


def _load() -> list:
    try:
        with open(history_fp(), encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(records: list):
    fp = history_fp()
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(fp), prefix='.hist-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(records[-MAX_RECORDS:], fh, ensure_ascii=False, indent=1)
        os.replace(tmp, fp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


@contextlib.contextmanager
def capture(op: str, style_id: str = '', extra: dict = None):
    """包住一次写操作；只在实际发生源文件变化时落一条历史记录。"""
    before = snapshot()
    try:
        yield
    finally:
        try:
            after = snapshot()
            entry = _build(op, style_id, before, after, extra or {})
            if entry:
                _save(_load() + [entry])
        except Exception as exc:  # 历史记录失败绝不能影响业务操作
            print('[history] 记录失败：%s' % exc)


def list_history(limit: int = 60) -> list:
    out = []
    for r in reversed(_load()):
        out.append({
            'op_id': r['op_id'], 'op': r['op'], 'style_id': r.get('style_id', ''),
            'time': r['time'], 'extra': r.get('extra', {}),
            'changed': len(r.get('files', [])),
            'paths': [c['path'] for c in r.get('files', [])],
            'images_added': len(r.get('images_added', [])),
            'images_removed': len(r.get('images_removed', [])),
            'revertable': r.get('revertable', False),
        })
        if len(out) >= limit:
            break
    return out


def detail(op_id: str) -> dict:
    for r in _load():
        if r['op_id'] == op_id:
            return r
    raise FileNotFoundError('找不到历史记录 %s' % op_id)


def _atomic_write(fp: str, text: str):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(fp), prefix='.revert-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
        os.replace(tmp, fp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def revert_file(op_id: str, rel_path: str) -> dict:
    """把单个文件还原到该操作之前的版本，并跑一次单文件校验。

    安全约束：
      1. 只还原「修改过」的文件；新增/删除走回收区，不在这里做危险操作
      2. 磁盘当前内容必须仍等于操作后版本，否则说明之后又编辑过，拒绝覆盖
      3. 写回后校验不过立即回滚
    """
    rec = detail(op_id)
    target = next((c for c in rec.get('files', []) if c['path'] == rel_path), None)
    if not target:
        return {'ok': False, 'error': '这条记录里没有该文件'}
    if target['kind'] != 'modified' or target.get('before') is None:
        return {'ok': False, 'error': '只支持还原「被修改」的文件；新增/删除请去回收区或 Git'}
    fp = ops.path(rel_path)
    current = _read_text(fp)
    if current != target.get('after'):
        return {'ok': False, 'error': '文件在此之后又被改过，为避免覆盖新编辑已拒绝还原'}
    validation = None
    failed = False
    # 还原本身也是一次可追溯的写操作：把快照放在写回之前
    with capture('revert', rec.get('style_id', ''), {'from': op_id, 'path': rel_path}):
        _atomic_write(fp, target['before'])
        if rel_path.endswith(('.yaml', '.yml')):
            validation = ops.validate_single(rel_path)
            if not validation['ok']:
                _atomic_write(fp, current)  # 前后一致 → 不会留下假记录
                failed = True
    if failed:
        return {'ok': False, 'error': '还原后的版本校验不通过，已回滚', 'validation': validation}
    ops.invalidate()
    return {'ok': True, 'path': rel_path, 'from': op_id,
            'diff': _diff(target['after'], target['before'], rel_path)}


def clear(confirm: bool) -> dict:
    if not confirm:
        return {'ok': False, 'error': '清空历史需要显式确认'}
    _save([])
    return {'ok': True, 'note': '历史记录已清空（不影响磁盘上的风格文件）'}
