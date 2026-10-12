#!/usr/bin/env python3
"""从 styles/ 目录读取所有 .yaml 风格文件，生成 data/styles.json。"""
from __future__ import annotations  # 允许 list[str]/X | None 注解在 3.8+ 上运行
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

STYLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'images')
BASE_URL = 'https://malongan.github.io/style-source'
NUMBERS_FILE = os.path.join(DATA_DIR, 'style_numbers.json')
TIMESTAMPS_FILE = os.path.join(DATA_DIR, 'style_timestamps.json')

# 配图文件名规范：{style_id}_{8位后缀}.{ext}
# 8 位后缀有两种来源：md5(原图)[:8]（hex）与 X/Twitter media id（base62），因此按字母数字锚定。
# 后缀 8 位是硬约束：换用更宽的匹配会把相邻风格的图误配进来（见 match_preview_files 注释）。
IMAGE_SUFFIX_RE = re.compile(r'^(?P<style_id>.+)_(?P<suffix>[0-9A-Za-z]{8})$')
FULL_IMAGE_EXTS = ('webp', 'jpg', 'jpeg', 'png')

# Markdown 变量表表头行（md → yaml 转换残留），不是真实变量，解析时跳过
VARIABLE_HEADER_ROWS = {('变量', '说明')}
VARIABLE_HEADER_ROWS_FLAT = {'变量', '说明'}   # 旧形态 list[str] 里的同款残留

# 旧形态 `variables: [str]` 里的 `"{占位符}" — 示例：xxx` 写法
LEGACY_VAR_RE = re.compile(
    r'^"?\s*(?P<name>\{[^{}]+\})\s*"?\s*(?:[—\-–:：]\s*)?(?:示例\s*[:：]?\s*)?(?P<desc>.*)$')

# 无筛选价值的英文标签词（通用词、无语义或极短）
TAG_STOPWORDS = {
    'a', 'an', 'the', 'is', 'it', 'of', 'or', 'and', 'for', 'to', 'in', 'on',
    'with', 'by', 'at', 'as', 'from', 'be', 'are', 'was', 'were', 'been',
    'this', 'that', 'these', 'those', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can',
    'i', 'you', 'he', 'she', 'we', 'they', 'my', 'your', 'his', 'her', 'its', 'our', 'their',
    'using', 'into', 'real', 'large', 'clean', 'subject', 'marks', 'with', 'and',
    'the', 'for', 'from', 'this', 'with', 'not', 'but', 'also', 'only', 'just',
    'so', 'very', 'too', 'more', 'most', 'some', 'any', 'all', 'each', 'other',
    'new', 'old', 'big', 'small', 'good', 'best', 'top', 'one', 'two',
    'style', 'image', 'photo', 'photograph', 'picture', 'design',
    'high', 'low', 'right', 'left', 'front', 'back', 'side', 'up', 'down',
    'out', 'off', 'over', 'under', 'again', 'once',
    '2d', '3d', '4d',  # 短到无意义，让上下文语义来区分
}

def is_valid_tag(tag: str) -> bool:
    """过滤无筛选价值的标签"""
    t = tag.strip()
    if not t:
        return False
    # 英文标签：长度 ≤ 2 过滤（中文不受此限制）
    if t.isascii() and len(t) <= 2:
        return False
    # 过滤 stopwords（仅英文小写比较）
    if t.lower() in TAG_STOPWORDS:
        return False
    # 过滤包含空格的长标签（描述性短语，不是标签）
    if ' ' in t and len(t) > 30:
        return False
    return True


def get_version() -> str:
    """获取版本号：从 git tag 读取，无 tag 时返回 commit hash 或 v0.0.0"""
    try:
        version = subprocess.check_output(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        return version if version else 'v0.0.0'
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 'v0.0.0'


def list_preview_files() -> list[str]:
    """列出 styles_previews/ 下所有全尺寸配图文件名（排除 .thumb.webp），排序保证跨平台一致。"""
    preview_dir = os.path.join(IMAGES_DIR, 'styles_previews')
    if not os.path.isdir(preview_dir):
        return []
    return sorted(f for f in os.listdir(preview_dir)
                  if not f.endswith('.thumb.webp'))


def match_preview_files(style_id: str, files: list[str] | None = None) -> tuple[list[str], list[str]]:
    """按 `{style_id}_{8位后缀}.{ext}` **整段锚定**匹配配图，返回 (exact, fuzzy)。

    ⚠️ 必须锚定整段文件名。历史实现用 `glob(f'{style_id}_*.webp')` 做前缀匹配并取
    `[0]`（glob 顺序不确定），导致：
      - `doodle_style` 命中 `doodle_style_poster_5f705d81.webp`（别的风格的图）→ 配图串号；
      - 真正属于它的 `doodle_style_e4aa24f7.webp` 反被判成"孤儿"，在 996224e 被清理删除。
    见 2026-10-10 事故。此后 fuzzy 候选（仅前缀相同、归属不明）只用于告警，**绝不自动采用**。

    - exact：去掉 8 位后缀后与 style_id 完全相等的候选
    - fuzzy：仅前缀相同、无法确认归属的候选（供调用方提示，禁止当作自己的配图）
    """
    files = list_preview_files() if files is None else files
    exact, fuzzy = [], []
    for name in files:
        stem, ext = os.path.splitext(name)
        if ext.lower().lstrip('.') not in FULL_IMAGE_EXTS:
            continue
        m = IMAGE_SUFFIX_RE.match(stem)
        if m and m.group('style_id') == style_id:
            exact.append(name)
        elif stem.startswith(style_id + '_'):
            fuzzy.append(name)
    return sorted(exact), sorted(fuzzy)


def find_image_in_repo(style_id: str, files: list[str] | None = None):
    """在 images/ 下查找 **style_id 自己的** 配图，返回相对于 images/ 的路径。
    优先 WebP，其次 JPEG，最后 PNG；没有自己的配图时返回 None（不借用他人配图）。"""
    exact, _ = match_preview_files(style_id, files)
    for ext in FULL_IMAGE_EXTS:  # webp → jpg → jpeg → png
        for name in exact:
            if name.lower().endswith('.' + ext):
                return os.path.join('styles_previews', name)
    return None


def resolve_image_url(style_id: str, yml_urls: list[str], files: list[str] | None = None) -> list[str]:
    """解析图片 URL：优先用 repo 里自己的文件，fallback 到 yml 中的 URL"""
    rel_path = find_image_in_repo(style_id, files)
    if rel_path:
        return [f'{BASE_URL}/images/{rel_path}']
    if yml_urls:
        return yml_urls
    return []


def ensure_thumb_exists(full_path: str, thumb_path: str) -> bool:
    """缩略图自愈：全尺寸 WebP 存在但缩略图缺失时，用 Pillow 自动生成。
    返回缩略图是否最终可用。Pillow 不可用时返回 False（保持 null）。"""
    if os.path.exists(thumb_path):
        return True
    try:
        from PIL import Image
        img = Image.open(full_path).convert('RGB')
        img.thumbnail((400, 400), Image.LANCZOS)
        img.save(thumb_path, 'WEBP', quality=85)
        print(f'   🔧 自动生成缺失缩略图: {os.path.relpath(thumb_path)}')
        return True
    except Exception as e:
        print(f'   ⚠️ 缩略图生成失败 {os.path.basename(thumb_path)}: {e}')
        return False


def resolve_image_webp(style_id: str, files: list[str] | None = None) -> dict:
    """解析 WebP 版本 URL，返回 {'full': str|None, 'thumb': str|None}
    只认 **自己** 的配图（整段锚定），兼容旧 .jpg/.png 源文件。
    自愈：全尺寸存在但缩略图缺失时自动生成（需 Pillow）。"""
    exact, _ = match_preview_files(style_id, files)

    # 优先查找全尺寸 WebP
    webp_matches = [n for n in exact if n.lower().endswith('.webp')]
    if webp_matches:
        full_name = webp_matches[0]
        base = os.path.splitext(full_name)[0]
        base_url = f'{BASE_URL}/images/styles_previews/{base}'
        thumb_path = os.path.join(IMAGES_DIR, 'styles_previews', f'{base}.thumb.webp')
        thumb_ok = ensure_thumb_exists(
            os.path.join(IMAGES_DIR, 'styles_previews', full_name), thumb_path)
        return {
            'full': f'{base_url}.webp',
            'thumb': f'{base_url}.thumb.webp' if thumb_ok else None,
        }

    # Fallback：从旧 JPG/PNG 文件推导 WebP 文件名
    legacy = [n for n in exact if n.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if not legacy:
        return {'full': None, 'thumb': None}
    base = os.path.splitext(legacy[0])[0]
    base_url = f'{BASE_URL}/images/styles_previews/{base}'
    return {
        'full': f'{base_url}.webp',
        'thumb': f'{base_url}.thumb.webp',
    }


def parse_legacy_variable(entry: str) -> tuple:
    """把旧形态 `variables: [str]` 的单个条目解析为 (kv_var, style_var, desc)。

    旧形态有三种写法（2026-10-12 实测）：
      1. `中文标题`                      → ('中文标题', '{中文标题}', '')
      2. `"{车型完整描述}" — 示例：xxx`    → ('车型完整描述', '{车型完整描述}', '示例：xxx')
      3. `"{SCENERY}" — 示例：xxx`        → ('SCENERY', '{SCENERY}', '示例：xxx')

    解析不出变量（既非短标识符、也不含 `{占位符}`）时返回 ('', '', entry)，
    由调用方跳过并告警 —— 绝不能把整句话当成变量名造出垃圾键。
    """
    m = LEGACY_VAR_RE.match(entry)
    if m:
        brace = m.group('name')          # 形如 {车型完整描述}
        name = brace[1:-1].strip()
        desc = (m.group('desc') or '').strip(' —-–:：\t')
        if name:
            return name, brace, desc
    # 纯变量名：无空白、无标点长句、长度合理
    if entry and len(entry) <= 24 and not re.search(r'[\s，。！？、/]', entry):
        return entry, f'{{{entry}}}', ''
    return '', '', entry


def parse_style_file(filepath: str) -> dict:
    """解析单个 .yaml 风格文件，提取结构化数据"""
    import yaml as _yaml
    with open(filepath, 'r', encoding='utf-8') as f:
        data = _yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        raise ValueError('YAML 文件为空或格式错误')

    filename = os.path.basename(filepath).replace('.yaml', '')
    dirname = os.path.basename(os.path.dirname(filepath))

    # 标签
    tags = data.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip() and is_valid_tag(t)]
    else:
        tags = [str(t).strip() for t in tags if t and is_valid_tag(str(t).strip())]

    # 触发词
    triggers = data.get('triggers', [])
    if isinstance(triggers, str):
        triggers = [t.strip() for t in triggers.split('、') if t.strip()]

    # 特点
    features_raw = data.get('features', [])
    features = []
    for feat in features_raw:
        if isinstance(feat, dict):
            title = feat.get('title', '')
            desc = feat.get('desc', '')
            features.append(f'**{title}** \u2014 {desc}' if desc else title)
        elif isinstance(feat, str):
            features.append(feat)

    # 来源
    source_author = str(data.get('source_author', '')).lstrip('@').strip()

    # 图片 URL（只认自己的配图；前缀相同但归属不明的候选只告警，不采用）
    preview_files = list_preview_files()
    exact, fuzzy = match_preview_files(filename, preview_files)
    if not exact:
        if fuzzy:
            print(f'   ⚠️  {filename}: 没有自己的配图，已忽略归属不明的前缀候选 {fuzzy} '
                  f'（禁止借用他人配图，请补 {filename}_<8位后缀>.webp）')
        else:
            print(f'   ⚠️  {filename}: 缺少配图（未找到 {filename}_<8位后缀>.*）')
    raw_url = data.get('preview', '')
    normalized = [raw_url] if raw_url else []
    preview_urls = resolve_image_url(filename, normalized, preview_files)
    webp_urls = resolve_image_webp(filename, preview_files)

    # 变量：两种形态都归一化，避免旧 `list[str]` 形态被静默丢弃
    #   标准形态 [{kv_var, style_var, desc?}] —— 新文件推荐
    #   旧形态   ['中文标题'] / ['"{车型}" — 示例：…']
    # 非列表（mapping）或无法识别的条目一律跳过并告警，不要造垃圾键。
    variables_raw = data.get('variables', []) or []
    variables = {}
    if not isinstance(variables_raw, list):
        print(f'   ⚠️  {filename}: variables 不是列表（{type(variables_raw).__name__}），已忽略')
        variables_raw = []
    for v in variables_raw:
        if isinstance(v, dict):
            kv_var = str(v.get('kv_var', '') or '').strip()
            style_var = str(v.get('style_var', '') or '').strip()
            if (kv_var, style_var) in VARIABLE_HEADER_ROWS:
                # Markdown 表格转 yaml 的表头残留，不是真实变量
                continue
            if kv_var and style_var:
                variables[kv_var] = style_var
        elif isinstance(v, str) and v.strip():
            if v.strip() in VARIABLE_HEADER_ROWS_FLAT:
                # 表头残留在旧形态里（['变量', '说明']）
                continue
            name, placeholder, desc = parse_legacy_variable(v.strip())
            if name and placeholder:
                variables[name] = placeholder
            else:
                print(f'   ⚠️  {filename}: 跳过无法识别的 variables 条目'
                      f'（既非变量名也不含 {{占位符}}）: {v.strip()[:60]}')

    return {
        'id': filename,
        'code': '',
        'name': data.get('name', filename),
        'category': data.get('category', dirname),
        'tags': tags,
        'triggers': triggers,
        'scene': data.get('scene', ''),
        'ratio': data.get('ratio', ''),
        'summary': data.get('summary', ''),
        'features': features,
        'prompt': data.get('prompt', ''),
        'variables': variables,
        'source_url': data.get('source_url', ''),
        'source_author': source_author,
        'preview_urls': preview_urls,
        'preview_webp': webp_urls.get('full'),
        'preview_webp_thumb': webp_urls.get('thumb'),
    }

def generate_styles_json(output_path: str):
    """生成 styles.json"""
    all_styles = []
    categories = set()

    # 检查 styles/ 根目录是否存在错放/后缀错误的风格文件（.yml 或根目录 .yaml）
    root_stray = [f for f in sorted(os.listdir(STYLES_DIR))
                  if (f.endswith('.yaml') or f.endswith('.yml')) and os.path.isfile(os.path.join(STYLES_DIR, f))]
    if root_stray:
        print('⚠️  发现错放的风格文件（应在 styles/{分类}/ 子目录且使用 .yaml 后缀）:')
        for f in root_stray:
            print(f'   ❌ styles/{f}  ← 需移动到 styles/typography/{f.replace(".yml", ".yaml")}')

    for entry in sorted(os.listdir(STYLES_DIR)):
        entry_path = os.path.join(STYLES_DIR, entry)
        if not os.path.isdir(entry_path) or entry.startswith('_'):
            continue
        categories.add(entry)
        for f in sorted(os.listdir(entry_path)):
            # 兼容 .yaml 与 .yml（.yml 会被读取但提示标准化）
            if not (f.endswith('.yaml') or f.endswith('.yml')) or f.startswith('_'):
                continue
            if f.endswith('.yml'):
                print(f'   ⚠️  建议将 {entry}/{f} 重命名为 .yaml 后缀（当前脚本兼容读取）')
            filepath = os.path.join(entry_path, f)
            try:
                style = parse_style_file(filepath)
                all_styles.append(style)
            except Exception as e:
                print(f'⚠️  跳过 {f}: {e}')

    # 排序（按文件名倒序，最新的优先）
    all_styles.sort(key=lambda s: s['id'], reverse=True)

    # 持久化编号：已有风格保持原编号，新风格分配下一个可用编号（永不重用）
    numbers_map = {}
    max_number = 0
    if os.path.exists(NUMBERS_FILE):
        with open(NUMBERS_FILE) as f:
            numbers_map = json.load(f)
        for v in numbers_map.values():
            # 支持字符串 'ST0151' 和整数 151 两种格式
            if isinstance(v, str):
                v = int(v.replace('ST', ''))
            max_number = max(max_number, v)

    existing_ids = {s['id'] for s in all_styles}
    # 清理已被删除风格的编号（不再占用数字）
    removed = [sid for sid in numbers_map if sid not in existing_ids]
    for sid in removed:
        del numbers_map[sid]

    next_number = max_number + 1 if max_number > 0 else 1
    for style in all_styles:
        sid = style['id']
        if sid in numbers_map:
            v = numbers_map[sid]
            if isinstance(v, str):
                v = int(v.replace('ST', ''))
            style['code'] = f'ST{v:04d}'
            style['number'] = f'ST{v:06d}'
        else:
            numbers_map[sid] = next_number
            style['code'] = f'ST{next_number:04d}'
            style['number'] = f'ST{next_number:06d}'
            next_number += 1

    # 持久化保存
    with open(NUMBERS_FILE, 'w') as f:
        json.dump(numbers_map, f, indent=2)
        f.write('\n')

    # 加载时间戳（用于排序）
    timestamps_map = {}
    if os.path.exists(TIMESTAMPS_FILE):
        with open(TIMESTAMPS_FILE) as f:
            timestamps_map = json.load(f)
    for style in all_styles:
        style['created_at'] = timestamps_map.get(style['id'], '')

    data = {
        'meta': {
            'version': get_version(),
            'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'total': len(all_styles),
            'categories': sorted(categories),
        },
        'styles': all_styles,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 统计数据
    webp_full = sum(1 for s in all_styles if s.get('preview_webp'))
    webp_thumb = sum(1 for s in all_styles if s.get('preview_webp_thumb'))
    missing = sum(1 for s in all_styles if not s['preview_urls'])

    print(f'✅ 已生成 {output_path}')
    print(f'   风格总数: {len(all_styles)}')
    print(f'   分类数:   {len(categories)}')
    print(f'   版本:     {data["meta"]["version"]}')
    print(f'   图片: 本地 {sum(1 for s in all_styles if s["preview_urls"])}, 远程 0, 缺失 {missing}')
    print(f'   WebP: 全尺寸 {webp_full}, 缩略图 {webp_thumb}')

    # 检查缺失 WebP 的风格
    no_webp = [s['id'] for s in all_styles if not s.get('preview_webp')]
    if no_webp:
        print(f'   ⚠️  以下风格缺少 WebP: {", ".join(no_webp)}')

    return data


def generate_plain_list(all_styles: list) -> str:
    """生成纯文本列表"""
    lines = [f"共 {len(all_styles)} 个风格\n"]
    for i, s in enumerate(all_styles, 1):
        code = s.get('code', f'ST{i:04d}')
        name = s.get('name', '?')
        preview = s.get('preview_urls', [])
        url = preview[0] if preview else '(无图片)'
        lines.append(f'{code} | {name} | {url}')
    return '\n'.join(lines)


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    data = generate_styles_json(os.path.join(DATA_DIR, 'styles.json'))
    list_path = os.path.join(DATA_DIR, 'styles_list.txt')
    with open(list_path, 'w', encoding='utf-8') as f:
        f.write(generate_plain_list(data['styles']))
    print(f'✅ 列表已生成 {list_path}')
