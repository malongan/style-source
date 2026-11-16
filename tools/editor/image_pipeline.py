#!/usr/bin/env python3
"""配图处理：上传图 → full + thumb 双版本 WebP。

沿用仓库既有规则（原本在技能仓库的 convert_to_webp.py，主仓库里缺失）：
  - 文件名 {style_id}_{md5(原图字节)[:8]}.webp / .thumb.webp
  - 全尺寸最长边 1000、quality 85；缩略图最长边 400、quality 75
  - 8 位后缀必须整段锚定，禁止前缀模糊匹配（历史上有配图串号事故）
"""
from __future__ import annotations

import hashlib
import io
import os
import re

from PIL import Image

IMAGE_NAME_RE = re.compile(r'^(?P<id>.+)_(?P<suffix>[0-9A-Za-z]{8})(?P<thumb>\.thumb)?\.webp$')


def convert_bytes(data: bytes, style_id: str, out_dir: str) -> dict:
    """把上传的字节流转成两份 WebP，返回文件名与尺寸。同名同 hash 时幂等覆盖。"""
    if not data:
        raise ValueError('图片内容为空')
    suffix = hashlib.md5(data).hexdigest()[:8]
    img = Image.open(io.BytesIO(data)).convert('RGB')
    w, h = img.size
    if max(w, h) > 1000:
        ratio = 1000 / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    os.makedirs(out_dir, exist_ok=True)
    base = '%s_%s' % (style_id, suffix)
    full_name = base + '.webp'
    thumb_name = base + '.thumb.webp'
    full_path = os.path.join(out_dir, full_name)
    thumb_path = os.path.join(out_dir, thumb_name)
    img.save(full_path, 'WEBP', quality=85)
    thumb = img.copy()
    thumb.thumbnail((400, 400), Image.LANCZOS)
    thumb.save(thumb_path, 'WEBP', quality=75)
    return {
        'full': full_name,
        'thumb': thumb_name,
        'full_rel': 'images/styles_previews/' + full_name,
        'thumb_rel': 'images/styles_previews/' + thumb_name,
        'size': list(img.size),
        'source_size': [w, h],
        'bytes': len(data),
    }


def find_images(style_id: str, images_dir: str) -> list:
    """精确找出属于该 style_id 的配图（不借用前缀相同的他人配图）。"""
    if not os.path.isdir(images_dir):
        return []
    out = []
    for name in sorted(os.listdir(images_dir)):
        m = IMAGE_NAME_RE.match(name)
        if m and m.group('id') == style_id:
            out.append(name)
    return out


def find_legacy_images(style_id: str, images_dir: str) -> list:
    """历史 jpg/png 配图（老风格可能没有 WebP）。"""
    if not os.path.isdir(images_dir):
        return []
    pat = re.compile(r'^%s_[0-9A-Za-z]{8}\.(?:jpg|jpeg|png)$' % re.escape(style_id))
    return sorted(n for n in os.listdir(images_dir) if pat.match(n))
