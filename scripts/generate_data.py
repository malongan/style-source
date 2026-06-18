#!/usr/bin/env python3
"""从 styles/ 目录读取所有 .md 风格文件，生成 data/styles.json。"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

STYLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

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

    # 提取配图 URL（统一为数组格式）
    preview_urls = re.findall(r'!\[.*?\]\((https?://[^\s)]+)\)', content)
    # 过滤只保留合法仓库的 URL（兼容 images 旧仓库和 style-source 新仓库）
    preview_urls = [u for u in preview_urls if (
        'malongan.github.io/images/' in u or
        'malongan.github.io/style-source/images/' in u
    )]

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
        'preview_urls': preview_urls,  # 统一为数组
        'variables': variables,
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

if __name__ == '__main__':
    main()
