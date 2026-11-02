#!/usr/bin/env python3
"""校验风格 .yaml 文件格式规范。"""
from __future__ import annotations  # 允许 list[str]/X | None 注解在 3.8+ 上运行
import argparse
import os
import re
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

# 提示词里的槽位：单花括号包一个短标识符（与插件 style-source 的扫描正则一致）
PLACEHOLDER_RE = re.compile(r'\{([^{}\n]{1,40})\}')

# style_var 写成「候选清单 / 一句人话」的特征：枚举分隔符、可选标记、举例引号
DESCRIPTIVE_VALUE_RE = re.compile(r'[、，/：]|（可选）|\(可选\)|如["“]')

# 一个风格最多给几个输入框（见 docs/PROMPT_VARIABLES_SPEC.md §5）
MAX_VARIABLES = 12

# 占位符名 / 标签里不该出现的字符：空白与中文标点。
# 刻意不含 / - _ ：「产品/道具」这类标签可读，{background/environment} 是历史写法，
# 两者不该因为 R6 被拦下（/ 另由 R6b 提示）。
NAME_BAD_PUNCT = re.compile(r'[\s，、：；（）()「」“”"]')

# 「说明书式」名字的特征：以填写指令开头，或整句带举例/可留空。
# 用锚定和完整词，避免误伤「可选禁用元素」这种合法标签。
NAME_BAD_WORD = re.compile(r'^(填写|请输入)|例如[：:]?|^如[：:]|可留空|不要文字')

# 允许保持英文的 kv_var（品牌名 / 通用术语），小写比较
ALLOW_EN_KV = {'prompt'} 

# desc 写这几个词等于没写（R7 专用），小写比较
DESC_JUNK = {'无', '暂无', '待定', '略', '同标签', 'todo', 'x', '-', '—'}


def check_variables_semantics(data: dict, require_desc: bool = False):
    """变量语义校验（PROMPT_VARIABLES_SPEC 的 R1–R7）。

    结构合法但语义无效的文件能一路绿灯过 CI，用户侧才会发现「填了没反应」，
    所以把这类问题提前到提交阶段。返回 (errors, warnings)。

    require_desc=True 时额外跑 R7（每条变量都要有 desc）。存量有 188 个风格
    desc 不完整，所以 R7 默认关闭，只由 CI 对「本 PR 新增」的风格打开。
    """
    errors, warnings = [], []
    prompt = str(data.get('prompt') or '')
    variables = data.get('variables')

    declared = []
    if isinstance(variables, list):
        declared = [v for v in variables if isinstance(v, dict)]
        # 旧形态 list[str] 已经在结构校验里提示迁移，这里不重复判定
        flat = [v for v in variables if isinstance(v, str)]
    else:
        flat = []

    if flat:
        return errors, warnings   # 旧形态无法可靠判定语义，交给迁移提示

    # R1：声明的占位符必须逐字出现在 prompt 里
    for v in declared:
        sv = str(v.get('style_var') or '').strip()
        if not (sv.startswith('{') and sv.endswith('}')):
            continue
        if sv not in prompt:
            errors.append(f'style_var {sv} 未出现在 prompt 中（用户填了不会生效）')

    # R2：style_var 只能是占位符本体，不能是描述或候选清单
    for v in declared:
        sv = str(v.get('style_var') or '').strip()
        if not sv or sv in ('{}', '{ }'):
            errors.append('style_var 为空（该条会被生成脚本丢弃）')
            continue
        if PLACEHOLDER_RE.fullmatch(sv):
            continue              # 合法占位符本体（名字是否合规由 R6 判）
        if DESCRIPTIVE_VALUE_RE.search(sv):
            errors.append(f'style_var 写成了描述/枚举，应改为 "{{占位符}}"：{sv}')
        elif not (sv.startswith('{') and sv.endswith('}')):
            warnings.append(f'style_var 未用花括号包裹（靠 key 兜底才能命中）：{sv}')

    # R3：prompt 里的每个槽位都该有声明。
    # 2026-11 已完成全库整改（未声明槽位 0 个），这条从 warning 升级为 error：
    # 漏声明的槽位不会出输入框，且标签会退化成英文占位符名，用户侧直接看不懂。
    for name in dict.fromkeys(PLACEHOLDER_RE.findall(prompt)):
        covered = False
        for v in declared:
            kv = str(v.get('kv_var') or '').strip().strip('`* ')
            sv = str(v.get('style_var') or '').strip()
            if kv == name or sv == '{' + name + '}':
                covered = True
                break
        if not covered:
            errors.append(f'prompt 槽位 {{{name}}} 没有对应 variables 声明（标签会退化成占位符名）')

    # R4：kv_var 是面板上给用户看的标签，必须是中文。
    # 一整片大写英文（SUBJECT / MAIN_TEXT）在中文界面里既占宽又难认，
    # 而且和「占位符名」混淆后很难判断某条声明到底有没有生效。
    for v in declared:
        kv = str(v.get('kv_var') or '').strip()
        if not kv or re.search(r'[\u4e00-\u9fa5]', kv):
            continue
        if kv.lower() in ALLOW_EN_KV:
            continue
        errors.append(f'kv_var 是纯英文标签，改成中文：{kv}')

    # R5：变量数量上限。面板是一列输入框，超过 12 个用户基本不会填完。
    # 需要更多输入时，先用一个「1/2/3」家族收成一个字段（值用 / 或 → 分隔）。
    n = len(declared)
    if n > MAX_VARIABLES:
        errors.append(f'变量 {n} 个，超过上限 {MAX_VARIABLES} 个（把一个位置上的多个元素合并成一个字段）')

    # R6：占位符名与标签不能写成「说明书」。
    # 历史写法把填写指南塞进名字：`{副标题，可留空}`、`{研究领域：生物医学 / 材料 / 纳米}`、
    # `{填写主题，例如：春日新品}`。插件会把整串当标签显示（长到没法看），
    # 而且这类槽位大多漏了声明，标签只能退化成英文占位符名。2026-11 清掉了 77 个。
    for name in dict.fromkeys(PLACEHOLDER_RE.findall(prompt)):
        if not name:
            continue
        if NAME_BAD_PUNCT.search(name):
            errors.append(f'prompt 槽位名含空白或标点，改成短名、说明写进 desc：{{{name}}}')
        elif NAME_BAD_WORD.search(name):
            errors.append(f'prompt 槽位名是填写指南，改成短名、说明写进 desc：{{{name}}}')
        elif '/' in name:
            # 英文模板里 {background/environment} 这类历史写法能用，不阻塞，只提示
            warnings.append(f'prompt 槽位名含 /（两个语义挤在一个槽位）：{{{name}}}')

    for v in declared:
        kv = str(v.get('kv_var') or '').strip()
        if not kv:
            continue
        if kv.startswith('{') and kv.endswith('}'):
            errors.append(f'kv_var 不能写成占位符形态（面板会照原样显示 {kv}），应写 {kv.strip("{}")}')
        elif NAME_BAD_PUNCT.search(kv):
            errors.append(f'kv_var 含空白或标点（面板上是字段名，不是句子）：{kv}')
        elif NAME_BAD_WORD.search(kv):
            errors.append(f'kv_var 是填写指南，应改成短标签：{kv}')

    # R7：每条变量都要有 desc。desc 是输入框的 placeholder，没有它面板上只剩一个
    # 空框，用户不知道该填什么 —— 前面 6 条保证「填了生效」，这条保证「知道填什么」。
    #
    # 默认关闭：全库 188 个风格 desc 不完整（1029 条缺失），追溯存量会一次打红。
    # CI 只对**本 PR 新增**的风格传 --require-desc，存量永不被追溯，缺口只减不增。
    if require_desc:
        for v in declared:
            kv = str(v.get('kv_var') or '').strip()
            desc = str(v.get('desc') or '').strip()
            if not desc:
                errors.append(f'变量「{kv}」缺少 desc（面板上只剩空输入框，用户不知道该填什么）')
            elif desc.strip('`* ') == kv:
                errors.append(f'变量「{kv}」的 desc 与标签重复，等于没写')
            elif desc.lower() in DESC_JUNK:
                errors.append(f'变量「{kv}」的 desc 是占位词（{desc}），写具体一点')
            elif len(desc) < 4:
                warnings.append(f'变量「{kv}」的 desc 太短（{desc}），建议写成「是什么 + 如：例子」')

    return errors, warnings


def validate_file(filepath: str, check_images: bool = False, require_desc: bool = False) -> tuple:
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

    # 变量语义校验（R1–R7）：结构合法 ≠ 插件能用，见 docs/PROMPT_VARIABLES_SPEC.md
    semantic_errors, semantic_warnings = check_variables_semantics(data, require_desc=require_desc)
    errors.extend(semantic_errors)
    warnings.extend(semantic_warnings)

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
    parser.add_argument('--require-desc', action='store_true',
                        help='额外要求每条变量都有 desc（R7）；CI 只对本 PR 新增的风格传此开关')
    args = parser.parse_args()

    had_errors = False
    if args.files:
        # 校验指定文件
        for filepath in args.files:
            errors, warnings = validate_file(filepath, check_images=args.check_images,
                                            require_desc=args.require_desc)
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
