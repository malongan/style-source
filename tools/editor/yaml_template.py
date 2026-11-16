#!/usr/bin/env python3
"""新建风格：从结构化表单数据渲染完整 yaml 文本。

新建和编辑走两条路径 —— 新文件没有「保留历史注释」的约束，可以直接整份渲染。
字段顺序与最近收录的标准文件保持一致；不写 code 字段（generate_data.py 会重算，写了是死代码）。
"""
from __future__ import annotations

import re

from yaml_patch import render_field

STYLE_ID_RE = re.compile(r'^[a-z][a-z0-9_]{2,79}$')

FIELD_ORDER = [
    'id', 'name', 'category', 'tags', 'triggers', 'features',
    'scene', 'ratio', 'summary', 'prompt', 'variables',
    'source_url', 'source_author',
]

REQUIRED_FIELDS = ('name', 'tags', 'triggers', 'summary', 'features', 'prompt')

VALID_CATEGORIES = [
    'social_media', 'brand_kv', 'e-commerce', 'science', 'print',
    'ip_character', 'travel', 'fashion', 'creative', 'vigo_cookbook',
    'typography', 'editorial',
]

MAX_VARIABLES = 12
MIN_PROMPT_LENGTH = 80


def check_form(style: dict) -> list:
    """前端提交后的硬校验，返回错误文案列表。脚本校验仍由 validate_style.py 把关。"""
    errors = []
    sid = str(style.get('id', '')).strip()
    if not STYLE_ID_RE.match(sid):
        errors.append('id 必须是小写字母开头、只含 a-z/0-9/_ 的 3–80 位 snake_case')
    if style.get('category') not in VALID_CATEGORIES:
        errors.append('分类必须是 12 个合法分类之一')
    for key in ('name', 'summary'):
        if not str(style.get(key, '')).strip():
            errors.append('缺少必填字段 %s' % key)
    prompt = str(style.get('prompt', '')).strip()
    if len(prompt) < MIN_PROMPT_LENGTH:
        errors.append('prompt 至少 %d 字（当前 %d）' % (MIN_PROMPT_LENGTH, len(prompt)))
    for key in ('tags', 'triggers', 'features'):
        if not style.get(key):
            errors.append('%s 不能为空' % key)

    variables = style.get('variables') or []
    if len(variables) > MAX_VARIABLES:
        errors.append('变量最多 %d 个（当前 %d）' % (MAX_VARIABLES, len(variables)))
    declared = set()
    for i, var in enumerate(variables):
        if not isinstance(var, dict):
            errors.append('variables[%d] 结构错误' % i)
            continue
        kv = str(var.get('kv_var', '')).strip()
        sv = str(var.get('style_var', '')).strip()
        desc = str(var.get('desc', '')).strip()
        if not kv or not sv or not desc:
            errors.append('variables[%d] 的 kv_var / style_var / desc 都必须填写' % i)
        if sv and not re.match(r'^\{[^{}\s]+\}$', sv):
            errors.append('variables[%d] 的 style_var 必须形如 {短名}' % i)
        declared.add(sv)
    used = set(re.findall(r'\{([^{}\n]{1,40})\}', prompt))
    for sv in declared:
        if sv[1:-1] not in used:
            errors.append('声明的 %s 没出现在 prompt 里（R1）' % sv)
    for name in used:
        if '{%s}' % name not in declared:
            errors.append('prompt 里的 {%s} 没有变量声明（R3）' % name)
    return errors


def render(style: dict, preview_rel: str = '') -> str:
    """渲染完整 yaml 文本；preview_rel 有值时在末尾补一行配图注释。"""
    lines = ['# ' + str(style.get('name', '')).strip(), '']
    for key in FIELD_ORDER:
        if key in ('scene', 'ratio', 'source_url', 'source_author') and not style.get(key):
            continue
        value = style.get(key)
        if value is None:
            continue
        lines.extend(render_field(key, value))
        lines.append('')
    text = '\n'.join(lines).rstrip('\n') + '\n'
    if preview_rel:
        text += '\n# 配图: %s\n' % preview_rel
    return text
