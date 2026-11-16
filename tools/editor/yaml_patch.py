#!/usr/bin/env python3
"""字段级 YAML 文本替换。

为什么不整文件 dump：库里的 yaml 带首行标题注释、末尾「# 配图」注释、
prompt 块标量、各文件字段顺序不一，还有 vigo_cookbook 的历史形态。
yaml.safe_dump 会丢注释、重排字段、改写引号，一次编辑就产生巨大 diff。

本模块按「顶层 key 区块」切分原始文本，只替换目标 key 的值区块：
  - 首个顶层 key 之前的文本（标题注释）原样保留
  - 区块之后的文本（末尾配图注释、空行）原样保留
  - 未涉及的字段字节不变
"""
from __future__ import annotations

import json
import re

import yaml

KNOWN_TOP_KEYS = {
    'name', 'id', 'code', 'category', 'tags', 'triggers', 'features',
    'scene', 'ratio', 'summary', 'prompt', 'variables', 'source_url',
    'source_author', 'preview', 'name_cn', 'created_at', 'verified_at',
    'source', 'derived_from', 'variables_guide',
}
SCALAR_KEYS = {
    'name', 'id', 'code', 'category', 'scene', 'ratio', 'summary',
    'source_url', 'source_author', 'preview', 'name_cn', 'created_at',
    'verified_at', 'source', 'derived_from',
}
TOP_KEY_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):')


def _q(value) -> str:
    """用 JSON 双引号字符串做 YAML 标量，转义规则与 YAML 双引号兼容。"""
    if value is None:
        value = ''
    return json.dumps(str(value), ensure_ascii=False)


def _plain_safe(v) -> bool:
    """值能否安全地写成 YAML 无引号纯标量（库里多数 tags 用这种写法）。"""
    s = str(v)
    if not s or s != s.strip() or '\n' in s:
        return False
    if s[0] in '-?:,[]{}#&*!|>\'"%@`':
        return False
    if ': ' in s or ' #' in s:
        return False
    if s.lower() in ('true', 'false', 'null', 'yes', 'no', 'on', 'off', '~'):
        return False
    if re.fullmatch(r'[-+]?[0-9]+(\.[0-9]+)?', s):
        return False
    return True


def render_field(key: str, value, list_style: str = None) -> list:
    """把单个字段渲染成文本行（不含区块后的空行）。

    list_style='plain' 时 tags/triggers 用无引号列表项，跟随原文件写法；
    否则用 _q() 双引号。保留引号风格能避免「只加一个标签却重写整个区块」。
    """
    if key == 'prompt':
        lines = ['prompt: |']
        text = str(value or '').strip('\n')
        for ln in text.split('\n'):
            lines.append('  ' + ln if ln.strip() else '')
        return lines

    if key in SCALAR_KEYS:
        return ['%s: %s' % (key, _q(value))]

    if key in ('tags', 'triggers'):
        items = [v for v in (value or []) if str(v).strip()]
        if not items:
            return ['%s: []' % key]
        out = ['%s:' % key]
        if list_style == 'plain':
            out += ['  - ' + (str(v) if _plain_safe(v) else _q(v)) for v in items]
        else:
            out += ['  - ' + _q(v) for v in items]
        return out

    if key == 'features':
        items = value or []
        if not items:
            return ['features: []']
        out = ['features:']
        for feat in items:
            if isinstance(feat, dict):
                out.append('  - title: ' + _q(feat.get('title', '')))
                out.append('    desc: ' + _q(feat.get('desc', '')))
            else:
                out.append('  - ' + _q(feat))
        return out

    if key == 'variables':
        items = value or []
        if not items:
            return ['variables: []']
        out = ['variables:']
        for var in items:
            if isinstance(var, dict):
                out.append('  - kv_var: ' + _q(var.get('kv_var', '')))
                out.append('    style_var: ' + _q(var.get('style_var', '')))
                out.append('    desc: ' + _q(var.get('desc', '')))
            else:
                out.append('  - ' + _q(var))
        return out

    # 兜底：未知结构交给 safe_dump，缩进到 2 空格
    dumped = yaml.safe_dump(value, allow_unicode=True, sort_keys=False,
                            default_flow_style=False).rstrip('\n')
    out = ['%s:' % key]
    out += ['  ' + ln for ln in dumped.split('\n')]
    return out


def _marks(lines: list) -> list:
    """返回 [(行号, key)]，只认已知顶层字段，避免把 prompt 正文里的英文行误判成字段。"""
    out = []
    for i, line in enumerate(lines):
        m = TOP_KEY_RE.match(line)
        if m and m.group(1) in KNOWN_TOP_KEYS:
            out.append((i, m.group(1)))
    return out


def _last_value_line(lines: list, start: int, end: int) -> int:
    """找到区块内最后一行「值」。顶层注释、空行、区块后的杂散文本都不算值。"""
    last = start
    for i in range(start + 1, end):
        line = lines[i]
        if line.startswith('#'):
            continue
        if not line.strip():
            continue
        if line.startswith((' ', '\t')):
            last = i
        else:
            break
    return last


def replace_field(text: str, key: str, value) -> str:
    """替换单个顶层字段，返回新的完整文本。字段不存在时追加到文件末尾。"""
    lines = text.split('\n')
    marks = _marks(lines)
    hits = [j for j, (_i, k) in enumerate(marks) if k == key]
    if len(hits) > 1:
        raise ValueError('文件存在重复顶层键 %r，请先手工修好再编辑' % key)
    if not hits:
        appended = '\n'.join(render_field(key, value))
        return text.rstrip('\n') + '\n\n' + appended + '\n'

    j = hits[0]
    start = marks[j][0]
    end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
    last = _last_value_line(lines, start, end)
    trailing = lines[last + 1:end]

    list_style = None
    if key in ('tags', 'triggers'):
        old_items = [lines[i] for i in range(start + 1, last + 1)
                     if re.match(r'^  -\s', lines[i])]
        # 只有原区块全部是无引号项时才跟随；混合写法或 flow 形式交给默认渲染
        if old_items and all(not re.match(r'^  - "', line) for line in old_items):
            list_style = 'plain'

    new_lines = lines[:start] + render_field(key, value, list_style) + trailing + lines[end:]
    return '\n'.join(new_lines)


def _normalize(value):
    """比较用的规范化：字符串去首尾空白，容器递归。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    return value


def _equal(a, b) -> bool:
    return _normalize(a) == _normalize(b)


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple)):
        return len(value) == 0
    return False


def replace_fields(text: str, changes: dict, skip_unchanged: bool = True) -> str:
    """按给定顺序逐个替换字段；每次都重新定位，互不干扰。

    默认跳过「值没变」的字段 —— 否则一次只改 name 的保存会把全文件引号、
    缩进、prompt 块尾空行全部重写，diff 噪音大到没法 review。
    """
    current = {}
    if skip_unchanged:
        try:
            current = parse(text)
        except Exception:
            current = {}
    for key, value in changes.items():
        if skip_unchanged and key in current and _equal(current.get(key), value):
            continue
        # 表单会把所有可选字段都提交上来。老文件里没有 scene / source_url 这类字段时，
        # 空值不能当成「新增字段」追加，否则保存一次就凭空多出一行 `scene: ""`。
        if skip_unchanged and key not in current and _is_empty(value):
            continue
        text = replace_field(text, key, value)
        if skip_unchanged:
            try:
                current = parse(text)
            except Exception:
                current = {}
    return text


def parse(text: str) -> dict:
    """解析文本并顺手挡住 lint_hygiene R1（重复顶层键）。"""
    lines = text.split('\n')
    keys = [k for _i, k in _marks(lines)]
    dup = [k for k, n in _count(keys).items() if n > 1]
    if dup:
        raise ValueError('重复顶层键：%s' % ', '.join(dup))
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError('YAML 顶层不是 mapping')
    return data


def _count(items) -> dict:
    out = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return out


def top_keys(text: str) -> list:
    return [k for _i, k in _marks(text.split('\n'))]


def no_op_roundtrip(text: str) -> bool:
    """自测用：把每个字段用自身值重渲染一遍，检查文本是否完全不变。
    只有库里现有文件恰好都是本模块的标准格式时才会 True，用于回归验证。"""
    data = parse(text)
    out = text
    for key in top_keys(text):
        if key in data:
            out = replace_field(out, key, data[key])
    return out == text
