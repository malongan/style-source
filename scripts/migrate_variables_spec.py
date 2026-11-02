#!/usr/bin/env python3
"""按 docs/PROMPT_VARIABLES_SPEC.md 整改 styles/**.yaml 的 variables。

设计原则（很重要）：
  1. **文本级编辑**，不用 yaml.dump 回写。yaml round-trip 会把缩进统一、
     把折行的 prompt 合并成一行，310 个文件全是假 diff，没法 review。
  2. **只碰占位符与 variables 段**：prompt 的措辞、配色、笔触、构图一律不动。
  3. 比例槽位不硬删，改用本文件 `ratio:` 字段的值替换成常量文本 ——
     「生成一张{比例}的饮品图」直接删会变成「生成一张的饮品图」，替换成
     「生成一张 16:9 的饮品图」才通顺。

做四件事：
  A. kv_var 剥掉反引号/星号（Vigo 批次 392 条）
  B. style_var 改成占位符本体 "{X}"；对不上的死声明直接删
  C. 比例类槽位替换成 ratio 常量，并删掉对应声明
  D. 方括号占位符里「明确是变量」的转花括号（段落标题/音标/描述句不动）

用法：
    python3 scripts/migrate_variables_spec.py --dry-run        # 只看统计与前若干个 diff
    python3 scripts/migrate_variables_spec.py --dry-run --diff 12
    python3 scripts/migrate_variables_spec.py --apply
"""
from __future__ import annotations

import argparse
import difflib
import glob
import os
import re
import sys

try:
    import yaml
except ModuleNotFoundError:
    sys.exit('❌ 缺少依赖 pyyaml：uv run --with pyyaml python3 scripts/migrate_variables_spec.py ...')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLE_GLOB = os.path.join(ROOT, 'styles', '*', '*.yaml')

PH_RE = re.compile(r'\{([^{}\n]{1,40})\}')

# 比例/尺寸类槽位：一律不做成变量（画布工具统一设定）
RATIO_SLOTS = {'ASPECT_RATIO', 'ASPECT RATIO', '比例', '画幅比例', '画幅', '尺寸比例'}

# 技术参数类槽位：是给模型看的元指令，不是给用户填的。
# spec 第 4 节要求「写成常量」——直接删会留下「...anchors: .」这种残句，
# 所以替换成一句常量说明，句子完整、槽位消失、声明随后自动变死声明被删。
TECH_CONST = {
    'STYLE_FIDELITY_ANCHORS': 'the core visual anchors of this style',
    'SOURCE_CONTENT_TO_AVOID': 'watermarks, real logos, and commercial advertising',
}

# 旧版 Markdown 表头残留，不是变量
HEADER_ROWS = {('变量', '说明'), ('变量', '')}

# 英文槽位 → 中文标签。只覆盖高频词，其余退化成「下划线转空格」。
LABELS = {
    'subject': '主体', 'subject_description': '主体描述', 'character': '角色',
    'character_description': '角色描述', 'person': '人物', 'people': '人物',
    'human': '人物', 'product': '产品', 'product_or_subject': '产品或主体',
    'object': '物体', 'animal': '动物', 'food': '食物',
    'headline': '主标题', 'title': '标题', 'main_text': '主文案',
    'subheadline': '副标题', 'subtitle': '副标题', 'subtitle_lines': '副标题',
    'tagline': '标语', 'slogan': '标语', 'short_slogan': '短标语',
    'brand': '品牌', 'brand_name': '品牌名', 'brand_mood': '品牌调性',
    'brand_subtitle': '品牌副标题', 'theme': '主题', 'destination': '目的地',
    'scene': '场景', 'scenery': '场景', 'scene_spec': '场景',
    'background': '背景', 'background_elements': '背景元素',
    'location': '地点', 'setting': '环境', 'text_spec': '文案',
    'main_copy': '主文案', 'secondary_text': '副文案',
    'extra_small_text': '小字文案', 'optional_short_text': '短文案',
    'color': '配色', 'colors': '配色', 'color_palette': '配色',
    'color1': '主色', 'color2': '辅色', 'color3': '点缀色', 'color4': '第四色',
    'palette': '配色', 'accent': '强调色', 'liquid_color': '液体颜色',
    'age': '年龄', 'pose': '姿态', 'hair': '发型', 'expression': '表情',
    'clothing': '服装', 'clothes': '服装', 'wardrobe_style': '服装造型',
    'style_keywords': '风格关键词', 'use_case': '用途',
    'size_requirement': '尺寸', 'ratio_spec': '比例',
    'collection_name': '系列名称', 'garment_type': '服装类型',
    'movie_title': '电影标题', 'japanese_title': '日文标题',
    'menu_name': '菜单名', 'price': '价格', 'name': '名称',
}


def clean_label(text: str) -> str:
    """去掉 markdown 残留（反引号/星号）与外围引号。"""
    return str(text or '').replace('`', '').replace('*', '').strip().strip('"\'').strip()


def strip_braces(text: str) -> str:
    return re.sub(r'\}+$', '', re.sub(r'^\{+', '', str(text or '').strip())).strip()


def is_placeholder_name(name: str) -> bool:
    if not name or len(name) > 40:
        return False
    if re.search(r'["\':,;{}\[\]\\]', name):
        return False
    if re.search(r'\s{2,}', name):
        return False
    return bool(re.search(r'[A-Za-z0-9\u4e00-\u9fa5]', name))


def prompt_slots(prompt: str) -> list:
    out, seen = [], set()
    for m in PH_RE.finditer(prompt or ''):
        name = m.group(1).strip()
        if is_placeholder_name(name) and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def first_ratio_value(ratio_field: str) -> str:
    """从 `ratio:` 字段取第一个规整比例值（如 '16:9 / 4:5' → '16:9'）。"""
    m = re.search(r'\d+\s*:\s*\d+', str(ratio_field or ''))
    return m.group(0).replace(' ', '') if m else ''


def is_clean_slot(name: str) -> bool:
    """能不能当变量名：纯英文标识符，或 1–8 字纯中文。

    `{填写主题，例如：灯影 / 折光}` 这类是作者写进 prompt 的说明书，
    补成输入框只会得到一个巨长标签 —— 不补，留给人工改 prompt。
    """
    if re.fullmatch(r'[A-Za-z0-9_]+', name):
        return True
    # 中文名允许带数字后缀（标题1 / 底色2）与单层斜杠（目的地/城市）
    cn = r'[\u4e00-\u9fa5][\u4e00-\u9fa5A-Za-z0-9]{0,9}'
    if re.fullmatch(cn + r'(/' + cn + r')?', name):
        return True
    return False


def label_for(slot: str) -> str:
    key = slot.strip().lower()
    if key in LABELS:
        return LABELS[key]
    # 本身是中文就直接用
    if re.search(r'[\u4e00-\u9fa5]', slot):
        return slot
    # 退化成「下划线转空格」
    return re.sub(r'[_-]+', ' ', slot).strip() or slot


def bracket_to_brace(name: str):
    """判断方括号内容能否安全转花括号。返回 (新名, 判定)。

    判定：
      'ok'       —— 纯字母数字下划线 / 纯中文短词，直接转
      'ratio'    —— 比例类，交给 ratio 常量替换，不转
      'skip'     —— 段落标题 / 音标 / 描述句，不是变量，原样保留
    """
    raw = name.strip()
    if not raw:
        return None, 'skip'
    # 比例类
    if re.fullmatch(r'[\d\s:/.]+', raw) or raw.upper() in RATIO_SLOTS:
        return None, 'ratio'
    # 音标
    if re.search(r'[ˈˌəɛɔʃʒθðŋɪʊæɑ]/', raw):
        return None, 'skip'
    # 中文+「如」= 变量带示例，走人工（不自动拆）
    if '如' in raw or '，' in raw:
        return None, 'skip'
    # 含冒号的是段落标题（「规格一：…」）
    if '：' in raw or ':' in raw:
        return None, 'skip'
    # 纯中文短词（≤8 字）
    if re.fullmatch(r'[\u4e00-\u9fa5]{1,8}', raw):
        return raw, 'ok'
    # 纯字母数字下划线（允许空格 → 下划线）
    if re.fullmatch(r'[A-Za-z0-9_]+(\s+[A-Za-z0-9_]+)*', raw):
        return re.sub(r'\s+', '_', raw), 'ok'
    return None, 'skip'


def parse_legacy_entry(entry: str):
    """解析旧形态 list[str] 条目：`"{占位符}" — 示例：xxx`。"""
    m = re.match(r'^\s*"?\s*(?P<name>\{[^{}]+\})\s*"?\s*(?:[—\-–:：]\s*)?(?:示例\s*[:：]?\s*)?(?P<desc>.*)$', entry)
    if m:
        return m.group('name').strip('{}'), m.group('desc').strip(), True
    if entry and len(entry) <= 24 and not re.search(r'[\s，。！？、/]', entry):
        return entry, '', True
    return None, '', False


def normalize_variables(raw, slots, ratio_value):
    """把 variables 条目规范化，返回 (entries, stats)。

    entries: [{'kv':..., 'sv':..., 'desc':...}]
    """
    stats = {'backtick': 0, 'desc_value': 0, 'dead': 0, 'ratio': 0, 'kept': 0, 'dirty': 0}
    entries = []

    items = raw if isinstance(raw, list) else []
    for item in items:
        if isinstance(item, dict):
            kv = clean_label(item.get('kv_var', ''))
            sv_raw = str(item.get('style_var', '') or '').strip()
            desc = str(item.get('desc', '') or '').strip()
            if '`' in str(item.get('kv_var', '')) or '*' in str(item.get('kv_var', '')):
                stats['backtick'] += 1
        elif isinstance(item, str):
            name, desc, ok = parse_legacy_entry(item)
            if not ok:
                continue
            kv, sv_raw = name, '{' + name + '}'
        else:
            continue

        if not kv:
            continue
        if (kv, sv_raw) in HEADER_ROWS:
            continue

        # 找这个声明到底对应哪个槽位
        sv_body = strip_braces(sv_raw)
        slot = None
        if sv_body and sv_body in slots:
            slot = sv_body
        elif kv in slots:
            slot = kv
        else:
            stats['dead'] += 1
            continue                      # 死声明：prompt 里没这个槽位，删掉

        # 比例槽位：不做变量
        if slot in RATIO_SLOTS:
            stats['ratio'] += 1
            continue

        if '{' not in sv_raw:
            stats['desc_value'] += 1
        entries.append({'kv': kv or label_for(slot), 'sv': '{' + slot + '}', 'desc': desc})
        stats['kept'] += 1

    # 去重（同一槽位只留一条，优先已有中文标签）
    seen = {}
    deduped = []
    for e in entries:
        if e['sv'] in seen:
            continue
        seen[e['sv']] = True
        deduped.append(e)

    # 补零声明：prompt 有槽位但没声明。脏槽位（说明书式占位符）不补。
    declared = {e['sv'] for e in deduped}
    for slot in slots:
        if slot in RATIO_SLOTS:
            continue
        if '{' + slot + '}' in declared:
            continue
        if not is_clean_slot(slot):
            stats['dirty'] += 1
            continue
        deduped.append({'kv': label_for(slot), 'sv': '{' + slot + '}', 'desc': '', 'added': True})

    return deduped, stats


def render_variables(entries, indent):
    """按原缩进风格渲染 variables 段（不含 `variables:` 行本身）。"""
    if not entries:
        return 'variables: []\n'
    pad = ' ' * indent
    lines = ['variables:']
    for e in entries:
        lines.append(f'{pad}- kv_var: {yaml_scalar(e["kv"])}')
        lines.append(f'{pad}  style_var: {yaml_scalar(e["sv"], force_quote=True)}')
        if e.get('desc'):
            lines.append(f'{pad}  desc: {yaml_scalar(e["desc"])}')
    return '\n'.join(lines) + '\n'


def yaml_scalar(value: str, force_quote: bool = False) -> str:
    """尽量保持裸标量（避免整段 diff 抖动），只在 YAML 真会误读时才加单引号。"""
    s = str(value or '')
    if s == '':
        return "''"
    if force_quote:
        return "'" + s.replace("'", "''") + "'"
    # 只有这些情况才必须引号：首字符是 YAML 指示符、含「冒号+空格」、含「空格+井号」、首尾空白
    if (re.match(r'^[-?:,\[\]{}#&*!|>\'"%@`]', s)
            or ': ' in s or s.endswith(':') or ' #' in s
            or s != s.strip() or '\n' in s):
        return "'" + s.replace("'", "''") + "'"
    return s


def find_block(text: str, key: str):
    """定位顶层 key 的块：返回 (起始行号, 结束行号, 缩进, 块内文本)。"""
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if re.match(r'^' + re.escape(key) + r':', line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*:', lines[j]):
            end = j
            break
    return start, end, lines


def detect_indent(lines, start):
    """看 variables 段第一条的 `- ` 缩进。"""
    for line in lines[start + 1:]:
        m = re.match(r'^(\s*)- ', line)
        if m:
            return len(m.group(1))
    return 0


def migrate_text(text: str, path: str):
    """对单个文件文本做迁移，返回 (new_text, changes, stats)。"""
    changes = []
    stats = {'backtick': 0, 'desc_value': 0, 'dead': 0, 'ratio': 0, 'added': 0, 'bracket': 0, 'dirty': 0, 'tech': 0}

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return text, changes, {'error': str(e)}
    if not isinstance(data, dict):
        return text, changes, {}

    prompt = str(data.get('prompt', '') or '')
    ratio_field = str(data.get('ratio', '') or '')
    ratio_value = first_ratio_value(ratio_field)
    slots = prompt_slots(prompt)

    new_text = text

    # ---- A1+A2. 只在 prompt 块内做占位符变换 ----
    # ⚠️ 不能全局替换：features / summary 里也有 `[TITLE]`、`{比例}` 这类文本，
    # 那是给人读的介绍，换成花括号既没意义又会破坏排版（2026-11-02 实测踩到）。
    ploc0 = find_block(new_text, 'prompt')
    if ploc0:
        pstart0, pend0, plines0 = ploc0
        pblock = ''.join(plines0[pstart0:pend0])

        # A1. 方括号 → 花括号（只转明确是变量的）
        def bracket_sub(m):
            name = m.group(1)
            new_name, verdict = bracket_to_brace(name)
            if verdict == 'ok' and new_name:
                stats['bracket'] += 1
                changes.append(f'方括号 [{name}] → {{{new_name}}}')
                return '{' + new_name + '}'
            return m.group(0)

        pblock = re.sub(r'\[([^\[\]\n]{1,30})\]', bracket_sub, pblock)

        # A2. 比例槽位 → ratio 常量
        if ratio_value:
            for slot in sorted(RATIO_SLOTS, key=len, reverse=True):
                token = '{' + slot + '}'
                if token in pblock:
                    pblock = pblock.replace(token, ratio_value)
                    stats['ratio'] += 1
                    changes.append(f'比例槽位 {token} → {ratio_value}')
            # 方括号形式的比例
            def rsub(m):
                stats['ratio'] += 1
                changes.append(f'比例占位 {m.group(0)} → {ratio_value}')
                return ratio_value
            pblock = re.sub(r'\[\s*\d+\s*:\s*\d+[^\]\n]*\]', rsub, pblock)
            pblock = re.sub(r'\[\s*ASPECT RATIO\s*\]', rsub, pblock, flags=re.I)

        # A3. 技术参数槽位 → 常量文本（不留输入框，句子也不破）
        for slot, const in TECH_CONST.items():
            token = '{' + slot + '}'
            if token in pblock:
                pblock = pblock.replace(token, const)
                stats['tech'] += 1
                changes.append(f'技术槽位 {token} → 常量')

        new_text = ''.join(plines0[:pstart0]) + pblock + ''.join(plines0[pend0:])

    # 重新取一次槽位（方括号转换后可能有新增）
    try:
        data2 = yaml.safe_load(new_text)
        prompt2 = str(data2.get('prompt', '') or '') if isinstance(data2, dict) else prompt
    except yaml.YAMLError:
        prompt2 = prompt
    slots2 = prompt_slots(prompt2)

    # ---- B. 规范化 variables 段 ----
    entries, vstats = normalize_variables(data.get('variables') or [], slots2, ratio_value)
    for k in ('backtick', 'desc_value', 'dead'):
        stats[k] = vstats.get(k, 0)
    stats['dirty'] = vstats.get('dirty', 0)
    stats['added'] = sum(1 for e in entries if e.get('added'))

    old_vars = data.get('variables')
    old_count = len(old_vars) if isinstance(old_vars, list) else 0

    # 只有当条目内容真的变了才重写（避免纯格式抖动）
    loc = find_block(new_text, 'variables')
    if loc:
        start, end, lines = loc
        indent = detect_indent(lines, start)
        new_block = render_variables(entries, indent)
        old_block = ''.join(lines[start:end])
        if new_block.rstrip('\n') != old_block.rstrip('\n'):
            new_text = ''.join(lines[:start]) + new_block + ''.join(lines[end:])
            changes.append(f'variables 段重写（{old_count} → {len(entries)} 条）')
    elif entries:
        # 原本没有 variables 段：插在 prompt 之后
        ploc = find_block(new_text, 'prompt')
        if ploc:
            pstart, pend, plines = ploc
            new_text = ''.join(plines[:pend]) + render_variables(entries, 0) + ''.join(plines[pend:])
        else:
            new_text = new_text.rstrip('\n') + '\n' + render_variables(entries, 0)
        changes.append(f'新增 variables 段（{len(entries)} 条）')

    # 校验仍可解析
    try:
        yaml.safe_load(new_text)
    except yaml.YAMLError as e:
        return text, [], {'error': f'改写后 YAML 非法: {e}'}

    return new_text, changes, stats


def main():
    ap = argparse.ArgumentParser(description='按 PROMPT_VARIABLES_SPEC 整改 variables')
    ap.add_argument('--apply', action='store_true', help='写回文件（默认 dry-run）')
    ap.add_argument('--dry-run', action='store_true', help='只预览，不写回（默认行为，显式声明用）')
    ap.add_argument('--diff', type=int, default=3, help='dry-run 时打印几个完整 diff')
    ap.add_argument('--only', default='', help='只处理文件名包含该子串的文件')
    args = ap.parse_args()

    files = sorted(glob.glob(STYLE_GLOB))
    if args.only:
        files = [f for f in files if args.only in f]

    total = {'backtick': 0, 'desc_value': 0, 'dead': 0, 'ratio': 0, 'added': 0, 'bracket': 0, 'dirty': 0, 'tech': 0}
    touched, errors, samples = [], [], []

    for path in files:
        text = open(path, encoding='utf-8').read()
        new_text, changes, stats = migrate_text(text, path)
        if stats.get('error'):
            errors.append((path, stats['error']))
            continue
        if new_text != text:
            touched.append(path)
            for k in total:
                total[k] += stats.get(k, 0)
            if len(samples) < args.diff:
                diff = list(difflib.unified_diff(
                    text.splitlines(), new_text.splitlines(),
                    fromfile=os.path.relpath(path, ROOT), tofile='after', lineterm='', n=1))
                samples.append('\n'.join(diff[:60]))
            if args.apply:
                open(path, 'w', encoding='utf-8').write(new_text)

    print(f"{'已写回' if args.apply else 'DRY-RUN'}：扫描 {len(files)} 个文件，改动 {len(touched)} 个")
    print(f"  剥 markdown 标签：{total['backtick']} 条")
    print(f"  style_var 写描述→本体：{total['desc_value']} 条")
    print(f"  删除死声明：{total['dead']} 条")
    print(f"  比例槽位→常量：{total['ratio']} 处")
    print(f"  技术槽位→常量：{total['tech']} 处")
    print(f"  方括号→花括号：{total['bracket']} 处")
    print(f"  补零声明：{total['added']} 条")
    print(f"  跳过脏槽位（说明书式占位符，待人工改 prompt）：{total['dirty']} 个")
    if errors:
        print(f"\n✗ 解析/改写失败 {len(errors)} 个：")
        for p, e in errors[:10]:
            print(f"  - {os.path.relpath(p, ROOT)}: {e}")
    for s in samples:
        print('\n' + s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
