#!/usr/bin/env python3
"""风格库变量体检：检查 data/styles.json 里的 `variables` 与提示词里的 {占位符} 是否对得上。

为什么要它：插件只能替换**提示词里真实出现的** `{占位符}`，而 `variables` 只是给占位符配标签。
两边写法不一致时，插件不会报错，只会「填了没反应」或者「一个输入框都没有」——线上就出现过：
970 条变量里 625 条的值只是一句人话描述，另有 78 个风格提示词里有 {xxx} 却一条都没声明。

用法：
    python3 scripts/audit_variables.py            # 只看汇总 + 前 20 条问题
    python3 scripts/audit_variables.py --all      # 打印全部问题
    python3 scripts/audit_variables.py --json     # 机器可读
    python3 scripts/audit_variables.py --strict   # 连 warning 也算失败（提交前 / CI 用）
退出码：有 ERROR 级问题 → 1（`--strict` 时 warning 也 → 1），否则 0。
规范：docs/PROMPT_VARIABLES_SPEC.md
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STYLES_JSON = os.path.join(HERE, '..', 'data', 'styles.json')

PH_RE = re.compile(r'\{([^{}\n]{1,40})\}')


def is_placeholder_name(name: str) -> bool:
    """占位符名只能是一个短标识符：排掉 JSON 碎片、句子、空括号。"""
    if not name or len(name) > 40:
        return False
    if re.search(r'["\':,;{}\[\]\\]', name):
        return False
    if re.search(r'\s{2,}', name):
        return False
    return bool(re.search(r'[A-Za-z0-9\u4e00-\u9fa5]', name))


def prompt_placeholders(prompt: str):
    out = []
    seen = set()
    for m in PH_RE.finditer(prompt or ''):
        name = m.group(1).strip()
        if not is_placeholder_name(name) or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def strip_braces(text: str) -> str:
    return re.sub(r'\}+$', '', re.sub(r'^\{+', '', str(text or '').strip())).strip()


def audit(styles):
    errors, warnings, infos = [], [], []
    stat = {
        'total': len(styles),
        'with_prompt_ph': 0,
        'with_variables': 0,
        'no_ph_no_vars': 0,
        'vars_dead': 0,
        'vars_ok': 0,
        'kv_backtick': 0,
        'style_var_plain': 0,
        'styles_vars_all_dead': 0,
        # desc 覆盖率：只统计不拦截（存量缺口大，见 PROMPT_VARIABLES_SPEC §4）
        'var_total': 0,
        'var_with_desc': 0,
        'styles_no_desc': 0,
    }

    for s in styles:
        sid = s.get('id', '?')
        name = s.get('name', '')
        tag = f'{sid}（{name}）' if name else sid
        names = prompt_placeholders(s.get('prompt', ''))
        variables = s.get('variables') or {}
        descs = s.get('variable_descs') or {}
        if not isinstance(variables, dict):
            errors.append((tag, 'variables 不是 mapping（生成数据应统一成 {标签: 占位符}）'))
            continue

        if names:
            stat['with_prompt_ph'] += 1
        if variables:
            stat['with_variables'] += 1
        if not names and not variables:
            stat['no_ph_no_vars'] += 1
            continue

        matched = set()
        has_desc = False
        for label, value in variables.items():
            raw = str(value or '').strip()
            key = str(label or '').strip()
            stat['var_total'] += 1
            if str(descs.get(key) or '').strip():
                stat['var_with_desc'] += 1
                has_desc = True
            if '`' in key or '*' in key:
                stat['kv_backtick'] += 1
                warnings.append((tag, f'变量标签带 markdown 残留：{key!r} → 去掉反引号/星号'))
            cands = [strip_braces(raw), key.strip('`* ')]
            hit = next((c for c in cands if c and c in names), None)
            if hit is None:
                stat['vars_dead'] += 1
                near = '、'.join('{%s}' % n for n in names[:6]) or '（提示词里没有占位符）'
                warnings.append((tag, f'声明的变量「{key}」在提示词里找不到对应占位符；提示词实际用的是 {near}'))
                continue
            matched.add(hit)
            if '{' not in raw:
                stat['style_var_plain'] += 1
                infos.append((tag, f'变量「{key}」的值写成描述（{raw!r}），推荐写成占位符本体 "{{{hit}}}"'))
            if '{' + hit + '}' not in (s.get('prompt') or ''):
                errors.append((tag, f'占位符 {{{hit}}} 未出现在提示词里（数据不一致）'))

        stat['vars_ok'] += len(matched)
        if variables and not matched:
            stat['styles_vars_all_dead'] += 1
        if variables and not has_desc:
            stat['styles_no_desc'] += 1
        missing = [n for n in names if n not in matched]
        if names and not matched:
            warnings.append((tag, '提示词有 %d 个占位符但一条变量都没声明：%s'
                             % (len(names), '、'.join('{%s}' % n for n in names[:8]))))
        elif missing:
            infos.append((tag, '有 %d 个占位符没声明（插件会用占位符名当标签）：%s'
                          % (len(missing), '、'.join('{%s}' % n for n in missing[:8]))))

        if re.search(r'\[[A-Z][A-Z _]{2,}\]', s.get('prompt') or ''):
            infos.append((tag, '提示词用 [SQUARE_BRACKETS] 写法，插件只认 {花括号}，这些不会被替换'))

    return stat, errors, warnings, infos


def main():
    show_all = '--all' in sys.argv
    as_json = '--json' in sys.argv
    strict = '--strict' in sys.argv   # 连 warning 也算失败（推荐挂 CI / 提交前自检）
    with open(STYLES_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    styles = data.get('styles', [])
    stat, errors, warnings, infos = audit(styles)

    if as_json:
        print(json.dumps({'stat': stat, 'errors': errors, 'warnings': warnings, 'infos': infos},
                         ensure_ascii=False, indent=2))
        return 1 if (errors or (strict and warnings)) else 0

    print(f"共 {stat['total']} 个风格")
    print(f"  · 提示词里含 {{占位符}}：{stat['with_prompt_ph']}")
    print(f"  · 有 variables 声明：{stat['with_variables']}")
    print(f"  · 两者都没有（本来就无变量可填）：{stat['no_ph_no_vars']}")
    print(f"  · 声明命中提示词：{stat['vars_ok']} 条 / 声明落空：{stat['vars_dead']} 条"
          f"（涉及 {stat['styles_vars_all_dead']} 个风格全部落空）")
    print(f"  · 标签带反引号等残留：{stat['kv_backtick']} 条 / 值写成描述而非占位符：{stat['style_var_plain']} 条")
    pct = (100.0 * stat['var_with_desc'] / stat['var_total']) if stat['var_total'] else 0.0
    print(f"  · 变量带 desc：{stat['var_with_desc']}/{stat['var_total']} 条（{pct:.0f}%）"
          f" / 整条风格一条 desc 都没有：{stat['styles_no_desc']} 个")

    def dump(title, items):
        if not items:
            return
        print(f"\n{title}（{len(items)}）")
        for tag, msg in (items if show_all else items[:20]):
            print(f'  - {tag}: {msg}')
        if not show_all and len(items) > 20:
            print(f'  … 还有 {len(items) - 20} 条，用 --all 查看')

    dump('✗ 错误', errors)
    dump('⚠ 建议修', warnings)
    dump('· 提示', infos)
    print('\n写法规范见 docs/PROMPT_VARIABLES_SPEC.md（提交前建议 `--strict`）。')
    return 1 if (errors or (strict and warnings)) else 0


if __name__ == '__main__':
    sys.exit(main())
