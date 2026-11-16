#!/usr/bin/env python3
"""工具后端对仓库的操作层：只读盘点、调用既有脚本、影响面分析、Git 状态。

设计原则：本模块不重新实现任何校验规则，全部 subprocess 调 scripts/ 下的现有脚本。
支持 STYLE_SOURCE_ROOT 环境变量指向 /tmp 沙箱，便于完整自测而不碰真实仓库。
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time

import yaml

import yaml_patch
from image_pipeline import find_images, find_legacy_images

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(os.path.dirname(HERE))
PY = sys.executable
_CACHE = {'ts': 0.0, 'data': None}

GENERATED_FILES = [
    'data/styles.json',
    'data/styles_list.txt',
    'data/style_numbers.json',
    'data/style_timestamps.json',
    'gallery.html',
    'gallery.css',
    'gallery-runtime.js',
]


def root() -> str:
    return os.environ.get('STYLE_SOURCE_ROOT', DEFAULT_ROOT)


def path(*parts) -> str:
    return os.path.join(root(), *parts)


def styles_dir() -> str:
    return path('styles')


def images_dir() -> str:
    return path('images', 'styles_previews')


def run(args, timeout=180) -> dict:
    """在仓库根跑一条命令，返回 {ok, output, cmd}。"""
    try:
        proc = subprocess.run(args, cwd=root(), capture_output=True,
                              text=True, timeout=timeout)
        return {
            'ok': proc.returncode == 0,
            'code': proc.returncode,
            'output': (proc.stdout + proc.stderr).strip(),
            'cmd': ' '.join(args),
        }
    except subprocess.TimeoutExpired:
        return {'ok': False, 'code': -1, 'output': '命令超时', 'cmd': ' '.join(args)}
    except Exception as exc:
        return {'ok': False, 'code': -1, 'output': str(exc), 'cmd': ' '.join(args)}


def _load_styles_json() -> dict:
    try:
        with open(path('data', 'styles.json'), encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {'styles': [], 'meta': {}}


def _style_files() -> list:
    return sorted(
        p for p in glob.glob(path('styles', '*', '*.yaml'))
        if not os.path.basename(p).startswith('_')
    )


def _numbers_map() -> dict:
    """编号的持久真相源。迁移后 styles.json 尚未重建时，用它回退显示 ST 编号。"""
    try:
        with open(path('data', 'style_numbers.json'), encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def _code_of(index: dict, numbers: dict, sid: str) -> str:
    code = index.get(sid, {}).get('code', '')
    if code:
        return code
    n = numbers.get(sid)
    try:
        return 'ST%04d' % int(n)
    except (TypeError, ValueError):
        return str(n) if isinstance(n, str) else ''


def _local_thumb(sid: str) -> str:
    """迁移/换图后 styles.json 里还是旧 URL；优先用磁盘上真实存在的缩略图。"""
    for n in find_images(sid, images_dir()):
        if n.endswith('.thumb.webp'):
            return '/images/styles_previews/' + n
    return ''


def list_styles(force=False) -> list:
    """列表以磁盘 yaml 为准（新建后无需重建即可看见），编号/配图从 styles.json 合并。"""
    now = time.time()
    if not force and _CACHE['data'] is not None and now - _CACHE['ts'] < 5:
        return _CACHE['data']
    index = {s['id']: s for s in _load_styles_json().get('styles', [])}
    numbers = _numbers_map()
    out = []
    for fp in _style_files():
        sid = os.path.basename(fp)[:-5]
        cat = os.path.basename(os.path.dirname(fp))
        item = {
            'id': sid,
            'category': cat,
            'name': sid,
            'code': _code_of(index, numbers, sid),
            'prompt': '',
            'variables': [],
            'tags': [],
            'preview': index.get(sid, {}).get('preview_webp', ''),
            'thumb': index.get(sid, {}).get('preview_webp_thumb', '') or _local_thumb(sid),
            'legacy': False,
            'errors': [],
        }
        try:
            with open(fp, encoding='utf-8') as fh:
                text = fh.read()
            data = yaml_patch.parse(text)
            item['name'] = data.get('name') or sid
            item['prompt'] = data.get('prompt') or ''
            item['tags'] = data.get('tags') or []
            item['variables'] = data.get('variables') or []
            item['category_file'] = data.get('category') or ''
            vars_raw = data.get('variables') or []
            item['legacy'] = (cat == 'vigo_cookbook' or
                              (isinstance(vars_raw, list) and
                               any(isinstance(v, str) for v in vars_raw)))
        except Exception as exc:
            item['errors'] = [str(exc)]
        item['has_image'] = bool(find_images(sid, images_dir()) or
                                 find_legacy_images(sid, images_dir()))
        item['var_count'] = len(item['variables']) if isinstance(item['variables'], list) else 0
        item['prompt_len'] = len(str(item['prompt']).strip())
        out.append(item)
    _CACHE['ts'] = now
    _CACHE['data'] = out
    return out


def invalidate():
    _CACHE['data'] = None
    _CACHE['ts'] = 0.0


def find_style_file(style_id: str):
    hits = [p for p in _style_files() if os.path.basename(p)[:-5] == style_id]
    return hits[0] if hits else None


def read_style(style_id: str) -> dict:
    fp = find_style_file(style_id)
    if not fp:
        raise FileNotFoundError('找不到风格 %s' % style_id)
    with open(fp, encoding='utf-8') as fh:
        text = fh.read()
    data = yaml_patch.parse(text)
    index = {s['id']: s for s in _load_styles_json().get('styles', [])}
    numbers = _numbers_map()
    return {
        'id': style_id,
        'path': os.path.relpath(fp, root()),
        'category': os.path.basename(os.path.dirname(fp)),
        'text': text,
        'data': data,
        'code': _code_of(index, numbers, style_id),
        'preview': index.get(style_id, {}).get('preview_webp', '') or _local_thumb(style_id),
        'images': find_images(style_id, images_dir()),
        'legacy_images': find_legacy_images(style_id, images_dir()),
        'top_keys': yaml_patch.top_keys(text),
    }


def validate_single(rel_path: str) -> dict:
    """编辑/新建后的单文件闸门：R1–R7 + YAML 卫生。"""
    v = run([PY, 'scripts/validate_style.py', '--require-desc', rel_path])
    h = run([PY, 'scripts/lint_hygiene.py', '--strict'])
    return {
        'ok': v['ok'] and h['ok'],
        'validate': v,
        'hygiene': h,
    }


def check_new(name: str, url: str = '', prompt: str = '') -> dict:
    """必须在写文件之前调用；写完后 --name 会命中自己产生假阳性。"""
    checks = {}
    checks['name'] = run([PY, 'scripts/check_duplicate.py', '--name', name])
    if url.strip():
        checks['url'] = run([PY, 'scripts/check_duplicate.py', '--url', url.strip()])
    if prompt.strip():
        checks['prompt'] = run([PY, 'scripts/check_duplicate.py', '--prompt', prompt.strip()[:4000]])
    # --name / --url 命中时输出 ❌；--prompt 相似度 >0.95 时只输出 ⚠️ 但 exit 1。
    # 只看字符串会让 prompt 查重形同虚设，所以退出码也必须算拦截依据。
    blocked = any((not c.get('ok')) or '❌' in c.get('output', '') for c in checks.values())
    warnings = [k for k, c in checks.items() if '⚠️' in c.get('output', '')]
    return {'ok': not blocked, 'checks': checks, 'blocked': blocked, 'warnings': warnings}


def impact(style_id: str) -> dict:
    """删除影响面清单。dry-run 与真正删除共用同一份计算结果。"""
    fp = find_style_file(style_id)
    imgs = find_images(style_id, images_dir()) + find_legacy_images(style_id, images_dir())
    try:
        with open(path('data', 'style_timestamps.json'), encoding='utf-8') as fh:
            ts_exists = style_id in json.load(fh)
    except Exception:
        ts_exists = False
    index = {s['id']: s for s in _load_styles_json().get('styles', [])}
    code = index.get(style_id, {}).get('code', '')
    return {
        'style_id': style_id,
        'code': code,
        'yaml': os.path.relpath(fp, root()) if fp else None,
        'images': ['images/styles_previews/' + n for n in imgs],
        'timestamp_entry': ts_exists,
        'number_entry': style_id,
        'generated': GENERATED_FILES + sorted(
            os.path.relpath(p, root()) for p in glob.glob(path('styles', '*', '_index.md'))
        ) + ['styles/_index.md'],
        'online_url': ('https://malongan.github.io/style-source/gallery.html?style=' + code
                       if code else ''),
    }


def timestamps_remove(style_id: str) -> bool:
    """generate_data.py 只读 timestamps，删除时的清理由工具补上。存量缺失不补。"""
    fp = path('data', 'style_timestamps.json')
    try:
        with open(fp, encoding='utf-8') as fh:
            data = json.load(fh)
        if style_id not in data:
            return False
        del data[style_id]
        with open(fp, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        return True
    except Exception:
        return False


def timestamps_add(style_id: str, stamp: str) -> bool:
    fp = path('data', 'style_timestamps.json')
    try:
        with open(fp, encoding='utf-8') as fh:
            data = json.load(fh)
        if style_id in data:
            return False
        data[style_id] = stamp
        with open(fp, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        return True
    except Exception:
        return False


def rebuild() -> dict:
    """显式重建：按 CI 顺序跑完 9 项闸门并重算全部生成物。"""
    result = run([PY, 'scripts/preflight.py'], timeout=300)
    invalidate()
    return result


def git_status() -> dict:
    r = run(['git', 'status', '--porcelain'], timeout=30)
    lines = [l for l in r.get('output', '').split('\n') if l.strip()]
    return {
        'ok': r['ok'],
        'lines': lines,
        'clean': not lines,
        'untouched': [l for l in lines if l.startswith('??')],
    }


def bootstrap() -> dict:
    data = _load_styles_json()
    numbers = {}
    try:
        with open(path('data', 'style_numbers.json'), encoding='utf-8') as fh:
            numbers = json.load(fh)
    except Exception:
        pass
    return {
        'root': root(),
        'total': len(_style_files()),
        'json_total': data.get('meta', {}).get('total', 0),
        'max_number': max(numbers.values()) if numbers else 0,
        'categories': sorted(os.path.basename(os.path.dirname(p)) for p in _style_files()),
        'git': git_status(),
        'sandbox': 'STYLE_SOURCE_ROOT' in os.environ,
    }
