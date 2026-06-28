#!/usr/bin/env python3
"""自动生成 styles/_index.md（基于实际文件扫描）。"""
import os
import re

STYLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')

CATEGORY_META = {
    'social_media': ('社交媒体', '📱', '小红书、朋友圈、头像'),
    'brand_kv': ('品牌视觉', '🎨', '品牌KV、公益态度'),
    'e-commerce': ('电商', '🛒', '产品主图、海报、美食'),
    'science': ('科研专业', '🔬', '信息图、期刊封面'),
    'print': ('印刷品', '📚', '书籍封面、电影海报'),
    'ip_character': ('IP/角色', '🎭', '吉祥物、头像、游戏'),
    'travel': ('旅行城市', '✈️', '旅行海报、城市'),
    'fashion': ('时尚美容', '👔', '时尚大片、美妆'),
    'creative': ('创意特殊', '🎪', '融合、复古、手绘'),
    'vigo_cookbook': ('VigoCookbook', '📖', '来自 Vigo Cookbook'),
}

def parse_yaml_file(filepath: str) -> dict:
    """读取 YAML 风格文件，返回结构化数据"""
    import yaml
    with open(filepath, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data or {}

def generate_category_index(cat_dir: str) -> str:
    """生成单个分类的 _index.md"""
    cat_name = os.path.basename(cat_dir)
    meta = CATEGORY_META.get(cat_name, (cat_name, '📁', ''))

    lines = [
        f'# {meta[0]}风格',
        '',
        f'> {meta[2]}',
        '',
        '| 风格 | 标签 | 适用场景 | 比例 |',
        '|------|------|----------|------|',
    ]

    for f in sorted(os.listdir(cat_dir)):
        if not f.endswith('.yaml') or f.startswith('_'):
            continue
        filepath = os.path.join(cat_dir, f)
        data = parse_yaml_file(filepath)
        name = f.replace('.yaml', '')
        tags_raw = data.get('tags', [])
        tags = ' '.join(f'#{t}' for t in tags_raw[:3]) if isinstance(tags_raw, list) else ''
        scene = data.get('scene', '')
        ratio = data.get('ratio', '')
        lines.append(f'| {name} | {tags} | {scene} | {ratio} |')

    lines.append('')
    return '\n'.join(lines)

def generate_main_index() -> str:
    """生成总 _index.md"""
    lines = [
        '# 风格索引',
        '',
        '> 快速预览所有可用风格，生成时按需加载详细文件',
        '',
        '---',
        '',
        '## 📂 分类目录',
        '',
        '| 分类 | 风格数 | 说明 |',
        '|------|--------|------|',
    ]

    total = 0
    for entry in sorted(os.listdir(STYLES_DIR)):
        entry_path = os.path.join(STYLES_DIR, entry)
        if not os.path.isdir(entry_path) or entry.startswith('_'):
            continue
        count = len([f for f in os.listdir(entry_path)
                     if f.endswith('.yaml') and not f.startswith('_')])
        meta = CATEGORY_META.get(entry, (entry, '📁', ''))
        lines.append(f'| {meta[1]} {meta[0]} | {count} | {meta[2]} |')
        total += count

    lines.extend([
        '',
        f'**总计：{total} 个风格文件**',
        '',
        '---',
        '',
    ])

    # 每个分类的详细列表
    for entry in sorted(os.listdir(STYLES_DIR)):
        entry_path = os.path.join(STYLES_DIR, entry)
        if not os.path.isdir(entry_path) or entry.startswith('_'):
            continue
        meta = CATEGORY_META.get(entry, (entry, '📁', ''))
        lines.extend([
            f'## {meta[1]} {meta[0]}',
            '',
            f'> [查看 {entry}/_index.md]({entry}/_index.md)',
            '',
            '| 风格 | 标签 | 适用场景 | 比例 |',
            '|------|------|----------|------|',
        ])
        for f in sorted(os.listdir(entry_path)):
            if not f.endswith('.yaml') or f.startswith('_'):
                continue
            filepath = os.path.join(entry_path, f)
            data = parse_yaml_file(filepath)
            name = f.replace('.yaml', '')
            tags_raw = data.get('tags', [])
            tags = ' '.join(f'#{t}' for t in tags_raw[:3]) if isinstance(tags_raw, list) else ''
            scene = data.get('scene', '')
            ratio = data.get('ratio', '')
            lines.append(f'| {name} | {tags} | {scene} | {ratio} |')
        lines.append('')

    return '\n'.join(lines)

def main():
    # 生成每个分类的 _index.md
    for entry in os.listdir(STYLES_DIR):
        entry_path = os.path.join(STYLES_DIR, entry)
        if not os.path.isdir(entry_path) or entry.startswith('_'):
            continue
        content = generate_category_index(entry_path)
        output_path = os.path.join(entry_path, '_index.md')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

    # 生成总 _index.md
    main_content = generate_main_index()
    main_path = os.path.join(STYLES_DIR, '_index.md')
    with open(main_path, 'w', encoding='utf-8') as f:
        f.write(main_content)

    print(f'✅ _index.md 已生成（总 {len(os.listdir(STYLES_DIR))-1} 个分类）')

if __name__ == '__main__':
    main()
