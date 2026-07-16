#!/usr/bin/env python3
"""本地构建 gallery.html：读取 data/styles.json，异步加载数据 + 骨架屏 + UI。"""
import json
import os
import shutil
import argparse
import sys
import re

FALLBACK_IMG = '<div class="img-fallback" style="width:100%;aspect-ratio:3/4;background:var(--bg-secondary);display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:12px;">图片加载失败</div>'

DIST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dist')
DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'styles.json')
GALLERY_HTML = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gallery.html')
GALLERY_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gallery', 'src')


def clean_dist():
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR, exist_ok=True)


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


def minify_css(css: str) -> str:
    """基础 CSS 压缩：去注释、去多余空白"""
    # 去除注释
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    # 去除多余空白
    css = re.sub(r'\s+', ' ', css)
    # 去除 { 前的空格
    css = re.sub(r'\s*{\s*', '{', css)
    # 去除 } 前的空格/分号
    css = re.sub(r'\s*}\s*', '}', css)
    # 去除 : 周围空格
    css = re.sub(r'\s*:\s*', ':', css)
    # 去除 , 周围空格
    css = re.sub(r'\s*,\s*', ',', css)
    # 去除 ; 周围空格
    css = re.sub(r'\s*;\s*', ';', css)
    # 去除开头/结尾空白
    css = css.strip()
    return css


def minify_js(js: str) -> str:
    """基础 JS 压缩：去注释、去多余空白（保持功能正确）"""
    # 去除多行注释 /* ... */
    js = re.sub(r'/\*.*?\*/', '', js, flags=re.DOTALL)
    # 去除单行注释 // ...（排除 URL 中的 //）
    lines = js.split('\n')
    result = []
    for line in lines:
        # 简单处理：去行内 // 注释（忽略字符串中的）
        in_string = False
        string_char = None
        i = 0
        while i < len(line):
            c = line[i]
            if in_string:
                if c == '\\':
                    i += 2
                    continue
                if c == string_char:
                    in_string = False
            else:
                if c in ("'", '"', '`'):
                    in_string = True
                    string_char = c
                elif c == '/' and i + 1 < len(line) and line[i + 1] == '/':
                    line = line[:i]
                    break
            i += 1
        result.append(line)
    js = '\n'.join(result)
    # 压缩空白
    js = re.sub(r'\s+', ' ', js)
    # 特定符号周围去空格（保留字符串内空格）
    js = re.sub(r'\s*([{}();,=+\-*/%&|!<>?:])\s*', r'\1', js)
    js = js.strip()
    return js


def build_gallery_html(data: dict, output_path: str):
    meta = data.get('meta', {})
    styles = data.get('styles', [])

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
            "  // auto-init when cards are already rendered (async loading)\n"
            "  if (document.querySelector('.style-card')) {\n"
            "    init();\n"
            "  } else {\n"
            "    window.init = init;\n"
            "  }"
        )
    else:
        # fallback: 替换尾声
        inline_js = inline_js_raw.replace(
            "})();",
            "  if (document.querySelector('.style-card')) {\n"
            "    init();\n"
            "  } else {\n"
            "    window.init = init;\n"
            "  }\n"
            "})();"
        )

    # 风格数据不再内联到 HTML，由 gallery-runtime.js 从 CDN 加载
    version = meta.get('version', '0.0.0').lstrip('v')
    total = len(styles)

    from datetime import datetime
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d %H:%M')
    cache_hash = now.strftime('%Y%m%d%H%M')  # 用于缓存版本（精确到分钟）
    description = f'AI 风格画廊 — 收集 {total} 个 AI 绘画风格提示词，涵盖品牌KV、社交媒体、IP角色、时尚、创意等多种分类。支持预览、搜索、标签筛选、收藏。'
    base_url = 'https://malongan.github.io/style-source'
    img_preview = f'{base_url}/images/styles_previews/'

    # 写出独立 CSS 文件（用于缓存，已压缩）
    css_path = os.path.join(os.path.dirname(output_path), 'gallery.css')
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(f'/* gallery.css v{cache_hash} — 由 build_gallery.py 生成 */\n')
        f.write(minify_css(inline_css))
    print(f'  📝 写出独立 CSS: {css_path} ({os.path.getsize(css_path)//1024}KB)')

    # 写出独立 JS 文件（用于缓存）— gallery.js IIFE + 渲染函数
    js_path = os.path.join(os.path.dirname(output_path), 'gallery-runtime.js')
    # 构建渲染模板（从 gallery.js IIFE 中提取 renderGallery/buildCardHTML 替换 })
    render_js = f'''
/* ========== 卡片渲染 ========== */
function buildCardHTML(s, idx, total) {{
  idx = idx || 0;
  total = total || 0;
  var isNew = total > 10 && idx >= total - 10;
  var imgUrl = s.preview_webp || (s.preview_urls || [])[0] || '';
  var thumbUrl = s.preview_webp_thumb || '';
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
  var badgeHtml = isNew ? '<span class="card-badge-new">🆕 NEW</span>' : '';
  var imgHtml = '<picture><source srcset="' + imgUrl + '" type="image/webp"><img src="' + imgUrl + '" alt="' + s.name + '" class="card-image" loading="lazy"'
    + ' onload="this.style.opacity=\\'1\\'" onerror="this.outerHTML=window.__FALLBACK_IMG__"></picture>';
  var wrapStyle = thumbUrl ? (' style="background-image:url(' + thumbUrl + ');background-size:cover;background-position:center;"') : '';
  return '<div class="style-card" tabindex="0" role="button" data-id="' + s.id + '"' +
    ' data-code="' + (s.code || '') + '"' +
    ' data-summary="' + summary.replace(/"/g,'&quot;') + '"' +
    ' data-features="' + features.replace(/"/g,'&quot;') + '"' +
    ' data-triggers="' + triggers.replace(/"/g,'&quot;') + '"' +
    ' data-tags="' + tags + '"' +
    ' data-number="' + (s.code || s.number || s.id || '') + '"' +
    ' data-category="' + s.category + '"' +
    ' data-created-at="' + (s.created_at || '') + '"' +
    ' data-original-index="' + idx + '">' +
    '<div class="card-image-wrap"' + wrapStyle + '>' + imgHtml + badgeHtml + '</div>' +
    '<div class="card-content">' +
      '<div class="card-title-row">' +
        '<span class="card-number" title="点击复制编号">' + (s.code ? '#' + s.code : '#' + (s.number || s.id || '')) + '</span>' +
        '<span class="card-category">' + (s.category || '') + '</span>' +
      '</div>' +
      '<h3 class="card-title">' + s.name + '</h3>' +
      '<div class="card-footer">' + linkHtml +
      '</div>' +
    '</div>' +
  '</div>';
}}

function renderGallery(data) {{
  var styles = data.styles || [];
  window.__allStyles = styles;
  window.__filteredStyles = null;
  window.__renderedUpTo = 0;
  window.__cardsRendered = false;  // 强制守卫：初始为空页面

  // 数据已就绪：展示筛选框架，但不预渲染任何卡片
  var app = document.getElementById('app');
  if (app) app.style.display = 'block';

  var grid = document.querySelector('.gallery-grid');
  if (grid) grid.innerHTML = '';  // 清空，不渲染任何卡片

  var countEl = document.getElementById('countVisible');
  var totalEl = document.getElementById('countTotal');
  if (countEl) countEl.textContent = styles.length;
  if (totalEl) totalEl.textContent = styles.length;
  window.__totalStyles = styles.length;

  if (typeof window.init === 'function') window.init();
  if (window.galleryCategories) {{
    window.galleryCategories.all = window.__totalStyles || styles.length;
    var catBtns = document.querySelectorAll('.category-btn');
    catBtns.forEach(function(b) {{
      if (b.dataset.category === 'all') {{
        var countSpan = b.querySelector('.tag-count');
        if (countSpan) countSpan.textContent = window.galleryCategories.all;
      }}
    }});
  }}
}}

async function loadGallery() {{
  var bar = document.getElementById('pixelBarFill');
  var loader = document.getElementById('pixelLoader');

  function animateBar(progress) {{
    if (bar) bar.style.width = progress + '%';
  }}

  // 模拟进度（真实场景 fetch 进度不可见，用动画模拟）
  var steps = [15, 35, 55, 75, 90, 100];
  var step = 0;
  var interval = setInterval(function() {{
    if (step < steps.length) animateBar(steps[step]);
    step++;
    if (step >= steps.length) clearInterval(interval);
  }}, 180);

  try {{
    const resp = await fetch('https://malongan.github.io/style-source/data/styles.json?t=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();

    // 加载完成
    animateBar(100);
    setTimeout(function() {{
      if (loader) {{
        loader.classList.add('fade-out');
        setTimeout(function() {{ loader.style.display = 'none'; }}, 300);
      }}
      // 显示空内容提示和主框架
      var emptyEl = document.getElementById('galleryEmpty');
      if (emptyEl) emptyEl.style.display = 'flex';
      renderGallery(data);
    }}, 250);
  }} catch(e) {{
    clearInterval(interval);
    if (loader) {{ loader.style.display = 'none'; }}
    console.warn('JSON 加载失败', e);
  }}
}}

loadGallery();
'''
    with open(js_path, 'w', encoding='utf-8') as f:
        combined_js = f'/* gallery-runtime.js v{cache_hash} — 由 build_gallery.py 生成 */\n'
        combined_js += inline_js + '\n' + render_js
        f.write(minify_js(combined_js))
    print(f'  📝 写出独立 JS:  {js_path} ({os.path.getsize(js_path)//1024}KB)')

    # 生成骨架屏卡片（10 张，随机宽度模拟内容）
    import random
    random.seed(cache_hash)
    widths = [(random.randint(25, 55), random.randint(55, 85)) for _ in range(10)]
    skeleton_cards = '\n'.join(
        f'      <div class="skeleton-card"><div class="skeleton-image"></div><div class="skeleton-bar" style="width:{w1}%"></div><div class="skeleton-bar" style="width:{w2}%"></div></div>'
        for w1, w2 in widths
    )

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
/* 像素风加载画面 */
.pixel-loader {{ position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#0d0d0d;z-index:9999; }}
.pixel-loader-title {{ font-family:monospace;font-size:18px;color:#00ff41;letter-spacing:4px;margin-bottom:32px;text-transform:uppercase;text-shadow:0 0 8px #00ff41; }}
.pixel-bar-wrap {{ width:240px;height:20px;background:#1a1a1a;border:2px solid #00ff41;position:relative;image-rendering:pixelated; }}
.pixel-bar-fill {{ height:100%;width:0%;background:#00ff41;transition:width 0.1s steps(1);box-shadow:0 0 8px #00ff41 inset; }}
.pixel-bar-wrap::after {{ content:'';position:absolute;top:-2px;left:-2px;right:-2px;bottom:-2px;background:repeating-linear-gradient(90deg,transparent 0px,transparent 8px,#0d0d0d 8px,#0d0d0d 10px);pointer-events:none; }}
.pixel-loader-sub {{ margin-top:20px;font-family:monospace;font-size:12px;color:#666;letter-spacing:2px; }}
.pixel-loader.fade-out {{ animation:fadeOutLoader 0.3s ease forwards; }}
@keyframes fadeOutLoader {{ to{{opacity:0;pointer-events:none;}} }}
@keyframes pixelScan {{ 0%{{background-position:0 0;}} 100%{{background-position:0 20px;}} }}
/* 空内容提示 */
.gallery-empty {{ position:fixed;inset:0;display:flex;align-items:center;justify-content:center;z-index:100;pointer-events:none; }}
.gallery-empty-inner {{ text-align:center; }}
.gallery-empty-icon {{ font-size:64px;color:#333;margin-bottom:16px;font-family:monospace; }}
.gallery-empty-text {{ font-size:18px;color:#555;margin-bottom:8px; }}
.gallery-empty-sub {{ font-size:13px;color:#888; }}
</style>
<noscript><link rel="stylesheet" href="gallery.css?v={cache_hash}"></noscript>
</head>
<body>
  <!-- 像素风加载画面 -->
  <div class="pixel-loader" id="pixelLoader">
    <div class="pixel-loader-title">STYLE GALLERY</div>
    <div class="pixel-bar-wrap">
      <div class="pixel-bar-fill" id="pixelBarFill"></div>
    </div>
    <div class="pixel-loader-sub">LOADING DATA...</div>
  </div>

  <!-- 空内容提示（数据加载后显示） -->
  <div class="gallery-empty" id="galleryEmpty" style="display:none;">
    <div class="gallery-empty-inner">
      <div class="gallery-empty-icon">▦</div>
      <div class="gallery-empty-text">选择一个分类开始浏览</div>
      <div class="gallery-empty-sub">点击上方分类按钮加载风格</div>
    </div>
  </div>

  <div class="container" id="app" style="display:none">
    <!-- Header -->
    <header class="header">
      <div class="header-left">
        <h1 class="header-title">🎨 AI 风格库 <span class="header-update" id="headerVersion">v{today_str}</span> <span class="header-author">by malongan</span></h1>
      </div>
      <div class="header-right">
        <a href="https://malongan.github.io/ip-gallery/" target="_blank" class="header-nav-link" title="IP 预览">🎭 IP</a>
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" placeholder="搜索名称、标签、提示词..." autofocus>
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
              <option value="code-asc">📐 编号顺序</option>
              <option value="date-desc">🆕 最新添加</option>
              <option value="name-asc">📄 名称 A-Z</option>
              <option value="name-desc">📄 名称 Z-A</option>
              <option value="favorites">❤️ 已收藏优先</option>
            </select>
            <div class="sidebar-action-row">
              <button class="filter-btn" id="filterFavorites">❤️ 只看收藏</button>
              <button class="filter-btn clear-filter-btn" id="clearFilters" style="display:none;">✕ 清除</button>
              <button class="filter-btn random-btn" id="randomBtn">🎲 随机</button>
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
        <picture><source srcset="" type="image/webp" class="lightbox-source"><img src="" alt="" class="lightbox-image"></picture>
          <button class="lightbox-close" id="lightboxClose">✕</button>
        </div>
        <div class="lightbox-body">
          <div class="lightbox-title-row">
            <h2 class="lightbox-title"></h2>
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="lightbox-index"></span>
              <button class="favorite-btn lightbox-fav-btn" title="收藏">收藏</button>
              <button class="copy-prompt-btn lightbox-copy-btn" title="复制提示词" data-id="">📋 复制提示词</button>
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
/* ★ 图片加载失败时的兜底 HTML */
window.__FALLBACK_IMG__ = '{js_str(FALLBACK_IMG)}';
</script>
<script defer src="gallery-runtime.js?v={cache_hash}"></script>
</body>
</html>'''

    # 压缩 HTML：去除标签间空白和注释（保留骨架屏 <div> 结构）
    html = re.sub(r'>\s+<', '><', html)
    html = re.sub(r'\s{2,}', ' ', html)
    html = re.sub(r'\n\s*', '', html)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    size_kb = len(html.encode('utf-8')) / 1024
    print(f'✅ 已生成 {output_path} ({size_kb:.1f}KB)')


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
