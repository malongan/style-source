#!/usr/bin/env python3
"""检查所有风格的配图完整性（防回归）：
1. 每个风格必须有 preview_webp（全尺寸）
2. 每个风格必须有 preview_webp_thumb（缩略图），且本地文件真实存在
3. 文件命名必须**整段锚定**匹配 {style_id}_{8位后缀}.webp 规范
4. 同一张图不得被多个风格引用（配图串号）
5. 一个风格不得有多个前缀相同的候选配图（前缀歧义 → 串号风险）
6. 错放的风格文件（styles/ 根目录 .yml/.yaml）会被标记
7. images/styles_previews/ 下未被 styles.json 引用的孤儿文件会被标记

> 第 4/5 条是 2026-10-10 事故的回归护栏：当时 generate_data.py 用未排序的
> `glob('{style_id}_*.webp')[0]` 前缀匹配，`doodle_style` 借用了
> `doodle_style_poster_5f705d81.webp`，导致它自己的真图被判"孤儿"而误删。

用法：
  python3 scripts/check_style_previews.py           # 检查并列出问题
  python3 scripts/check_style_previews.py --strict  # 有问题时 exit 1（供 CI 使用）
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLES_DIR = os.path.join(ROOT, 'styles')
IMAGES_DIR = os.path.join(ROOT, 'images')
PREVIEW_DIR = os.path.join(IMAGES_DIR, 'styles_previews')
DATA_FILE = os.path.join(ROOT, 'data', 'styles.json')

# 与 generate_data.py 保持一致：{style_id}_{8位字母数字后缀}.{ext}
IMAGE_SUFFIX_RE = re.compile(r'^(?P<style_id>.+)_(?P<suffix>[0-9A-Za-z]{8})$')
FULL_IMAGE_EXTS = ('.webp', '.jpg', '.jpeg', '.png')

# 内容级重复图检查（300 张大图全量读一遍 ~18MB，可接受；--no-content-check 可关）
IMAGES_CONTENT_CHECK = '--no-content-check' not in sys.argv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true', help='有问题时 exit 1')
    args = parser.parse_args()

    problems = []
    notes = []

    # 1. 检查 styles/ 根目录错放文件
    for f in sorted(os.listdir(STYLES_DIR)):
        full = os.path.join(STYLES_DIR, f)
        if os.path.isfile(full) and (f.endswith('.yaml') or f.endswith('.yml')):
            problems.append(f'[错放] styles/{f} 应在 styles/{f.replace(".yml", ".yaml").replace(".yaml", "typography/") if "typography" not in f else "子目录"}')

    # 2. 加载 styles.json
    if not os.path.exists(DATA_FILE):
        problems.append(f'[缺失] {DATA_FILE} 不存在，先运行 python3 scripts/generate_data.py')
        return _report(problems, notes, args.strict)

    with open(DATA_FILE) as fp:
        data = json.load(fp)

    # 3. 逐风格检查
    referenced_full = collections.Counter()
    for s in data['styles']:
        sid = s.get('id', '?')
        full_url = s.get('preview_webp') or ''
        thumb_url = s.get('preview_webp_thumb') or ''

        if not full_url:
            problems.append(f'[{sid}] 缺少 preview_webp（全尺寸）')
            continue

        # 全尺寸本地文件存在性 + 整段锚定命名 + 归属校验
        full_name = full_url.split('/')[-1]
        referenced_full[full_name] += 1
        if not os.path.exists(os.path.join(PREVIEW_DIR, full_name)):
            problems.append(f'[{sid}] preview_webp 文件不存在: {full_name}')
        else:
            stem = os.path.splitext(full_name)[0]
            m = IMAGE_SUFFIX_RE.match(stem)
            if not m:
                problems.append(f'[{sid}] 文件命名不规范: {full_name}'
                                f'（应为 {sid}_<8位后缀>.webp）')
            elif m.group('style_id') != sid:
                problems.append(f'[{sid}] 配图串号: {full_name} 实际归属 "{m.group("style_id")}"'
                                f'（{sid} 需要自己的 {sid}_<8位后缀>.webp）')

        if not thumb_url:
            problems.append(f'[{sid}] 缺少 preview_webp_thumb（缩略图）— 运行 generate_data.py 会自动生成')
            continue

        thumb_name = thumb_url.split('/')[-1]
        if not os.path.exists(os.path.join(PREVIEW_DIR, thumb_name)):
            problems.append(f'[{sid}] preview_webp_thumb 文件不存在: {thumb_name}（404 风险）')
        elif not thumb_name.endswith('.thumb.webp'):
            problems.append(f'[{sid}] 缩略图命名不规范: {thumb_name}（应以 .thumb.webp 结尾）')
        elif thumb_name != os.path.splitext(full_name)[0] + '.thumb.webp':
            # 缩略图必须与全尺寸同 base：否则详情页会显示另一张图（仅靠孤儿检查不一定暴露）
            problems.append(f'[{sid}] 缩略图与全尺寸不是同一 base: full={full_name} thumb={thumb_name}')

    # 3b. 同一张图被多个风格引用 → 配图串号（回归护栏）
    for name, n in sorted(referenced_full.items()):
        if n > 1:
            owners = [s['id'] for s in data['styles']
                      if (s.get('preview_webp') or '').split('/')[-1] == name]
            problems.append(f'[配图串号] {name} 被 {n} 个风格同时引用: {owners}')

    # 3b-2. 内容级重复：不同文件名但**字节相同**的配图。
    # 同一来源推文派生多个风格时，复用同一张参考图是**合理**的（如 science_cover/illustration/
    # infographic），所以只提示不判失败 —— 但它是发现"误配同一张图"的兜底信号。
    if os.path.isdir(PREVIEW_DIR) and IMAGES_CONTENT_CHECK:
        by_md5 = collections.defaultdict(list)
        for s in data['styles']:
            name = (s.get('preview_webp') or '').split('/')[-1]
            path = os.path.join(PREVIEW_DIR, name)
            if name and os.path.exists(path):
                with open(path, 'rb') as fp:
                    by_md5[hashlib.md5(fp.read()).hexdigest()].append(s['id'])
        for h, ids in sorted(by_md5.items()):
            if len(ids) > 1:
                notes.append(f'内容重复配图（{h[:8]}）被 {len(ids)} 个风格共用: {ids}'
                             f' —— 同一来源派生多风格属正常，若非预期需核对')

    # 3c. 前缀歧义：某风格存在 ≥2 个前缀相同的候选配图（锚定匹配已免疫，仅作提示，不判失败）
    if os.path.isdir(PREVIEW_DIR):
        all_files = [f for f in os.listdir(PREVIEW_DIR) if not f.endswith('.thumb.webp')]
        for s in data['styles']:
            sid = s.get('id', '?')
            candidates = [f for f in all_files
                          if os.path.splitext(f)[0].startswith(sid + '_')
                          and os.path.splitext(f)[1].lower() in FULL_IMAGE_EXTS]
            if len(candidates) > 1:
                notes.append(f'[{sid}] 前缀歧义：{len(candidates)} 个候选配图 {sorted(candidates)}'
                             f'—— 当前靠"整段锚定"正确归属，禁止改回前缀匹配')

    # 4. 全量文件 vs styles.json 引用（找出 styles.json 未引用的孤儿文件，提醒清理）
    referenced = set()
    for s in data['styles']:
        for k in ('preview_webp', 'preview_webp_thumb'):
            u = s.get(k) or ''
            if u:
                referenced.add(u.split('/')[-1])
    if os.path.isdir(PREVIEW_DIR):
        for f in sorted(os.listdir(PREVIEW_DIR)):
            if f not in referenced:
                problems.append(f'[孤儿文件] images/styles_previews/{f} 未被 styles.json 引用，'
                                f'先确认不是被前缀匹配挤掉的合法配图，再清理')

    return _report(problems, notes, args.strict)


def _report(problems: list, notes: list, strict: bool) -> int:
    for n in notes:
        print(f'ℹ️  {n}')
    if not problems:
        print('✅ 配图完整性检查通过：所有风格都有全尺寸 + 缩略图，命名规范，无串号')
        return 0
    print(f'⚠️  发现 {len(problems)} 个问题:')
    for p in problems:
        print(f'   {p}')
    if strict:
        print('❌ 检查未通过（--strict）')
        return 1
    print('ℹ️  运行 python3 scripts/generate_data.py 可自动修复缩略图缺失')
    return 0


if __name__ == '__main__':
    sys.exit(main())
