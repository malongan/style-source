#!/usr/bin/env python3
"""即梦（jimeng.jianying.com）作品页抓取器 —— 一条命令拿提示词 + 原图。

用法（工作目录 style-source）：
    /usr/bin/python3 scripts/fetch_jimeng.py "<即梦作品URL>"
    /usr/bin/python3 scripts/fetch_jimeng.py "<URL>" --no-download      # 只看元信息与图片 URL
    /usr/bin/python3 scripts/fetch_jimeng.py "<URL>" --all              # 多图作品下载全部（默认只取第一张）
    /usr/bin/python3 scripts/fetch_jimeng.py "<URL>" --out /tmp/x.png   # 指定首图输出路径

产出：
    /tmp/jimeng_result.json   结构化结果（prompt / author / model / images / downloaded）
    默认下载首张原图到 /tmp/jimeng_orig.png（多张时为 /tmp/jimeng_p1.png ...）

原理与坑（2026-11-05 用两个真实作品验证，见 SKILL.md「即梦抓取」章节）：
  * 作品页是 SSR，HTML 里直接内嵌作品 JSON，不用登录、不用浏览器、不用 WebFetch 摘要。
  * JSON 里的 URL 被转义成 \\u002F / \\u0026，必须先还原再抓 byteimg 签名地址。
  * `aigc_resize:0:0.png` 是原图；`4096:4096.jpeg` 是同尺寸有损版；其余是缩略档。
  * 签名 URL 带 x-expires，抓完立刻下载；下载要带 Referer。
  * `"prompt"` 字段在页面里出现多次，还会混进无关的短串；以 text2imageParams 里那条为准。
只用标准库；下载复用 curl（对代理环境比 urllib 稳）。
"""

import argparse
import html as html_mod
import json
import os
import re
import subprocess
import sys
import tempfile

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
REFERER = "https://jimeng.jianying.com/"
WORK_ID_RE = re.compile(r"/work-detail/(\d+)")
IMG_URL_RE = re.compile(r'https://[a-z0-9.\-]*byteimg\.com/[^"\s<>\\]+')
TOS_KEY_RE = re.compile(r"(tos-cn-[^/]+/[0-9a-f]{32})")


def die(msg):
    print("❌ " + msg, file=sys.stderr)
    sys.exit(1)


def fetch_html(url, dest):
    cmd = ["curl", "-sL", "--retry", "2", "--retry-all-errors",
           "--max-time", "45", "-A", UA, "-H", "Referer: " + REFERER,
           "-o", dest, "-w", "%{http_code}", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        die("抓页面超时（45s）。检查网络，或稍后重试；不要改用浏览器猜内容。")
    code = (r.stdout or "").strip()
    if code != "200" or not os.path.exists(dest) or os.path.getsize(dest) < 5000:
        die("页面抓取失败（HTTP %s，%s 字节）。可能是网络抖动、需要登录或页面改版；"
            "把 HTML 存下来人工看一眼，不要拿别的作品的图凑。" %
            (code or "?", os.path.getsize(dest) if os.path.exists(dest) else 0))
    return open(dest, encoding="utf-8", errors="replace").read()


def unescape_ssr(raw):
    """还原 SSR JSON 里的 URL 转义，顺手处理 HTML 属性里的 &amp;。"""
    t = raw.replace("\\u002F", "/").replace("\\u0026", "&")
    t = t.replace("\\/", "/").replace('\\"', '"')
    return html_mod.unescape(t)


def json_string_after(t, key, start=0):
    """从 `"key":` 之后用 JSON 解码器取一个字符串值，避免正则被内嵌引号截断。"""
    m = re.search(r'"%s"\s*:\s*' % re.escape(key), t[start:])
    if not m:
        return None
    pos = start + m.end()
    try:
        val, _ = json.JSONDecoder().raw_decode(t[pos:])
        return val if isinstance(val, str) else None
    except (ValueError, TypeError):
        return None


def json_object_after(t, key):
    m = re.search(r'"%s"\s*:\s*' % re.escape(key), t)
    if not m:
        return {}
    try:
        val, _ = json.JSONDecoder().raw_decode(t[m.end():])
        return val if isinstance(val, dict) else {}
    except (ValueError, TypeError):
        return {}


def extract_prompt(t):
    """优先取 text2imageParams.prompt；没有再退回 aigcImageParams / 顶层 prompt。"""
    for anchor in ("text2imageParams", "aigcImageParams"):
        m = re.search(r'"%s"\s*:\s*\{' % anchor, t)
        if m:
            p = json_string_after(t, "prompt", m.start())
            if p and len(p) >= 20:
                return p
    candidates = []
    pos = 0
    while True:
        m = re.search(r'"prompt"\s*:\s*"', t[pos:])
        if not m:
            break
        p = json_string_after(t, "prompt", pos + m.start())
        if p:
            candidates.append(p)
        pos += m.end()
    return max(candidates, key=len) if candidates else None


def collect_images(t, cover_uri=None):
    """按 tos 图片 key 分组；同 key 的多档位只保留原图（0:0.png）或最大 jpeg。

    只认 aigc_resize 档位：页面里还有作者头像、相邻推荐作品的 ~tplv-resize:200:200
    之类的图，放宽条件会把它们误收成「多图作品」（2026-11-05 ST0338 实测踩过）。
    主图用 coverUri 锚定排到第一位，不按 URL 字典序猜。
    """
    groups = {}
    for u in sorted(set(IMG_URL_RE.findall(t))):
        if "aigc_resize" not in u:
            continue
        m = TOS_KEY_RE.search(u)
        if not m:
            continue
        key = m.group(1)
        if "aigc_resize:0:0.png" in u:
            rank = 10000
        else:
            size = re.search(r"aigc_resize:(\d+):", u)
            rank = int(size.group(1)) if size else 0
        prev = groups.get(key)
        if prev is None or rank > prev["rank"]:
            groups[key] = {"rank": rank, "url": u, "original": "aigc_resize:0:0.png" in u}
    values = list(groups.values())
    if cover_uri:
        values.sort(key=lambda v: 0 if cover_uri in v["url"] else 1)
    return [dict(url=v["url"], original=v["original"]) for v in values]


def download(url, dest):
    cmd = ["curl", "-sL", "--retry", "3", "--retry-all-errors",
           "--max-time", "90", "-A", UA, "-H", "Referer: " + REFERER,
           "-o", dest, "-w", "%{http_code}", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
    except subprocess.TimeoutExpired:
        return False, "下载超时"
    code = (r.stdout or "").strip()
    if code != "200" or not os.path.exists(dest):
        return False, "HTTP %s" % (code or "?")
    with open(dest, "rb") as f:
        head = f.read(12)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        fmt = "PNG"
    elif head.startswith(b"\xff\xd8\xff"):
        fmt = "JPEG"
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        fmt = "WEBP"
    else:
        return False, "文件头不是图片（可能拿到 HTML 错误页，或签名已过期）"
    return True, "%s %d bytes" % (fmt, os.path.getsize(dest))


def main():
    ap = argparse.ArgumentParser(description="即梦作品页：抓提示词 + 下载原图")
    ap.add_argument("url", help="即梦 work-detail 链接（带不带分享参数都行）")
    ap.add_argument("--no-download", action="store_true", help="只解析，不下载图片")
    ap.add_argument("--all", action="store_true", help="下载全部图片（默认只下第一张）")
    ap.add_argument("--out", help="首图输出路径（默认 /tmp/jimeng_orig.png）")
    ap.add_argument("--json", default="/tmp/jimeng_result.json", help="结构化结果输出路径")
    args = ap.parse_args()

    m = WORK_ID_RE.search(args.url)
    if not m:
        die("URL 里没有 /work-detail/<数字id>，这不是即梦作品页。X/推特请用 fetch_twitter.py。")
    work_id = m.group(1)
    canonical = "https://jimeng.jianying.com/ai-tool/work-detail/" + work_id

    tmp_html = os.path.join(tempfile.gettempdir(), "jimeng_%s.html" % work_id)
    raw = fetch_html(args.url, tmp_html)
    t = unescape_ssr(raw)

    prompt = extract_prompt(t)
    author_obj = json_object_after(t, "author")
    author = author_obj.get("name") if author_obj else None
    model_obj = json_object_after(t, "modelInfo")
    model = model_obj.get("modelName") if model_obj else None
    if not model:
        model = json_string_after(t, "modelName")
    ref_prompt = json_string_after(t, "referencePrompt")
    cover_uri = json_string_after(t, "coverUri")
    size_obj = json_object_after(t, "largeImageInfo")
    width, height = size_obj.get("width"), size_obj.get("height")
    images = collect_images(t, cover_uri)

    result = {
        "id": work_id,
        "source_url": canonical,          # 直接填 yaml 的 source_url，去掉易变的分享参数
        "page_html": tmp_html,
        "author": author,
        "model": model,
        "prompt": prompt,
        "reference_prompt": ref_prompt,
        "cover_uri": cover_uri,
        "width": width,
        "height": height,
        "images": images,
        "downloaded": [],
        "warnings": [],
    }

    if not prompt:
        result["warnings"].append("未解析到 prompt：页面结构可能改了，检查 %s 里的 text2imageParams" % tmp_html)
    if not images:
        result["warnings"].append("未找到 byteimg 签名图：可能是多图/视频作品或页面改版，检查 %s" % tmp_html)
    if cover_uri and len(images) > 1:
        result["warnings"].append("发现 %d 组图片，确认哪一组是本作品的成品图；默认只取第一张" % len(images))

    if not args.no_download and images:
        picked = images if args.all else images[:1]
        for i, img in enumerate(picked, 1):
            if args.out and i == 1:
                dest = args.out
            elif len(picked) == 1 and not args.all:
                dest = "/tmp/jimeng_orig.png"
            else:
                dest = "/tmp/jimeng_p%d.png" % i
            ok, detail = download(img["url"], dest)
            if ok:
                result["downloaded"].append({"path": dest, "info": detail, "original": img["original"]})
            else:
                result["warnings"].append("图片 %d 下载失败：%s（签名可能过期，重新跑一次本脚本）" % (i, detail))

    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("作品 ID : %s" % work_id)
    print("来源    : %s" % canonical)
    print("作者    : %s" % (author or "（未解析到）"))
    print("模型    : %s" % (model or "（未解析到）"))
    print("尺寸    : %s x %s" % (width, height))
    print("提示词  : %s" % (prompt or "（未解析到）"))
    if ref_prompt:
        print("参考词  : %s" % ref_prompt)
    print("图片组  : %d 组（原图档 %d 组）" % (len(images), sum(1 for x in images if x["original"])))
    for i, img in enumerate(images, 1):
        print("  [%d] %s %s" % (i, "原图" if img["original"] else "有损/缩略", img["url"].split("?")[0][-70:]))
    for d in result["downloaded"]:
        print("已下载  : %s (%s)" % (d["path"], d["info"]))
    for w in result["warnings"]:
        print("⚠️  %s" % w)
    print("JSON    : %s" % args.json)
    if not prompt or not images:
        sys.exit(1)
    if not args.no_download and not result["downloaded"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
