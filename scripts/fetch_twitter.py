#!/usr/bin/env python3
"""抓取 X（Twitter）推文正文与原始配图。

为什么不用网页解析：x.com 对无登录直连返回 SSL EOF 或空壳页面，
`data-testid="tweetText"` 早就取不到内容（2026-11 实测：SSL: EOF occurred
in violation of protocol）。api.fxtwitter.com 一次 GET 就给出正文、作者、
媒体原始 URL、原始尺寸和 alt，不用浏览器、不用登录、不触发反爬。

用法：
    python3 scripts/fetch_twitter.py <url>                # 正文 + 第一张原图 → /tmp/style_preview.jpg
    python3 scripts/fetch_twitter.py <url> --no-parent    # 关闭「父推配图回退」

自回复（self-thread）自动回退：prompt 在回复里、成品图在父推里是这批账号的主流形态。
本条推文 media 为 null 且 replying_to_status 存在时，自动沿同作者的父推向上找图（默认最多 5 层），
并在输出的 media_source 字段里记明来源；父推作者不同则不继承（那是别人的图）。
    python3 scripts/fetch_twitter.py <url> --all          # 全部原图 → /tmp/style_p1.jpg, style_p2.jpg ...
    python3 scripts/fetch_twitter.py <url> --no-download  # 只取正文与图片 URL
    python3 scripts/fetch_twitter.py <url> --json         # 只打印 JSON（供管线消费）

图片下载按 orig → large → medium 三档降级：pbs.twimg.com 会随机返回空响应，
单档重试不够，换档才有可能拿到（这是 CDN 侧的抖动，不是 URL 写错）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = 'https://api.fxtwitter.com/{user}/status/{tid}'

# 兼容 x.com / twitter.com / mobile. 前缀，以及 /status/ 与 /statuses/ 两种写法
TWEET_URL_RE = re.compile(
    r'(?:^|//|\.)(?:twitter|x)\.com/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d+)')

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

# 「teaser 推文」识别：正文只是引子，真正的 prompt 在作者自己的回复里。
#
# 2026-11-03 用**真实语料**定的规则，不是拍脑袋：
#   语料 = 中文化之前的 90 条英文 prompt（git show 61a08d6^:data/styles.json）
#   硬信号在 90 条上**零误报**，8 种 teaser 变体**全部命中**
#   软信号只命中 1 条已知边界（korean_illustration，357 字符的完整但无变量 prompt）
#
# 误报与漏报的代价不对称：
#   漏报 → 用户以为抓全了，实际只拿到引子 → **静默失败**（D46 同款陷阱）
#   误报 → 多看一眼就知道 → 可见，代价低
# 所以宁可误报，不可漏报：硬信号放宽，软信号只提示不报警。
CONTINUATION_RE = re.compile(
    r'(prompt|full\s+(?:prompt|text)|提示词|完整)?\s*[🔽👇⬇↓🧵]\s*$', re.I)
ENDS_COLON_RE = re.compile(
    r'(prompt|full\s+(?:prompt|text)|提示词)\s*[:：]\s*$', re.I)
BELOW_RE = re.compile(
    r'(see\s+below|read\s+below|more\s+below|below\s+the\s+line|'
    r'in\s+the\s+thread|see\s+thread|thread\s+below|see\s+reply|'
    r'full\s+prompt\s+below|见下方|评论区|往下翻|往下看|下方回复)\s*[.。!！]?\s*$', re.I)
SLOT_RE = re.compile(r'\{[^{}\n]{1,40}\}|\[[A-Z_ ]{2,30}=\s*_+\]')


def detect_teaser(text: str):
    """判断这条推文是不是「teaser」—— 正文只是引子，prompt 在回复里。

    返回 (hard, soft)：
      hard = 强信号，几乎确定是 teaser（正文里有明确的「往下看」引导）
      soft = 弱信号，可能不是完整 prompt（很短且没有任何槽位），只提示不报警

    2026-11-03 实测：@AmirMushich 的 prompt 系列都这样，首推只有一句引子加
    「Prompt 🔽」，真正的 9000+ 字符 prompt 在自己的第一条回复里。
    抓首推会得到「238 字符的引子 + 4 张图」，看起来像抓成功了，其实 prompt 没拿到。
    """
    t = (text or '').strip()
    if not t or len(t) > 800:
        return False, False
    if CONTINUATION_RE.search(t) or ENDS_COLON_RE.search(t) or BELOW_RE.search(t):
        return True, False
    # 「Prompt:」开头、正文却很短 —— 大概率后面还有正文
    if t.lower().startswith('prompt') and len(t) < 300:
        return True, False
    # 弱信号：短且无槽位。像 korean_illustration 这种（357 字符、无变量的完整
    # prompt）会命中 —— 所以只给软提示，不报警。
    if len(t) < 500 and not SLOT_RE.search(t):
        return False, True
    return False, False


def looks_like_teaser(text: str) -> bool:
    """只关心「是不是 teaser」的布尔视图（旧的调用方用）。"""
    return detect_teaser(text)[0]


# 只认真实的图片字节，防止把 HTML 错误页存成 .jpg
IMG_MAGIC = ((b'\xff\xd8\xff', 'jpg'), (b'\x89PNG', 'png'),
             (b'RIFF', 'webp'), (b'GIF8', 'gif'))


def parse_url(url: str) -> tuple:
    """从推文 URL 解析出 (用户名, 推文 id)。"""
    m = TWEET_URL_RE.search(url)
    if not m:
        sys.exit('❌ 无法解析 URL：%s\n   需要形如 https://x.com/{用户}/status/{数字id}' % url)
    return m.group(1), m.group(2)


def fetch(url: str, retries: int = 3) -> dict:
    """调 fxtwitter API 取推文原始 JSON，失败时带退避重试。"""
    user, tid = parse_url(url)
    api = API.format(user=user, tid=tid)
    last = '未知错误'
    for i in range(retries):
        try:
            req = urllib.request.Request(
                api, headers={'User-Agent': UA, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=25) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
            if payload.get('code') == 200 and payload.get('tweet'):
                return payload['tweet']
            last = 'API 返回 code=%s message=%s' % (payload.get('code'), payload.get('message'))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = '%s: %s' % (type(exc).__name__, exc)
        if i < retries - 1:
            time.sleep(1.5 * (i + 1))
    raise RuntimeError('抓取失败（已重试 %d 次）：%s' % (retries, last))


def normalize(tweet: dict) -> dict:
    """把 API 响应压成稳定结构，只留收集流程要用的字段。"""
    media = tweet.get('media') or {}
    photos = []
    for item in media.get('all') or []:
        if item.get('type') != 'photo':
            continue
        photos.append({
            'url': item.get('url'),
            'width': item.get('width'),
            'height': item.get('height'),
            'alt': (item.get('altText') or '').strip(),
        })
    author = tweet.get('author') or {}
    return {
        'url': tweet.get('url'),
        'id': tweet.get('id'),
        'text': (tweet.get('text') or '').strip(),
        'author_name': author.get('name'),
        'author_handle': author.get('screen_name'),
        'created_at': tweet.get('created_at'),
        'photos': photos,
        'has_video': any(m.get('type') in ('video', 'gif')
                         for m in media.get('all') or []),
        # 自回复（self-thread）：prompt 在回复里、配图在父推里 —— 这类账号的主流发布形态
        'replying_to': tweet.get('replying_to'),
        'replying_to_status': tweet.get('replying_to_status'),
        'media_source': {'from': 'self' if photos else 'none'},
    }


def resolve_parent_media(result: dict, max_depth: int = 5) -> dict:
    """目标推文没有配图时，沿 self-thread 向上找父推的配图。

    背景：这批 prompt 分享号的常见形态是「父推发成品图，回复里发 prompt 文本」。
    直接抓回复会得到 media=null，正文却是完整的 prompt —— 只有回收到父推才拿得到图。

    安全边界：只在「父推作者 == 目标作者」时才继承。回复别人的推文时，
    父推的图属于别人，不能被当成这个风格的配图，宁可报 0 张让人工处理。

    多级回退：父推自己也可能没有图（连续多条回复后才附图），最多向上找 max_depth 层。
    """
    if result['photos'] or result.get('has_video'):
        return result

    handle = result.get('author_handle')
    tid = result.get('replying_to_status')
    if not handle or not tid:
        return result

    seen = {result.get('id')}
    for depth in range(1, max_depth + 1):
        if tid in seen:
            break
        seen.add(tid)
        try:
            parent = normalize(fetch('https://x.com/%s/status/%s' % (handle, tid)))
        except RuntimeError as exc:
            print('  ⚠️ 父推 %s 抓取失败：%s' % (tid, exc), file=sys.stderr)
            break
        if (parent.get('author_handle') or '').lower() != handle.lower():
            print('  ⓘ 父推 %s 作者是 @%s（非同作者），不继承其配图'
                  % (tid, parent.get('author_handle')), file=sys.stderr)
            break
        if parent['photos']:
            result['photos'] = parent['photos']
            result['media_source'] = {
                'from': 'parent',
                'tweet_id': parent['id'],
                'parent_url': parent.get('url'),
                'depth': depth,
                'note': 'prompt 在本条，配图在父推（self-thread）',
            }
            return result
        tid = parent.get('replying_to_status')
        if not tid:
            break
    result['media_source'] = {'from': 'none'}
    return result


def sniff(head: bytes):
    """按文件头判断图片格式，认不出就返回 None。"""
    for magic, ext in IMG_MAGIC:
        if head.startswith(magic):
            return ext
    return None


def download(photo_url: str, dest_base: str, retries: int = 3):
    """按 orig → large → medium 逐档降级下载，返回 (路径, 档位, 字节数) 或 None。

    fxtwitter 给的 URL 有时已带 `?name=orig`，必须先剥掉 query 再拼档位，
    否则会变成 `?name=orig&name=orig` 直接 404。
    """
    base_url = photo_url.split('?')[0]
    last_err = ''
    for quality in ('orig', 'large', 'medium'):
        candidate = '%s?name=%s' % (base_url, quality)
        for attempt in range(retries):
            try:
                req = urllib.request.Request(candidate, headers={
                    'User-Agent': UA, 'Referer': 'https://x.com/'})
                with urllib.request.urlopen(req, timeout=40) as resp:
                    body = resp.read()
                ext = sniff(body[:16])
                if not ext:
                    raise ValueError('返回的不是图片（%r）' % body[:40])
                path = '%s.%s' % (dest_base, ext)
                with open(path, 'wb') as fh:
                    fh.write(body)
                return path, quality, len(body)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                last_err = '%s: %s' % (type(exc).__name__, exc)
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
    print('  ⚠️ 三档全部失败：%s\n     %s' % (photo_url, last_err), file=sys.stderr)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description='抓取 X 推文正文与原始配图')
    ap.add_argument('url', help='推文 URL')
    ap.add_argument('--all', action='store_true', help='下载全部配图（默认只下第一张）')
    ap.add_argument('--no-download', action='store_true', help='只取正文与图片 URL')
    ap.add_argument('--json', action='store_true', help='只打印 JSON')
    ap.add_argument('--out-dir', default='/tmp', help='图片保存目录（默认 /tmp）')
    ap.add_argument('--no-parent', action='store_true',
                    help='不沿 self-thread 回退父推取配图（默认会回退）')
    args = ap.parse_args()

    try:
        result = normalize(fetch(args.url))
        if not args.no_parent:
            result = resolve_parent_media(result)
    except RuntimeError as exc:
        print('❌ %s' % exc, file=sys.stderr)
        return 1

    result['local_images'] = []
    if not args.no_download and result['photos']:
        picks = result['photos'] if args.all else result['photos'][:1]
        for i, photo in enumerate(picks, 1):
            base = os.path.join(args.out_dir,
                                'style_p%d' % i if args.all else 'style_preview')
            got = download(photo['url'], base)
            if got:
                path, quality, size = got
                result['local_images'].append(
                    {'path': path, 'quality': quality, 'bytes': size})

    # 固定落一份 JSON，方便后续步骤直接读，不用再解析 stdout
    with open(os.path.join(args.out_dir, 'twitter_result.json'), 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print('=== 抓取成功 ===')
    print('作者：%s @%s' % (result['author_name'], result['author_handle']))
    print('时间：%s' % result['created_at'])
    _hard, _soft = detect_teaser(result.get('text'))
    if _hard:
        print()
        print('⚠️  ⚠️  这条推文疑似「teaser」：正文只是引子，真正的 prompt 在作者自己的回复里。')
        print('   本次抓到的是 %d 字符的引子，不是完整 prompt。' % len(result.get('text') or ''))
        print('   怎么办：')
        print('     1) 打开该推文页面，找到作者的第一条回复（正文以 "Prompt:" 开头那条）')
        print('     2) 复制那条回复的链接，形如 https://x.com/<作者>/status/<数字id>')
        print('     3) 用那条链接再跑一次本脚本：')
        print('        python3 scripts/fetch_twitter.py "https://x.com/<作者>/status/<回复id>"')
        print('     4) 脚本会自动沿父推回退取到配图（输出会写「取自父推」）')
        print('   判据：正文结尾有下引引导（🔽 / 👇 / ↓ / 🧵 / Prompt: 结尾 / see below 等）。')
    elif _soft:
        print()
        print('ℹ️  这条推文很短（%d 字符）且正文里没有任何槽位占位符，'
              % len(result.get('text') or ''))
        print('   —— 可能是完整 prompt（本就没有变量），也可能是只抓到了引子。')
        print('   请扫一眼正文，确认它是完整的 prompt 模板再继续。')

    src = result.get('media_source') or {}
    if src.get('from') == 'parent':
        print('配图：%d 张（**取自父推** %s，prompt 在本条回复里）'
              % (len(result['photos']), src.get('tweet_id')))
    elif src.get('from') == 'none' and result.get('replying_to_status'):
        if args.no_parent:
            print('配图：0 张（本条是回复且自身无图；--no-parent 已关闭父推回退）')
        else:
            print('配图：0 张（本条与同作者父推链上均无图 —— 页面上的图可能属于别人，需人工确认）')
    else:
        print('配图：%d 张%s' % (len(result['photos']),
                                '（含视频/GIF）' if result['has_video'] else ''))
    print()
    print('--- 正文 ---')
    print(result['text'] or '（空）')
    for i, photo in enumerate(result['photos'], 1):
        print()
        print('--- 图%d %sx%s ---' % (i, photo['width'], photo['height']))
        print('URL：%s' % photo['url'])
        print('alt：%s' % (photo['alt'] or '（空）'))
    if result['local_images']:
        print()
        print('--- 已下载 ---')
        for img in result['local_images']:
            print('  %s  (%s, %.0f KB)' % (img['path'], img['quality'], img['bytes'] / 1024))
    print()
    print('JSON：%s' % os.path.join(args.out_dir, 'twitter_result.json'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
