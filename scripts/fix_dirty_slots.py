#!/usr/bin/env python3
"""脏槽位整改：把「说明书当占位符名」的槽位改成短名 + 把原内容降级成 desc。

背景：这些风格的 prompt 写成 `副标题：{副标题，可留空}`、`研究领域：{生物医学 / 材料 / ...}`，
占位符名里塞了整个填写指南。插件会把整串当标签显示（输入框标题长得没法看），
而且这些槽位大多没有 variables 声明，标签只能退化成占位符名本身。

四类处理：
  RENAME  中文说明书名 → 短中文名，原文降级成 desc
  KEEP    英文 prompt 里的英文槽位名保持不动，只补 kv_var 声明（中文标签 + desc）
  DELETE  比例 / 尺寸槽位：整行删掉（比例由 ratio 字段统一管）
  PATCH   结构性坏损的 prompt（占位符跨句、重复段落），按字面量整段替换

做法（默认 dry-run）：
  1. 从 prompt 的 `标签：{占位符}` 或 `【标签】{占位符}` 结构反推中文标签
  2. 占位符换成短名
  3. 原内容去掉「填写 / 例如 / 如：」前缀后存进 desc，给插件当输入提示
  4. 重写 variables 声明：补新槽位、删 prompt 里已不存在的幽灵声明

用法：
  python3 scripts/fix_dirty_slots.py            # dry-run，打印每条改法
  python3 scripts/fix_dirty_slots.py --apply
  python3 scripts/fix_dirty_slots.py --only science
"""
import argparse
import glob
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLE_GLOB = os.path.join(ROOT, 'styles', '*', '*.yaml')

# 与 docs/PROMPT_VARIABLES_SPEC.md 的 R5 一致；整改不得把风格推过这个线
MAX_VARIABLES = 12

# 判定「占位符名是说明书」：含空白/标点，或含这些词
BAD_NAME = re.compile(r'[\s/,:：，、（）()；;]|填写|例如|如：|可选|可留空|不要文字|^.{41,}$')
# 清理 desc 前缀（可能叠加多层，如「填写，例如：」）
DESC_PREFIX = re.compile(r'^(填写|请填写|例如|如|示例)[\s:：，,、]*')

# 比例槽位：整行删掉
DROP_NAMES = {
    '1:1 / 4:5 / 3:4 / 16:9 / 5:2 / 3:2',
    '16:9',
}

# 逐槽位人工裁定：(新槽位名 or None=删, 中文标签, desc)
SLOT_MAP = {
    # ---- 英文 prompt：保留英文槽位名，只给中文标签 ----
    'indoor/outdoor setting': None,      # 结构性问题，见 PATCH
    'main architectural elements': None,
    'furniture/interior details': None,
    'People/subjects': None,
    'emotion/atmosphere': None,
    'surrounding environment/view': None,
    'dominant colors': None,
    'medium/technique': None,
    'artistic details': None,
    'overall aesthetic': None,
    'opponent/situation': ('opponent/situation', '对手情境', '对手或情境，如 at Doflamingo'),
    'background/environment': ('background/environment', '场景背景', '环境描述，如 Marineford battlefield'),
    '目的地/城市': ('目的地/城市', '目的地/城市', '城市或地区，如 京都 / Kyoto'),
    '行业/场景': ('行业/场景', '行业/场景', 'AI / 投资 / 消费 / SaaS / 创业等'),
    '可选禁用元素': ('可选禁用元素', '禁用元素', '不想出现的元素，可留空'),
    '活动时间/副行': ('活动时间/副行', '活动时间', '活动时间或副行文案，如 5.1–5.7'),
    # ---- 中文 prompt：改成短名 ----
    '填写': 'FROM_CONTEXT',              # 由上下文行决定；推不出来就删
    '填写中文或日文标题': ('主标题', '主标题', ''),
    '填写简短英文标题': ('英文辅助标题', '英文辅助标题', '如 SPRING LIGHT'),
    '填写 2 个与主题相关的汉字': ('野字内容', '野字内容', '2 个与主题相关的汉字'),
    '填写 1–2 种传统色': ('主色', '主色', '1–2 种传统色，如 朱砂 / 靛青'),
    '填写 2–4 个颜色，例如：暖橙 + 杏黄 + 暖白 / 青瓷绿 + 暖白 + 朱砂点色 / 沉香褐 + 米白 / 墨黑 + 暖白 + 朱红':
        ('主色域', '主色域', '2–4 个颜色，如 暖橙 + 杏黄 + 暖白'),
    '填写一个最强的单一大形，例如：巨大纸圆 / 扇形展开 / 沉香色块 / 墨黑版面':
        ('核心主形', '核心主形', '如 巨大纸圆 / 扇形展开 / 沉香色块'),
    '填写一个真实的小型文化场景，例如：糊纸灯彩 / 制扇裱贴 / 篆香合香 / 刻版印刷':
        ('微场景', '微场景', '如 糊纸灯彩 / 制扇裱贴 / 篆香合香'),
    '填写少量必要器物，例如：竹骨、薄纸、香炉、印版、刻刀、扇骨、纸灯等':
        ('文化元素', '文化元素', '如 竹骨、薄纸、香炉、印版、刻刀、扇骨'),
    '填写主题，例如：灯影 / 折光 / 面相 / 烟迹': ('主题', '主题', '如 灯影 / 折光 / 面相 / 烟迹'),
    '填写一个具有强轮廓、强材质感的真实器物，例如：纸灯、玻璃器皿、青铜器、木雕、香炉':
        ('核心主体', '核心主体', '如 纸灯、玻璃器皿、青铜器、木雕、香炉'),
    # ---- 结构坏损：两个槽位挤在同一行 ----
    '左侧元素如：桨阵/骨架/弓身': ('左侧元素', '左侧元素', '如 桨阵 / 骨架 / 弓身'),
    '右侧元素如：声波/羽翼/杆件': ('右侧元素', '右侧元素', '如 声波 / 羽翼 / 杆件'),
    '中央硬轴描述，如：竹脊/船身/箭矢/器物结构':
        ('中央硬轴', '中央硬轴', '如 竹脊 / 船身 / 箭矢 / 器物结构'),
    # ---- 其它 ----
    '3-5个相关人物、建筑、器物或自然景观':
        ('文化元素', '文化元素', '3–5 个相关人物 / 建筑 / 器物 / 自然景观'),
    '3–10个必须展示的信息点': ('核心信息点', '核心信息点', '3–10 个必须出现的信息点'),
    '3–10个必须出现的元素': ('关键视觉元素', '关键视觉元素', '3–10 个必须出现的元素'),
    '3–6个必须出现的元素': ('关键视觉元素', '关键视觉元素', '3–6 个必须出现的元素'),
    '一句话写清楚发生了什么': ('核心内容', '核心内容', '一句话说清画面发生了什么'),
    '一句话写清楚研究亮点或封面概念': ('视觉概念', '视觉概念', '一句话说清研究亮点 / 封面概念'),
    '包围方式：人物环绕/三边巨字/实体边界/嵌套框/其他':
        ('包围方式', '包围方式', '人物环绕 / 三边巨字 / 实体边界 / 嵌套框'),
    'date和金句': ('日期与金句', '日期与金句', '如 2024.11.08 — 春天总会来'),
    '主体描述：桃子（表皮绒毛质感，通过粉色短促线条排列交叉来表现形体与质感，暗部线条更密集，亮部稀疏）；枝叶（通过绿色细密线条来塑造叶脉纹理与层次感）。':
        ('主体', '主体', '如 桃子（绒毛质感，粉色短促线条交叉排线）+ 枝叶（绿色细密线条勾叶脉）'),
    '主体描述：米白双层小房子（青绿色坡屋顶，墙面手写品牌英文字体），房子侧边伸出肉粉色卡通手掌，手背印aigc、DESIGN 贴纸，手托蓝色浮雕 Idea 字样飞盘；左侧装饰元素，右上装饰元素，房内探出带双眼的装饰，屋内塞满蓬松白色云朵。':
        ('主体', '主体', '如 米白双层小房子（青绿坡屋顶）+ 卡通手掌托 Idea 飞盘'),
    '6种配色方案选择': ('配色方案', '配色方案', '从 6 种配色方案中选一个'),
    '从15种隐喻中选择': ('核心隐喻', '核心隐喻', '从 15 种商业隐喻中选一个，如 被市场曲线切开 / 变成迷宫'),
}

# 整段 prompt 改写（结构性坏损，靠替换槽位救不回来）
# 2026-11-02 清空：下面两条 PATCH 都已 --apply 并随 PR #195 合并，重跑只会打印「未命中」。
# 保留空结构，将来有新脏数据按同样格式再填。
#   - pen_ink_point_line_peaches：正文已是「点缀：{画面点缀}（可有可无…）」
#   - eastern_art_..._wild_calligraphy：主题 / 展览信息已并入正文，尾部 {变量说明} 块已截断
PROMPT_PATCH = {}

# 这些风格的正文整段重写（占位符散落、重复段落）
# 2026-11-02 清空：quiet_corner 的整段重写早已应用，之后 L3 又把它从 14 条收敛到 12 条。
# 留着重跑会把 14 条槽位版本写回去、顶破 R5 上限，所以直接删规则（守卫见 MAX_VARIABLES）。
PROMPT_REPLACE = {}

# 从 prompt 尾部整块删掉的组织性文字（匹配起始标记 → 到 prompt 末尾）
PROMPT_TRUNCATE = {
    'eastern_art_exhibition_poster_wild_calligraphy': '\n{变量说明}',
}

# 已声明槽位补 desc（这些槽位名本来就干净，只是缺填写提示）
DESC_MAP = {
    'eastern_art_exhibition_poster_wild_calligraphy': {
        '主题': '如 灯影 / 折光 / 面相 / 烟迹',
        '野字内容': '2 个与主题相关的汉字',
        '核心主体': '如 纸灯、玻璃器皿、青铜器、木雕、香炉',
        '主体主色': '如 琥珀金 / 钴蓝 / 深木褐 / 朱砂红',
        '主体与文字互动': '折射 / 投影 / 穿插 / 遮挡 / 消解 / 切割 / 拉伸',
        '英文辅助标题': '如 SPRING LIGHT',
        '展览信息': '如 2024.11.08–12.20 · 上海',
    },
}

# 整段 variables 重写（原声明与 prompt 已对不上，只能整块换）
# 2026-11-02 清空：quiet_corner 的 14 条覆盖表是整改前的快照，已由 L3 收敛成 12 条。
# 别再填回去 —— 会直接顶破 MAX_VARIABLES。
VARS_OVERRIDE = {}


def label_from_context(prompt, start):
    """从 `标签：{占位符}` / `【标签】{占位符}` 反推标签。"""
    line_start = prompt.rfind('\n', 0, start) + 1
    seg = prompt[line_start:start]
    # 【主标题】：  或  【主题 / 活动名称】
    m = re.search(r'【([^】]{1,20})】\s*[：:]?\s*$', seg)
    if m:
        return m.group(1).strip()
    # 主题：
    m = re.search(r'([^\s：:【】\[\]]{1,14})\s*[：:]\s*$', seg)
    if m:
        return m.group(1).strip()
    return ''


def clean_desc(name, label=''):
    """占位符原名 → desc：去掉「填写/例如」前缀与重复的标签前缀。"""
    d = str(name or '').strip()
    for _ in range(3):
        d2 = DESC_PREFIX.sub('', d)
        if d2 == d:
            break
        d = d2
    if label and d.startswith(label):
        d = re.sub(r'^' + re.escape(label) + r'[\s:：，,、]*', '', d)
    d = d.strip(' \u3000:：，,、')
    if d in ('', label, '可留空', '可选'):
        return ''
    if d == '留空':
        return '可留空'
    return d


def find_entries(prompt):
    """找出所有「名字像说明书」或已在 SLOT_MAP 里点名的占位符。"""
    out = []
    for m in re.finditer(r'\{\{([^{}]{1,300})\}\}|\{([^{}\n]{1,300})\}', prompt):
        name = (m.group(1) or m.group(2) or '').strip()
        if not name:
            continue
        if name in DROP_NAMES or name in SLOT_MAP or BAD_NAME.search(name):
            out.append((m.start(), m.end(), name))
    return out


def plan_for(prompt, style_id=''):
    """生成整改计划：[(原文, 新槽位 or None, 标签, desc, 动作)]。"""
    plans = []
    for start, end, name in find_entries(prompt):
        if name in DROP_NAMES:
            # 记下这一行的标签前缀（比例 / 画幅比例），删完槽位后整行收走
            plans.append((name, None, label_from_context(prompt, start), None, 'DROP_LINE'))
            continue
        spec = SLOT_MAP.get(name, 'AUTO')
        if spec is None:                          # 交给 PATCH 处理
            continue
        if spec == 'FROM_CONTEXT':
            label = label_from_context(prompt, start)
            if not label:
                plans.append((name, None, None, None, 'DROP'))
                continue
            slot, desc = re.sub(r'[^\w\u4e00-\u9fa5]', '', label) or '变量', ''
            plans.append((name, slot, label, desc, 'RENAME'))
            continue
        if spec == 'AUTO':
            label = label_from_context(prompt, start)
            if not label:
                continue                          # 推不出来就不动，留给人工
            slot = re.sub(r'[^\w\u4e00-\u9fa5]', '', label) or '变量'
            desc = clean_desc(name, label)
            plans.append((name, slot, label, desc, 'RENAME'))
            continue
        slot, label, desc = spec
        plans.append((name, slot, label, desc, 'RENAME' if slot != name else 'KEEP'))

    seen, uniq = set(), []
    for p in plans:
        if p[0] in seen:
            continue
        seen.add(p[0])
        uniq.append(p)
    return uniq


def render_prompt_block(prompt):
    """按 `|` 文本块风格重排 prompt，避免 safe_dump 把整段塞成一行单引号。"""
    body = str(prompt).rstrip('\n')
    lines = ['prompt: |']
    for ln in body.split('\n'):
        lines.append(('  ' + ln) if ln.strip() else '')
    return '\n'.join(lines) + '\n'


def yaml_scalar(s):
    s = str(s or '')
    if s == '':
        return "''"
    if re.match(r'^[-?:,\[\]{}#&*!|>\'"%@`]', s) or ': ' in s or s.endswith(':') or ' #' in s:
        return "'" + s.replace("'", "''") + "'"
    return s


def render_vars_block(entries):
    """entries: [(kv_var, style_var, desc)]"""
    lines = ['variables:']
    if not entries:
        lines[0] = 'variables: []'
        return '\n'.join(lines) + '\n'
    for kv, sv, desc in entries:
        lines.append('- kv_var: %s' % yaml_scalar(kv))
        lines.append("  style_var: '%s'" % sv)
        if desc:
            lines.append('  desc: %s' % yaml_scalar(desc))
    return '\n'.join(lines) + '\n'


def find_block(text, key):
    lines = text.splitlines(keepends=True)
    start = None
    for i, ln in enumerate(lines):
        if ln.rstrip('\n') == key + ':' or ln.startswith(key + ':'):
            start = i
            break
    if start is None:
        return None
    end = start + 1
    while end < len(lines):
        ln = lines[end]
        if ln.strip() and not ln.startswith((' ', '-', '\t')):
            break
        end += 1
    return start, end, lines


def strip_dangling_labels(prompt, labels):
    """只收走「槽位被删后只剩 `比例：`」的空壳行，不动正常段落标题。"""
    if not labels:
        return prompt, []
    pats = [re.compile(r'^\s*%s\s*[：:]\s*$' % re.escape(l)) for l in labels if l]
    kept, dropped = [], []
    for ln in prompt.split('\n'):
        if any(p.match(ln) for p in pats):
            dropped.append(ln.strip())
            continue
        kept.append(ln)
    return '\n'.join(kept), dropped


def build(text, style_id):
    data = yaml.safe_load(text)
    prompt = str(data.get('prompt', '') or '')
    old_vars = [v for v in (data.get('variables') or []) if isinstance(v, dict)]
    changes = []

    # 1) 整段 prompt 改写
    if style_id in PROMPT_REPLACE:
        prompt = PROMPT_REPLACE[style_id]
        changes.append('PATCH 整段 prompt：槽位收进正文，删掉尾部孤立占位符块')
    if style_id in PROMPT_PATCH:
        for old, new in PROMPT_PATCH[style_id]:
            if old in prompt:
                prompt = prompt.replace(old, new)
                changes.append('PATCH 句式：%s → %s' % (old[:16], new[:16]))
            else:
                changes.append('!! PATCH 未命中（请检查原文）：%s' % old[:26])
    if style_id in PROMPT_TRUNCATE:
        mark = PROMPT_TRUNCATE[style_id]
        if mark in prompt:
            prompt = prompt[:prompt.index(mark)]
            changes.append('PATCH 截断尾部变量说明块')

    # 2) 逐槽位改名 / 删除
    plans = plan_for(prompt, style_id)
    new_decls = {}
    renames = {}          # 旧槽位名 → 新槽位名，用于把旧声明接过来
    drop_labels = []
    for name, slot, label, desc, action in plans:
        if slot is None:
            if action == 'DROP_LINE':
                drop_labels.append(label)
            for token in ('{{' + name + '}}', '{' + name + '}'):
                if token in prompt:
                    prompt = prompt.replace(token, '')
                    why = '比例由 ratio 字段统一管' if action == 'DROP_LINE' else '无上下文可用'
                    changes.append('DELETE {%s}（%s）' % (name[:16], why))
                    break
            continue
        for token in ('{{' + name + '}}', '{' + name + '}'):
            if token in prompt:
                prompt = prompt.replace(token, '{' + slot + '}')
                new_decls[slot] = (label, desc)
                if slot != name:
                    renames[name] = slot
                    changes.append('RENAME {%s} → {%s}  [标签 %s]' % (name[:22], slot, label))
                break

    # 3) 收拾空壳行与多余空白
    prompt, dangling = strip_dangling_labels(prompt, drop_labels)
    for d in dangling:
        changes.append('删除空壳行「%s」' % d)
    prompt = re.sub(r'[ \t]+\n', '\n', prompt)
    prompt = re.sub(r'\n{3,}', '\n\n', prompt).strip('\n')

    # 4) 重建 variables
    desc_extra = DESC_MAP.get(style_id, {})
    if style_id in VARS_OVERRIDE:
        merged = [tuple(x) for x in VARS_OVERRIDE[style_id]]
        changes.append('重写 variables：%d 条（原 %d 条）' % (len(merged), len(old_vars)))
    else:
        merged, seen = [], set()
        for v in old_vars:
            inner = str(v.get('style_var') or '').strip().strip('{}')
            inner = renames.get(inner, inner)
            if ('{' + inner + '}') not in prompt:
                changes.append('删除幽灵声明 {%s}（prompt 里已无此槽位）' % inner)
                continue
            if inner in seen:
                continue
            seen.add(inner)
            kv = str(v.get('kv_var') or '').strip()
            desc = str(v.get('desc') or '').strip()
            if inner in new_decls:
                label, d2 = new_decls.pop(inner)
                if kv != label:
                    changes.append('改标签 %s → %s' % (kv, label))
                if d2 and d2 != desc:
                    changes.append('加 desc「%s」→ %s' % (label, d2[:34]))
                kv, desc = label, (d2 or desc)
            merged.append((kv, '{' + inner + '}', desc_extra.get(inner, desc)))
        for slot, (label, desc) in new_decls.items():
            merged.append((label, '{' + slot + '}', desc_extra.get(slot, desc)))
            changes.append('新增声明 %s → {%s}' % (label, slot))

    # 5) 兜底：prompt 里有、声明里没有的槽位（插件不会给它们出输入框）
    covered = {sv.strip('{}') for _, sv, _ in merged}
    for m in re.finditer(r'\{([^{}\n]{1,60})\}', prompt):
        name = m.group(1).strip()
        if not name or name in covered:
            continue
        covered.add(name)
        merged.append((name, '{' + name + '}', desc_extra.get(name, '')))
        changes.append('补漏声明 {%s}（prompt 用到但未声明）' % name)

    # 6) 按 prompt 里首次出现的顺序排序：插件按声明顺序渲染输入框
    order = {}
    for i, m in enumerate(re.finditer(r'\{([^{}\n]{1,60})\}', prompt)):
        order.setdefault(m.group(1).strip(), i)
    merged.sort(key=lambda e: order.get(e[1].strip('{}'), 10 ** 6))

    return prompt, merged, changes


def main():
    ap = argparse.ArgumentParser(description='脏槽位整改：长名 → 短名 + desc')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--only', default='')
    args = ap.parse_args()

    files = sorted(glob.glob(STYLE_GLOB))
    if args.only:
        files = [f for f in files if args.only in f]

    touched = 0
    skipped = 0
    for path in files:
        text = open(path, encoding='utf-8').read()
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            continue
        style_id = str(data.get('id') or '')
        prompt0 = str(data.get('prompt', '') or '')
        if not find_entries(prompt0) and style_id not in PROMPT_PATCH \
                and style_id not in VARS_OVERRIDE:
            continue
        new_prompt, merged, changes = build(text, style_id)
        if not changes:
            continue
        # 守卫：整改后变量数不得超硬上限（SPEC R5）。规则过期时会把已收敛的风格改回去，
        # 例如 quiet_corner 从 12 条被 VARS_OVERRIDE 回退成 14 条 —— 直接拦下。
        if len(merged) > MAX_VARIABLES:
            print('\n### %s' % os.path.relpath(path, ROOT))
            print('   ❌ 跳过：整改后 %d 个变量 > 上限 %d，八成是规则过期' % (len(merged), MAX_VARIABLES))
            print('      该风格当前已是 %d 条，确认后再改 PROMPT_REPLACE / VARS_OVERRIDE'
                  % len([v for v in (data.get('variables') or []) if isinstance(v, dict)]))
            skipped += 1
            continue
        touched += 1
        rel = os.path.relpath(path, ROOT)
        print('\n### %s' % rel)
        for c in changes:
            print('   ' + c)
        if args.apply:
            out = text
            ploc = find_block(out, 'prompt')
            if ploc:
                s, e, lines = ploc
                out = ''.join(lines[:s]) + render_prompt_block(new_prompt) + ''.join(lines[e:])
            vloc = find_block(out, 'variables')
            block = render_vars_block(merged)
            if vloc:
                vs, ve, vlines = vloc
                out = ''.join(vlines[:vs]) + block + ''.join(vlines[ve:])
            elif merged:
                # 插到 source_url 之前，保持文件字段顺序观感
                sloc = find_block(out, 'source_url')
                if sloc:
                    s, e, lines = sloc
                    out = ''.join(lines[:s]) + block + ''.join(lines[s:])
                else:
                    out = out.rstrip('\n') + '\n\n' + block
            open(path, 'w', encoding='utf-8').write(out)

    print('\n%s：%d 个风格' % ('已写回' if args.apply else 'DRY-RUN', touched))
    if skipped:
        print('跳过 %d 个（整改后超出 %d 个变量上限，规则需更新）' % (skipped, MAX_VARIABLES))
    return 0


if __name__ == '__main__':
    sys.exit(main())
