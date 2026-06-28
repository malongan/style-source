#!/usr/bin/env python3
"""合并后自动追加 _collection_log.md。

环境变量：
  PR_AUTHOR: PR 提交者 GitHub 用户名
  GIT_BASE_SHA: PR 目标分支 SHA
  GIT_HEAD_SHA: PR 源分支 SHA
"""
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

STYLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')
LOG_FILE = os.path.join(STYLES_DIR, '_collection_log.md')

def get_changed_md_files(base_sha: str, head_sha: str) -> list:
    """使用三点语法获取 PR 引入的新增/修改的 .yaml 文件"""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', '--diff-filter=AM',
             f'{base_sha}...{head_sha}'],
            capture_output=True, text=True, check=True,
            cwd=os.path.dirname(STYLES_DIR)
        )
        files = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line.startswith('styles/') and line.endswith('.yaml') and not os.path.basename(line).startswith('_'):
                files.append(line)
        return files
    except subprocess.CalledProcessError as e:
        print(f'⚠️  git diff 失败: {e}', file=sys.stderr)
        return []

def extract_source_url(filepath: str) -> str:
    """从风格 YAML 文件中提取来源链接"""
    import yaml
    full_path = os.path.join(os.path.dirname(STYLES_DIR), filepath)
    if not os.path.isfile(full_path):
        return ''
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return (data.get('source_url', '') or '').strip()
    except Exception:
        return ''

def append_to_log(entries: list):
    """追加日志到 _collection_log.md"""
    if not entries:
        return

    # 按日期排序
    entries.sort(key=lambda x: x['date'])

    header = '# 收集记录日志\n\n记录每次收集提示词的时间、来源、生成风格等信息。\n\n| 日期 | 来源链接 | 生成风格 | 收集者 | 备注 |\n|------|----------|----------|--------|------|\n'

    # 读取现有日志
    existing = []
    if os.path.isfile(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        # 提取已存在的表行
        for line in content.split('\n'):
            if line.strip().startswith('|') and '|' in line[2:]:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4 and parts[1] and re.match(r'\d{4}-\d{2}-\d{2}', parts[1]):
                    existing.append(line.rstrip())

    # 追加新行
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    new_lines = []
    for entry in entries:
        url_short = entry['url'][:60] + '...' if len(entry['url']) > 60 else entry['url']
        new_lines.append(f"| {entry['date']} | {url_short} | {entry['style']} | @{entry['author']} | 新建 |")

    # 合并去重（按来源链接 + 风格名去重）
    seen = set()
    all_lines = []
    for line in existing + new_lines:
        parts = [p.strip() for p in line.split('|')]
        key = f"{parts[2]}|{parts[3]}" if len(parts) >= 4 else line
        if key not in seen:
            seen.add(key)
            all_lines.append(line)

    # 写入
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(all_lines))
        f.write('\n')

    print(f'✅ _collection_log.md 已更新，新增 {len(new_lines)} 条记录')

def main():
    author = os.environ.get('PR_AUTHOR', 'unknown')
    base_sha = os.environ.get('GIT_BASE_SHA', '')
    head_sha = os.environ.get('GIT_HEAD_SHA', '')

    if not base_sha or not head_sha:
        # 回退：使用最近的 commit
        print('⚠️  GIT_BASE_SHA/GIT_HEAD_SHA 未设置，使用 HEAD~1', file=sys.stderr)
        base_sha = 'HEAD~1'
        head_sha = 'HEAD'

    files = get_changed_md_files(base_sha, head_sha)

    if not files:
        print('ℹ️  未检测到新增的风格文件')
        return

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    entries = []
    for f in files:
        style_name = os.path.basename(f).replace('.yaml', '')
        url = extract_source_url(f)
        entries.append({
            'date': today,
            'url': url or '(无来源链接)',
            'style': style_name,
            'author': author,
        })

    append_to_log(entries)

if __name__ == '__main__':
    main()
