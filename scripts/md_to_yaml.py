#!/usr/bin/env python3
"""将 styles/ 下所有 .md 风格文件转换为 .yaml 格式。"""
import os
import re
import sys
import json
import yaml

STYLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')
NUMBERS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'style_numbers.json')


def load_style_numbers():
    """加载编号映射 {id: code}"""
    if not os.path.isfile(NUMBERS_FILE):
        return {}
    with open(NUMBERS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {entry['id']: entry['code'] for entry in data.get('styles', [])}


def parse_md_to_dict(filepath):
    """解析 .md 文件为结构化字典"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    filename = os.path.basename(filepath).replace('.md', '')
    category = os.path.basename(os.path.dirname(filepath))

    # 标题
    title_match = re.match(r'^#\s+(.+)', content)
    name = title_match.group(1).strip() if title_match else filename

    # 元数据字段
    def extract_field(pattern):
        m = re.search(pattern, content, re.MULTILINE)
        return m.group(1).strip() if m else ''

    # 标签
    tags_raw = extract_field(r'\*\*标签\*\*[：:]\s*(.+)')
    tags = [t.strip().lstrip('#') for t in re.split(r'[#＃\s]+', tags_raw) if t.strip()]

    # 触发词
    triggers_raw = extract_field(r'\*\*触发词\*\*[：:]\s*(.+)')
    triggers = [t.strip() for t in re.split(r'[、，,]+', triggers_raw) if t.strip()]

    # 场景
    scene = extract_field(r'\*\*适用场景\*\*[：:]\s*(.+)')

    # 比例
    ratio = extract_field(r'\*\*比例\*\*[：:]\s*(.+)')

    # 来源
    source_author = extract_field(r'\*\*来源\*\*[：:]\s*(.+)')

    # 来源链接
    source_url = extract_field(r'\*\*来源链接\*\*[：:]\s*(.+)')

    # 一句话理解
    summary_match = re.search(r'##\s*一句话理解\s*\n+(.+?)(?:\n+---|\n+##)', content, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else ''

    # 核心特点
    features = []
    features_match = re.search(r'##\s*核心特点\s*\n+((?:- .+\n?)+)', content)
    if features_match:
        for line in features_match.group(1).strip().split('\n'):
            line = line.strip().lstrip('- ')
            bold_match = re.match(r'\*\*(.+?)\*\*\s*[—–\-]\s*(.+)', line)
            if bold_match:
                features.append({'title': bold_match.group(1), 'desc': bold_match.group(2)})
            elif line:
                features.append({'title': line, 'desc': ''})

    # 完整模板 (prompt)
    prompt_match = re.search(r'##\s*完整模板\s*\n+```\n(.+?)\n```', content, re.DOTALL)
    prompt = prompt_match.group(1).strip() if prompt_match else ''

    # 变量使用指南
    variables = []
    in_guide = False
    for line in content.split('\n'):
        if line.strip().startswith('## 变量使用指南'):
            in_guide = True
            continue
        if in_guide and line.strip().startswith('## '):
            break
        if in_guide and '|' in line and '---' not in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4 and parts[1] and parts[1] != 'KV套用时的变量':
                variables.append({
                    'kv_var': parts[1].strip(),
                    'style_var': parts[2].strip(),
                    'desc': parts[3].strip() if len(parts) > 3 else '',
                })

    # 参考配图 URL
    img_matches = re.findall(r'!\[.*?\]\((https?://[^\s)]+)\)', content)
    preview = img_matches[-1] if img_matches else ''

    return {
        'name': name,
        'category': category,
        'ratio': ratio,
        'source_author': source_author,
        'source_url': source_url,
        'summary': summary,
        'tags': tags,
        'triggers': triggers,
        'features': features,
        'variables': variables,
        'prompt': prompt,
        'preview': preview,
    }


def convert_all():
    """转换所有 .md 文件为 .yaml"""
    numbers = load_style_numbers()
    success = 0
    errors = []
    skipped = 0

    for root, dirs, files in os.walk(STYLES_DIR):
        for f in sorted(files):
            if not f.endswith('.md') or f.startswith('_'):
                continue

            filepath = os.path.join(root, f)
            filename = f.replace('.md', '')
            yaml_path = os.path.join(root, filename + '.yaml')

            try:
                data = parse_md_to_dict(filepath)
                data['id'] = filename
                data['code'] = numbers.get(filename, '')

                # 写入 YAML
                with open(yaml_path, 'w', encoding='utf-8') as out:
                    yaml.dump(data, out, allow_unicode=True, default_flow_style=False, sort_keys=False, width=200)

                # 验证可读
                with open(yaml_path, 'r', encoding='utf-8') as verify:
                    parsed = yaml.safe_load(verify)

                if not parsed or 'name' not in parsed:
                    errors.append((filepath, '转换后缺少 name 字段'))
                    os.remove(yaml_path)
                    continue

                success += 1
            except Exception as e:
                errors.append((filepath, str(e)))

    print(f'\n📊 转换结果:')
    print(f'  ✅ 成功: {success}')
    print(f'  ❌ 失败: {len(errors)}')
    if errors:
        for path, err in errors:
            print(f'    {os.path.relpath(path, STYLES_DIR)}: {err}')

    return success, errors


if __name__ == '__main__':
    convert_all()
