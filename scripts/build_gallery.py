#!/usr/bin/env python3
"""本地构建 gallery.html：读取 data/styles.json，生成 dist/gallery.html（内联 CSS/JS + FALLBACK_DATA）。"""
import json
import os
import shutil
import argparse
import sys

FALLBACK_LIMIT = 50
DIST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dist')
DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'styles.json')
GALLERY_HTML = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dist', 'gallery.html')

def clean_dist():
    """强制清空 dist/ 目录"""
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR, exist_ok=True)

def build_fallback_data(all_styles: list) -> dict:
    """截取最近 FALLBACK_LIMIT 个风格，保留核心字段"""
    sorted_styles = sorted(
        all_styles,
        key=lambda x: x.get('id', ''),
        reverse=True
    )[:FALLBACK_LIMIT]

    fallback_styles = []
    for s in sorted_styles:
        fallback_styles.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "category": s.get("category"),
            "preview_urls": s.get("preview_urls", []),
            "summary": s.get("summary", ""),
        })

    return {
        "meta": {
            "version": getattr(sys.modules.get('generate_data'), 'get_version', lambda: 'v0.0.0')(),
            "total": len(all_styles),
            "fallback_count": len(fallback_styles),
        },
        "styles": fallback_styles
    }

def build_gallery_html(data: dict, output_path: str):
    """生成 gallery.html（内联 CSS/JS + 数据）"""
    meta = data.get('meta', {})
    styles = data.get('styles', [])
    fallback = build_fallback_data(styles)

    # 此处为 gallery.html 模板，CSS/JS 内联
    # 实际 CSS/JS 内容应来自 painter 工作区的 gallery.css 和 gallery.js
    # 这里给出核心结构
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>风格画廊 v{meta.get('version', '0')}</title>
<style>
/* ★ 样式内联 — 由 build_gallery.py 打包时写入 */
/* 实际内容从 painter/styles/gallery.css 读取 */
:root {{ --primary: #333; --bg: #f5f5f5; }}
body {{ font-family: -apple-system, sans-serif; margin: 0; background: var(--bg); color: var(--primary); }}
#gallery {{ column-count: 5; column-gap: 16px; padding: 20px; max-width: 1600px; margin: 0 auto; }}
.card {{ break-inside: avoid; margin-bottom: 16px; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.card img {{ width: 100%; display: block; }}
.card-body {{ padding: 12px; }}
.card-tags {{ display: flex; gap: 6px; flex-wrap: wrap; }}
.card-tags span {{ font-size: 12px; padding: 2px 8px; background: #f0f0f0; border-radius: 4px; }}
#loading {{ text-align: center; padding: 60px; color: #999; }}
#refresh-btn {{ position: fixed; bottom: 24px; right: 24px; padding: 12px 20px; border: none; border-radius: 24px; background: var(--primary); color: #fff; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
@media (max-width: 1200px) {{ #gallery {{ column-count: 4; }} }}
@media (max-width: 900px) {{ #gallery {{ column-count: 3; }} }}
@media (max-width: 600px) {{ #gallery {{ column-count: 2; }} }}
</style>
</head>
<body>
<div id="loading">🔄 加载风格画廊...</div>
<div id="gallery"></div>
<button id="refresh-btn" onclick="loadGallery()">🔄 刷新</button>

<script>
/* ★ FALLBACK DATA — 部署时内嵌，JSON 加载失败时使用 */
window.__FALLBACK_DATA__ = {json.dumps(fallback, ensure_ascii=False, indent=2)};

/* ★ JS 交互 — 内联 */
async function loadGallery() {{
  try {{
    const resp = await fetch('https://cdn.jsdelivr.net/gh/malongan/style-source@main/data/styles.json?t=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    renderGallery(data);
  }} catch(e) {{
    console.warn('JSON 加载失败，使用备用数据', e);
    renderGallery(window.__FALLBACK_DATA__);
  }}
}}

function renderGallery(data) {{
  document.getElementById('loading').style.display = 'none';
  const gallery = document.getElementById('gallery');
  const styles = data.styles || [];
  gallery.innerHTML = styles.map(s => `
    <div class="card" data-id="${{s.id}}">
      <img src="${{(s.preview_urls || [])[0] || ''}}" alt="${{s.name}}" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22300%22><rect fill=%22%23eee%22 width=%22300%22 height=%22300%22/></svg>'">
      <div class="card-body">
        <strong>${{s.name}}</strong>
        <div class="card-tags">${{ (s.tags || []).map(t => '<span>#' + t + '</span>').join('') }}</div>
        <small>${{s.summary || ''}}</small>
      </div>
    </div>
  `).join('');
}}

loadGallery();
</script>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    size_kb = os.path.getsize(output_path) / 1024
    print(f'✅ 已生成 {output_path} ({size_kb:.1f}KB, 备选 {FALLBACK_LIMIT} 个风格)')

def main():
    parser = argparse.ArgumentParser(description='构建 gallery.html')
    parser.add_argument('--output', default=GALLERY_HTML, help='输出路径（默认 dist/gallery.html）')
    args = parser.parse_args()

    # 强制清理 dist/
    clean_dist()

    # 读取数据
    if not os.path.isfile(DATA_FILE):
        print(f'❌ data/styles.json 不存在，请先运行 generate_data.py')
        sys.exit(1)

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 确保输出目录存在
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    build_gallery_html(data, args.output)

if __name__ == '__main__':
    main()
