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

def check_by_name(name: str) -> list:
    """按风格名查重"""
    existing = list_all_style_files()
    matches = [s for s in existing if s['name'] == name]
    return matches

def check_by_url(url: str) -> list:
    """按来源链接查重"""
    records = load_collection_log()
    matches = [r for r in records if r['url'] == url]
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
            print(f'❌ 来源链接已被收集:')
            for m in matches:
                print(f'   风格: {m["style"]}, 时间: {m["date"]}, 收集者: {m["collector"]}')
            found = True
        else:
            print(f'✅ 来源链接未收集过')

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
        # PR 模式：检查 git diff 中的新文件是否冲突
        import subprocess
        base_sha = os.environ.get('GIT_BASE_SHA', 'main')
        result = subprocess.run(
            ['git', 'diff', '--name-only', f'{base_sha}...HEAD'],
            capture_output=True, text=True, cwd=os.path.dirname(STYLES_DIR)
        )
        new_files = [f for f in result.stdout.split('\n') if f.startswith('styles/') and f.endswith('.yaml') and not os.path.basename(f).startswith('_')]
        
        for f in new_files:
            name = os.path.basename(f).replace('.yaml', '')
            if check_by_name(name):
                print(f'❌ PR 中的新风格 "{name}" 与已有风格同名')
                found = True

    sys.exit(1 if found else 0)

if __name__ == '__main__':
    main()
