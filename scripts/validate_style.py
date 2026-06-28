#!/usr/bin/env python3
"""校验风格 .yaml 文件格式规范。"""
import argparse
import os
import sys
import yaml

REQUIRED_FIELDS = {
    'name': str,
    'tags': list,
    'triggers': list,
    'summary': str,
    'features': list,
    'prompt': str,
}

OPTIONAL_FIELDS = {
    'id': str,
    'code': str,
    'category': str,
    'scene': str,
    'ratio': str,
    'source_author': str,
    'source_url': str,
    'variables': list,
    'preview': str,
}

VALID_CATEGORIES = [
    'social_media', 'brand_kv', 'e-commerce', 'science', 'print',
    'ip_character', 'travel', 'fashion', 'creative', 'vigo_cookbook',
]


def validate_file(filepath: str, check_images: bool = False) -> tuple:
    """校验单个 .yaml 文件，返回 (errors, warnings) 元组。"""
    errors = []
    warnings = []
    filename = os.path.basename(filepath)
    dirname = os.path.basename(os.path.dirname(filepath))

    if filename.startswith('_'):
        return [], []

    # 文件名校验
    if not filename.endswith('.yaml'):
        errors.append(f'文件名 "{filename}" 不是 .yaml 格式')
        return errors, warnings

    base_name = filename[:-5]  # 去掉 .yaml
    if not base_name.replace('_', '').isalnum() or not base_name[0].isalpha():
        errors.append(f'文件名 "{filename}" 不符合 snake_case.yaml 规范')

    # 分类目录校验
    if dirname not in VALID_CATEGORIES and not dirname.startswith('_'):
        errors.append(f'文件 {filename} 在无效分类目录 "{dirname}" 中')

    # 读取 YAML
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        errors.append(f'YAML 解析失败: {e}')
        return errors, warnings
    except Exception as e:
        errors.append(f'文件读取失败: {e}')
        return errors, warnings

    if not data or not isinstance(data, dict):
        errors.append('YAML 文件为空或格式错误（需要 mapping）')
        return errors, warnings

    # 必填字段校验
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f'缺少必填字段: {field}')
        elif not isinstance(data[field], expected_type):
            errors.append(f'字段 {field} 类型错误: 期望 {expected_type.__name__}, 实际 {type(data[field]).__name__}')
        elif expected_type == str and not data[field].strip():
            errors.append(f'字段 {field} 为空字符串')
        elif expected_type == list and len(data[field]) == 0:
            warnings.append(f'字段 {field} 为空列表')

    # 标签校验
    tags = data.get('tags', [])
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                warnings.append(f'标签中存在空值')

    # features 结构校验
    features = data.get('features', [])
    if isinstance(features, list):
        for i, feat in enumerate(features):
            if isinstance(feat, dict):
                if 'title' not in feat:
                    errors.append(f'features[{i}] 缺少 title 字段')
            elif not isinstance(feat, str):
                errors.append(f'features[{i}] 类型错误: 期望 dict 或 str, 实际 {type(feat).__name__}')

    # variables 结构校验
    variables = data.get('variables', [])
    if isinstance(variables, list):
        for i, v in enumerate(variables):
            if isinstance(v, dict):
                if 'kv_var' not in v or 'style_var' not in v:
                    warnings.append(f'variables[{i}] 缺少 kv_var 或 style_var')

    # 图片 URL 校验（可选）
    if check_images:
        preview = data.get('preview', '')
        if preview:
            from urllib.request import urlopen, URLError
            try:
                resp = urlopen(preview, timeout=5)
                if resp.status not in (200, 301, 302):
                    warnings.append(f'预览图 URL 返回状态码 {resp.status}')
            except (URLError, OSError):
                warnings.append(f'预览图 URL 不可达: {preview[:60]}')

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description='校验风格 .yaml 文件格式')
    parser.add_argument('files', nargs='*', help='要校验的文件路径')
    parser.add_argument('--check-images', action='store_true', help='检查图片 URL 可达性')
    args = parser.parse_args()

    if args.files:
        # 校验指定文件
        for filepath in args.files:
            errors, warnings = validate_file(filepath, check_images=args.check_images)
            if errors:
                print(f'❌ {filepath}:')
                for e in errors:
                    print(f'  - {e}')
            elif warnings:
                print(f'⚠️  {filepath}:')
                for w in warnings:
                    print(f'  - {w}')
            else:
                print(f'✅ {filepath}')
    else:
        # 校验所有风格文件
        from validate_all import main as validate_all_main
        validate_all_main()


if __name__ == '__main__':
    main()
