#!/usr/bin/env python3
"""检查所有风格的配图完整性（防回归）：
1. 每个风格必须有 preview_webp（全尺寸）
2. 每个风格必须有 preview_webp_thumb（缩略图），且本地文件真实存在
3. 文件命名必须匹配 {style_id}_{hash}.webp 规范
4. 错放的风格文件（styles/ 根目录 .yml/.yaml）会被标记

用法：
  python3 scripts/check_style_previews.py           # 检查并列出问题
  python3 scripts/check_style_previews.py --strict  # 有问题时 exit 1（供 CI 使用）
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLES_DIR = os.path.join(ROOT, 'styles')
IMAGES_DIR = os.path.join(ROOT, 'images')
DATA_FILE = os.path.join(ROOT, 'data', 'styles.json')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true', help='有问题时 exit 1')
    args = parser.parse_args()

    problems = []

    # 1. 检查 styles/ 根目录错放文件
    for f in sorted(os.listdir(STYLES_DIR)):
        full = os.path.join(STYLES_DIR, f)
        if os.path.isfile(full) and (f.endswith('.yaml') or f.endswith('.yml')):
            problems.append(f'[错放] styles/{f} 应在 styles/{f.replace(".yml", ".yaml").replace(".yaml", "typography/") if "typography" not in f else "子目录"}')

    # 2. 加载 styles.json
    if not os.path.exists(DATA_FILE):
        problems.append(f'[缺失] {DATA_FILE} 不存在，先运行 python3 scripts/generate_data.py')
        return _report(problems, args.strict)

    with open(DATA_FILE) as fp:
        data = json.load(fp)

    # 3. 逐风格检查
    for s in data['styles']:
        sid = s.get('id', '?')
        full_url = s.get('preview_webp') or ''
        thumb_url = s.get('preview_webp_thumb') or ''

        if not full_url:
            problems.append(f'[{sid}] 缺少 preview_webp（全尺寸）')
            continue

        # 全尺寸本地文件存在性
        full_name = full_url.split('/')[-1]
        if not os.path.exists(os.path.join(IMAGES_DIR, 'styles_previews', full_name)):
            problems.append(f'[{sid}] preview_webp 文件不存在: {full_name}')
        elif not full_name.startswith(sid + '_'):
            problems.append(f'[{sid}] 文件命名不规范: {full_name}（应为 {sid}_*.webp）')

        if not thumb_url:
            problems.append(f'[{sid}] 缺少 preview_webp_thumb（缩略图）— 运行 generate_data.py 会自动生成')
            continue

        thumb_name = thumb_url.split('/')[-1]
        if not os.path.exists(os.path.join(IMAGES_DIR, 'styles_previews', thumb_name)):
            problems.append(f'[{sid}] preview_webp_thumb 文件不存在: {thumb_name}（404 风险）')
        elif not thumb_name.endswith('.thumb.webp'):
            problems.append(f'[{sid}] 缩略图命名不规范: {thumb_name}（应以 .thumb.webp 结尾）')

    # 4. 全量文件 vs styles.json 引用（找出 styles.json 未引用的孤儿文件，提醒清理）
    referenced = set()
    for s in data['styles']:
        for k in ('preview_webp', 'preview_webp_thumb'):
            u = s.get(k) or ''
            if u:
                referenced.add(u.split('/')[-1])
    for f in sorted(os.listdir(os.path.join(IMAGES_DIR, 'styles_previews'))):
        if f not in referenced:
            problems.append(f'[孤儿文件] images/styles_previews/{f} 未被 styles.json 引用，可清理')

    return _report(problems, args.strict)


def _report(problems: list, strict: bool) -> int:
    if not problems:
        print('✅ 配图完整性检查通过：所有风格都有全尺寸 + 缩略图，命名规范')
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
