#!/usr/bin/env python3
"""本地构建 gallery.html：读取 data/styles.json，生成 gallery.html（内联 CSS/JS + FALLBACK_DATA + 完整 UI 结构）。"""
import json
import os
import shutil
import argparse
import sys

FALLBACK_LIMIT = 50
FALLBACK_IMG = '<div style=padding:40px;text-align:center;color:#999>图片加载失败</div>'

DIST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dist')
DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'styles.json')
GALLERY_HTML = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gallery.html')
GALLERY_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gallery', 'src')


def clean_dist():
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR, exist_ok=True)


def build_fallback_data(all_styles: list) -> dict:
    sorted_styles = sorted(all_styles, key=lambda x: x.get('id', ''), reverse=True)[:FALLBACK_LIMIT]
    return {
        "meta": {"version": "v0.0.0", "total": len(all_styles), "fallback_count": len(sorted_styles)},
        "styles": [{
            "id": s.get("id"),
            "name": s.get("name"),
            "category": s.get("category"),
            "preview_urls": s.get("preview_urls", []),
            "summary": s.get("summary", ""),
            "triggers": s.get("triggers", ""),
            "features": s.get("features", []),
            "tags": s.get("tags", []),
            "source_url": s.get("source_url", ""),
            "source_author": s.get("source_author", ""),
        } for s in sorted_styles]
    }


def read_source(filename):
    path = os.path.join(GALLERY_SRC_DIR, filename)
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return f'/* {filename} not found */'


def js_str(s):
    """转义 JS 字符串字面量中的特殊字符"""
    if not s:
        return ''
    return s.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '')


def build_gallery_html(data: dict, output_path: str):
    meta = data.get('meta', {})
    styles = data.get('styles', [])
    fallback = build_fallback_data(styles)

    inline_css = read_source('gallery.css')
    inline_js_raw = read_source('gallery.js')
    inline_js = inline_js_raw.replace("})();", "  window.init = init;\n})();")

    # 预生成风格数据的 JS 数组（用于 renderGallery）
    styles_js = []
    for s in styles:
        preview_urls = s.get('preview_urls', [])
        img_url = preview_urls[0] if preview_urls else ''
        tags = s.get('tags', [])
        features = s.get('features', [])
        styles_js.append('{')
        styles_js.append(f"  id: '{js_str(s.get('id', ''))}',")
        styles_js.append(f"  name: '{js_str(s.get('name', ''))}',")
        styles_js.append(f"  category: '{js_str(s.get('category', ''))}',")
        styles_js.append(f"  imgUrl: '{js_str(img_url)}',")
        styles_js.append(f"  summary: '{js_str(s.get('summary', ''))}',")
        styles_js.append(f"  triggers: '{js_str(s.get('triggers', ''))}',")
        styles_js.append(f"  features: {json.dumps(features, ensure_ascii=False)},")
        styles_js.append(f"  tags: {json.dumps(tags, ensure_ascii=False)},")
        styles_js.append(f"  sourceUrl: '{js_str(s.get('source_url', ''))}',")
        styles_js.append(f"  sourceAuthor: '{js_str(s.get('source_author', ''))}'")
        styles_js.append('},')

    styles_json_array = '\n    '.join(styles_js)

    version = meta.get('version', '0')
    total = len(styles)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 风格画廊 v{version}</title>
<style>
/* ★ 样式内联 — 来自 gallery/src/gallery.css */
{inline_css}
</style>
</head>
<body>
  <div id="loading">🔄 加载风格画廊...</div>

  <div class="container" id="app" style="display:none">
    <!-- Header -->
    <header class="header">
      <div class="header-left">
        <h1 class="header-title">AI 风格库<span class="header-update">· 最后更新：{version}</span></h1>
        <span class="header-author">by malongan</span>
      </div>
      <div class="header-right">
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" placeholder="搜索风格...">
        </div>
        <button class="theme-toggle" id="themeToggle" title="切换主题">🌙</button>
      </div>
    </header>

    <!-- 主布局：左侧标签 + 右侧内容 -->
    <div class="main-layout">
      <!-- 左侧标签栏 -->
      <aside class="sidebar">
        <div class="sidebar-section">
          <h3 class="sidebar-title">🏷️ 标签筛选</h3>
          <div class="tag-list">
            <!-- 标签由 JS 动态生成 -->
          </div>
        </div>
      </aside>

      <!-- 右侧内容区 -->
      <div class="content-area">
        <!-- 筛选栏 -->
        <div class="filter-bar">
          <button class="filter-btn" id="filterFavorites">
            ❤️ 只看收藏
          </button>
          <span class="result-count" style="margin-left: auto; color: var(--text-muted); font-size: 13px;">
            共 <span class="count-num">{total}</span> 个风格
          </span>
        </div>

        <!-- 风格卡片网格（由 renderGallery 填充） -->
        <div id="gallery" class="gallery-grid">
          <!-- renderGallery 将在此生成 .style-card -->
        </div>
      </div>
    </div>

    <!-- Lightbox 详情弹窗 -->
    <div class="lightbox" id="lightbox">
      <div class="lightbox-card">
        <div class="lightbox-image-wrap">
          <img src="" alt="" class="lightbox-image">
          <button class="lightbox-close" id="lightboxClose">✕</button>
        </div>
        <div class="lightbox-body">
          <div class="lightbox-title-row">
            <h2 class="lightbox-title"></h2>
            <span class="lightbox-index"></span>
          </div>
          <div class="lightbox-content">
            <div class="lightbox-section lightbox-summary-section">
              <h4 class="lightbox-section-title">💡 一句话理解</h4>
              <p class="lightbox-summary"></p>
            </div>
            <div class="lightbox-section lightbox-triggers-section">
              <h4 class="lightbox-section-title">🎯 触发词</h4>
              <p class="lightbox-triggers"></p>
            </div>
            <div class="lightbox-section lightbox-features-section">
              <h4 class="lightbox-section-title">✨ 核心特点</h4>
              <ul class="lightbox-features"></ul>
            </div>
            <div class="lightbox-section lightbox-tags-section">
              <h4 class="lightbox-section-title">🏷️ 标签</h4>
              <div class="lightbox-tags"></div>
            </div>
            <div class="lightbox-section lightbox-link-section">
              <a href="#" target="_blank" class="lightbox-link"></a>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div class="footer" style="text-align:center; padding:40px 20px; color:var(--text-muted); font-size:13px;">
    <p>by malongan · <a href="https://github.com/malongan/style-source" target="_blank" style="color:var(--accent-color)">GitHub</a></p>
  </div>

<script>
/* ★ FALLBACK DATA — 部署时内嵌 */
window.__FALLBACK_DATA__ = {json.dumps(fallback, ensure_ascii=False, indent=2)};
window.__FALLBACK_IMG__ = '{js_str(FALLBACK_IMG)}';

/* ★ JS 交互 — 来自 gallery/src/gallery.js */
{inline_js}

/* ========== 渲染功能 ========== */

/** 构建单张 style-card 的 HTML */
function buildCardHTML(s) {{
  var imgUrl = s.imgUrl || (s.preview_urls || [])[0] || '';
  var tags = (s.tags || []).join(',');
  var summary = s.summary || '';
  var triggers = s.triggers || '';
  var features = (s.features || []).join('|');
  var sourceUrl = s.sourceUrl || '';
  var sourceAuthor = s.sourceAuthor || '';

  return '<div class="style-card" data-id="' + s.id + '"' +
    ' data-summary="' + summary.replace(/"/g,'&quot;') + '"' +
    ' data-features="' + features.replace(/"/g,'&quot;') + '"' +
    ' data-triggers="' + triggers.replace(/"/g,'&quot;') + '"' +
    ' data-tags="' + tags + '"' +
    ' data-number="' + (s.number || s.id || '') + '"' +
    ' data-category="' + s.category + '">' +
    '<img src="' + imgUrl + '" alt="' + s.name + '" class="card-image" loading="lazy"' +
    ' onerror="this.parentElement.innerHTML=window.__FALLBACK_IMG__">' +
    '<div class="card-content">' +
      '<div class="card-title-row">' +
        '<span class="card-number">#' + (s.number || s.id || '') + '</span>' +
        '<h3 class="card-title">' + s.name + '</h3>' +
      '</div>' +
      '<div class="card-footer">' +
        '<span class="card-category">' + (s.category || '') + '</span>' +
        '<button class="favorite-btn" title="收藏">收藏</button>' +
      '</div>' +
    '</div>' +
  '</div>';
}}

/** 从 JSON 数据渲染瀑布流卡片 */
function renderGallery(data) {{
  var styles = data.styles || [];
  var loading = document.getElementById('loading');
  var app = document.getElementById('app');

  if (loading) loading.style.display = 'none';
  if (app) app.style.display = 'block';

  var grid = document.querySelector('.gallery-grid');
  if (!grid) return;

  grid.innerHTML = styles.map(function(s) {{ return buildCardHTML(s); }}).join('');

  // 更新结果计数
  var countEl = document.querySelector('.count-num');
  if (countEl) countEl.textContent = styles.length;

  // 渲染完成后调用 gallery.js 的 init() 绑定事件
  if (typeof window.init === 'function') window.init();
}}

/** 从 JSON 或回退数据渲染 */
async function loadGallery() {{
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
    size_kb = len(html.encode('utf-8')) / 1024
    print(f'✅ 已生成 {output_path} ({size_kb:.1f}KB, 备选 {FALLBACK_LIMIT} 个风格)')


def main():
    parser = argparse.ArgumentParser(description='构建 gallery.html')
    parser.add_argument('--output', default=GALLERY_HTML, help='输出路径')
    args = parser.parse_args()

    clean_dist()

    if not os.path.isfile(DATA_FILE):
        print(f'❌ data/styles.json 不存在，请先运行 generate_data.py')
        sys.exit(1)

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    build_gallery_html(data, args.output)


if __name__ == '__main__':
    main()
