#!/usr/bin/env python3
"""YAML 卫生检查：捞 validate / audit 都不会报的「静默问题」。

这三类问题 `yaml.safe_load` 全都不报错、CI 也全都不拦，只在人肉 review 或线上才发现：

  R1 重复的顶层键   —— 取后一个，前一个成死代码（2026-11 ST0172 实际踩过）
  R2 camelCase 槽位 —— 全库约定是「中文短名 / UPPER_SNAKE / snake_case」，camelCase 无先例
  R3 槽位语种错配   —— 中文正文里夹 {BRAND_NAME}、英文正文里夹 {主体}（插件能用，但读着割裂）
  R4 方括号当槽位   —— [UPPER_SNAKE] 这种写法插件不认（只认 {花括号}），等于没槽位

用法：
    python3 scripts/lint_hygiene.py            # 有人话问题就列出
    python3 scripts/lint_hygiene.py --strict   # warning 也算失败（preflight / CI 用）
    python3 scripts/lint_hygiene.py --all      # 不截断，打印全部

退出码：有 ERROR → 1；--strict 时 warning 也 → 1。
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLES = os.path.join(REPO, 'styles')

CJK = re.compile(r'[\u4e00-\u9fa5]')
SLOT = re.compile(r'\{([^{}\n]{1,40})\}')
BRACKET_NAME = re.compile(r'\[([A-Za-z][A-Za-z0-9_]{2,30})\]')  # 只认「像槽位名」的方括号
CAMEL = re.compile(r'^[a-z]+[A-Z][A-Za-z0-9]*$')

# 上游模板分类保留英文接口（{SUBJECT} 等），不参与语种一致性判定
EXEMPT_CATEGORIES = {'vigo_cookbook'}

TOP_KEYS = ('id', 'name', 'category', 'tags', 'triggers', 'features', 'scene',
            'ratio', 'summary', 'prompt', 'variables', 'source_url', 'source_author')


def zh_ratio(text: str) -> float:
    body = re.sub(r'\s+', '', text or '')
    return len(CJK.findall(body)) / len(body) if body else 0.0


def check_file(path: str) -> tuple:
    """返回 (errors, warnings)，每条是 (文件相对路径, 说明)。"""
    rel = os.path.relpath(path, REPO)
    errors, warnings = [], []
    try:
        raw = open(path, 'r', encoding='utf-8').read()
        data = yaml.safe_load(raw) or {}
    except Exception as exc:
        return [(rel, 'YAML 解析失败：%s' % exc)], []

    # R1 重复顶层键：数「行首」「key:」出现的次数
    for key in TOP_KEYS:
        n = len(re.findall(r'^%s\s*:' % re.escape(key), raw, re.M))
        if n > 1:
            errors.append((rel, 'R1 重复顶层键 %r 出现 %d 次（YAML 只取最后一个，其余是死代码）'
                           % (key, n)))

    prompt = data.get('prompt') or ''
    if not isinstance(prompt, str):
        return errors, warnings
    slots = sorted(set(SLOT.findall(prompt)))
    category = data.get('category') or ''

    # R2 camelCase
    for s in slots:
        if CAMEL.match(s):
            errors.append((rel, 'R2 camelCase 槽位 {%s}（改成中文短名 / UPPER_SNAKE / snake_case）' % s))

    # R3 槽位语种：同一风格内不混用中英两套体系（技能 Step 2.5 的硬约定）。
    # 不做正文语种阈值判断 —— 阈值会让「中文正文但英文占多数」的样本漏检。
    zh_slots = [s for s in slots if CJK.search(s)]
    en_slots = [s for s in slots if not CJK.search(s)]
    if zh_slots and en_slots:
        errors.append((rel, 'R3 槽位中英混用：中文 %s / 英文 %s（一次只能混一套体系）'
                       % (zh_slots, en_slots)))
    # R3b 正文中文但槽位全英文（上游模板分类豁免：vigo_cookbook 保留 {SUBJECT} 接口）
    elif category not in EXEMPT_CATEGORIES and en_slots and zh_ratio(prompt) >= 0.5:
        errors.append((rel, 'R3b 中文正文配英文槽位 %s（槽位语种应跟正文一致）' % en_slots))

    # R4 方括号当槽位（只报「像槽位名」的，避免误伤 [PROFILE / GLOW] / [规格一：…]）
    for b in sorted(set(BRACKET_NAME.findall(prompt))):
        warnings.append((rel, 'R4 方括号 [%s] 插件不认（应为 {%s}）' % (b, b)))

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description='YAML 卫生检查（重复键 / camelCase / 语种错配 / 方括号）')
    ap.add_argument('--strict', action='store_true', help='warning 也算失败')
    ap.add_argument('--all', action='store_true', help='打印全部问题（默认截断 40 条）')
    args = ap.parse_args()

    files = sorted(f for f in glob.glob(os.path.join(STYLES, '*', '*.yaml'))
                   if not os.path.basename(f).startswith('_'))
    all_err, all_warn = [], []
    for f in files:
        e, w = check_file(f)
        all_err += e
        all_warn += w

    def dump(title, items):
        if not items:
            return
        print()
        print('%s（%d 条）' % (title, len(items)))
        shown = items if args.all else items[:40]
        for rel, msg in shown:
            print('  %s' % rel)
            print('     %s' % msg)
        if len(items) > len(shown):
            print('  … 还有 %d 条（--all 看全部）' % (len(items) - len(shown)))

    print('检查了 %d 个风格文件' % len(files))
    dump('❌ ERROR', all_err)
    dump('⚠️  WARNING', all_warn)

    if not all_err and not all_warn:
        print('✅ 无卫生问题')
        return 0
    if all_err or (args.strict and all_warn):
        print()
        print('❌ 未通过（error %d / warning %d）' % (len(all_err), len(all_warn)))
        return 1
    print()
    print('✅ 通过（仅 warning %d，未加 --strict）' % len(all_warn))
    return 0


if __name__ == '__main__':
    sys.exit(main())

