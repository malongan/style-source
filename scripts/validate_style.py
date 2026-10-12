#!/usr/bin/env python3
"""校验风格 .yaml 文件格式规范。"""
from __future__ import annotations  # 允许 list[str]/X | None 注解在 3.8+ 上运行
import argparse
import os
import sys

try:
    import yaml
except ModuleNotFoundError:  # 缺依赖时给可照做的命令，而不是裸 traceback
    sys.exit('❌ 缺少依赖 pyyaml。请用以下方式运行：\n'
             '   uv run --with pyyaml python3 scripts/validate_style.py <文件>\n'
             '   （或 pip install pyyaml 后重试）')

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
    'code': str,          # ⚠️ 无效字段：generate_data.py 一律按收录顺序重算编号，yml 里写的会被覆盖
    'category': str,
    'scene': str,
    'ratio': str,
    'source_author': str,
    'source_url': str,
    'variables': list,
    'preview': str,       # 旧字段：仅在没有本地配图时兜底；当前配图一律从 images/ 解析
    # 以下为仓库已在用但长期未写进文档的字段
    'name_cn': str,
    'created_at': str,
    'verified_at': str,
}

VALID_CATEGORIES = [
    'social_media', 'brand_kv', 'e-commerce', 'science', 'print',
    'ip_character', 'travel', 'fashion', 'creative', 'vigo_cookbook', 'typography',
    'editorial',
]

# 详情页会直接复制 prompt；过短文本通常表示只留下标题或占位内容。
MIN_PROMPT_LENGTH = 80

# 旧版变量表头行（Markdown 表格转 yaml 时的残留），不是真实变量
VARIABLE_HEADER_ROWS = {('变量', '说明')}


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
    if not base_name.replace('_', '').isalnum():
        errors.append(f'文件名 "{filename}" 仅能包含字母、数字和下划线')

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
            # tags 特殊：generate_data.py 显式支持逗号分隔字符串，别把能跑的东西判死
            if field == 'tags' and isinstance(data[field], str):
                if not data[field].strip():
                    errors.append('字段 tags 为空字符串')
                else:
                    warnings.append('tags 用了逗号分隔字符串；建议改成 YAML 列表，可读且不易出错')
            else:
                errors.append(f'字段 {field} 类型错误: 期望 {expected_type.__name__}, 实际 {type(data[field]).__name__}')
        elif expected_type == str and not data[field].strip():
            errors.append(f'字段 {field} 为空字符串')
        elif expected_type == list and len(data[field]) == 0:
            warnings.append(f'字段 {field} 为空列表')

    # prompt 质量校验：它是详情页“复制提示词”的唯一内容来源。
    prompt = data.get('prompt', '')
    if isinstance(prompt, str) and prompt.strip() and len(prompt.strip()) < MIN_PROMPT_LENGTH:
        errors.append(f'字段 prompt 过短（至少 {MIN_PROMPT_LENGTH} 个字符，当前 {len(prompt.strip())}）')

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
                elif not str(feat.get('title') or '').strip():
                    warnings.append(f'features[{i}] 的 title 为空 —— 详情页会出现空条目')
            elif not isinstance(feat, str):
                errors.append(f'features[{i}] 类型错误: 期望 dict 或 str, 实际 {type(feat).__name__}')
            elif not feat.strip():
                warnings.append(f'features[{i}] 为空字符串')

    # variables 结构校验
    #   标准形态：[{kv_var, style_var, desc?}]   ← 新文件必须用这个
    #   旧形态：  ['中文标题'] / ['"{车型}" — 示例：…']  ← generate_data.py 能归一化，但请迁移
    variables = data.get('variables', [])
    if isinstance(variables, list):
        if variables and all(isinstance(v, str) for v in variables):
            warnings.append(
                'variables 使用了旧形态 list[str]，请迁移为标准形态 '
                '[{kv_var, style_var}]（旧形态虽可归一化，但无法表达英文替换值）')
        elif variables and any(isinstance(v, str) for v in variables):
            warnings.append('variables 混用了 dict 与 str 两种条目；请统一为标准形态')
        for i, v in enumerate(variables):
            if isinstance(v, dict):
                kv_var = str(v.get('kv_var', '') or '').strip()
                style_var = str(v.get('style_var', '') or '').strip()
                if not kv_var or not style_var:
                    errors.append(f'variables[{i}] 缺少 kv_var 或 style_var（两字段都必填）')
                elif (kv_var, style_var) in VARIABLE_HEADER_ROWS:
                    warnings.append(f'variables[{i}] 是 Markdown 表头残留（变量/说明），应删除')
            elif isinstance(v, str):
                if v.strip() in ('变量', '说明'):
                    warnings.append(f'variables[{i}] 是 Markdown 表头残留（变量/说明），应删除')
            else:
                errors.append(f'variables[{i}] 类型错误: 期望 dict 或 str, 实际 {type(v).__name__}')
    elif variables is not None:
        # mapping 形态：generate_data.py 只认列表，写成 {} 会被跳过（不是报错，是静默丢失）
        errors.append(f'variables 类型错误: 期望 list, 实际 {type(variables).__name__}'
                      '（generate_data.py 只解析列表，mapping 会被忽略）')

    # 来源校验：详情页要有出处。原文 URL 优先；确实没有链接时必须填作者。
    source_url = str(data.get('source_url') or '').strip()
    source_author = str(data.get('source_author') or '').strip()
    if not source_url and not source_author:
        errors.append('source_url 与 source_author 同时为空 —— 详情页将没有任何来源信息')
    elif not source_url:
        warnings.append('缺少 source_url（无链接时请确认 source_author 已填作者名）')

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

    had_errors = False
    if args.files:
        # 校验指定文件
        for filepath in args.files:
            errors, warnings = validate_file(filepath, check_images=args.check_images)
            if errors:
                had_errors = True
                print(f'❌ {filepath}:')
                for e in errors:
                    print(f'  - {e}')
            elif warnings:
                print(f'⚠️  {filepath}:')
                for w in warnings:
                    print(f'  - {w}')
            else:
                print(f'✅ {filepath}')
        sys.exit(1 if had_errors else 0)
    else:
        # 校验所有风格文件
        from validate_all import main as validate_all_main
        validate_all_main()


if __name__ == '__main__':
    main()
