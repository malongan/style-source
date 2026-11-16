#!/usr/bin/env python3
"""P2 · 改名 / 改分类迁移向导 + 配图替换。

为什么 P0 锁死这三个字段：它们不是普通字段，而是散落在 6 处的「身份」——
  styles/{category}/{id}.yaml 路径、yaml 内 id / category / # 配图 注释、
  images/styles_previews/{id}_{hash}.webp(+thumb)、
  data/style_numbers.json 的 key（编号按 id 保号）、data/style_timestamps.json 的 key。
迁移必须一次性改完，且失败整体回滚，否则会出现「编号被重新分配」或「配图串号」。

两条硬约束：
  - 保号：generate_data.py 用 style_numbers.json 的 key 认风格；只改 yaml 文件名
    而不同步迁移这个 key，旧条目会被当成「已删除」清掉、新 id 拿 max+1 的新编号。
  - 即时校验不跑 check_style_previews.py：它读的是生成物 styles.json，
    重建之前必然误报。配图完整性由本模块自己按文件名断言，preflight 在重建时兜底。
"""
from __future__ import annotations

import base64
import difflib
import io
import json
import os
import re
import shutil
import tempfile
from datetime import datetime

from PIL import Image

import image_pipeline
import ops
import yaml_patch
import yaml_template

ID_RE = re.compile(r'^[a-z0-9_]{3,80}$')
PREVIEW_COMMENT_RE = re.compile(r'^#\s*配图[:：].*$', re.M)
IMG_PREFIX_RE_TMPL = r'(images/styles_previews/)%s_'


def _atomic_write(fp: str, text: str):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(fp), prefix='.migrate-', suffix='.tmp')
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


def _json_load(rel: str) -> dict:
    fp = ops.path(rel)
    if not os.path.isfile(fp):
        return {}
    try:
        with open(fp, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def _read_raw(rel: str):
    fp = ops.path(rel)
    if not os.path.isfile(fp):
        return None
    with open(fp, encoding='utf-8') as fh:
        return fh.read()


def _write_json(rel: str, data: dict):
    fp = ops.path(rel)
    _atomic_write(fp, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def _restore_json(rel: str, raw):
    fp = ops.path(rel)
    if raw is None:
        if os.path.isfile(fp):
            os.remove(fp)
    else:
        _atomic_write(fp, raw)


def _insert_id(text: str, sid: str) -> str:
    """老文件可能没有 id 字段；插在首行标题注释之后，不追加到文件末尾。"""
    lines = text.split('\n')
    idx = 0
    while idx < len(lines) and (lines[idx].startswith('#') or not lines[idx].strip()):
        idx += 1
    lines.insert(idx, 'id: %s' % sid)
    if idx + 1 < len(lines) and lines[idx + 1].strip():
        lines.insert(idx + 1, '')
    return '\n'.join(lines)


def _set_identity_field(text: str, key: str, value: str) -> str:
    """改 id / category 时跟随原文件的标量写法：原来无引号就继续无引号。

    yaml_patch.render_field 一律输出双引号，迁移一个 id 会多出两行噪音 diff。
    """
    pat = re.compile(r'^%s:[ \t]*(.*)$' % re.escape(key), re.M)
    m = pat.search(text)
    if not m:
        return yaml_patch.replace_field(text, key, value)
    old_raw = m.group(1).strip()
    plain = bool(old_raw) and old_raw[0] not in ('"', "'", '|', '>', '[', '{')
    new_val = str(value) if (plain and yaml_patch._plain_safe(value)) else \
        json.dumps(str(value), ensure_ascii=False)
    return pat.sub(lambda mm: '%s: %s' % (key, new_val), text, count=1)


def _rewrite_preview_refs(text: str, old_id: str, new_id: str) -> str:
    """注释与 preview 旧字段里的配图路径都跟着改前缀；只匹配严格的图片路径模式。"""
    if old_id == new_id:
        return text
    pat = re.compile(IMG_PREFIX_RE_TMPL % re.escape(old_id))
    return pat.sub(lambda m: m.group(1) + new_id + '_', text)


def _image_renames(old_id: str, new_id: str) -> list:
    if old_id == new_id:
        return []
    names = (image_pipeline.find_images(old_id, ops.images_dir()) +
             image_pipeline.find_legacy_images(old_id, ops.images_dir()))
    out = []
    for n in names:
        prefix = old_id + '_'
        if not n.startswith(prefix):
            continue
        new_name = new_id + n[len(old_id):]
        out.append({
            'from': 'images/styles_previews/' + n,
            'to': 'images/styles_previews/' + new_name,
        })
    return out


# ---------------- 1. 改名 / 改分类迁移 ----------------
def analyze_migration(style_id: str, new_id: str, new_category: str) -> dict:
    """只算不写。dry-run 与真正应用共用同一份结果，避免预览与落盘不一致。"""
    new_id = str(new_id or '').strip()
    new_category = str(new_category or '').strip()
    info = ops.read_style(style_id)
    old_cat = info['category']
    old_rel = info['path']
    old_fp = ops.path(old_rel)
    new_rel = 'styles/%s/%s.yaml' % (new_category, new_id)
    new_fp = ops.path(new_rel)

    errors, warnings = [], []
    if not ID_RE.match(new_id):
        errors.append('新 id 不合法（只允许小写字母、数字、下划线，3–80 位）')
    if new_category not in yaml_template.VALID_CATEGORIES:
        errors.append('新分类必须是 12 个合法分类之一')
    if new_id == style_id and new_category == old_cat:
        errors.append('新 id 与分类都没有变化')
    if new_id != style_id:
        hit = ops.find_style_file(new_id)
        if hit:
            errors.append('风格 %s 已存在：%s' % (new_id, os.path.relpath(hit, ops.root())))
        if image_pipeline.find_images(new_id, ops.images_dir()) or \
                image_pipeline.find_legacy_images(new_id, ops.images_dir()):
            errors.append('已存在 %s 前缀的配图（孤儿图），请先处理' % new_id)
    if os.path.isfile(new_fp):
        errors.append('目标文件已存在：%s' % new_rel)

    numbers = _json_load('data/style_numbers.json')
    timestamps = _json_load('data/style_timestamps.json')
    kept_number = numbers.get(style_id, '')
    if new_id != style_id and new_id in numbers:
        errors.append('新 id 在 style_numbers.json 里已有编号 %s，会与保号冲突' % numbers[new_id])
    if new_id != style_id and new_id in timestamps:
        errors.append('新 id 在 style_timestamps.json 里已有条目，会覆盖旧时间戳')

    text = info['text']
    keys = info['top_keys']
    if 'id' in keys:
        text = _set_identity_field(text, 'id', new_id)
    else:
        text = _insert_id(text, new_id)
        warnings.append('原文件没有 id 字段，迁移时会按文件名补上一行')
    if new_category != old_cat:
        text = _set_identity_field(text, 'category', new_category)
    text = _rewrite_preview_refs(text, style_id, new_id)

    renames = _image_renames(style_id, new_id)
    for r in renames:
        if os.path.exists(ops.path(r['to'])):
            errors.append('目标配图已存在：%s' % r['to'])
    if not image_pipeline.find_images(style_id, ops.images_dir()) and renames:
        warnings.append('该风格没有标准 WebP 配图，只迁移到历史 jpg/png；重建后可能仍缺 full/thumb')

    try:
        yaml_patch.parse(text)
    except Exception as exc:
        errors.append('迁移后的 YAML 解析失败：%s' % exc)
    parsed = {}
    try:
        parsed = yaml_patch.parse(text)
    except Exception:
        pass
    if parsed.get('id') != new_id:
        errors.append('迁移后 id 字段不是 %s' % new_id)

    if kept_number:
        shown = 'ST%04d' % kept_number if isinstance(kept_number, int) else str(kept_number)
        warnings.append('编号 %s 会随 style_numbers.json 的 key 一起迁到新 id（保号）' % shown)
    else:
        warnings.append('该风格还没有分配编号，重建时才会分配')

    code = info['code'] or (('ST%04d' % kept_number) if isinstance(kept_number, int) else '')
    return {
        'ok': not errors,
        'errors': errors, 'warnings': warnings,
        'old': {'id': style_id, 'category': old_cat, 'path': old_rel,
                'code': code, 'images': ['images/styles_previews/' + n for n in
                                        image_pipeline.find_images(style_id, ops.images_dir())]},
        'new': {'id': new_id, 'category': new_category, 'path': new_rel},
        'yaml_diff': _diff(info['text'], text, old_rel + '  →  ' + new_rel),
        'new_text': text,
        'renames': renames,
        'metadata': {
            'numbers': bool(new_id != style_id and style_id in numbers),
            'timestamps': bool(new_id != style_id and style_id in timestamps),
            'kept_number': kept_number,
        },
        'generated': ops.GENERATED_FILES + ['styles/_index.md',
                                            'styles/%s/_index.md' % old_cat,
                                            'styles/%s/_index.md' % new_category],
        'online_url': ('https://malongan.github.io/style-source/gallery.html?style=' + code
                       if code else ''),
        'note': ('编号不回收、随 key 迁移，线上 ?style=STxxxx 链接保持不变；'
                 '但旧 yaml 路径与配图 URL 会失效。改完必须点「重建生成物」，'
                 'preflight 才会按新 id 校验配图引用。'),
    }


def commit_migration(style_id: str, new_id: str, new_category: str) -> dict:
    a = analyze_migration(style_id, new_id, new_category)
    if not a['ok']:
        return {'ok': False, 'errors': a['errors'], 'warnings': a['warnings']}

    old_rel, new_rel = a['old']['path'], a['new']['path']
    old_fp, new_fp = ops.path(old_rel), ops.path(new_rel)
    json_rels = ['data/style_numbers.json', 'data/style_timestamps.json']
    json_backup = {r: _read_raw(r) for r in json_rels}
    changed_json = [r for r in json_rels if a['metadata'][
        'numbers' if r.endswith('style_numbers.json') else 'timestamps']]
    old_text_backup = _read_raw(old_rel) or ''
    done_renames = []
    written_new_yaml = False
    removed_old_yaml = False

    def rollback():
        for item in reversed(done_renames):
            src, dst = ops.path(item['from']), ops.path(item['to'])
            if os.path.exists(dst) and not os.path.exists(src):
                os.rename(dst, src)
        for r, raw in json_backup.items():
            try:
                _restore_json(r, raw)
            except Exception:
                pass
        if written_new_yaml and os.path.isfile(new_fp):
            os.remove(new_fp)
        if removed_old_yaml and not os.path.isfile(old_fp):
            _atomic_write(old_fp, old_text_backup)

    try:
        # 1. 写新 yaml（先写新、后删旧，避免同 id 改分类时把刚写的文件删掉）
        _atomic_write(new_fp, a['new_text'])
        written_new_yaml = True
        if old_fp != new_fp:
            os.remove(old_fp)
            removed_old_yaml = True

        # 2. 配图改前缀
        for item in a['renames']:
            src, dst = ops.path(item['from']), ops.path(item['to'])
            if not os.path.isfile(src):
                continue
            os.rename(src, dst)
            done_renames.append(item)

        # 3. 迁移编号与时间戳的 key（保号的关键一步）
        for rel in changed_json:
            data = _json_load(rel)
            if style_id in data and new_id != style_id:
                data[new_id] = data.pop(style_id)
                _write_json(rel, data)

        # 4. 校验：单文件闸门 + 自有配图断言（不能跑依赖生成物的 check_style_previews）
        v = ops.validate_single(new_rel)
        if not v['ok']:
            raise RuntimeError('迁移后单文件校验未通过：%s\n%s' % (
                v['validate']['output'][-600:], v['hygiene']['output'][-400:]))
        parsed = yaml_patch.parse(_read_raw(new_rel) or '')
        if parsed.get('id') != new_id or parsed.get('category') != new_category:
            raise RuntimeError('迁移后的 id / category 不符合预期')
        imgs = image_pipeline.find_images(new_id, ops.images_dir())
        if a['renames'] and not any(n.endswith('.thumb.webp') for n in imgs):
            raise RuntimeError('迁移后缺少缩略图')
        if new_id != style_id and image_pipeline.find_images(style_id, ops.images_dir()):
            raise RuntimeError('旧 id 前缀的配图仍有残留')

        ops.invalidate()
        paths = [old_rel, new_rel] + [r['from'] for r in a['renames']] + \
                [r['to'] for r in a['renames']] + changed_json
        return {
            'ok': True, 'old_id': style_id, 'new_id': new_id,
            'old_path': old_rel, 'new_path': new_rel,
            'renames': a['renames'], 'metadata': a['metadata'],
            'diff': a['yaml_diff'], 'validation': v,
            'paths': sorted(set(paths)), 'warnings': a['warnings'],
            'hint': a['note'],
        }
    except Exception as exc:
        rollback()
        ops.invalidate()
        return {'ok': False, 'error': str(exc), 'rolled_back': True,
                'warnings': a['warnings'], 'diff': a['yaml_diff']}


# ---------------- 2. 配图替换 ----------------
def _decode_image(image: dict) -> bytes:
    if not image or not image.get('data'):
        raise ValueError('请先上传 1 张新配图')
    raw = base64.b64decode(str(image['data']).split(',')[-1])
    if not raw:
        raise ValueError('图片内容为空')
    # 先验证是真图片，避免落盘后才发现坏文件
    Image.open(io.BytesIO(raw)).verify()
    return raw


def analyze_replace(style_id: str, image: dict = None) -> dict:
    info = ops.read_style(style_id)
    d = ops.images_dir()
    old = (image_pipeline.find_images(style_id, d) +
           image_pipeline.find_legacy_images(style_id, d))
    result = {
        'ok': True, 'style_id': style_id, 'yaml': info['path'],
        'old_images': ['images/styles_previews/' + n for n in old],
        'unchanged': False, 'errors': [], 'warnings': [],
    }
    if not old:
        result['warnings'].append('该风格当前没有配图，替换操作等同补图')
    if image:
        try:
            raw = _decode_image(image)
            import hashlib
            suffix = hashlib.md5(raw).hexdigest()[:8]
            im = Image.open(io.BytesIO(raw))
            size = list(im.size)
            new_full = '%s_%s.webp' % (style_id, suffix)
            result['new_images'] = ['images/styles_previews/' + new_full,
                                    'images/styles_previews/%s_%s.thumb.webp' % (style_id, suffix)]
            result['source_size'] = size
            result['unchanged'] = new_full in old
            if result['unchanged']:
                result['warnings'].append('新图与原图内容一致（md5 相同），无需替换')
        except Exception as exc:
            result['ok'] = False
            result['errors'].append(str(exc))
    result['yaml_will_change'] = bool(PREVIEW_COMMENT_RE.search(info['text']) or
                                      info['data'].get('preview'))
    result['note'] = ('旧图会移入回收区（可一键还原），新图按 md5 前 8 位生成 full + thumb；'
                      'yaml 的 # 配图 注释同步更新。改完必须点「重建生成物」更新 styles.json 的配图 URL。')
    return result


def commit_replace(style_id: str, image: dict) -> dict:
    a = analyze_replace(style_id, image)
    if not a['ok']:
        return {'ok': False, 'errors': a['errors']}
    if a['unchanged']:
        return {'ok': True, 'unchanged': True, 'note': '新图与原图内容一致，未做任何改动'}
    try:
        raw = _decode_image(image)
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}

    info = ops.read_style(style_id)
    yaml_rel = info['path']
    yaml_backup = info['text']
    batch = datetime.now().strftime('%Y%m%d-%H%M%S') + '_img_' + style_id
    dest = os.path.join(ops.path('tools', 'editor', '.trash'), batch)
    moved = []
    new_files = []
    manifest_written = False
    try:
        # 1. 先把旧图整体移进回收区，保证新图同名时也不会覆盖丢原图
        os.makedirs(dest, exist_ok=True)
        for rel in a['old_images']:
            src = ops.path(rel)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(dest, rel.replace('/', '__'))
            shutil.move(src, dst)
            moved.append({'from': rel, 'to': os.path.relpath(dst, ops.root())})
        manifest = {
            'batch': batch, 'style_id': style_id, 'code': info['code'],
            'time': datetime.now().astimezone().isoformat(timespec='seconds'),
            'moved': moved, 'timestamp': None,
            'note': '配图替换时移走的旧图；还原会把它们移回原位（新图需自行清理）',
        }
        with open(os.path.join(dest, 'manifest.json'), 'w', encoding='utf-8') as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        manifest_written = True

        # 2. 生成新图
        meta = image_pipeline.convert_bytes(raw, style_id, ops.images_dir())
        new_files = [ops.path('images', 'styles_previews', meta['full']),
                     ops.path('images', 'styles_previews', meta['thumb'])]

        # 3. 更新 yaml：配图注释 + 旧 preview 字段
        text = info['text']
        comment = '# 配图: %s' % meta['full_rel']
        if PREVIEW_COMMENT_RE.search(text):
            text = PREVIEW_COMMENT_RE.sub(comment, text)
        else:
            text = text.rstrip('\n') + '\n\n' + comment + '\n'
        old_preview = str(info['data'].get('preview') or '')
        if old_preview:
            # 旧 preview 常是线上 URL，保留 host 只换文件名，别把它降级成本地相对路径
            new_preview = (old_preview.rsplit('/', 1)[0] + '/' + meta['full']
                           if old_preview.startswith('http') else meta['full_rel'])
            text = yaml_patch.replace_field(text, 'preview', new_preview)
        yaml_patch.parse(text)
        _atomic_write(ops.path(yaml_rel), text)

        # 4. 校验（同样不跑依赖生成物的 check_style_previews）
        v = ops.validate_single(yaml_rel)
        if not v['ok']:
            raise RuntimeError('替换后校验未通过：%s\n%s' % (
                v['validate']['output'][-600:], v['hygiene']['output'][-400:]))
        imgs = image_pipeline.find_images(style_id, ops.images_dir())
        if meta['full'] not in imgs or meta['thumb'] not in imgs:
            raise RuntimeError('新配图 full / thumb 不完整')

        ops.invalidate()
        return {
            'ok': True, 'style_id': style_id, 'batch': batch,
            'old_images': a['old_images'], 'new_images': [meta['full_rel'], meta['thumb_rel']],
            'images': meta, 'validation': v,
            'diff': _diff(yaml_backup, text, yaml_rel),
            'paths': [yaml_rel] + a['old_images'] + [meta['full_rel'], meta['thumb_rel']],
            'hint': a['note'],
        }
    except Exception as exc:
        # 整体回滚：删新图 → 旧图移回原位 → 恢复 yaml → 清掉空批次
        for fp in new_files:
            if os.path.isfile(fp):
                os.remove(fp)
        for item in reversed(moved):
            src, dst = ops.path(item['from']), ops.path(item['to'])
            if os.path.isfile(dst) and not os.path.exists(src):
                shutil.move(dst, src)
        _atomic_write(ops.path(yaml_rel), yaml_backup)
        if manifest_written and os.path.isdir(dest):
            shutil.rmtree(dest)
        ops.invalidate()
        return {'ok': False, 'error': str(exc), 'rolled_back': True}
