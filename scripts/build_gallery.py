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

GALLERY_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gallery', 'src')
GALLERY_OUTPUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gallery.html')

def read_source(filename):
    """从 gallery/src/ 读取源文件"""
    path = os.path.join(GALLERY_SRC_DIR, filename)
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return f'/* {filename} not found */'

def build_gallery_html(data: dict, output_path: str):
    """生成 gallery.html（内联真实 CSS/JS + 数据）"""
    meta = data.get('meta', {})
    styles = data.get('styles', [])
    fallback = build_fallback_data(styles)

    # 读取真实的 CSS/JS 源文件
    inline_css = read_source('gallery.css')
    inline_js_raw = read_source('gallery.js')

    # 暴露 gallery.js IIFE 内的 init 到全局
    inline_js = inline_js_raw.replace(
        "})();",
        "  window.init = init;\n})();"
    )

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>风格画廊 v{meta.get('version', '0')}</title>
<style>
/* ★ 样式内联 — 来自 gallery/src/gallery.css */
{inline_css}
</style>
</head>
<body>
<div id="loading">🔄 加载风格画廊...</div>
<div id="gallery"></div>
<button id="refresh-btn" onclick="loadGallery()">🔄 刷新</button>

<script>
/* ★ FALLBACK DATA — 部署时内嵌 */
window.__FALLBACK_DATA__ = {json.dumps(fallback, ensure_ascii=False, indent=2)};

/* ★ JS 交互 — 来自 gallery/src/gallery.js */
// gallery.js 使用 IIFE，函数在闭包内不可全局访问
// 已通过 window.init = init 暴露给 renderGallery 调用
{inline_js}

/* ★ renderGallery — 从 JSON 数据渲染瀑布流卡片 */
function renderGallery(data) {{
  const styles = data.styles || [];
  const container = document.getElementById('gallery');
  const loading = document.getElementById('loading');
  if (loading) loading.style.display = 'none';
  if (!container) return;

  var fallbackImg = '<div style=padding:40px;text-align:center;color:#999>图片加载失败</div>';

  // 创建与 gallery.js 匹配的 HTML 结构：.gallery-grid > .style-card
  container.innerHTML = '<div class="gallery-grid">' +
    styles.map(function(s) {{
      var imgUrl = (s.preview_urls || [])[0] || '';
      var tags = (s.tags || []).map(function(t) {{ return '<span class="tag" data-tag="' + t + '">#' + t + '</span>'; }}).join('');
      return '<div class="style-card" data-id="' + s.id + '" data-tags="' + (s.tags || []).join(',') + '" data-category="' + s.category + '">' +
        '<div class="card-img-wrap">' +
          '<img src="' + imgUrl + '" alt="' + s.name + '" loading="lazy" onerror="this.parentElement.innerHTML=window.__FALLBACK_IMG__">' +
          '<div class="card-number">#' + s.id + '</div>' +
        '</div>' +
        '<div class="card-body">' +
          '<h3 class="card-title">' + s.name + '</h3>' +
          '<div class="card-tags">' + tags + '</div>' +
          '<p class="card-summary">' + (s.summary || '') + '</p>' +
        '</div>' +
      '</div>';
    }}).join('') +
  '</div>';

  // 渲染完成后，调用 gallery.js 的 init() 绑定事件
  if (typeof window.init === 'function') window.init();
}}

/* ★ 数据加载逻辑 */
async function loadGallery() {{
  window.__FALLBACK_IMG__ = '<div style=padding:40px;text-align:center;color:#999>图片加载失败</div>';
  try {{
    const resp = await fetch('https://cdn.jsdelivr.net/gh/malongan/style-source@main/data/styles.json?t=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    renderGallery(data);
  }} catch(e) {{
    console.warn('JSON 加载失败，使用备用数据', e);
    if (window.__FALLBACK_DATA__) renderGallery(window.__FALLBACK_DATA__);
  }}
}}

loadGallery();
</script>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    size_kb = os.path.getsize(output_path) / 1024
    print(f'✅ 已生成 {output_path} ({size_kb:.1f}KB)')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    size_kb = os.path.getsize(output_path) / 1024
    print(f'✅ 已生成 {output_path} ({size_kb:.1f}KB, 备选 {FALLBACK_LIMIT} 个风格)')

def main():
    parser = argparse.ArgumentParser(description='构建 gallery.html')
    parser.add_argument('--output', default=GALLERY_OUTPUT, help='输出路径（默认仓库根目录 gallery.html）')
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
