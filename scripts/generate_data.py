#!/usr/bin/env python3
"""从 styles/ 目录读取所有 .md 风格文件，生成 data/styles.json。"""
import json
import os
import re
import glob
import subprocess
import sys
from datetime import datetime, timezone

STYLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'images')
BASE_URL = 'https://malongan.github.io/style-source'
NUMBERS_FILE = os.path.join(DATA_DIR, 'style_numbers.json')


def get_version() -> str:
    """获取版本号：从 git tag 读取，无 tag 时返回 commit hash 或 v0.0.0"""
    try:
        version = subprocess.check_output(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        return version if version else 'v0.0.0'
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 'v0.0.0'


def find_image_in_repo(style_id: str):
    """在 images/ 下查找 style_id 对应的图片文件，返回相对于 images/ 的路径
    优先查找 WebP，其次 JPEG，最后 PNG"""
    patterns = [
        f'styles_previews/{style_id}_*.webp',    # 新风格：WebP 优先
        f'styles_previews/{style_id}_*.jpg',     # 旧风格：JPEG fallback
        f'styles_previews/{style_id}_*.png',     # PNG fallback
    ]
    for pat in patterns:
        # 排除 .thumb.webp（只找全尺寸）
        matches = [m for m in glob.glob(os.path.join(IMAGES_DIR, pat))
                   if not m.endswith('.thumb.webp')]
        if matches:
            return os.path.relpath(matches[0], IMAGES_DIR)
    return None


def resolve_image_url(style_id: str, yml_urls: list[str]) -> list[str]:
    """解析图片 URL：优先用 repo 里的文件，fallback 到 yml 中的 URL"""
    rel_path = find_image_in_repo(style_id)
    if rel_path:
        return [f'{BASE_URL}/images/{rel_path}']
    if yml_urls:
        return yml_urls
    return []


def resolve_image_webp(style_id: str) -> dict:
    """解析 WebP 版本 URL，返回 {'full': str|None, 'thumb': str|None}
    优先查找已有的 .webp 文件，兼容旧 .jpg/.png 源文件"""
    # 优先查找全尺寸 WebP
    webp_matches = glob.glob(os.path.join(IMAGES_DIR, f'styles_previews/{style_id}_*.webp'))
    webp_matches = [m for m in webp_matches if not m.endswith('.thumb.webp')]
    if webp_matches:
        base = os.path.splitext(os.path.basename(webp_matches[0]))[0]
        base_url = f'{BASE_URL}/images/styles_previews/{base}'
        thumb_path = os.path.join(IMAGES_DIR, 'styles_previews', f'{base}.thumb.webp')
        return {
            'full': f'{base_url}.webp',
            'thumb': f'{base_url}.thumb.webp' if os.path.exists(thumb_path) else None,
        }

    # Fallback：从旧 JPG/PNG 文件推导 WebP 文件名
    jpeg_matches = glob.glob(os.path.join(IMAGES_DIR, f'styles_previews/{style_id}_*.jpg'))
    png_matches = glob.glob(os.path.join(IMAGES_DIR, f'styles_previews/{style_id}_*.png'))
    matches = jpeg_matches or png_matches
    if not matches:
        return {'full': None, 'thumb': None}
    base = os.path.splitext(os.path.basename(matches[0]))[0]
    base_url = f'{BASE_URL}/images/styles_previews/{base}'
    return {
        'full': f'{base_url}.webp',
        'thumb': f'{base_url}.thumb.webp',
    }


def parse_style_file(filepath: str) -> dict:
    """解析单个 .md 文件，提取结构化数据"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    filename = os.path.basename(filepath).replace('.md', '')
    dirname = os.path.basename(os.path.dirname(filepath))

    # 提取标签
    tags_match = re.search(r'\*\*标签\*\*\s*[：:]\s*(.+)', content)
    tags = re.findall(r'#(\S+)', tags_match.group(1)) if tags_match else []

    # 提取场景
    scene_match = re.search(r'\*\*适用场景\*\*\s*[：:]\s*(.+)', content)
    scene = scene_match.group(1).strip() if scene_match else ''

    # 提取比例
    ratio_match = re.search(r'\*\*比例\*\*\s*[：:]\s*(.+)', content)
    ratio = ratio_match.group(1).strip() if ratio_match else ''

    # 提取来源
    source_match = re.search(r'\*\*来源\*\*\s*[：:]\s*(.+)', content)
    source_author = source_match.group(1).strip() if source_match else ''
    # 去掉开头的 @ 符号，保持统一
    source_author = source_author.lstrip('@').strip() if source_author else ''

    # 提取链接
    link_match = re.search(r'\*\*链接\*\*\s*[：:]\s*(.+)', content)
    source_url = link_match.group(1).strip() if link_match else ''

    # 提取一句话理解
    summary_match = re.search(r'## 一句话理解\s*\n(.+?)(?:\n|$)', content)
    summary = summary_match.group(1).strip() if summary_match else ''

    # 提取特点
    features = []
    in_features = False
    for line in content.split('\n'):
        if line.strip().startswith('## 核心特点'):
            in_features = True
            continue
        if in_features:
            if line.strip().startswith('## '):
                break
            if line.strip().startswith('- '):
                features.append(line.strip()[2:])

    # 提取配图 URL — 从 repo 文件自动匹配（优先），fallback 到 yml 中的 URL
    raw_urls = re.findall(r'!\[.*?\]\((https?://[^\s)]+)\)', content)
    normalized = []
    for u in raw_urls:
        if 'malongan.github.io/images/' in u or 'malongan.github.io/style-source/images/' in u:
            normalized.append(u)
        elif 'raw.githubusercontent.com/malongan/images/' in u:
            u_clean = u.replace('raw.githubusercontent.com/malongan/images/main/', 'malongan.github.io/images/')
            normalized.append(u_clean)
    # ★ 优先使用 repo 中的文件自动生成正确 URL（WebP 优先）
    preview_urls = resolve_image_url(filename, normalized)
    # ★ WebP 版本 URL
    webp_urls = resolve_image_webp(filename)

    # 提取变量
    variables = {}
    in_guide = False
    for line in content.split('\n'):
        if line.strip().startswith('## 变量使用指南'):
            in_guide = True
            continue
        if in_guide and line.strip().startswith('## '):
            break
        if in_guide and '|' in line and '{{' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3:
                var_match = re.search(r'\{\{(\w+)\}\}', parts[1])
                if var_match:
                    variables[var_match.group(1)] = parts[2]

    return {
        'id': filename,
        'name': filename.replace('_', ' ').title(),
        'category': dirname,
        'tags': tags,
        'scene': scene,
        'ratio': ratio,
        'summary': summary,
        'features': features,
        'preview_urls': preview_urls,  # 统一为数组（WebP 优先，兼容旧 JPG）
        'preview_webp': webp_urls['full'],   # WebP 全尺寸
        'preview_thumb': webp_urls['thumb'], # WebP 缩略图
        'variables': variables,
        'source_author': source_author,
        'source_url': source_url,
    }


def generate_styles_json(output_path: str):
    """生成 styles.json"""
    all_styles = []
    categories = set()

    for entry in sorted(os.listdir(STYLES_DIR)):
        entry_path = os.path.join(STYLES_DIR, entry)
        if not os.path.isdir(entry_path) or entry.startswith('_'):
            continue
        categories.add(entry)
        for f in sorted(os.listdir(entry_path)):
            if not f.endswith('.md') or f.startswith('_'):
                continue
            filepath = os.path.join(entry_path, f)
            try:
                style = parse_style_file(filepath)
                all_styles.append(style)
            except Exception as e:
                print(f'⚠️  跳过 {f}: {e}')

    # 排序（按文件名倒序，最新的优先）
    all_styles.sort(key=lambda s: s['id'], reverse=True)

    # 持久化编号：已有风格保持原编号，新风格分配下一个可用编号（永不重用）
    numbers_map = {}
    max_number = 0
    if os.path.exists(NUMBERS_FILE):
        with open(NUMBERS_FILE) as f:
            numbers_map = json.load(f)
        for v in numbers_map.values():
            # 支持字符串 'ST0151' 和整数 151 两种格式
            if isinstance(v, str):
                v = int(v.replace('ST', ''))
            max_number = max(max_number, v)

    existing_ids = {s['id'] for s in all_styles}
    # 清理已被删除风格的编号（不再占用数字）
    removed = [sid for sid in numbers_map if sid not in existing_ids]
    for sid in removed:
        del numbers_map[sid]

    next_number = max_number + 1 if max_number > 0 else 1
    for style in all_styles:
        sid = style['id']
        if sid in numbers_map:
            v = numbers_map[sid]
            if isinstance(v, str):
                v = int(v.replace('ST', ''))
            style['code'] = f'ST{v:04d}'
        else:
            numbers_map[sid] = next_number
            style['code'] = f'ST{next_number:04d}'
            next_number += 1

    # 持久化保存
    with open(NUMBERS_FILE, 'w') as f:
        json.dump(numbers_map, f, indent=2)
        f.write('\n')

    data = {
        'meta': {
            'version': get_version(),
            'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'total': len(all_styles),
            'categories': sorted(categories),
        },
        'styles': all_styles,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 统计数据
    webp_full = sum(1 for s in all_styles if s.get('preview_webp'))
    webp_thumb = sum(1 for s in all_styles if s.get('preview_thumb'))
    missing = sum(1 for s in all_styles if not s['preview_urls'])

    print(f'✅ 已生成 {output_path}')
    print(f'   风格总数: {len(all_styles)}')
    print(f'   分类数:   {len(categories)}')
    print(f'   版本:     {data["meta"]["version"]}')
    print(f'   图片: 本地 {sum(1 for s in all_styles if s["preview_urls"])}, 远程 0, 缺失 {missing}')
    print(f'   WebP: 全尺寸 {webp_full}, 缩略图 {webp_thumb}')

    # 检查缺失 WebP 的风格
    no_webp = [s['id'] for s in all_styles if not s.get('preview_webp')]
    if no_webp:
        print(f'   ⚠️  以下风格缺少 WebP: {", ".join(no_webp)}')

    return data


def generate_plain_list(all_styles: list) -> str:
    """生成纯文本列表"""
    lines = [f"共 {len(all_styles)} 个风格\n"]
    for i, s in enumerate(all_styles, 1):
        code = s.get('code', f'ST{i:04d}')
        name = s.get('name', '?')
        preview = s.get('preview_urls', [])
        url = preview[0] if preview else '(无图片)'
        lines.append(f'{code} | {name} | {url}')
    return '\n'.join(lines)


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    data = generate_styles_json(os.path.join(DATA_DIR, 'styles.json'))
    list_path = os.path.join(DATA_DIR, 'styles_list.txt')
    with open(list_path, 'w', encoding='utf-8') as f:
        f.write(generate_plain_list(data['styles']))
    print(f'✅ 列表已生成 {list_path}')
