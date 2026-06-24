#!/usr/bin/env python3
"""
检查 data/styles.json 中所有预览图 URL（WebP）是否可访问。
顺序检查+重试。用于 CI 流程，确保图片没有丢失。
如果 URL 不可达但本地文件存在（新图片未部署），也视为通过。
"""
import json, os, sys, subprocess, time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(REPO_ROOT, 'data', 'styles.json')


def check_url(url: str) -> bool:
    """检查 URL 是否返回 200，最多重试 2 次"""
    for attempt in range(3):
        try:
            result = subprocess.run(
                ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                 '--max-time', '10', '--head', url],
                capture_output=True, text=True, timeout=15)
            code = result.stdout.strip()
            if code == '200':
                return True
        except Exception:
            pass
        if attempt < 2:
            time.sleep(2)
    return False


def check_local(url: str) -> bool:
    """检查 URL 对应的文件是否在本地仓库中存在"""
    if 'images/' not in url:
        return False
    rel_path = url.split('images/', 1)[1]
    return os.path.isfile(os.path.join(REPO_ROOT, 'images', rel_path))


def main():
    if not os.path.isfile(DATA_FILE):
        print(f'❌ {DATA_FILE} 不存在'); sys.exit(1)

    with open(DATA_FILE, encoding='utf-8') as f:
        data = json.load(f)

    failed = []
    local_only = []
    total = len(data['styles'])
    print(f'📋 检查 {total} 个风格的 WebP 预览图 URL\n')

    for i, style in enumerate(data['styles'], 1):
        sid = style.get('id', '?')
        url = style.get('preview_webp', '') or (style.get('preview_urls') or [''])[0]
        if not url:
            print(f'  ⚠️  [{i:3d}/{total}] {sid}: 无预览图 URL')
            failed.append((sid, '无 URL'))
            continue

        if 'style-source' not in url:
            print(f'  ➖  [{i:3d}/{total}] {sid}: 跳过外部 URL')
            continue

        # 优先检查 URL 可达性
        if check_url(url):
            print(f'  ✅  [{i:3d}/{total}] {sid}')
            continue

        # URL 不可达时，回退到本地文件检查（新图片尚未部署到 Pages）
        if check_local(url):
            print(f'  📁  [{i:3d}/{total}] {sid}: 本地文件存在，URL 待部署')
            local_only.append(sid)
            continue

        # 都不存在 → 错误
        print(f'  ❌  [{i:3d}/{total}] {sid}: URL 不可达且本地不存在')
        failed.append((sid, 'URL 不可达且本地不存在'))

    print(f'\n📊 通过: {total - len(failed)}/{total}')
    if local_only:
        print(f'📁 本地文件待部署: {len(local_only)} 个')
    if failed:
        print(f'❌ 失败 {len(failed)} 个:')
        for sid, r in failed:
            print(f'  - {sid}: {r}')
        sys.exit(1)
    print('✅ 全部通过！')


if __name__ == '__main__':
    main()
