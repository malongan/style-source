#!/usr/bin/env python3
"""本地构建 gallery.html：读取 data/styles.json，生成 gallery.html（内联 CSS/JS + FALLBACK_DATA + 完整 UI 结构）。"""
import json
import os
import shutil
import argparse
import sys

FALLBACK_LIMIT = 50
FALLBACK_IMG = '<div class="img-fallback" style="width:100%;aspect-ratio:3/4;background:var(--bg-secondary);display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:12px;">图片加载失败</div>'

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
            "code": s.get("code", ""),
            "name": s.get("name"),
            "category": s.get("category"),
            "preview_urls": s.get("preview_urls", []),
            "preview_webp": s.get("preview_webp", ""),
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

    # 处理 gallery.js IIFE：阻止 auto-init，暴露 init 到全局
    # 替换最后几行的自动启动逻辑
    auto_init_block = (
        "  if (document.readyState === 'loading') {\n"
        "    document.addEventListener('DOMContentLoaded', init);\n"
        "  } else {\n"
        "    init();\n"
        "  }"
    )
    if auto_init_block in inline_js_raw:
        inline_js = inline_js_raw.replace(
            auto_init_block,
            "  // auto-init disabled, init() called by renderGallery\n  window.init = init;"
        )
    else:
        # fallback: 替换尾声
        inline_js = inline_js_raw.replace(
            "})();",
            "  window.init = init;\n})();"
        )

    # 风格数据不再内联到 HTML，由 gallery-runtime.js 从 CDN 加载
    version = meta.get('version', '0.0.0').lstrip('v')
    total = len(styles)

    from datetime import date
    today_str = date.today().strftime('%Y-%m-%d')
    cache_hash = today_str.replace('-', '')  # 20260626 用于缓存版本
    description = f'AI 风格画廊 — 收集 {total} 个 AI 绘画风格提示词，涵盖品牌KV、社交媒体、IP角色、时尚、创意等多种分类。支持预览、搜索、标签筛选、收藏。'
    base_url = 'https://malongan.github.io/style-source'
    img_preview = f'{base_url}/images/styles_previews/'

    # 写出独立 CSS 文件（用于缓存）
    css_path = os.path.join(os.path.dirname(output_path), 'gallery.css')
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(f'/* gallery.css v{cache_hash} — 由 build_gallery.py 生成 */\n')
        f.write(inline_css)
    print(f'  📝 写出独立 CSS: {css_path}')

    # 写出独立 JS 文件（用于缓存）— 仅 gallery.js IIFE
    js_path = os.path.join(os.path.dirname(output_path), 'gallery-runtime.js')
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(f'/* gallery-runtime.js v{cache_hash} — 由 build_gallery.py 生成 */\n')
        f.write(inline_js)
    print(f'  📝 写出独立 JS:  {js_path}')

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 风格画廊 ({total} 个风格)</title>
<meta name="description" content="{description}">
<meta name="keywords" content="AI绘画,风格提示词,Stable Diffusion,Midjourney,AI画廊,提示词库">
<meta name="author" content="malongan">
<meta property="og:title" content="AI 风格画廊 ({total} 个风格)">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{base_url}/gallery.html">
<meta property="og:type" content="website">
<meta property="og:image" content="{base_url}/images/styles_previews/avantgarde_bw_poster_44361c82.webp">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="AI 风格画廊 v{version}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{base_url}/images/styles_previews/avantgarde_bw_poster_44361c82.webp">
<link rel="canonical" href="{base_url}/gallery.html">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎨</text></svg>">
<link rel="preconnect" href="https://malongan.github.io" crossorigin>
<link rel="preload" href="gallery.css?v={cache_hash}" as="style">
<link rel="preload" href="gallery-runtime.js?v={cache_hash}" as="script">
<link rel="stylesheet" href="gallery.css?v={cache_hash}">
<style>
/* ★ 首屏关键样式（防 FOUC，完整样式从 gallery.css 加载） */
:root {{ --bg-primary:#f0f2f5;--bg-card:#fff;--text-primary:#1f2937;--text-muted:#9ca3af;--accent-color:#3b82f6; }}
[data-theme="dark"] {{ --bg-primary:#111827;--bg-card:#1f2937;--text-primary:#f9fafb;--accent-color:#60a5fa; }}
* {{ margin:0;padding:0;box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg-primary);color:var(--text-primary); }}
#app {{ display:none; }}
.loading-skeleton {{ padding:20px 0;text-align:center;color:var(--text-muted); }}
</style>
<noscript><link rel="stylesheet" href="gallery.css?v={cache_hash}"></noscript>
</head>
<body>
  <div id="loading" class="loading-skeleton">
    <div class="skeleton-grid">
      <div class="skeleton-card"><div class="skeleton-image"></div><div class="skeleton-bar" style="width:40%"></div><div class="skeleton-bar" style="width:70%"></div></div>
      <div class="skeleton-card"><div class="skeleton-image"></div><div class="skeleton-bar" style="width:35%"></div><div class="skeleton-bar" style="width:65%"></div></div>
      <div class="skeleton-card"><div class="skeleton-image"></div><div class="skeleton-bar" style="width:45%"></div><div class="skeleton-bar" style="width:60%"></div></div>
    </div>
    <div class="skeleton-loading-text">🔄 加载风格画廊...</div>
  </div>

  <div class="container" id="app" style="display:none">
    <!-- Header -->
    <header class="header">
      <div class="header-left">
        <h1 class="header-title">🎨 AI 风格库 <span class="header-update" id="headerVersion">v{today_str}</span> <span class="header-author">by malongan</span></h1>
      </div>
      <div class="header-right">
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" placeholder="搜索风格、标签、作者..." autofocus>
          <span class="search-clear" id="searchClear" style="display:none;">✕</span>
        </div>
        <button class="theme-toggle" id="themeToggle" title="切换主题">🌙</button>
      </div>
    </header>

    <!-- 分类固定栏（sticky）：左分类 + 右计数 -->
    <div class="category-bar" id="categoryBar">
      <div class="category-filter" id="categoryFilter">
        <!-- 由 renderCategoryFilters() 动态填充 -->
      </div>
      <span class="result-count">
        显示 <span class="count-num" id="countVisible">{total}</span> / <span class="count-total" id="countTotal">{total}</span> 个风格
      </span>
    </div>

    <!-- 主布局：左侧标签 + 右侧内容 -->
    <div class="main-layout">
      <!-- 左侧侧边栏：排序+收藏 + 标签 -->
      <aside class="sidebar">
        <div class="sidebar-section">
          <div class="sidebar-actions">
            <select id="sortSelect" class="sort-select">
              <option value="default">默认排序</option>
              <option value="newest">🆕 最新添加</option>
              <option value="name-asc">📄 名称 A-Z</option>
              <option value="name-desc">📄 名称 Z-A</option>
              <option value="favorites">❤️ 已收藏优先</option>
            </select>
            <div class="sidebar-action-row">
              <button class="filter-btn" id="filterFavorites">❤️ 只看收藏</button>
              <button class="filter-btn clear-filter-btn" id="clearFilters" style="display:none;">✕ 清除</button>
            </div>
          </div>
          <div class="sidebar-divider"></div>
          <h3 class="sidebar-title">🏷️ 标签筛选</h3>
          <div class="tag-list">
            <!-- 标签由 JS 动态生成 -->
          </div>
        </div>
      </aside>

      <!-- 右侧内容区：风格卡片网格 -->
      <div class="content-area">
        <div id="gallery" class="gallery-grid">
          <!-- renderGallery 将在此生成 .style-card -->
        </div>
      </div>
    </div>

    <!-- Lightbox 详情弹窗 -->
    <div class="lightbox" id="lightbox">
      <button class="lightbox-nav lightbox-nav-prev" id="lightboxPrev" title="上一个 (←)">◀</button>
      <button class="lightbox-nav lightbox-nav-next" id="lightboxNext" title="下一个 (→)">▶</button>
      <div class="lightbox-card">
        <div class="lightbox-image-wrap">
          <img src="" alt="" class="lightbox-image">
          <button class="lightbox-close" id="lightboxClose">✕</button>
        </div>
        <div class="lightbox-body">
          <div class="lightbox-title-row">
            <h2 class="lightbox-title"></h2>
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="lightbox-index"></span>
              <button class="favorite-btn lightbox-fav-btn" title="收藏">收藏</button>
            </div>
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

  <!-- 回到顶部按钮 -->
  <button class="back-to-top" id="backToTop" title="回到顶部">↑</button>

<script>
/* ★ FALLBACK DATA — 部署时内嵌（紧凑格式节省体积） */
window.__FALLBACK_DATA__ = {json.dumps(fallback, ensure_ascii=False, separators=(',', ':'))};
window.__FALLBACK_IMG__ = '{js_str(FALLBACK_IMG)}';
</script>
<script src="gallery-runtime.js?v={cache_hash}"></script>
<script>
/* ========== 渲染功能 ========== */

/** 构建单张 style-card 的 HTML（WebP 优先） */
function buildCardHTML(s, idx, total) {{
  idx = idx || 0;
  total = total || 0;
  var isNew = total > 10 && idx >= total - 10;
  var imgUrl = s.preview_webp || (s.preview_urls || [])[0] || '';
  var tags = (s.tags || []).join(',');
  var summary = s.summary || '';
  var triggers = Array.isArray(s.triggers) ? s.triggers.join(', ') : (s.triggers || '');
  var features = (s.features || []).join('|');
  var sourceUrl = s.sourceUrl || s.source_url || '';
  var sourceAuthor = s.sourceAuthor || s.source_author || '';

  var linkHtml = '';
  if (sourceUrl) {{
    linkHtml = '<a href="' + sourceUrl.replace(/"/g,'&quot;') + '" target="_blank" class="card-link">' +
      (sourceAuthor ? '🔗 @' + sourceAuthor.replace(/"/g,'&quot;') : '🔗 来源') + '</a>';
  }}

  // 🆕 新风格标记（最后10个）
  var badgeHtml = isNew ? '<span class="card-badge-new">🆕 NEW</span>' : '';

  // 直接用 WebP（不再使用 <picture> 包装，节省体积）
  var imgHtml = '<img src="' + imgUrl + '" alt="' + s.name + '" class="card-image" loading="lazy"'
    + ' onerror="this.outerHTML=window.__FALLBACK_IMG__">';

  return '<div class="style-card" data-id="' + s.id + '"' +
    ' data-code="' + (s.code || '') + '"' +
    ' data-summary="' + summary.replace(/"/g,'&quot;') + '"' +
    ' data-features="' + features.replace(/"/g,'&quot;') + '"' +
    ' data-triggers="' + triggers.replace(/"/g,'&quot;') + '"' +
    ' data-tags="' + tags + '"' +
    ' data-number="' + (s.code || s.number || s.id || '') + '"' +
    ' data-category="' + s.category + '"' +
    ' data-original-index="' + idx + '">' +
    '<div class="card-image-wrap">' +
    imgHtml +
    badgeHtml +
    '</div>' +
    '<div class="card-content">' +
      '<div class="card-title-row">' +
        '<span class="card-number">' + (s.code ? '#' + s.code : '#' + (s.number || s.id || '')) + '</span>' +
        '<span class="card-category">' + (s.category || '') + '</span>' +
      '</div>' +
      '<h3 class="card-title">' + s.name + '</h3>' +
      '<div class="card-footer">' +
        linkHtml +
        '<button class="favorite-btn" data-id="' + s.id + '" title="收藏">收藏</button>' +
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

  var totalStyles = styles.length;
  grid.innerHTML = styles.map(function(s, i) {{ return buildCardHTML(s, i, totalStyles); }}).join('');

  // 更新结果计数（可见数 = 总数，初始无筛选）
  var countEl = document.getElementById('countVisible');
  var totalEl = document.getElementById('countTotal');
  if (countEl) countEl.textContent = styles.length;
  if (totalEl) totalEl.textContent = styles.length;

  // 修正 gallery.js extractCategories() 的 all 计数 bug
  window.__totalStyles = styles.length;

  // 渲染完成后调用 gallery.js 的 init() 绑定事件
  if (typeof window.init === 'function') window.init();

  // 修复 all 计数（gallery.js 的 extractCategories 不递增 all）
  if (window.galleryCategories) {{
    window.galleryCategories.all = window.__totalStyles || styles.length;
    // 重新渲染分类按钮以显示正确计数
    var catBtns = document.querySelectorAll('.category-btn');
    catBtns.forEach(function(b) {{
      if (b.dataset.category === 'all') {{
        var countSpan = b.querySelector('.tag-count');
        if (countSpan) countSpan.textContent = window.galleryCategories.all;
      }}
    }});

    // 绑定编号点击复制
    document.querySelectorAll('.card-number').forEach(function(el) {{
      el.addEventListener('click', function(e) {{
        e.stopPropagation();
        var code = this.textContent.replace('#', '').trim();
        if (!code) return;
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          navigator.clipboard.writeText(code).then(function() {{
            el.classList.add('copied');
            setTimeout(function() {{ el.classList.remove('copied'); }}, 1500);
          }}).catch(function() {{ fallbackCopy(code, el); }});
        }} else {{
          fallbackCopy(code, el);
        }}
      }});
    }});
  }}

  function fallbackCopy(text, el) {{
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    el.classList.add('copied');
    setTimeout(function() {{ el.classList.remove('copied'); }}, 1500);
  }}
}}

/** 从 JSON 或回退数据渲染 */
async function loadGallery() {{
  try {{
    const resp = await fetch('https://malongan.github.io/style-source/data/styles.json?t=' + Date.now());
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
