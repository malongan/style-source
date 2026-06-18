#!/usr/bin/env python3
"""上传配图到 style-source/images/styles_previews/，与风格文件一起版本管理。

用法：python3 scripts/upload_preview.py <图片路径> <风格名>

示例：
  python3 scripts/upload_preview.py /tmp/preview.jpg bubble_card
  → 输出：https://malongan.github.io/style-source/images/styles_previews/bubble_card_a3f8c92e.jpg

不再需要单独上传到 malongan/images 仓库，
图片与 .md 文件在同一仓库中一起提交。
"""
import os
import sys
import hashlib
import shutil

IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'images', 'styles_previews')
STYLE_SOURCE_URL = 'https://malongan.github.io/style-source/images/styles_previews'

def get_content_hash(image_path: str) -> str:
    """计算图片内容的 MD5 哈希前 8 位"""
    hash_md5 = hashlib.md5()
    with open(image_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()[:8]

def compress_image(src: str, max_width: int = 1200) -> str:
    """压缩图片到指定宽度（用系统自带 sips）"""
    import subprocess
    # 检查是否已经是 jpg/png/webp
    ext = os.path.splitext(src)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        print(f'⚠️  不支持的图片格式: {ext}，尝试强制转 jpg')
        ext = '.jpg'

    # 压缩
    out_path = src  # 原地压缩
    try:
        subprocess.run(
            ['sips', '-Z', str(max_width), src],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        print(f'⚠️  sips 压缩失败: {e.stderr}')
    return out_path

def main():
    if len(sys.argv) < 3:
        print('用法: python3 scripts/upload_preview.py <图片路径> <风格名>')
        print('示例: python3 scripts/upload_preview.py /tmp/preview.jpg bubble_card')
        sys.exit(1)

    image_path = sys.argv[1]
    style_name = sys.argv[2]

    if not os.path.isfile(image_path):
        print(f'❌ 图片文件不存在: {image_path}')
        sys.exit(1)

    # 获取文件大小
    file_size = os.path.getsize(image_path)
    if file_size > 2 * 1024 * 1024:
        print(f'⚠️  图片 {file_size/1024/1024:.1f}MB，超过 2MB 限制，自动压缩')
        compress_image(image_path)

    # 计算内容哈希
    content_hash = get_content_hash(image_path)
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        ext = '.jpg'

    # 目标文件名
    target_filename = f'{style_name}_{content_hash}{ext}'
    target_path = os.path.join(IMAGES_DIR, target_filename)

    # 确保目录存在
    os.makedirs(IMAGES_DIR, exist_ok=True)

    # 复制文件
    shutil.copy2(image_path, target_path)
    file_size_kb = os.path.getsize(target_path) / 1024

    # 输出 URL
    image_url = f'{STYLE_SOURCE_URL}/{target_filename}'

    print(f'✅ 图片已保存: {target_path}')
    print(f'   大小: {file_size_kb:.1f}KB')
    print(f'   URL: {image_url}')
    print(f'')
    print(f'下一步:')
    print(f'  1. 将以上 URL 填入风格文件的 ## 参考配图')
    print(f'  2. git add images/styles_previews/{target_filename}')
    print(f'  3. git commit -m "feat: add preview image for {style_name}"')

if __name__ == '__main__':
    main()
