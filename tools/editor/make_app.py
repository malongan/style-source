#!/usr/bin/env python3
"""生成「风格编辑器.app」——把启动/停止合成一个图标。

用法：
    /usr/bin/python3 tools/editor/make_app.py            # 装到 /Applications
    /usr/bin/python3 tools/editor/make_app.py --dir ~/Applications

特点：
  - 图标用 Pillow 现画（暖色渐变 + 白色四角星），不依赖外部素材
  - 双击行为：没运行就启动并打开浏览器；已在运行就弹框让你选「打开 / 停止」
  - 包里写的是本仓库的绝对路径，仓库搬家后重跑本脚本即可
  - CFBundleExecutable 是编译出来的原生启动器（不是 shell 脚本）：
    脚本型 app 容易被 Finder 丢进 Rosetta 翻译成 x86_64，子进程跟着变 x86_64，
    撞上 ~/Library/Python 里 arm64 的 Pillow（ImportError: incompatible architecture）。
    有编译环境就用原生启动器；没有就退回脚本（editorctl 里还有第二层兜底）。
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
CTL = os.path.join(HERE, 'editorctl')
APP_NAME = '风格编辑器'
BUNDLE_ID = 'cn.malongan.style-editor'

# 图标参数（在 1024 画布上试过：2.45 的四角星辨识度和重量最平衡）
S = 1024
PAD = 100
SIDE = S - PAD * 2
RADIUS = 185
STAR_POWER = 2.45
STAR_RATIO = 0.33
C1 = (255, 193, 94)     # 暖橙
C2 = (226, 62, 95)      # 玫红

RUN_SH = r"""#!/bin/bash
# 风格编辑器 —— 统一入口：没运行就启动，在运行就让你选打开还是停止
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
APP_NAME="{app_name}"
CTL="{ctl}"
LOG="{log}"

mkdir -p "$(dirname "$LOG")"
say() {{ printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" >> "$LOG"; }}

# 无图形界面的自检模式：直接打印动作，不弹框
nogui() {{ [ "${{STYLE_EDITOR_NOGUI:-0}}" = "1" ]; }}

ask() {{   # $1=正文  $2=按钮(AppleScript 列表)  $3=默认按钮
  if nogui; then
    echo "DIALOG: $1 | $2 | default=$3" >&2
    printf '%s' "$3"          # 自检模式：直接当用户点了默认按钮
    return 0
  fi
  /usr/bin/osascript -e "display dialog \"$1\" buttons $2 default button \"$3\" with title \"$APP_NAME\" with icon note" 2>/dev/null \
    | sed 's/^button returned://'
}}

notify() {{
  if nogui; then echo "NOTIFY: $1"; return 0; fi
  /usr/bin/osascript -e "display notification \"$1\" with title \"$APP_NAME\"" >/dev/null 2>&1
}}

if [ ! -x "$CTL" ]; then
  say "找不到控制脚本 $CTL"
  ask "找不到控制脚本：$CTL —— 仓库可能被移动了，请重新运行 tools/editor/make_app.py。" '{{"好"}}' "好" >/dev/null
  exit 1
fi

state="$("$CTL" state 2>>"$LOG")"
say "state=$state"

case "$state" in
  running-ok)
    btn="$(ask "编辑器正在运行。要打开，还是停止服务？" '{{"取消","停止服务","打开编辑器"}}' "打开编辑器")"
    case "$btn" in
      打开编辑器) "$CTL" open >>"$LOG" 2>&1 ;;
      停止服务)   "$CTL" stop >>"$LOG" 2>&1; notify "编辑器已停止" ;;
    esac
    ;;
  running-bad)
    btn="$(ask "服务进程在，但数据接口异常（多半是上一次启动残留）。重启一下？" '{{"取消","重启服务"}}' "重启服务")"
    [ "$btn" = "重启服务" ] && {{ "$CTL" restart >>"$LOG" 2>&1 && "$CTL" open >>"$LOG" 2>&1; }}
    ;;
  *)
    btn="$(ask "编辑器没有在运行。启动后会直接打开浏览器，不用输口令。" '{{"取消","启动并打开"}}' "启动并打开")"
    if [ "$btn" = "启动并打开" ]; then
      if ! "$CTL" up >>"$LOG" 2>&1; then
        msg="$("$CTL" last-error 2>/dev/null)"
        [ -z "$msg" ] && msg="看日志：tools/editor/.state/editor.log"
        say "启动失败：$msg"
        ask "启动失败：$msg" '{{"好"}}' "好" >/dev/null
        exit 1
      fi
    fi
    ;;
esac

exit 0
"""

# 原生启动器：只做一件事——把 Resources/run.sh 交给 bash。
# 为什么不用脚本当 CFBundleExecutable：脚本型 app 被 LaunchServices 启动时
# 可能落进 Rosetta（进程被翻译成 x86_64），子进程继承翻译，python 于是加载不了
# arm64 的 Pillow。Mach-O 二进制的架构是明确的，arm64 机器上必然原生启动。
RUN_C = r"""/* 风格编辑器原生启动器：exec /bin/bash Resources/run.sh */
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char exe[PATH_MAX];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0) {
        return 127;
    }
    char *slash = strrchr(exe, '/');           /* .../Contents/MacOS/run */
    if (slash == NULL) {
        return 127;
    }
    *slash = '\0';

    char script[PATH_MAX];
    snprintf(script, sizeof(script), "%s/../Resources/run.sh", exe);

    char **args = calloc((size_t)argc + 2, sizeof(char *));
    if (args == NULL) {
        return 127;
    }
    args[0] = (char *)"/bin/bash";
    args[1] = script;
    for (int i = 1; i < argc; i++) {
        args[i + 1] = argv[i];
    }

    execv("/bin/bash", args);
    perror("execv /bin/bash");
    return 127;
}
"""

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>{name}</string>
  <key>CFBundleDisplayName</key><string>{name}</string>
  <key>CFBundleIdentifier</key><string>{bid}</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>run</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>10.15</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSArchitecturePriority</key><array><string>arm64</string><string>x86_64</string></array>
  <key>LSApplicationCategoryType</key><string>public.app-category.developer-tools</string>
</dict>
</plist>
"""


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def draw_icon(master_path):
    from PIL import Image, ImageDraw, ImageFilter

    grad = Image.new('RGB', (SIDE, SIDE))
    px = grad.load()
    for y in range(SIDE):
        for x in range(SIDE):
            t = min(1.0, x / SIDE * 0.42 + y / SIDE * 0.58)
            px[x, y] = lerp(C1, C2, t)

    mask = Image.new('L', (SIDE, SIDE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIDE - 1, SIDE - 1), radius=RADIUS, fill=255)
    body = Image.new('RGBA', (SIDE, SIDE), (0, 0, 0, 0))
    body.paste(grad.convert('RGBA'), (0, 0), mask)

    pts = []
    for i in range(960):
        t = 2 * math.pi * i / 960
        c, s = math.cos(t), math.sin(t)
        pts.append((SIDE / 2 + SIDE * STAR_RATIO * math.copysign(abs(c) ** STAR_POWER, c),
                    SIDE / 2 + SIDE * STAR_RATIO * math.copysign(abs(s) ** STAR_POWER, s)))
    star = Image.new('RGBA', (SIDE, SIDE), (0, 0, 0, 0))
    ImageDraw.Draw(star).polygon(pts, fill=(255, 255, 255, 255))

    sh = Image.new('RGBA', (SIDE, SIDE), (0, 0, 0, 0))
    sh.paste((120, 25, 35, 90), (0, 0), star.split()[3])
    body = Image.alpha_composite(body, sh.filter(ImageFilter.GaussianBlur(18)))
    body = Image.alpha_composite(body, star)

    inner = Image.new('RGBA', (SIDE, SIDE), (0, 0, 0, 0))
    ImageDraw.Draw(inner).rounded_rectangle((3, 3, SIDE - 4, SIDE - 4), radius=RADIUS - 3,
                                            outline=(255, 255, 255, 55), width=3)
    body = Image.alpha_composite(body, inner)

    canvas = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    canvas.paste(body, (PAD, PAD), body)
    canvas.save(master_path)
    return canvas


def make_icns(build_dir):
    from PIL import Image
    from PIL.Image import LANCZOS
    iconset = os.path.join(build_dir, 'AppIcon.iconset')
    os.makedirs(iconset, exist_ok=True)
    master = Image.open(os.path.join(build_dir, 'master.png'))
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = base * scale
            name = 'icon_%dx%d%s.png' % (base, base, '@2x' if scale == 2 else '')
            master.resize((px, px), LANCZOS).save(os.path.join(iconset, name))
    icns = os.path.join(build_dir, 'AppIcon.icns')
    subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', icns], check=True)
    return icns


def build_launcher(macos_dir, res_dir, build_dir):
    """返回 'native' / 'script'：优先编译原生启动器，编译不了就退回脚本。"""
    script = os.path.join(res_dir, 'run.sh')
    with open(script, 'w', encoding='utf-8') as fh:
        fh.write(RUN_SH.format(app_name=APP_NAME, ctl=CTL,
                               log=os.path.join(HERE, '.state', 'app.log')))
    os.chmod(script, 0o755)

    exe = os.path.join(macos_dir, 'run')
    src = os.path.join(build_dir, 'launcher.c')
    with open(src, 'w', encoding='utf-8') as fh:
        fh.write(RUN_C)
    for cmd in (['clang', '-arch', 'arm64', '-arch', 'x86_64', '-O2', '-o', exe, src],
                ['clang', '-O2', '-o', exe, src]):
        if shutil.which('clang') is None:
            break
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode == 0 and os.path.isfile(exe):
            os.chmod(exe, 0o755)
            return 'native'

    shutil.copy2(script, exe)
    os.chmod(exe, 0o755)
    return 'script'


def build(target_dir, build_dir):
    os.makedirs(build_dir, exist_ok=True)
    draw_icon(os.path.join(build_dir, 'master.png'))
    icns = make_icns(build_dir)

    app = os.path.join(target_dir, APP_NAME + '.app')
    if os.path.exists(app):
        shutil.rmtree(app)
    macos = os.path.join(app, 'Contents', 'MacOS')
    res = os.path.join(app, 'Contents', 'Resources')
    os.makedirs(macos)
    os.makedirs(res)
    shutil.copy2(icns, os.path.join(res, 'AppIcon.icns'))

    kind = build_launcher(macos, res, build_dir)

    with open(os.path.join(app, 'Contents', 'Info.plist'), 'w', encoding='utf-8') as fh:
        fh.write(INFO_PLIST.format(name=APP_NAME, bid=BUNDLE_ID))

    # 本地自签，避免 Gatekeeper 把未签名的可执行文件当成可疑程序
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', app],
                   check=False, capture_output=True)
    return app, kind


def main():
    ap = argparse.ArgumentParser(description='生成 风格编辑器.app')
    ap.add_argument('--dir', default='/Applications', help='装到哪个目录（默认 /Applications）')
    args = ap.parse_args()

    target = os.path.expanduser(args.dir)
    if not os.access(target, os.W_OK):
        sys.exit('目录不可写：%s（可加 --dir ~/Applications）' % target)
    if not os.path.isfile(CTL):
        sys.exit('缺少 editorctl：%s' % CTL)

    app, kind = build(target, os.path.join(HERE, '.state', 'appbuild'))
    # 让 Finder / Launchpad 立刻认到新图标
    subprocess.run(['/System/Library/Frameworks/CoreServices.framework/Frameworks/'
                    'LaunchServices.framework/Support/lsregister', '-f', app], check=False)
    print('已生成：%s' % app)
    if kind == 'native':
        print('启动器：原生二进制（arm64 + x86_64），不会被 Rosetta 翻译')
    else:
        print('启动器：shell 脚本（没找到 clang；靠 editorctl 里的架构兜底）')
    print('双击行为：未运行 → 启动并打开浏览器；已运行 → 选「打开 / 停止」')


if __name__ == '__main__':
    main()
