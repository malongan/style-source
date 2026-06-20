#!/usr/bin/env python3
"""上传配图到 style-source/images/styles_previews/，自动生成 JPEG + WebP 版本。

用法：python3 scripts/upload_preview.py <图片路径> <风格名>

示例：
  python3 scripts/upload_preview.py /tmp/preview.jpg bubble_card
  → 输出：
      JPEG: https://.../bubble_card_a3f8c92e.jpg
      WebP: https://.../bubble_card_a3f8c92e.webp（全尺寸）
      Thumb: https://.../bubble_card_a3f8c92e.thumb.webp（400px 缩略图）

不再需要单独上传到 malongan/images 仓库，
图片与 .md 文件在同一仓库中一起提交。
"""
import os
import sys
import hashlib
import shutil
from PIL import Image

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
    ext = os.path.splitext(src)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        print(f'⚠️  不支持的图片格式: {ext}，尝试强制转 jpg')
        ext = '.jpg'
    out_path = src
    try:
        subprocess.run(
            ['sips', '-Z', str(max_width), src],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        print(f'⚠️  sips 压缩失败: {e.stderr}')
    return out_path

def generate_webp_versions(base_path: str, img: Image.Image):
    """从 PIL Image 生成 WebP 版本"""
    w, h = img.size

    # 全尺寸 WebP（最大 1000px，quality=85）
    webp_path = base_path + '.webp'
    if max(w, h) > 1000:
        ratio = 1000 / max(w, h)
        img_full = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    else:
        img_full = img.copy()
    img_full.save(webp_path, 'WEBP', quality=85, method=6)
    img_full.close()

    # 缩略图 WebP（最大 400px，quality=75）
    thumb_path = base_path + '.thumb.webp'
    if max(w, h) > 400:
        ratio = 400 / max(w, h)
        img_thumb = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    else:
        img_thumb = img.copy()
    img_thumb.save(thumb_path, 'WEBP', quality=75, method=6)
    img_thumb.close()

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

    # 确保目录存在
    os.makedirs(IMAGES_DIR, exist_ok=True)

    # 1. 保存原始文件（PNG 自动转 JPEG，统一格式）
    target_filename = f'{style_name}_{content_hash}.jpg'
    target_path = os.path.join(IMAGES_DIR, target_filename)
    if ext in ('.png',):
        # PNG → JPEG 转换（保持 RGB 模式）
        img_pil = Image.open(image_path).convert('RGB')
        img_pil.save(target_path, 'JPEG', quality=90)
        img_pil.close()
        print(f'  ↪ PNG 已转换为 JPEG')
    else:
        shutil.copy2(image_path, target_path)

    # 2. 从 JPEG 生成 WebP 版本
    base_name = os.path.splitext(target_path)[0]
    img = Image.open(target_path)
    generate_webp_versions(base_name, img)
    img.close()

    # 计算各版本大小
    jpg_size = os.path.getsize(target_path) / 1024
    webp_path = base_name + '.webp'
    thumb_path = base_name + '.thumb.webp'
    webp_size = os.path.getsize(webp_path) / 1024 if os.path.exists(webp_path) else 0
    thumb_size = os.path.getsize(thumb_path) / 1024 if os.path.exists(thumb_path) else 0

    # 输出
    jpg_url = f'{STYLE_SOURCE_URL}/{target_filename}'
    webp_url = f'{STYLE_SOURCE_URL}/{style_name}_{content_hash}.webp'
    thumb_url = f'{STYLE_SOURCE_URL}/{style_name}_{content_hash}.thumb.webp'

    print(f'✅ 图片已保存 ({style_name})')
    print(f'   JPEG: {jpg_url} ({jpg_size:.0f}KB)')
    print(f'   WebP: {webp_url} ({webp_size:.0f}KB, {100 - webp_size/jpg_size*100:.0f}% 缩小)')
    print(f'   Thumb: {thumb_url} ({thumb_size:.0f}KB)')
    print(f'')
    print(f'下一步:')
    print(f'  1. 将 JPEG URL 填入风格文件的 ## 参考配图')
    print(f'  2. git add images/styles_previews/{style_name}_{content_hash}*')
    print(f'  3. git commit -m "feat: add preview for {style_name}"')

if __name__ == '__main__':
    main()
