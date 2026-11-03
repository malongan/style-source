#!/usr/bin/env python3
"""提交前一键体检：按 CI 的顺序跑完全部闸门，只给一个结论。

为什么需要它：CI 的检查散在 3 个 workflow、9 类命令里，本地「只跑记得住的那几条」
是常态 —— 2026-11-03 就漏跑了 `audit_variables.py --strict`（PR 侥幸全绿，因为库本来就干净）。
一条命令跑完，绿了再开 PR，就不会出现「本地通过、CI 红」。

用法：
    python3 scripts/preflight.py                 # 默认全量（不含联网 / 安全扫描）
    python3 scripts/preflight.py --with-network  # 额外验证配图 URL 可达性（需联网，慢）
    python3 scripts/preflight.py --with-security # 额外跑发布前安全扫描
    python3 scripts/preflight.py --base main     # 指定 PR 查重基线（默认 origin/main）
    python3 scripts/preflight.py --skip-generate # 只校验，不重算生成物

退出码：全部通过 0；任一 FAIL 1。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

# (名称, 命令, 是否必须通过)
def steps(args):
    dupe_base = args.base
    s = [
        ('格式 + 变量语义（validate_all --strict --require-desc）',
         [PY, 'scripts/validate_all.py', '--strict', '--require-desc']),
        ('生成 styles.json（generate_data）',
         [PY, 'scripts/generate_data.py']),
        ('变量语义体检（audit_variables --strict）',
         [PY, 'scripts/audit_variables.py', '--strict']),
        ('生成 gallery（build_gallery）',
         [PY, 'scripts/build_gallery.py']),
        ('重算索引（generate_index）',
         [PY, 'scripts/generate_index.py']),
        ('配图完整性（check_style_previews --strict）',
         [PY, 'scripts/check_style_previews.py', '--strict']),
        ('teaser 检测回归（test_teaser_detector）',
         [PY, 'scripts/test_teaser_detector.py']),
        ('YAML 卫生（lint_hygiene）',
         [PY, 'scripts/lint_hygiene.py', '--strict']),
        ('查重（check_duplicate --pr-mode）',
         [PY, 'scripts/check_duplicate.py', '--pr-mode'], {'GIT_BASE_SHA': dupe_base}),
    ]
    if args.with_network:
        s.append(('配图 URL 可达性（validate_all --check-images，联网）',
                  [PY, 'scripts/validate_all.py', '--check-images', '--no-strict']))
    if args.with_security:
        scan = '/Users/qiqi/open/agents/scripts/github-manager/pre-push-security-scan.py'
        if os.path.isfile(scan):
            s.append(('发布前安全扫描', [PY, scan, '.']))
        else:
            s.append(('发布前安全扫描（脚本缺失，跳过）', None))
    return s


def check_env() -> bool:
    """先探测解释器：本机 /usr/bin/python3 自带 pyyaml + Pillow。"""
    try:
        import yaml  # noqa: F401
        import PIL  # noqa: F401
        print('  ✅ %s  pyyaml=%s  Pillow=%s'
              % (PY, yaml.__version__, PIL.__version__))
        return True
    except Exception as exc:
        print('  ❌ 解释器缺依赖：%s' % exc)
        print('     用 /usr/bin/python3 跑本脚本，或：')
        print('       python3 -m venv /tmp/stylevenv && /tmp/stylevenv/bin/pip install pyyaml pillow')
        return False


def run(name, cmd, env_extra=None) -> bool:
    print()
    print('▶ %s' % name)
    if cmd is None:
        print('  ⚠️ 跳过')
        return True
    env = dict(os.environ)
    if env_extra:
        env.update({k: str(v) for k, v in env_extra.items()})
    proc = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True)
    tail = [l for l in (proc.stdout + proc.stderr).strip().split('\n') if l.strip()]
    for line in tail[-6:]:
        print('  ' + line)
    ok = proc.returncode == 0
    print('  %s' % ('✅ PASS' if ok else '❌ FAIL (exit %d)' % proc.returncode))
    return ok


def report_unstaged_generated() -> None:
    """生成物有改动就提醒 —— 提交时最容易漏的就是 style_numbers.json / styles_list.txt。"""
    try:
        out = subprocess.run(
            ['git', 'status', '--porcelain', '--', 'data/', 'gallery.html',
             'gallery.css', 'gallery-runtime.js', 'styles/_index.md'],
            cwd=REPO, capture_output=True, text=True).stdout.strip()
    except Exception:
        return
    if not out:
        return
    # porcelain 格式是 "XY <path>"，路径前有 1 个空格分隔；用 split 比定长切片稳
    files = [l.strip().split(None, 1)[1] for l in out.split('\n')
             if l.strip() and len(l.strip().split(None, 1)) > 1]
    print()
    print('▶ 生成物变更（提交时不要漏，用目录通配 git add data/ gallery.html ...）')
    for f in files:
        print('  M %s' % f)


def main() -> int:
    ap = argparse.ArgumentParser(description='提交前一键体检')
    ap.add_argument('--with-network', action='store_true', help='额外验证配图 URL 可达性（联网）')
    ap.add_argument('--with-security', action='store_true', help='额外跑发布前安全扫描')
    ap.add_argument('--base', default='origin/main', help='查重基线（默认 origin/main）')
    ap.add_argument('--skip-generate', action='store_true', help='跳过 generate_*（只校验）')
    args = ap.parse_args()

    print('=' * 64)
    print('preflight — 提交前一键体检   仓库：%s' % REPO)
    print('=' * 64)

    print()
    print('▶ 环境探测')
    if not check_env():
        return 1

    results = []
    for item in steps(args):
        name, cmd = item[0], item[1]
        extra = item[2] if len(item) > 2 else None
        if args.skip_generate and 'generate' in ' '.join(cmd or []):
            continue
        results.append((name, run(name, cmd, extra)))

    report_unstaged_generated()

    failed = [n for n, ok in results if not ok]
    print()
    print('=' * 64)
    if failed:
        print('❌ preflight 未通过（%d/%d 失败）：' % (len(failed), len(results)))
        for n in failed:
            print('   - %s' % n)
        print('=' * 64)
        return 1
    print('✅ preflight 全绿（%d 项）—— 可以开 PR' % len(results))
    print('=' * 64)
    return 0


if __name__ == '__main__':
    sys.exit(main())

