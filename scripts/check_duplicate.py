#!/usr/bin/env python3
"""查重工具：检查风格名/URL/内容哈希是否已存在。"""
import os
import re
import sys
import argparse
from difflib import SequenceMatcher

STYLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')

def load_collection_log() -> list:
    """读取 _collection_log.md，返回已有记录列表"""
    log_path = os.path.join(STYLES_DIR, '_collection_log.md')
    if not os.path.isfile(log_path):
        return []
    
    records = []
    with open(log_path, 'r', encoding='utf-8') as f:
        in_table = False
        for line in f:
            if '| 日期' in line and '来源链接' in line:
                in_table = True
                continue
            if in_table and line.strip().startswith('|'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    records.append({
                        'date': parts[1],
                        'url': parts[2],
                        'style': parts[3],
                        'collector': parts[4] if len(parts) > 4 else '',
                    })
    return records

# 用户从浏览器复制的分享链接常带 `?a=...&s=20` 这类参数，yaml 里存的是裸链接。
# 不归一化就永远比对不上 —— 这是「URL 查重形同虚设」的隐藏原因之一。
URL_CANON_RE = re.compile(
    r'^(?:https?://)?(?:www\.)?(?:twitter|x)\.com/(.+?)(?:[?#].*)?$', re.I)


def canon_url(url: str) -> str:
    """归一化来源链接：去 query/fragment、twitter.com 视同 x.com、去尾斜杠、小写。"""
    if not url:
        return ''
    m = URL_CANON_RE.match(url.strip())
    if not m:
        return url.strip().rstrip('/').lower()
    return 'https://x.com/%s' % m.group(1).strip().rstrip('/').lower()


def load_yaml_urls() -> list:
    """从所有风格 yaml 的 `source_url` 收集来源链接。

    这是查重的**真相源**。过去 `check_by_url` 只读 `_collection_log.md`，
    而那份日志 2026-06-26 之后就断更了（此后 200+ 个风格没进日志），
    等于近半年的 URL 查重全部落空 —— 查什么都说「未收集过」。
    yaml 的 source_url 跟风格文件一起提交，永远是最新的。
    """
    import yaml
    out = []
    for root, _dirs, files in os.walk(STYLES_DIR):
        for f in files:
            if not f.endswith('.yaml') or f.startswith('_'):
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    data = yaml.safe_load(fh) or {}
            except Exception:
                continue
            su = (data.get('source_url') or '')
            if isinstance(su, str) and su.strip():
                out.append({
                    'style': data.get('id') or f[:-5],
                    'path': os.path.relpath(fp, STYLES_DIR),
                    'url': su.strip(),
                    'from': 'yaml',
                })
    return out


def list_all_style_files() -> list:
    """列出所有现有的风格文件"""
    styles = []
    for root, dirs, files in os.walk(STYLES_DIR):
        for f in files:
            if f.endswith('.yaml') and not f.startswith('_'):
                rel_path = os.path.relpath(os.path.join(root, f), STYLES_DIR)
                styles.append({
                    'name': f.replace('.yaml', ''),
                    'path': rel_path,
                })
    return styles

def check_by_name(name: str, exclude_rel: str = None) -> list:
    """按风格名查重。

    exclude_rel：要排除的文件（相对 styles/ 的路径）。PR 模式下传入正在检查的
    新文件自身 —— 它已经在磁盘上，不排除的话每个新风格都会「与自己同名」。
    """
    existing = list_all_style_files()
    matches = [s for s in existing if s['name'] == name]
    if exclude_rel:
        matches = [s for s in matches if s['path'] != exclude_rel]
    return matches

def check_by_url(url: str) -> list:
    """按来源链接查重：yaml source_url（主真相源）+ _collection_log.md（历史补）。

    两边都查 —— yaml 覆盖全部存量风格，日志覆盖早期（2026-06 之前）的收集记录。
    """
    target = canon_url(url)
    if not target:
        return []
    matches = [r for r in load_yaml_urls() if canon_url(r['url']) == target]
    for r in load_collection_log():
        if canon_url(r['url']) == target:
            matches.append({
                'style': r['style'], 'url': r['url'], 'date': r['date'],
                'collector': r['collector'], 'path': '(collection_log)',
                'from': 'log',
            })
    return matches

def check_similarity(new_prompt: str, threshold: float = 0.8) -> list:
    """内容相似度检测（读取已有风格 YAML 文件的提示词进行比较）"""
    import yaml
    results = []
    for root, dirs, files in os.walk(STYLES_DIR):
        for f in files:
            if not f.endswith('.yaml') or f.startswith('_'):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath, 'r', encoding='utf-8') as fp:
                    data = yaml.safe_load(fp)
                existing_prompt = (data.get('prompt', '') or '')[:300]
                if not existing_prompt:
                    continue
                similarity = SequenceMatcher(
                    None, new_prompt[:300], existing_prompt
                ).ratio()
                if similarity > threshold:
                    results.append({
                        'style': f.replace('.yaml', ''),
                        'similarity': round(similarity, 3),
                    })
            except Exception:
                continue
    return results

def main():
    parser = argparse.ArgumentParser(description='查重工具')
    parser.add_argument('--name', help='检查风格名是否已存在')
    parser.add_argument('--url', help='检查来源链接是否已存在')
    parser.add_argument('--prompt', help='检查提示词内容相似度')
    parser.add_argument('--pr-mode', action='store_true', help='PR 模式：检查当前分支新增文件是否与已有文件冲突')
    args = parser.parse_args()

    found = False

    if args.name:
        matches = check_by_name(args.name)
        if matches:
            print(f'❌ 风格名 "{args.name}" 已存在:')
            for m in matches:
                print(f'   {m["path"]}')
            found = True
        else:
            print(f'✅ 风格名 "{args.name}" 可用')

    if args.url:
        matches = check_by_url(args.url)
        if matches:
            print('❌ 来源链接已被收集（比对前已归一化 query/域名）:')
            for m in matches:
                extra = m.get('date') or m.get('path')
                print(f'   风格: {m["style"]}  [{m.get("from")}]  {extra}')
            found = True
        else:
            print('✅ 来源链接未收集过')

    if args.prompt:
        matches = check_similarity(args.prompt)
        if matches:
            print(f'⚠️  提示词与以下风格高度相似 (>80%):')
            for m in matches:
                print(f'   {m["style"]} (相似度: {m["similarity"]:.1%})')
            found = bool([m for m in matches if m['similarity'] > 0.95])
        else:
            print(f'✅ 提示词无高度相似匹配')

    if args.pr_mode:
        # PR 模式：检查 git diff 中的**新增**文件是否冲突
        import subprocess
        base_sha = os.environ.get('GIT_BASE_SHA', 'main')
        repo_root = os.path.dirname(STYLES_DIR)
        # --diff-filter=A 必须带：原来只用 --name-only，把「修改过的文件」也当成
        # 新增，于是一个只改 desc 的 PR 会报 30 条「与已有风格同名」。
        result = subprocess.run(
            ['git', 'diff', '--name-only', '--diff-filter=A', f'{base_sha}...HEAD'],
            capture_output=True, text=True, cwd=repo_root
        )
        new_files = [f for f in result.stdout.split('\n')
                     if f.startswith('styles/') and f.endswith('.yaml')
                     and not os.path.basename(f).startswith('_')]

        import yaml
        # 先建一张「归一化 URL -> 现有风格」的表（排除本次新增文件自身）
        new_rel_set = {os.path.relpath(os.path.join(repo_root, f), STYLES_DIR) for f in new_files}
        url_index = {}
        for r in load_yaml_urls():
            if r['path'] in new_rel_set:
                continue
            url_index.setdefault(canon_url(r['url']), []).append(r)

        for f in new_files:
            name = os.path.basename(f).replace('.yaml', '')
            # 排除新文件自身：它已经在工作区里，否则必然「与自己同名」
            self_rel = os.path.relpath(os.path.join(repo_root, f), STYLES_DIR)
            if check_by_name(name, exclude_rel=self_rel):
                print(f'❌ PR 中的新风格 "{name}" 与已有风格同名')
                found = True

            # 来源 URL 冲突：同一推文收成两个风格（ST0240/ST0241 那类重复就是这么来的）
            try:
                with open(os.path.join(repo_root, f), 'r', encoding='utf-8') as fh:
                    src = (yaml.safe_load(fh) or {}).get('source_url') or ''
            except Exception:
                src = ''
            if src:
                hits = url_index.get(canon_url(src), [])
                if hits:
                    print(f'❌ PR 中的新风格 "{name}" 来源链接已被收集:')
                    for h in hits:
                        print(f'   已存在: {h["style"]}  ({h["path"]})')
                    print(f'   来源: {src}')
                    found = True

    sys.exit(1 if found else 0)

if __name__ == '__main__':
    main()
