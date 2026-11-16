#!/usr/bin/env python3
"""style-source 本地编辑工具（P0）。

启动：  /usr/bin/python3 tools/editor/server.py
访问：  http://127.0.0.1:8765

局域网（需口令）： /usr/bin/python3 tools/editor/server.py --lan
                   可选 --token <自定义口令>，不填则随机生成并打印

沙箱自测： STYLE_SOURCE_ROOT=/tmp/style-source-sandbox /usr/bin/python3 tools/editor/server.py --port 8766

边界：
  - 默认只监听 127.0.0.1，不联网、不发布；--lan 才绑 0.0.0.0 且强制访问口令
  - 保存只改 yaml（及新建时的配图），生成物一律由显式「重建」按钮触发
  - 绝不自动 git add -A / commit / push，变更中心只给精确路径清单
"""
from __future__ import annotations

import argparse
import base64
import difflib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import extensions  # noqa: E402
import history  # noqa: E402
import image_pipeline  # noqa: E402
import migrate  # noqa: E402
import normalize  # noqa: E402
import ops  # noqa: E402
import release  # noqa: E402
import yaml_patch  # noqa: E402
import yaml_template  # noqa: E402

STATIC_DIR = os.path.join(HERE, 'static')
SAFE_ID_RE = re.compile(r'^[a-z0-9_]+$')
LOCKED_FIELDS = {'id', 'category', 'preview', 'code'}
ALLOWED_STATIC = {'.html', '.css', '.js', '.svg', '.ico'}

SESSION_CHANGES = []
ACCESS_TOKEN = ''          # 空 = 默认本机模式，不做鉴权
LAN_MODE = False
LAN_URLS = []


def lan_ips() -> list:
    """列出本机非回环 IPv4，仅用于启动时提示访问地址（不发起任何网络连接）。"""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       socket.AF_INET, socket.SOCK_STREAM):
            ip = info[4][0]
            if ip and not ip.startswith('127.'):
                found.add(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('192.0.2.1', 9))          # UDP connect 不发包，只取出口地址
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith('127.'):
            found.add(ip)
    except Exception:
        pass
    # macOS 可能有多个活动网卡（Wi-Fi + 有线 / 扩展坞），逐个列出来
    if sys.platform == 'darwin':
        for _, name in (socket.if_nameindex() if hasattr(socket, 'if_nameindex') else []):
            if not name.startswith(('en', 'bridge')):
                continue
            try:
                ip = subprocess.check_output(
                    ['/usr/sbin/ipconfig', 'getifaddr', name],
                    stderr=subprocess.DEVNULL, text=True, timeout=2).strip()
                if ip and not ip.startswith('127.'):
                    found.add(ip)
            except Exception:
                continue      # 未启用的网卡取不到地址是正常的
    return sorted(found)


def trash_root() -> str:
    return os.path.join(ops.root(), 'tools', 'editor', '.trash')


def tracked(op: str, style_id: str, fn, extra: dict = None):
    """所有写操作统一走这一层：前后各做一次源文件快照，自动落一条历史记录。"""
    with history.capture(op, style_id, extra):
        return fn()


def record(op: str, style_id: str, paths: list, extra: dict = None):
    item = {
        'op': op,
        'id': style_id,
        'paths': sorted(set(p for p in paths if p)),
        'time': datetime.now().strftime('%H:%M:%S'),
    }
    if extra:
        item.update(extra)
    SESSION_CHANGES.append(item)


def atomic_write(fp: str, text: str):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(fp), prefix='.editor-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
        os.replace(tmp, fp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def unified_diff(old: str, new: str, label: str) -> str:
    return ''.join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=label + ' (before)', tofile=label + ' (after)', n=2))


class Handler(BaseHTTPRequestHandler):
    server_version = 'StyleEditor/0.1'

    def log_message(self, fmt, *args):
        sys.stderr.write('[%s] %s\n' % (self.log_date_time_string(), fmt % args))

    # ---------- 访问口令 ----------
    def _auth_ok(self, path: str) -> bool:
        """局域网模式下所有 /api/ 请求都要口令；静态资源与配图放行。

        口令走自定义头 X-Editor-Token：跨站 fetch 带自定义头会先触发 OPTIONS
        预检，而 do_OPTIONS 直接拒绝，因此顺带挡住了 CSRF。页面外壳本身
        不含数据，无口令也能加载，首次打开时由前端弹出口令框。
        """
        if not ACCESS_TOKEN or not path.startswith('/api/'):
            return True
        if path == '/api/auth/status':
            return True
        if hmac.compare_digest(self.headers.get('X-Editor-Token', ''), ACCESS_TOKEN):
            return True
        self._json({'error': '需要访问口令（见启动终端，或本机 .state/lan_token）',
                    'need_token': True, 'auth_required': True}, 401)
        return False

    def do_OPTIONS(self):
        # 不提供任何跨源能力，预检一律失败
        self._send(403, b'{}', 'application/json; charset=utf-8')

    # ---------- 基础响应 ----------
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'),
                   'application/json; charset=utf-8')

    def _static(self, rel: str):
        name = os.path.basename(rel) or 'index.html'
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED_STATIC:
            return self._json({'error': 'forbidden'}, 403)
        fp = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(fp):
            return self._json({'error': 'not found: ' + name}, 404)
        ctype = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
                 '.js': 'application/javascript; charset=utf-8',
                 '.svg': 'image/svg+xml', '.ico': 'image/x-icon'}[ext]
        with open(fp, 'rb') as fh:
            self._send(200, fh.read(), ctype)

    def _body(self) -> dict:
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0:
            return {}
        if length > 24 * 1024 * 1024:
            raise ValueError('请求体过大（>24MB）')
        raw = self.rfile.read(length)
        return json.loads(raw.decode('utf-8'))

    def _qs(self) -> dict:
        return parse_qs(urlparse(self.path).query)

    # ---------- 路由 ----------
    def do_GET(self):
        p = urlparse(self.path).path
        if not self._auth_ok(p):
            return
        try:
            if p == '/api/auth/status':
                return self._json({'auth_required': bool(ACCESS_TOKEN),
                                   'lan': LAN_MODE, 'urls': LAN_URLS})
            if p in ('/', '/index.html'):
                return self._static('index.html')
            if p.startswith('/static/'):
                return self._static(p[len('/static/'):])
            if p.startswith('/images/styles_previews/'):
                name = os.path.basename(p)
                if not re.match(r'^[A-Za-z0-9_.-]+$', name) or not name.endswith(
                        ('.webp', '.jpg', '.jpeg', '.png')):
                    return self._json({'error': 'forbidden'}, 403)
                fp = ops.path('images', 'styles_previews', name)
                if not os.path.isfile(fp):
                    return self._json({'error': 'not found'}, 404)
                ctype = ('image/webp' if name.endswith('.webp') else
                         'image/png' if name.endswith('.png') else 'image/jpeg')
                with open(fp, 'rb') as fh:
                    return self._send(200, fh.read(), ctype)
            if p == '/api/bootstrap':
                info = ops.bootstrap()
                info['categories'] = yaml_template.VALID_CATEGORIES
                info['locked_fields'] = sorted(LOCKED_FIELDS)
                info['freshness'] = extensions.freshness()
                info['drafts'] = len(extensions.list_drafts())
                info['trash'] = len(list_batches())
                return self._json(info)
            if p == '/api/styles':
                q = self._qs()
                term = (q.get('q', [''])[0] or '').strip().lower()
                cat = (q.get('cat', [''])[0] or '').strip()
                items = ops.list_styles()
                if cat and cat != 'all':
                    items = [s for s in items if s['category'] == cat]
                if term:
                    items = [s for s in items if term in s['id'].lower()
                             or term in str(s['name']).lower()
                             or term in str(s['code']).lower()
                             or term in str(s['prompt']).lower()]
                return self._json({'total': len(items), 'styles': items})
            if p.startswith('/api/style/'):
                sid = unquote(p[len('/api/style/'):])
                return self._json(ops.read_style(sid))
            if p.startswith('/api/impact/'):
                sid = unquote(p[len('/api/impact/'):])
                return self._json(ops.impact(sid))
            if p == '/api/trash':
                return self._json({'batches': list_batches()})
            if p.startswith('/api/trash/'):
                return self._json(extensions.trash_detail(unquote(p[len('/api/trash/'):])))
            if p == '/api/drafts':
                return self._json({'drafts': extensions.list_drafts()})
            if p.startswith('/api/draft/'):
                return self._json(extensions.get_draft(unquote(p[len('/api/draft/'):])))
            if p == '/api/freshness':
                return self._json(extensions.freshness())
            if p == '/api/changes':
                return self._json({'changes': SESSION_CHANGES,
                                   'generated': ops.GENERATED_FILES})
            if p == '/api/normalize/scan':
                return self._json(normalize.scan())
            if p == '/api/history':
                return self._json({'records': history.list_history()})
            if p.startswith('/api/history/'):
                return self._json(history.detail(unquote(p[len('/api/history/'):])))
            if p == '/api/git':
                return self._json(ops.git_status())
            if p == '/api/release/check':
                # 纯只读：只查 git 状态与生成物新鲜度，绝不执行写命令
                return self._json(release.check(
                    SESSION_CHANGES, ops.GENERATED_FILES, LAN_MODE))
            return self._json({'error': 'not found'}, 404)
        except FileNotFoundError as exc:
            return self._json({'error': str(exc)}, 404)
        except Exception as exc:
            return self._json({'error': '%s: %s' % (type(exc).__name__, exc)}, 500)

    def do_POST(self):
        p = urlparse(self.path).path
        if not self._auth_ok(p):
            return
        try:
            body = self._body()
            if p == '/api/style/check-new':
                return self._json(ops.check_new(
                    str(body.get('id', '')), str(body.get('source_url', '')),
                    str(body.get('prompt', ''))))
            if p == '/api/style':
                sid = str((body.get('style') or {}).get('id', ''))
                return self._json(tracked('create', sid, lambda: create_style(body)))
            if p == '/api/rebuild':
                r = tracked('rebuild', '', lambda: ops.rebuild())
                record('rebuild', '', ops.GENERATED_FILES)
                if r['ok']:
                    r['snapshot'] = extensions.write_snapshot()
                r['freshness'] = extensions.freshness()
                return self._json(r)
            if p == '/api/restore':
                batch = str(body.get('batch', ''))
                return self._json(tracked('restore', batch,
                                         lambda: restore_batch(batch), {'batch': batch}))
            if p == '/api/import/check':
                return self._json(extensions.analyze_import(
                    str(body.get('text', '')), str(body.get('filename', '')),
                    str(body.get('mode', 'normalized')),
                    str(body.get('id', '')), str(body.get('category', ''))))
            if p == '/api/import/commit':
                r = tracked('import', str(body.get('id', '')), lambda: extensions.commit_import(
                    str(body.get('text', '')), str(body.get('filename', '')),
                    str(body.get('mode', 'normalized')),
                    str(body.get('id', '')), str(body.get('category', '')),
                    body.get('image') or {}))
                if r.get('ok'):
                    record('import', r['id'], r['paths'], {'mode': r['mode']})
                return self._json(r)
            if p == '/api/draft':
                return self._json(extensions.save_draft(
                    body.get('style') or {}, str(body.get('id', ''))))
            if p.startswith('/api/draft/') and p.endswith('/publish'):
                did = unquote(p[len('/api/draft/'):-len('/publish')])
                draft = extensions.get_draft(did)
                style = draft.get('style') or {}
                r = tracked('draft-publish', str(style.get('id', '')),
                            lambda: create_style({'style': style, 'image': body.get('image') or {}}))
                if r.get('ok'):
                    extensions.delete_draft(did)
                    r['draft_deleted'] = did
                return self._json(r)
            if p == '/api/batch/tags':
                dry = bool(body.get('dry_run', True))
                call = lambda: extensions.batch_tags(
                    body.get('ids') or [], str(body.get('field', 'tags')),
                    str(body.get('action', 'add')), body.get('values') or [], dry)
                r = call() if dry else tracked(
                    'batch-tags', '%s/%s' % (body.get('field'), body.get('action')), call)
                if r.get('ok') and not dry:
                    record('batch-tags', '%s/%s' % (body.get('field'), body.get('action')),
                           r.get('paths', []), {'changed': r.get('changed', 0)})
                return self._json(r)
            if p == '/api/freshness/snapshot':
                return self._json(extensions.write_snapshot())

            # ---------- P2：迁移 / 换图 / 规范化 / 历史 ----------
            if p == '/api/migrate/check':
                return self._json(migrate.analyze_migration(
                    str(body.get('id', '')), str(body.get('new_id', '')),
                    str(body.get('new_category', ''))))
            if p == '/api/migrate/commit':
                old_id = str(body.get('id', ''))
                r = tracked('migrate', old_id, lambda: migrate.commit_migration(
                    old_id, str(body.get('new_id', '')), str(body.get('new_category', ''))),
                    {'new_id': str(body.get('new_id', ''))})
                if r.get('ok'):
                    record('migrate', old_id, r['paths'],
                           {'new_id': r['new_id'], 'batch': ''})
                return self._json(r)
            if p == '/api/image/check':
                return self._json(migrate.analyze_replace(
                    str(body.get('id', '')), body.get('image')))
            if p == '/api/image/replace':
                sid = str(body.get('id', ''))
                r = tracked('image-replace', sid,
                            lambda: migrate.commit_replace(sid, body.get('image') or {}))
                if r.get('ok') and not r.get('unchanged'):
                    record('image-replace', sid, r['paths'], {'batch': r['batch']})
                return self._json(r)
            if p == '/api/normalize/preview':
                return self._json(normalize.preview(body.get('ids') or [],
                                                    body.get('options') or {}))
            if p == '/api/normalize/apply':
                r = tracked('normalize', '', lambda: normalize.apply(
                    body.get('ids') or [], body.get('options') or {}))
                if r.get('ok') and r.get('changed'):
                    record('normalize', '', r['paths'], {'changed': r['changed']})
                return self._json(r)
            if p == '/api/history/revert':
                return self._json(history.revert_file(
                    str(body.get('op_id', '')), str(body.get('path', ''))))
            if p == '/api/history/clear':
                return self._json(history.clear(bool(body.get('confirm'))))
            return self._json({'error': 'not found'}, 404)
        except Exception as exc:
            return self._json({'error': '%s: %s' % (type(exc).__name__, exc)}, 500)

    def do_PUT(self):
        p = urlparse(self.path).path
        if not self._auth_ok(p):
            return
        try:
            if not p.startswith('/api/style/'):
                return self._json({'error': 'not found'}, 404)
            sid = unquote(p[len('/api/style/'):])
            body = self._body()
            return self._json(tracked('edit', sid, lambda: update_style(sid, body)))
        except FileNotFoundError as exc:
            return self._json({'error': str(exc)}, 404)
        except Exception as exc:
            return self._json({'error': '%s: %s' % (type(exc).__name__, exc)}, 500)

    def do_DELETE(self):
        p = urlparse(self.path).path
        if not self._auth_ok(p):
            return
        try:
            if p.startswith('/api/draft/'):
                return self._json(extensions.delete_draft(unquote(p[len('/api/draft/'):])))
            if p.startswith('/api/trash/'):
                confirm = self._qs().get('confirm', ['0'])[0] == '1'
                r = extensions.trash_purge(unquote(p[len('/api/trash/'):]), confirm)
                if r.get('ok'):
                    record('trash-purge', r['batch'], [])
                return self._json(r)
            if not p.startswith('/api/style/'):
                return self._json({'error': 'not found'}, 404)
            sid = unquote(p[len('/api/style/'):])
            dry = self._qs().get('dry_run', ['0'])[0] == '1'
            call = lambda: delete_style(sid, dry)
            return self._json(call() if dry else tracked('delete', sid, call))
        except Exception as exc:
            return self._json({'error': '%s: %s' % (type(exc).__name__, exc)}, 500)


# ---------- 业务操作 ----------
def update_style(style_id: str, body: dict) -> dict:
    if not SAFE_ID_RE.match(style_id):
        raise ValueError('非法 style id')
    info = ops.read_style(style_id)
    fp = ops.path(info['path'])
    old = info['text']

    if body.get('raw') is not None:
        new = str(body['raw'])
        yaml_patch.parse(new)  # 语法 + 重复键
    else:
        fields = body.get('fields') or {}
        locked = sorted(set(fields) & LOCKED_FIELDS)
        if locked:
            return {'ok': False, 'error': '锁定字段 %s 不能在表单里改：请用「改名/迁移」或「替换配图」向导，'
                                         '它们会同步处理文件名、配图前缀与编号保号' % ', '.join(locked)}
        unknown = sorted(set(fields) - set(yaml_template.FIELD_ORDER) - set(info['top_keys']))
        if unknown:
            return {'ok': False, 'error': '未知字段：%s' % ', '.join(unknown)}
        try:
            new = yaml_patch.replace_fields(old, fields)
            yaml_patch.parse(new)
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    if new == old:
        return {'ok': True, 'changed': False, 'diff': '', 'validation': {'ok': True}}

    # 写回后立即校验；失败用内存副本回滚，磁盘上不会留坏文件
    atomic_write(fp, new)
    result = ops.validate_single(info['path'])
    if not result['ok']:
        atomic_write(fp, old)
        return {'ok': False, 'rolled_back': True,
                'error': '校验未通过，已回滚', 'validation': result,
                'diff': unified_diff(old, new, info['path'])}

    ops.invalidate()
    record('edit', style_id, [info['path']])
    return {'ok': True, 'changed': True, 'diff': unified_diff(old, new, info['path']),
            'validation': result, 'path': info['path']}


def create_style(body: dict) -> dict:
    style = body.get('style') or {}
    sid = str(style.get('id', '')).strip()
    if not SAFE_ID_RE.match(sid):
        return {'ok': False, 'error': '非法 style id（只允许小写字母、数字、下划线）'}
    errors = yaml_template.check_form(style)
    if errors:
        return {'ok': False, 'errors': errors}
    if ops.find_style_file(sid):
        return {'ok': False, 'error': '风格 %s 已存在' % sid}
    if image_pipeline.find_images(sid, ops.images_dir()):
        return {'ok': False, 'error': '已存在同名配图，请先处理孤儿图'}

    dup = ops.check_new(sid, str(style.get('source_url', '')), str(style.get('prompt', '')))
    if dup['blocked']:
        return {'ok': False, 'error': '查重未通过（必须在写文件之前拦截）', 'checks': dup}

    image = body.get('image') or {}
    if not image.get('data'):
        return {'ok': False, 'error': '新建必须上传 1 张配图（--strict 要求 full + thumb 齐全）'}
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
        text = yaml_template.render(style, meta['full_rel'])
        yaml_fp = ops.path('styles', str(style['category']), sid + '.yaml')
        atomic_write(yaml_fp, text)
        rel = os.path.relpath(yaml_fp, ops.root())
        result = ops.validate_single(rel)
        if not result['ok']:
            raise RuntimeError('新建文件校验未通过：' + result['validate']['output'][-800:])
        stamp = datetime.now().astimezone().isoformat(timespec='seconds')
        ops.timestamps_add(sid, stamp)
        ops.invalidate()
        paths = [rel, meta['full_rel'], meta['thumb_rel'], 'data/style_timestamps.json']
        record('create', sid, paths)
        return {
            'ok': True, 'id': sid, 'path': rel, 'images': meta,
            'diff': unified_diff('', text, rel), 'validation': result,
            'warnings': dup['warnings'],
            'hint': '编号将在点「重建生成物」后由 generate_data.py 自动分配；提交前请核对生成物 diff',
        }
    except Exception as exc:
        # 全流程回滚：新建失败不留半套文件
        for fp in written:
            if os.path.exists(fp):
                os.remove(fp)
        if yaml_fp and os.path.exists(yaml_fp):
            os.remove(yaml_fp)
        ops.timestamps_remove(sid)
        ops.invalidate()
        return {'ok': False, 'error': str(exc), 'rolled_back': True}


def delete_style(style_id: str, dry: bool) -> dict:
    if not SAFE_ID_RE.match(style_id):
        raise ValueError('非法 style id')
    imp = ops.impact(style_id)
    if not imp['yaml']:
        return {'ok': False, 'error': '找不到风格 %s' % style_id}
    if dry:
        return {'ok': True, 'dry_run': True, 'impact': imp,
                'note': '确认后将 yaml + 配图移入回收区，并清理时间戳条目；编号不回收'}

    batch = datetime.now().strftime('%Y%m%d-%H%M%S') + '_' + style_id
    dest = os.path.join(trash_root(), batch)
    os.makedirs(dest, exist_ok=True)
    moved = []
    for rel in [imp['yaml']] + imp['images']:
        src = ops.path(rel)
        if not os.path.exists(src):
            continue
        dst = os.path.join(dest, rel.replace('/', '__'))
        shutil.move(src, dst)
        moved.append({'from': rel, 'to': os.path.relpath(dst, ops.root())})

    stamp = None
    fp = ops.path('data', 'style_timestamps.json')
    try:
        with open(fp, encoding='utf-8') as fh:
            ts = json.load(fh)
        if style_id in ts:
            stamp = ts[style_id]
    except Exception:
        pass
    ops.timestamps_remove(style_id)
    manifest = {
        'batch': batch, 'style_id': style_id, 'code': imp['code'],
        'time': datetime.now().astimezone().isoformat(timespec='seconds'),
        'moved': moved, 'timestamp': stamp,
        'note': '编号不回收；data/style_numbers.json 由 generate_data.py 在重建时清理',
    }
    with open(os.path.join(dest, 'manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    ops.invalidate()
    paths = [m['from'] for m in moved] + ['data/style_timestamps.json']
    record('delete', style_id, paths, {'batch': batch})
    return {'ok': True, 'batch': batch, 'impact': imp, 'moved': moved,
            'hint': '已移入回收区；点「重建生成物」后编号记录会被自动清理，线上旧链接将失效'}


def list_batches() -> list:
    base = trash_root()
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base), reverse=True):
        mf = os.path.join(base, name, 'manifest.json')
        if os.path.isfile(mf):
            try:
                with open(mf, encoding='utf-8') as fh:
                    out.append(json.load(fh))
            except Exception:
                pass
    return out


def restore_batch(batch: str) -> dict:
    if not re.match(r'^[\w.\-]+$', batch):
        return {'ok': False, 'error': '非法批次名'}
    mf = os.path.join(trash_root(), batch, 'manifest.json')
    if not os.path.isfile(mf):
        return {'ok': False, 'error': '找不到回收批次'}
    with open(mf, encoding='utf-8') as fh:
        manifest = json.load(fh)
    restored = []
    for item in manifest['moved']:
        src = ops.path(item['to'])
        dst = ops.path(item['from'])
        if not os.path.exists(src):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        restored.append(item['from'])
    if manifest.get('timestamp'):
        ops.timestamps_add(manifest['style_id'], manifest['timestamp'])
    ops.invalidate()
    record('restore', manifest['style_id'], restored, {'batch': batch})
    return {'ok': True, 'restored': restored, 'batch': batch}


def main():
    global ACCESS_TOKEN, LAN_MODE, LAN_URLS
    ap = argparse.ArgumentParser(description='style-source 本地编辑工具')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--host', default='127.0.0.1', help='监听地址（默认仅本机 127.0.0.1）')
    ap.add_argument('--lan', action='store_true',
                    help='绑定 0.0.0.0 开放局域网，并强制启用访问口令')
    ap.add_argument('--token', default='',
                    help='访问口令；--lan 时留空会自动生成（单独指定也可只加固本机模式）')
    args = ap.parse_args()
    if not os.path.isdir(STATIC_DIR):
        sys.exit('缺少 static/ 目录：' + STATIC_DIR)

    host = args.host
    LAN_MODE = bool(args.lan)
    if LAN_MODE:
        host = '0.0.0.0'
    ACCESS_TOKEN = args.token.strip() or (secrets.token_urlsafe(12) if LAN_MODE else '')
    if host in ('0.0.0.0', '', '::') and not ACCESS_TOKEN:
        sys.exit('拒绝无口令开放监听：请改用 --lan（自动生成口令）或显式传 --token')
    if ACCESS_TOKEN and LAN_MODE:
        LAN_URLS = ['http://%s:%d' % (ip, args.port) for ip in lan_ips()]
        # 只有自动生成的口令才回写文件；显式 --token 由调用方（editorctl）负责，
        # 避免临时测试实例把正式口令覆盖掉
        if not args.token.strip():
            token_file = os.path.join(ops.root(), 'tools', 'editor', '.state', 'lan_token')
            os.makedirs(os.path.dirname(token_file), exist_ok=True)
            with open(token_file, 'w', encoding='utf-8') as fh:
                fh.write(ACCESS_TOKEN + '\n')

    srv = ThreadingHTTPServer((host, args.port), Handler)
    print('style-source 编辑器已启动： http://%s:%d' % (host, args.port))
    if LAN_MODE:
        print('局域网访问已开启，需要访问口令')
        print('  访问口令： %s' % ACCESS_TOKEN)
        for u in LAN_URLS:
            print('  地址： %s' % u)
        print('  口令同时写入 tools/editor/.state/lan_token（已 gitignore，重启会更新）')
    elif ACCESS_TOKEN:
        print('已启用访问口令（仍只监听本机）')
    else:
        print('仅本机可访问，未启用口令')
    print('仓库根： %s%s' % (ops.root(), '  [沙箱]' if 'STYLE_SOURCE_ROOT' in os.environ else ''))
    print('Ctrl+C 退出')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
    finally:
        srv.server_close()


if __name__ == '__main__':
    main()
