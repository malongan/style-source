#!/usr/bin/env python3
"""校验单个风格 .md 文件的格式是否符合规范。"""
import sys
import os
import re
import argparse
from urllib.request import Request, urlopen
from urllib.error import URLError

REQUIRED_SECTIONS = [
    r'^\*\*标签\*\*',
    r'^\*\*触发词\*\*',
    r'^\*\*适用场景\*\*',
    r'^\*\*比例\*\*',
    r'^\*\*来源\*\*',
    # 来源链接 是新增规范，旧文件可能没有，不设为必填
    # r'^\*\*来源链接\*\*',
    r'^## 一句话理解',
    r'^## 核心特点',
    r'^## 完整模板',
    r'^## 变量使用指南',
    r'^## 参考配图',
]

WARN_ONLY_SECTIONS = {
    r'^\*\*来源链接\*\*': '来源链接',
}

def check_url_reachable(url: str) -> bool:
    """检查 URL 是否可访问（HEAD 请求返回 200/301）"""
    try:
        req = Request(url, method='HEAD')
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urlopen(req, timeout=10) as resp:
            return resp.status in (200, 301, 302)
    except (URLError, OSError):
        return False

def extract_variables(template_section: str) -> set:
    """从模板中提取所有 {{变量}}"""
    return set(re.findall(r'\{\{(\w+)\}\}', template_section))

def extract_variable_guide_vars(content: str) -> set:
    """从变量使用指南中提取已定义的变量名"""
    vars_found = set()
    in_guide = False
    for line in content.split('\n'):
        if line.strip().startswith('## 变量使用指南'):
            in_guide = True
            continue
        if in_guide and line.strip().startswith('## '):
            break
        if in_guide and '|' in line and '{{' in line:
            match = re.search(r'\{\{(\w+)\}\}', line)
            if match:
                vars_found.add(match.group(1))
    return vars_found

def extract_image_urls(content: str) -> list:
    """提取所有配图 URL"""
    return re.findall(r'!\[.*?\]\((https?://[^\s)]+)\)', content)

def validate_file(filepath: str, check_images: bool = False) -> tuple:
    """校验单个文件，返回 (errors, warnings) 元组。errors 为空才算通过。"""
    errors = []
    warnings = []
    filename = os.path.basename(filepath)
    dirname = os.path.basename(os.path.dirname(filepath))

    # 跳过自动生成的文件
    if filename.startswith('_'):
        return [], []

    # 1. 文件名规范
    if not re.match(r'^[a-z][a-z0-9_]*\.md$', filename):
        errors.append(f'文件名 "{filename}" 不符合 snake_case.md 规范')

    # 2. 读取内容
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 3. 分类目录检查
    valid_categories = [
        'social_media', 'brand_kv', 'e-commerce', 'science', 'print',
        'ip_character', 'travel', 'fashion', 'creative', 'vigo_cookbook'
    ]
    if dirname not in valid_categories and not dirname.startswith('_'):
        errors.append(f'文件 {filename} 在无效分类目录 "{dirname}" 中')

    # 4. 检查必填章节
    for pattern in REQUIRED_SECTIONS:
        if not re.search(pattern, content, re.MULTILINE):
            section_name = pattern.replace(r'^\*\*', '').replace(r'\*\*', '').replace(r'^## ', '')
            errors.append(f'缺少必填字段/章节: {section_name}')

    # 4b. 警告性检查（旧文件可能缺失，不报错只提醒）
    for pattern, name in WARN_ONLY_SECTIONS.items():
        if not re.search(pattern, content, re.MULTILINE):
            warnings.append(f'建议添加: {name}')

    # 5. 模板变量闭环检查
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

    # 6. 配图检查（旧文件可能用 raw.githubusercontent.com，只警告不报错）
    image_urls = extract_image_urls(content)
    if not image_urls:
        errors.append('参考配图中至少需要 1 张图片')
    else:
        for url in image_urls:
            if not url.startswith('https://malongan.github.io/images/'):
                warnings.append(f'配图 URL 建议迁移到 images 仓库: {url[:40]}...')
            if check_images and not check_url_reachable(url):
                warnings.append(f'配图 URL 不可访问: {url[:40]}...')

    # 7. 标签检查
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
    parser.add_argument('--check-images', action='store_true', help='检查配图 URL 可访问性')
    args = parser.parse_args()

    if not os.path.isfile(args.filepath):
        print(f'❌ 文件不存在: {args.filepath}')
        sys.exit(1)

    errors, warnings = validate_file(args.filepath, check_images=args.check_images)
    if warnings:
        for w in warnings:
            print(f'   ⚠️ {w}')
    if errors:
        print(f'❌ {os.path.basename(args.filepath)}:')
        for err in errors:
            print(f'   - {err}')
        sys.exit(1)
    else:
        print(f'✅ {os.path.basename(args.filepath)} 格式正确')
        sys.exit(0)

if __name__ == '__main__':
    main()
