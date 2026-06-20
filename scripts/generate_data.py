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
    """在 images/ 下查找 style_id 对应的图片文件，返回相对于 images/ 的路径"""
    patterns = [
        f'styles_previews/{style_id}_*.jpg',
        f'styles_previews/{style_id}_*.png',
        f'styles_previews/{style_id}_*.webp',
    ]
    for pat in patterns:
        matches = glob.glob(os.path.join(IMAGES_DIR, pat))
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
    兼容 .jpg 和 .png 源文件（共用 hash，从同名 .webp/.thumb.webp 生成 URL）"""
    # 查找原始文件（优先 JPEG，其次 PNG）
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
    # 过滤掉过长的标签（描述性句子误标为标签，如 "A#retro#skate#zine..."）
    tags = [t for t in tags if len(t) <= 40]

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
    # ★ 优先使用 repo 中的文件自动生成正确 URL
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
        'preview_urls': preview_urls,  # 统一为数组（JPEG fallback）
        'preview_webp': webp_urls['full'],   # WebP 全尺寸
        'preview_thumb': webp_urls['thumb'], # WebP 缩略图
        'variables': variables,
        'source_author': source_author,  # 来源作者
        'source_url': source_url,        # 来源链接
    }

def scan_category(cat_dir: str) -> dict:
    """扫描一个分类目录，返回分类信息和风格列表"""
    cat_name = os.path.basename(cat_dir)
    styles = []
    for f in sorted(os.listdir(cat_dir)):
        if not f.endswith('.md') or f.startswith('_'):
            continue
        filepath = os.path.join(cat_dir, f)
        try:
            style = parse_style_file(filepath)
            styles.append(style)
        except Exception as e:
            print(f'⚠️  解析失败 {f}: {e}', file=sys.stderr)
    return cat_name, styles

def main():
    if not os.path.isdir(STYLES_DIR):
        print(f'❌ styles/ 目录不存在: {STYLES_DIR}')
        sys.exit(1)

    all_styles = []
    categories = {}

    for entry in sorted(os.listdir(STYLES_DIR)):
        entry_path = os.path.join(STYLES_DIR, entry)
        if not os.path.isdir(entry_path) or entry.startswith('_'):
            continue
        cat_name, styles = scan_category(entry_path)
        categories[cat_name] = {
            'count': len(styles),
        }
        all_styles.extend(styles)

    # 分类显示名和图标映射
    CATEGORY_META = {
        'social_media': {'name': '社交媒体', 'icon': '📱'},
        'brand_kv': {'name': '品牌视觉', 'icon': '🎨'},
        'e-commerce': {'name': '电商', 'icon': '🛒'},
        'science': {'name': '科研专业', 'icon': '🔬'},
        'print': {'name': '印刷品', 'icon': '📚'},
        'ip_character': {'name': 'IP/角色', 'icon': '🎭'},
        'travel': {'name': '旅行城市', 'icon': '✈️'},
        'fashion': {'name': '时尚美容', 'icon': '👔'},
        'creative': {'name': '创意特殊', 'icon': '🎪'},
        'vigo_cookbook': {'name': 'VigoCookbook', 'icon': '📖'},
    }

    # 合并分类信息
    for cat_name in categories:
        meta = CATEGORY_META.get(cat_name, {'name': cat_name, 'icon': '📁'})
        categories[cat_name].update(meta)

    # 生成总数据
    # 为每个风格分配固定编号码（4位数字，前缀ST方便识别）
    for i, style in enumerate(all_styles):
        style['code'] = f'ST{i+1:04d}'

    data = {
        'meta': {
            'version': get_version(),
            'total': len(all_styles),
            'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'categories': categories,
        },
        'styles': all_styles,
    }

    # 写入 data/styles.json
    os.makedirs(DATA_DIR, exist_ok=True)
    output_path = os.path.join(DATA_DIR, 'styles.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'✅ 已生成 {output_path}')
    print(f'   风格总数: {data["meta"]["total"]}')
    print(f'   分类数:   {len(categories)}')
    print(f'   版本:     {data["meta"]["version"]}')

    # 统计图片情况
    found = sum(1 for s in all_styles if s['preview_urls'] and BASE_URL in s['preview_urls'][0])
    missing = sum(1 for s in all_styles if not s['preview_urls'])
    remote = len(all_styles) - found - missing
    print(f'   图片: 本地 {found}, 远程 {remote}, 缺失 {missing}')

    # WebP 统计
    webp_full = sum(1 for s in all_styles if s.get('preview_webp'))
    webp_thumb = sum(1 for s in all_styles if s.get('preview_thumb'))
    if webp_full:
        print(f'   WebP: 全尺寸 {webp_full}, 缩略图 {webp_thumb}')

    if missing:
        print(f'\n⚠️  以下 {missing} 个风格无可用的图片：')
        for s in all_styles:
            if not s['preview_urls']:
                print(f'  - {s["code"]} {s["id"]}')

if __name__ == '__main__':
    main()
