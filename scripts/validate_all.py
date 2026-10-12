#!/usr/bin/env python3
"""校验 styles/ 下所有风格文件的格式。

用法：
  python3 scripts/validate_all.py                  # 报告问题，但只要有 error 就 exit 1
  python3 scripts/validate_all.py --check-images   # 附带预览图 URL 可达性
  python3 scripts/validate_all.py --no-strict      # 只报告，exit 0（排查遗留数据时用）

⚠️ 2026-10-12 更正：本脚本此前无论有无 error 都 `sys.exit(0)`，注释还谎称
"新文件在 PR 检查中会被拦截"——而两个 workflow 调的都是本脚本，导致格式闸门
形同虚设。现在默认 **有 error 即 exit 1**，CI 才真的拦得住。
"""
import sys
import os

from validate_style import validate_file


def main():
    styles_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')
    if not os.path.isdir(styles_dir):
        print(f'❌ styles/ 目录不存在: {styles_dir}')
        sys.exit(1)

    check_images = '--check-images' in sys.argv
    strict = '--no-strict' not in sys.argv

    all_errors = {}
    all_warnings = {}
    total = 0
    for root, dirs, files in os.walk(styles_dir):
        for f in sorted(files):
            if not f.endswith('.yaml') or f.startswith('_'):
                continue
            filepath = os.path.join(root, f)
            errors, warnings = validate_file(filepath, check_images=check_images)
            total += 1
            if errors:
                all_errors[filepath] = errors
            if warnings:
                all_warnings[filepath] = warnings

    print(f'\n检查了 {total} 个风格文件')

    if all_warnings:
        print(f'\n⚠️ {len(all_warnings)} 个文件有建议项:')
        for filepath, warnings in sorted(all_warnings.items())[:5]:
            relpath = os.path.relpath(filepath, styles_dir)
            for w in warnings:
                print(f'  {relpath}: {w}')
        if len(all_warnings) > 5:
            print(f'  ... 还有 {len(all_warnings)-5} 个文件有建议项')

    if all_errors:
        print(f'\n❌ {len(all_errors)} 个文件有格式错误:')
        for filepath, errors in sorted(all_errors.items())[:10]:
            relpath = os.path.relpath(filepath, styles_dir)
            for err in errors[:3]:
                print(f'  {relpath}: {err}')
        if len(all_errors) > 10:
            print(f'  ... 还有 {len(all_errors)-10} 个文件需清理')
        if strict:
            print('\n❌ 校验未通过（--no-strict 可只报告不失败）')
            sys.exit(1)
        print('\n⚠️  --no-strict：只报告，不失败')
        sys.exit(0)

    print(f'✅ 全部 {total} 个文件格式正确')
    sys.exit(0)


if __name__ == '__main__':
    main()
