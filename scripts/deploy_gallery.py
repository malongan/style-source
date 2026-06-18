#!/usr/bin/env python3
"""将 dist/gallery.html 推送到 malongan/style-gallery 仓库。"""
import os
import subprocess
import sys
import tempfile
import shutil

DIST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dist')
GALLERY_HTML = os.path.join(DIST_DIR, 'gallery.html')
TARGET_REPO = 'git@github.com:malongan/style-gallery.git'
TARGET_BRANCH = 'main'

def deploy():
    if not os.path.isfile(GALLERY_HTML):
        print(f'❌ {GALLERY_HTML} 不存在，请先运行 build_gallery.py')
        sys.exit(1)

    # 克隆目标仓库到临时目录
    tmp_dir = tempfile.mkdtemp(prefix='style-deploy-')
    try:
        subprocess.run(
            ['git', 'clone', '--depth=1', TARGET_REPO, tmp_dir],
            check=True, capture_output=True, text=True
        )

        # 复制 gallery.html
        shutil.copy2(GALLERY_HTML, os.path.join(tmp_dir, 'gallery.html'))

        # 提交并推送
        subprocess.run(['git', 'add', 'gallery.html'], check=True, cwd=tmp_dir)
        result = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            cwd=tmp_dir, capture_output=True
        )

        if result.returncode == 0:
            print('ℹ️  gallery.html 无变化，跳过部署')
        else:
            subprocess.run(
                ['git', 'commit', '-m', 'chore: update gallery.html [skip ci]'],
                check=True, cwd=tmp_dir
            )
            subprocess.run(['git', 'push'], check=True, cwd=tmp_dir)
            print('✅ gallery.html 已推送到 style-gallery')

            # 触发 Pages 构建
            token = os.environ.get('GITHUB_TOKEN', '')
            if token:
                import urllib.request
                req = urllib.request.Request(
                    'https://api.github.com/repos/malongan/style-gallery/pages/builds',
                    data=b'{}',
                    headers={
                        'Authorization': f'token {token}',
                        'Content-Type': 'application/json',
                    },
                    method='POST'
                )
                try:
                    urllib.request.urlopen(req, timeout=30)
                    print('✅ Pages 构建已触发')
                except Exception as e:
                    print(f'⚠️  Pages 构建触发失败: {e}')
            else:
                print('⚠️  GITHUB_TOKEN 未设置，跳过 Pages 构建触发')

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == '__main__':
    deploy()
