#!/usr/bin/env python3
"""校验风格 .md 文件格式规范。"""
import argparse
import os
import re
import sys
from urllib.request import urlopen, URLError
from urllib.parse import urlparse

REQUIRED_SECTIONS = [
    r'^\*\*标签\*\*',
    r'^\*\*触发词\*\*',
    r'^\*\*适用场景\*\*',
    r'^\*\*比例\*\*',
    r'^\*\*来源\*\*',
    r'^## 一句话理解',
    r'^## 核心特点',
    r'^## 完整模板',
    r'^## 变量使用指南',
    r'^## 参考配图',
]

WARN_ONLY_SECTIONS = {
    r'^\*\*来源链接\*\*': '来源链接',
}

# 合法的图片 URL 前缀
VALID_IMAGE_PREFIXES = (
    'https://malongan.github.io/images/',
    'https://malongan.github.io/style-source/images/',
)

def is_valid_image_url(url: str) -> bool:
    return any(url.startswith(p) for p in VALID_IMAGE_PREFIXES)

def check_url_reachable(url: str) -> bool:
    try:
        resp = urlopen(url, timeout=5)
        return resp.status in (200, 301, 302)
    except (URLError, OSError):
        return False

def extract_variables(text: str) -> set:
    return set(re.findall(r'\{\{(\w+)\}\}', text))

def extract_variable_guide_vars(content: str) -> set:
    vars_found = set()
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
                    vars_found.add(var_match.group(1))
    return vars_found

def extract_image_urls(content: str) -> list:
    return re.findall(r'!\[.*?\]\((https?://[^\s)]+)\)', content)

def validate_file(filepath: str, check_images: bool = False) -> tuple:
    """校验单个文件，返回 (errors, warnings) 元组。"""
    errors = []
    warnings = []
    filename = os.path.basename(filepath)
    dirname = os.path.basename(os.path.dirname(filepath))

    if filename.startswith('_'):
        return [], []

    if not re.match(r'^[a-z][a-z0-9_]*\.md$', filename):
        errors.append(f'文件名 "{filename}" 不符合 snake_case.md 规范')

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    valid_categories = [
        'social_media', 'brand_kv', 'e-commerce', 'science', 'print',
        'ip_character', 'travel', 'fashion', 'creative', 'vigo_cookbook'
    ]
    if dirname not in valid_categories and not dirname.startswith('_'):
        errors.append(f'文件 {filename} 在无效分类目录 "{dirname}" 中')

    for pattern in REQUIRED_SECTIONS:
        if not re.search(pattern, content, re.MULTILINE):
            section_name = pattern.replace(r'^\*\*', '').replace(r'\*\*', '').replace(r'^## ', '')
            errors.append(f'缺少必填字段/章节: {section_name}')

    for pattern, name in WARN_ONLY_SECTIONS.items():
        if not re.search(pattern, content, re.MULTILINE):
            warnings.append(f'建议添加: {name}')

    template_match = re.search(
        r'## 完整模板\s*\n\s*```(?:\w+)?\s*\n(.+?)\n\s*```',
        content, re.DOTALL
    )
    if template_match:
        template_vars = extract_variables(template_match.group(1))
        guide_vars = extract_variable_guide_vars(content)
        undefined_vars = template_vars - guide_vars
        if undefined_vars:
            errors.append(f'模板中有未在变量使用指南中定义的变量: {", ".join(sorted(undefined_vars)[:10])}')

    image_urls = extract_image_urls(content)
    if not image_urls:
        errors.append('参考配图中至少需要 1 张图片')
    else:
        for url in image_urls:
            if not is_valid_image_url(url):
                warnings.append(f'配图 URL 建议放入 style-source 或 images 仓库: {url[:40]}...')
            if check_images and not check_url_reachable(url):
                warnings.append(f'配图 URL 不可访问: {url[:40]}...')

    tags_match = re.search(r'\*\*标签\*\*\s*[：:]\s*(.+)', content)
    if tags_match:
        tags = re.findall(r'#(\S+)', tags_match.group(1))
        for tag in tags:
            if len(tag) > 20:
                warnings.append(f'标签 "#{tag[:15]}..." 超过 20 字符，建议精简')

    return errors, warnings

def main():
    parser = argparse.ArgumentParser(description='校验风格文件格式')
    parser.add_argument('filepath', help='风格文件路径')
    parser.add_argument('--check-images', action='store_true', help='检查配图 URL 可达性')
    args = parser.parse_args()

    if not os.path.isfile(args.filepath):
        print(f'❌ 文件不存在: {args.filepath}')
        sys.exit(1)

    errors, warnings = validate_file(args.filepath, check_images=args.check_images)

    filename = os.path.basename(args.filepath)
    if errors:
        print(f'❌ {filename} — {len(errors)} 个错误')
        for e in errors:
            print(f'  ✗ {e}')
    if warnings:
        print(f'⚠️  {filename} — {len(warnings)} 个建议')
        for w in warnings:
            print(f'  → {w}')
    if not errors and not warnings:
        print(f'✅ {filename} — 格式规范通过')

    sys.exit(1 if errors else 0)

if __name__ == '__main__':
    main()
