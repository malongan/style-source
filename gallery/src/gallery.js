/**
 * Gallery 功能脚本 v4
 * 包含：搜索过滤、标签筛选、收藏、Lightbox信息卡片、深色模式、无限滚动、复制提示词
 */

(function() {
  'use strict';

  // ========== 状态管理 ==========
  const state = {
    currentTag: 'all',
    currentCategory: 'all',
    currentSort: 'default',
    searchQuery: '',
    showFavoritesOnly: false,
    favorites: JSON.parse(localStorage.getItem('galleryFavorites') || '[]'),
    theme: localStorage.getItem('galleryTheme') || 'light',
    lightboxCurrentIndex: -1,   // 当前 Lightbox 显示的卡片索引
    lightboxVisibleCards: []     // 当前可见卡片列表（用于导航）
  };

  // 标签最小展示频次阈值（低于此值折叠到「其他」）
  const TAG_MIN_COUNT = 3;

  // 渲染批次大小
  const RENDER_BATCH = 30;

  // ========== DOM 元素 ==========
  let elements = {};

  // ========== 初始化 ==========
  let initialized = false;
  function init() {
    if (initialized) return;
    initialized = true;
    cacheElements();
    loadTheme();
    bindEvents();
    // 从 __allStyles 数据提取标签和分类（DOM 可能只有部分卡片）
    extractTagsFromData();
    extractCategoriesFromData();
    renderSidebarTags();
    renderCategoryFilters();
    // URL 参数路由：加载后读取 URL params 并应用筛选
    readURLParams();
    // 同步下拉选择器的值
    if (elements.sortSelect) elements.sortSelect.value = state.currentSort;
    setupLazyLoading();
    // 无限的滚动监听
    setupInfiniteScroll();
    // Hash 路由：页面加载后检查 URL hash
    setTimeout(handleHashRoute, 100);
  }

  // ========== URL 参数路由 ==========
  /** 从 URL search params 读取筛选状态并应用 */
  function readURLParams() {
    var params = new URLSearchParams(window.location.search);
    var hasFilter = false;

    if (params.has('q')) {
      state.searchQuery = params.get('q');
      if (elements.searchInput) {
        elements.searchInput.value = state.searchQuery;
        elements.searchClear.style.display = state.searchQuery ? 'block' : 'none';
      }
      hasFilter = true;
    }
    if (params.has('category')) {
      state.currentCategory = params.get('category');
      // 高亮对应的分类按钮
      document.querySelectorAll('.category-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.category === state.currentCategory);
      });
      hasFilter = true;
    }
    if (params.has('tag')) {
      state.currentTag = params.get('tag');
      hasFilter = true;
    }
    if (params.has('sort')) {
      state.currentSort = params.get('sort');
      if (elements.sortSelect) elements.sortSelect.value = state.currentSort;
      hasFilter = true;
    }
    if (params.has('fav') && params.get('fav') === '1') {
      state.showFavoritesOnly = true;
      if (elements.filterFavorites) elements.filterFavorites.classList.add('active');
      hasFilter = true;
    }

    if (hasFilter) {
      filterCards();
    }
  }

  /** 将当前筛选状态同步到 URL search params */
  function updateURLParams() {
    var params = new URLSearchParams();
    if (state.searchQuery) params.set('q', state.searchQuery);
    if (state.currentCategory !== 'all') params.set('category', state.currentCategory);
    if (state.currentTag !== 'all') params.set('tag', state.currentTag);
    if (state.currentSort !== 'default') params.set('sort', state.currentSort);
    if (state.showFavoritesOnly) params.set('fav', '1');

    var qs = params.toString();
    var newURL = window.location.pathname + (qs ? '?' + qs : '') + window.location.hash;
    history.replaceState(null, '', newURL);
  }

  function cacheElements() {
    elements = {
      searchInput: document.getElementById('searchInput'),
      searchClear: document.getElementById('searchClear'),
      themeToggle: document.getElementById('themeToggle'),
      filterFavorites: document.getElementById('filterFavorites'),
      clearFilters: document.getElementById('clearFilters'),
      randomBtn: document.getElementById('randomBtn'),
      sortSelect: document.getElementById('sortSelect'),
      galleryGrid: document.querySelector('.gallery-grid'),
      lightbox: document.getElementById('lightbox'),
      lightboxCard: document.querySelector('.lightbox-card'),
      lightboxClose: document.getElementById('lightboxClose'),
      lightboxPrev: document.getElementById('lightboxPrev'),
      lightboxNext: document.getElementById('lightboxNext')
    };
    // styleCards 不缓存 — 随无限滚动渲染动态变化
  }

  // ========== 主题切换 ==========
  function loadTheme() {
    document.documentElement.setAttribute('data-theme', state.theme);
    updateThemeIcon();
  }

  function toggleTheme() {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', state.theme);
    localStorage.setItem('galleryTheme', state.theme);
    updateThemeIcon();
  }

  function updateThemeIcon() {
    if (elements.themeToggle) {
      elements.themeToggle.textContent = state.theme === 'light' ? '🌙' : '☀️';
    }
  }

  // ========== 从数据提取标签和分类（不再依赖 DOM） ==========

  /** 获取当前显示的样式列表（全部或已筛选） */
  function getDisplayStyles() {
    return window.__filteredStyles || window.__allStyles || [];
  }

  /** 从 __allStyles 数据提取标签 */
  function extractTagsFromData() {
    const styles = window.__allStyles || [];
    const tagsMap = { all: 0 };
    
    styles.forEach(s => {
      const tags = s.tags || [];
      tags.forEach(tag => {
        if (tag == null) return;
        const tagText = tag.trim();
        if (tagText) {
          if (!tagsMap[tagText]) tagsMap[tagText] = 0;
          tagsMap[tagText]++;
        }
      });
    });
    
    // 按频次分类
    const highFreq = {};
    let lowFreqCount = 0;
    Object.entries(tagsMap).forEach(([tag, count]) => {
      if (tag === 'all') {
        highFreq.all = count;
      } else if (count >= TAG_MIN_COUNT) {
        highFreq[tag] = count;
      } else {
        lowFreqCount += count;
      }
    });
    if (lowFreqCount > 0) {
      highFreq['_other'] = lowFreqCount;
    }
    
    window.galleryTags = highFreq;
    window.galleryTagsRaw = tagsMap;
    window.galleryTagsLow = Object.entries(tagsMap)
      .filter(([tag, count]) => tag !== 'all' && count < TAG_MIN_COUNT)
      .sort((a, b) => b[1] - a[1]);
  }

  /** 从 __allStyles 数据提取分类 */
  function extractCategoriesFromData() {
    const styles = window.__allStyles || [];
    const categoriesMap = { all: styles.length };
    
    styles.forEach(s => {
      const category = s.category || 'root';
      if (!categoriesMap[category]) categoriesMap[category] = 0;
      categoriesMap[category]++;
    });
    
    // 特殊分类（基于 tags 关键词）
    const paintingKeywords = ['painting', '绘画', '水彩', '油画', '手绘', '插画', '画'];
    const d3Keywords = ['3d', 'c4d', '三维', '建模', 'cgi', 'render', '3d渲染'];
    
    let paintingCount = 0;
    let d3Count = 0;
    
    styles.forEach(s => {
      const tagsStr = (s.tags || []).join(' ').toLowerCase();
      const title = (s.name || '').toLowerCase();
      const searchText = tagsStr + ' ' + title;
      
      if (paintingKeywords.some(k => searchText.includes(k))) paintingCount++;
      if (d3Keywords.some(k => searchText.includes(k))) d3Count++;
    });
    
    categoriesMap['painting'] = paintingCount;
    categoriesMap['3d'] = d3Count;
    
    window.galleryCategories = categoriesMap;
  }

  /** 获取匹配当前筛选条件的 styles 列表 */
  function getMatchingStyles() {
    const all = window.__allStyles || [];
    const query = state.searchQuery.toLowerCase().trim();
    
    return all.filter(function(s) {
      // 标签筛选
      if (state.currentTag !== 'all') {
        const tags = (s.tags || []).filter(t => t != null).map(t => t.toLowerCase());
        if (!tags.includes(state.currentTag.toLowerCase())) return false;
      }
      // 分类筛选
      if (state.currentCategory !== 'all') {
        const tagsStr = (s.tags || []).join(' ').toLowerCase();
        const title = (s.name || '').toLowerCase();
        const searchText = tagsStr + ' ' + title;
        
        if (state.currentCategory === 'painting') {
          const paintingKeywords = ['painting', '绘画', '水彩', '油画', '手绘', '插画', '画'];
          if (!paintingKeywords.some(k => searchText.includes(k))) return false;
        } else if (state.currentCategory === '3d') {
          const d3Keywords = ['3d', 'c4d', '三维', '建模', 'cgi', 'render', '3d渲染'];
          if (!d3Keywords.some(k => searchText.includes(k))) return false;
        } else {
          if ((s.category || 'root') !== state.currentCategory) return false;
        }
      }
      // 搜索
      if (query) {
        const searchable = (s.name + ' ' + (s.code || '') + ' ' + (s.number || '') + ' ' + (s.summary || '') + ' ' + (s.tags || []).join(' ') + ' ' + (s.triggers || '') + ' ' + (s.features || []).join(' ')).toLowerCase();
        if (!searchable.includes(query)) return false;
      }
      // 收藏筛选
      if (state.showFavoritesOnly) {
        if (!state.favorites.includes(s.id)) return false;
      }
      return true;
    });
  }

  /** 对 styles 列表按当前排序方式排序 */
  function sortStyles(styles) {
    if (state.currentSort === 'default' || state.currentSort === 'date-desc') {
      // date-desc: 按 created_at 倒序
      return styles.slice().sort(function(a, b) {
        const dateA = a.created_at || '';
        const dateB = b.created_at || '';
        if (dateA && dateB) return dateB.localeCompare(dateA);
        return 0;
      });
    } else if (state.currentSort === 'name-asc') {
      return styles.slice().sort(function(a, b) { return (a.name || '').localeCompare(b.name || ''); });
    } else if (state.currentSort === 'name-desc') {
      return styles.slice().sort(function(a, b) { return (b.name || '').localeCompare(a.name || ''); });
    } else if (state.currentSort === 'favorites') {
      return styles.slice().sort(function(a, b) {
        const favA = state.favorites.includes(a.id) ? 0 : 1;
        const favB = state.favorites.includes(b.id) ? 0 : 1;
        return favA - favB;
      });
    }
    return styles; // default: no sort
  }

  /** 重新渲染网格：清除现有卡片 + 渲染第一批 + 重置无限滚动 */
  function reRenderGrid() {
    const matching = sortStyles(getMatchingStyles());
    window.__filteredStyles = matching;
    
    const grid = elements.galleryGrid;
    if (!grid) return;
    
    // 清空网格
    grid.innerHTML = '';
    
    // 渲染第一批
    window.__renderedUpTo = 0;
    renderNextBatch();
    
    // 更新计数
    const allTotal = (window.__allStyles || []).length;
    document.getElementById('countVisible').textContent = matching.length;
    document.getElementById('countTotal').textContent = allTotal;
    
    // 更新清除按钮
    const hasActiveFilter = state.currentTag !== 'all' || state.currentCategory !== 'all' || 
                            state.searchQuery !== '' || state.showFavoritesOnly ||
                            state.currentSort !== 'default';
    if (elements.clearFilters) {
      elements.clearFilters.style.display = hasActiveFilter ? 'inline-block' : 'none';
    }
    
    // 无结果提示
    showNoResults(matching.length === 0);
    
    // 更新收藏按钮状态
    updateAllFavButtons();
    
    // 更新 URL 参数
    updateURLParams();
  }

  /** 渲染下一批卡片（追加到网格末尾） */
  function renderNextBatch() {
    const styles = window.__filteredStyles || window.__allStyles || [];
    const grid = elements.galleryGrid;
    if (!grid || window.__renderedUpTo >= styles.length) return;
    
    const start = window.__renderedUpTo;
    const end = Math.min(start + RENDER_BATCH, styles.length);
    const total = styles.length;
    
    var html = '';
    for (var i = start; i < end; i++) {
      html += buildCardHTML(styles[i], i, total);
    }
    grid.insertAdjacentHTML('beforeend', html);
    window.__renderedUpTo = end;
    
    // 同步收藏按钮状态
    updateAllFavButtons();
    
    // 更新无限滚动 sentinel 位置
    updateSentinel();
  }

  /** 显示/隐藏无结果提示 */
  function showNoResults(visible) {
    let el = document.querySelector('.no-results');
    if (visible) {
      if (!el) {
        el = document.createElement('div');
        el.className = 'no-results';
        el.innerHTML = '<div class="no-results-icon">🔍</div><p>没有找到匹配的风格</p>';
        elements.galleryGrid.appendChild(el);
      }
      el.style.display = 'block';
    } else if (el) {
      el.style.display = 'none';
    }
  }

  /** 设置无限滚动 IntersectionObserver */
  function setupInfiniteScroll() {
    // 创建 sentinel 元素
    var sentinel = document.createElement('div');
    sentinel.id = 'infinite-scroll-sentinel';
    sentinel.style.cssText = 'width:100%;height:1px;pointer-events:none;';
    elements.galleryGrid.after(sentinel);
    
    window.__scrollObserver = new IntersectionObserver(function(entries) {
      if (entries[0].isIntersecting) {
        renderNextBatch();
      }
    }, { rootMargin: '400px' });
    window.__scrollObserver.observe(sentinel);
  }

  /** 更新 sentinel 位置到网格末尾 */
  function updateSentinel() {
    var sentinel = document.getElementById('infinite-scroll-sentinel');
    if (sentinel) {
      sentinel.parentNode.appendChild(sentinel); // move to end
    }
  }

  /** 同步页面上所有收藏按钮状态 */
  function updateAllFavButtons() {
    document.querySelectorAll('.favorite-btn').forEach(function(btn) {
      const id = btn.dataset.id;
      if (state.favorites.includes(id)) {
        btn.classList.add('active');
        btn.textContent = '已收藏';
      } else {
        btn.classList.remove('active');
        btn.textContent = '收藏';
      }
    });
  }

  // ========== 渲染分类按钮（渲染到固定的 category-bar） ==========
  function renderCategoryFilters() {
    const catFilter = document.getElementById('categoryFilter');
    if (!catFilter) return;

    const categories = Object.entries(window.galleryCategories || {});
    categories.sort((a, b) => {
      // 固定排序：all 优先，然后按数量
      if (a[0] === 'all') return -1;
      if (b[0] === 'all') return 1;
      return b[1] - a[1];
    });

    // 分类显示名称映射
    const categoryNames = {
      'all': '📦 全部',
      'social_media': '📱 社交媒体',
      'brand_kv': '🎨 品牌视觉',
      'e-commerce': '🛒 电商',
      'science': '🔬 科研',
      'print': '📚 印刷品',
      'ip_character': '🎭 IP角色',
      'travel': '✈️ 旅行',
      'fashion': '👔 时尚',
      'creative': '🎪 创意',
      'vigo_cookbook': '📖 Cookbook',
      'roots': '📁 未分类',
      'meigen': '⚠️ 待整理',
      'typography': '🔤 字体设计',
      'painting': '🖌️ 绘画',
      '3d': '📐 3D'
    };

    let html = '';
    categories.forEach(([cat, count]) => {
      const name = categoryNames[cat] || cat;
      const active = state.currentCategory === cat ? 'active' : '';
      html += `<button class="category-btn ${active}" data-category="${cat}">${name} <span class="tag-count">${count}</span></button>`;
    });

    catFilter.innerHTML = html;

    // 绑定分类按钮事件
    document.querySelectorAll('.category-btn').forEach(btn => {
      btn.addEventListener('click', handleCategoryClick);
    });
  }

  // ========== 分类筛选处理 ==========
  function handleCategoryClick(e) {
    const btn = e.currentTarget;
    const category = btn.dataset.category;
    
    // 更新状态
    state.currentCategory = category;
    
    // 更新按钮样式
    document.querySelectorAll('.category-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    // 重新过滤
    filterCards();
  }

  function renderSidebarTags() {
    const sidebar = document.querySelector('.sidebar .tag-list');
    if (!sidebar) return;

    const tags = Object.entries(window.galleryTags || {});
    tags.sort((a, b) => {
      // all 排第一，_other 排最后
      if (a[0] === 'all') return -1;
      if (b[0] === 'all') return 1;
      if (a[0] === '_other') return 1;
      if (b[0] === '_other') return -1;
      return b[1] - a[1];
    });

    const total = Object.values(window.galleryTagsRaw || window.galleryTags || {}).reduce((sum, t) => sum + t, 0);
    
    let html = `
      <button class="tag-item ${state.currentTag === 'all' ? 'active' : ''}" data-tag="all">
        📦 全部
        <span class="tag-count">${total}</span>
      </button>
    `;

    tags.forEach(([tag, count]) => {
      if (tag === '_other') {
        html += `<div class="other-tag-divider"></div>`;
        html += `<button class="tag-item tag-other-toggle" id="otherTagToggle" title="展开低频标签">
          🔍 其他 <span class="tag-count">${count}</span>
        </button>`;
        html += `<div id="otherTagList" class="other-tag-list" style="display:none;"></div>`;
      } else if (tag !== 'all') {
        html += `
          <button class="tag-item ${state.currentTag === tag ? 'active' : ''}" data-tag="${tag}">
            ${tag}
            <span class="tag-count">${count}</span>
          </button>
        `;
      }
    });

    sidebar.innerHTML = html;
    
    // 绑定标签按钮事件
    sidebar.querySelectorAll('.tag-item').forEach(btn => {
      btn.addEventListener('click', handleTagClick);
    });
    
    // 绑定"其他"标签展开/折叠（懒加载）
    var otherToggle = document.getElementById('otherTagToggle');
    var otherList = document.getElementById('otherTagList');
    var lowTagsRendered = false;
    if (otherToggle && otherList) {
      otherToggle.addEventListener('click', function(e) {
        // 首次展开时懒渲染低頻标签
        if (!lowTagsRendered) {
          var lowHtml = '';
          (window.galleryTagsLow || []).forEach(function(low) {
            var lowTag = low[0], lowCount = low[1];
            lowHtml += '<button class="tag-item tag-item-low" data-tag="' + lowTag + '">'
              + lowTag + ' <span class="tag-count">' + lowCount + '</span></button>';
          });
          otherList.innerHTML = lowHtml;
          // 绑定这些低頻标签的点击事件
          otherList.querySelectorAll('.tag-item').forEach(function(btn) {
            btn.addEventListener('click', handleTagClick);
          });
          lowTagsRendered = true;
        }
        var isHidden = otherList.style.display === 'none';
        otherList.style.display = isHidden ? 'flex' : 'none';
        otherToggle.classList.toggle('active', isHidden);
        otherToggle.textContent = isHidden ? '🔼 收起' : '🔍 其他';
        // 恢复计数
        var countSpan = otherToggle.querySelector('.tag-count');
        if (countSpan && isHidden) countSpan.textContent = (window.galleryTagsLow || []).reduce(function(s, t) { return s + t[1]; }, 0);
        e.stopPropagation();
      });
      // 低频标签点击时自动收起
      otherList.querySelectorAll('.tag-item-low').forEach(function(btn) {
        btn.addEventListener('click', function() {
          otherList.style.display = 'none';
          otherToggle.classList.remove('active');
          otherToggle.textContent = '🔍 其他';
        });
      });
    }
  }

  // ========== 事件处理 ==========
  function bindEvents() {
    // 搜索
    if (elements.searchInput) {
      elements.searchInput.addEventListener('input', debounce(handleSearch, 300));
    }
    
    // 搜索清除按钮
    if (elements.searchClear) {
      elements.searchClear.addEventListener('click', function() {
        if (elements.searchInput) {
          elements.searchInput.value = '';
          state.searchQuery = '';
          elements.searchClear.style.display = 'none';
          filterCards();
          elements.searchInput.focus();
        }
      });
    }

    // 键盘快捷键：Ctrl+K 或 / 聚焦搜索
    document.addEventListener('keydown', function(e) {
      // Ctrl+K 或 Cmd+K
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (elements.searchInput) elements.searchInput.focus();
        return;
      }
      // / 键聚焦搜索（不在输入框中时）
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && 
          document.activeElement?.tagName !== 'INPUT' && 
          document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault();
        if (elements.searchInput) elements.searchInput.focus();
      }
    });

    // 主题切换
    if (elements.themeToggle) {
      elements.themeToggle.addEventListener('click', toggleTheme);
    }

    // 排序
    if (elements.sortSelect) {
      elements.sortSelect.addEventListener('change', handleSortChange);
    }

    // 清除筛选
    if (elements.clearFilters) {
      elements.clearFilters.addEventListener('click', clearFilters);
    }

    // 收藏筛选
    if (elements.filterFavorites) {
      elements.filterFavorites.addEventListener('click', handleFavoriteFilter);
    }

    // 随机发现
    if (elements.randomBtn) {
      elements.randomBtn.addEventListener('click', handleRandom);
    }

    // 卡片交互 — 事件委托（无需重新绑定）
    if (elements.galleryGrid) {
      elements.galleryGrid.addEventListener('click', function(e) {
        var card = e.target.closest('.style-card');
        if (!card) return;
        
        // 点击编号复制
        if (e.target.closest('.card-number')) {
          var num = card.dataset.number || '';
          if (num) {
            copyToClipboard(num, e.target.closest('.card-number'));
          }
          return;
        }
        
        // 卡片链接（让默认行为处理）
        if (e.target.closest('.card-link')) return;
        
        // 打开详情
        openLightbox(card);
      });
    }

    // Lightbox 关闭
    if (elements.lightbox) {
      elements.lightbox.addEventListener('click', (e) => {
        if (e.target === elements.lightbox || e.target.classList.contains('lightbox-card')) {
          closeLightbox();
        }
      });
    }
    if (elements.lightboxClose) {
      elements.lightboxClose.addEventListener('click', (e) => {
        e.stopPropagation();
        closeLightbox();
      });
    }

    // ESC 关闭 Lightbox + ← → 导航
    document.addEventListener('keydown', (e) => {
      if (!elements.lightbox.classList.contains('show')) return;
      if (e.key === 'Escape') {
        closeLightbox();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        navigateLightbox(-1);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        navigateLightbox(1);
      }
    });

    // 导航按钮点击
    if (elements.lightboxPrev) {
      elements.lightboxPrev.addEventListener('click', (e) => {
        e.stopPropagation();
        navigateLightbox(-1);
      });
    }
    if (elements.lightboxNext) {
      elements.lightboxNext.addEventListener('click', (e) => {
        e.stopPropagation();
        navigateLightbox(1);
      });
    }

    // 浏览器前进/后退按钮（hash 变化）
    // 浏览器前进/后退按钮：处理 hash 变化和 URL params 变化
    window.addEventListener('popstate', function() {
      var hash = window.location.hash.replace('#', '');
      if (hash) {
        var card = document.querySelector('.style-card[data-id="' + CSS.escape(hash) + '"]');
        if (card) {
          openLightbox(card, true);
        }
      } else {
        if (elements.lightbox.classList.contains('show')) {
          closeLightbox();
        }
      }
      // 重新读取 URL params 并应用（当用户通过浏览器前进/后退改变筛选时）
      readURLParams();
    });

    // ========== 键盘导航 ==========
    document.addEventListener('keydown', function(e) {
      // 搜索框内按 Escape 清空并失焦
      if (e.key === 'Escape' && document.activeElement === elements.searchInput) {
        elements.searchInput.value = '';
        elements.searchInput.blur();
        state.searchQuery = '';
        filterCards();
      }
      // 卡片上有焦点时，按 Enter 或 Space 打开详情
      if ((e.key === 'Enter' || e.key === ' ') && document.activeElement) {
        var focusedCard = document.activeElement.closest('.style-card');
        if (focusedCard && !e.target.closest('.card-link')) {
          e.preventDefault();
          openLightbox(focusedCard);
        }
      }
    });

    // 回到顶部按钮
    var backToTop = document.getElementById('backToTop');
    if (backToTop) {
      // 用 IntersectionObserver 替代 scroll 事件
      var sentinel = document.createElement('div');
      sentinel.id = 'scroll-sentinel';
      sentinel.style.cssText = 'position:fixed;top:1px;left:0;width:1px;height:1px;pointer-events:none;opacity:0;';
      document.body.appendChild(sentinel);

      var scrollObserver = new IntersectionObserver(function(entries) {
        // sentinel 不可见 → 已滚动超过 1px
        backToTop.classList.toggle('visible', !entries[0].isIntersecting);
      }, { threshold: 0 });
      scrollObserver.observe(sentinel);

      backToTop.addEventListener('click', function() {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }

    // 收藏按钮 — 事件委托（卡片 + Lightbox）
    document.addEventListener('click', function(e) {
      var btn = e.target.closest('.favorite-btn');
      if (!btn) return;
      e.stopPropagation();
      handleFavoriteToggle(btn.dataset.id, btn);
    });

    // 复制提示词按钮 — 事件委托（Lightbox 内）
    document.addEventListener('click', function(e) {
      var btn = e.target.closest('.copy-prompt-btn');
      if (!btn) return;
      e.stopPropagation();
      var styleId = btn.dataset.id;
      var styles = window.__allStyles || [];
      var s = styles.find(function(st) { return st.id === styleId; });
      if (!s) return;
      var promptText = s.prompt || '';
      if (!promptText) {
        var parts = [s.name];
        if (s.triggers) parts.push('Triggers: ' + s.triggers);
        if (s.summary) parts.push(s.summary);
        promptText = parts.join('\n');
      }
      copyToClipboard(promptText, btn);
    });
  }

  /** 复制文本到剪贴板（带反馈） */
  function copyToClipboard(text, btn) {
    var origText = btn.textContent;
    function done() {
      btn.textContent = '✅ 已复制';
      setTimeout(function() { btn.textContent = origText; }, 2000);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function() {
        fallbackCopy(text, done);
      });
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, cb) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    if (cb) cb();
  }

  function handleSearch(e) {
    const query = e.target.value.toLowerCase().trim();
    state.searchQuery = query;
    
    // 显示/隐藏搜索清除按钮
    if (elements.searchClear) {
      elements.searchClear.style.display = query ? 'inline' : 'none';
    }
    
    filterCards();
  }

  function handleTagClick(e) {
    const btn = e.currentTarget;
    state.currentTag = btn.dataset.tag;
    
    // 更新所有标签按钮状态
    document.querySelectorAll('.tag-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tag-item[data-tag="' + state.currentTag + '"]').forEach(b => b.classList.add('active'));
    
    filterCards();
  }

  function handleSortChange(e) {
    state.currentSort = e.target.value;
    filterCards();  // sortCards + filterCards 合并为一次 reRenderGrid
  }

  function sortCards() {
    // 排序通过 filterCards 完成（数据驱动，重新渲染）
    filterCards();
  }

  function handleFavoriteFilter() {
    state.showFavoritesOnly = !state.showFavoritesOnly;
    elements.filterFavorites.classList.toggle('active', state.showFavoritesOnly);
    filterCards();
  }

  // ========== 随机发现 ==========
  function handleRandom() {
    var styles = window.__filteredStyles || window.__allStyles || [];
    if (styles.length === 0) return;
    var idx = Math.floor(Math.random() * styles.length);
    var card = document.querySelector('.style-card[data-original-index="' + idx + '"]') ||
               document.querySelector('.style-card[data-id="' + styles[idx].id + '"]');
    if (card) {
      card.click();
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  // ========== 清除所有筛选 ==========
  function clearFilters() {
    state.currentTag = 'all';
    state.currentCategory = 'all';
    state.currentSort = 'default';
    state.searchQuery = '';
    state.showFavoritesOnly = false;

    // 重置搜索框
    if (elements.searchInput) elements.searchInput.value = '';
    if (elements.searchClear) elements.searchClear.style.display = 'none';

    // 重置排序
    if (elements.sortSelect) elements.sortSelect.value = 'default';

    // 重置标签高亮
    document.querySelectorAll('.tag-item').forEach(function(b) {
      b.classList.toggle('active', b.dataset.tag === 'all');
    });

    // 重置分类高亮
    document.querySelectorAll('.category-btn').forEach(function(b) {
      b.classList.toggle('active', b.dataset.category === 'all');
    });

    // 重置收藏筛选
    state.showFavoritesOnly = false;
    if (elements.filterFavorites) elements.filterFavorites.classList.remove('active');

    // 重新渲染（数据驱动，包含排序恢复）
    filterCards();
  }

  function handleFavoriteToggle(cardId, btn) {
    const index = state.favorites.indexOf(cardId);
    if (index > -1) {
      state.favorites.splice(index, 1);
    } else {
      state.favorites.push(cardId);
    }
    localStorage.setItem('galleryFavorites', JSON.stringify(state.favorites));
    
    // 同步更新页面上所有相同 cardId 的收藏按钮（卡片 + Lightbox）
    document.querySelectorAll(`.favorite-btn[data-id="${cardId}"]`).forEach(function(b) {
      updateFavoriteButton(cardId, b);
    });
  }

  function updateFavoriteButton(cardId, btn) {
    if (state.favorites.includes(cardId)) {
      btn.classList.add('active');
      btn.textContent = '已收藏';
    } else {
      btn.classList.remove('active');
      btn.textContent = '收藏';
    }
  }

  // ========== 过滤逻辑 ==========
  // ========== 过滤逻辑（数据驱动 → 重新渲染网格） ==========
  function filterCards() {
    reRenderGrid();

    // 搜索高亮：新渲染的卡片还没有 search-highlight，需要处理
    var query = state.searchQuery.toLowerCase().trim();
    if (query) {
      document.querySelectorAll('.style-card:not(.hidden) .card-title').forEach(function(titleEl) {
        var text = titleEl.textContent;
        var regex = new RegExp('(' + query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        if (regex.test(text)) {
          if (!titleEl.dataset.origTitle) titleEl.dataset.origTitle = text;
          titleEl.innerHTML = text.replace(regex, '<mark class="search-highlight">$1</mark>');
        }
      });
    }

    updateURLParams();
  }

  // ========== Lightbox 信息卡片 - 左图右文 ==========
  function openLightbox(card, skipHashUpdate) {
    const data = extractCardData(card, card.dataset.id);
    renderLightboxContent(data);
    elements.lightbox.classList.add('show');
    document.body.style.overflow = 'hidden';
    // 记录当前索引用于导航
    updateLightboxIndex(card);
    // 更新 URL hash
    if (!skipHashUpdate && data.id) {
      history.pushState(null, '', '#' + data.id);
    }
  }

  function extractCardData(card, cardId) {
    return {
      id: cardId || card.dataset.id || '',
      imageUrl: card.querySelector('.card-image')?.src || '',
      title: card.querySelector('.card-title')?.textContent || '',
      number: card.dataset.number || '',
      summary: card.dataset.summary || '',
      features: card.dataset.features?.split('|').filter(f => f) || [],
      triggers: card.dataset.triggers || '',
      tags: card.dataset.tags?.split(',').filter(t => t) || [],
      link: card.querySelector('.card-link')?.href || '',
      linkText: card.querySelector('.card-link')?.textContent || ''
    };
  }

  function renderLightboxContent(data) {
    const card = elements.lightboxCard;
    
    // 标题（不含编号）
    const indexEl = card.querySelector('.lightbox-index');
    card.querySelector('.lightbox-title').textContent = data.title;
    if (data.number) {
      indexEl.textContent = `#${data.number}`;
      indexEl.style.cursor = 'pointer';
      indexEl.title = '点击复制编号';
      // 复制编号
      indexEl.onclick = function(e) {
        e.stopPropagation();
        navigator.clipboard.writeText(data.number).then(function() {
          var orig = indexEl.textContent;
          indexEl.textContent = '✅ 已复制';
          indexEl.style.color = 'var(--accent-color)';
          setTimeout(function() {
            indexEl.textContent = orig;
            indexEl.style.color = '';
          }, 1500);
        }).catch(function() {
          // fallback
          var ta = document.createElement('textarea');
          ta.value = data.number;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          var orig = indexEl.textContent;
          indexEl.textContent = '✅ 已复制';
          setTimeout(function() {
            indexEl.textContent = orig;
          }, 1500);
        });
      };
    } else {
      indexEl.textContent = '';
      indexEl.onclick = null;
    }
    
    // 收藏按钮
    const favBtn = card.querySelector('.lightbox-fav-btn');
    if (favBtn && data.id) {
      favBtn.dataset.id = data.id;
      updateFavoriteButton(data.id, favBtn);
      // 移除旧监听，绑定新监听
      var newBtn = favBtn.cloneNode(true);
      favBtn.parentNode.replaceChild(newBtn, favBtn);
      newBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        handleFavoriteToggle(data.id, newBtn);
      });
    }
    
    // 复制提示词按钮（Lightbox）
    const copyBtn = card.querySelector('.lightbox-copy-btn');
    if (copyBtn && data.id) {
      copyBtn.dataset.id = data.id;
    }
    
    // 图片
    const img = card.querySelector('.lightbox-image');
    img.src = data.imageUrl;
    img.alt = data.title;
    // 同步更新 <picture> 的 <source> 标签
    const source = card.querySelector('.lightbox-source');
    if (source) source.srcset = data.imageUrl;
    
    // 一句话理解
    const summarySection = card.querySelector('.lightbox-summary-section');
    if (data.summary) {
      summarySection.querySelector('.lightbox-summary').textContent = data.summary;
      summarySection.style.display = 'block';
    } else {
      summarySection.style.display = 'none';
    }
    
    // 触发词
    const triggersSection = card.querySelector('.lightbox-triggers-section');
    if (data.triggers) {
      triggersSection.querySelector('.lightbox-triggers').textContent = data.triggers;
      triggersSection.style.display = 'block';
    } else {
      triggersSection.style.display = 'none';
    }
    
    // 核心特点
    const featuresSection = card.querySelector('.lightbox-features-section');
    const featuresList = featuresSection.querySelector('.lightbox-features');
    if (data.features.length > 0) {
      featuresList.innerHTML = data.features.map(f => `<li>${f}</li>`).join('');
      featuresSection.style.display = 'block';
    } else {
      featuresSection.style.display = 'none';
    }
    
    // 标签
    const tagsSection = card.querySelector('.lightbox-tags-section');
    const tagsContainer = tagsSection.querySelector('.lightbox-tags');
    if (data.tags.length > 0) {
      tagsContainer.innerHTML = data.tags.map(t => `<span class="lightbox-tag">${t}</span>`).join('');
      tagsSection.style.display = 'block';
    } else {
      tagsSection.style.display = 'none';
    }
    
    // 链接
    const linkSection = card.querySelector('.lightbox-link-section');
    const linkEl = linkSection.querySelector('.lightbox-link');
    if (data.link) {
      linkEl.href = data.link;
      linkEl.textContent = data.linkText || '🔗 查看原文';
      linkSection.style.display = 'block';
    } else {
      linkSection.style.display = 'none';
    }
  }

  function closeLightbox() {    
    elements.lightbox.classList.remove('show');
    document.body.style.overflow = '';
    state.lightboxCurrentIndex = -1;
    // 清除 hash（不触发 popstate）
    if (window.location.hash) {
      history.pushState(null, '', window.location.pathname + window.location.search);
    }
  }

  // ========== Lightbox 左右导航 ==========
  /** 获取当前可见卡片列表（按 DOM 顺序） */
  function getVisibleCards() {
    return Array.from(document.querySelectorAll('.style-card')).filter(function(c) { return !c.classList.contains('hidden'); });
  }

  /** 根据当前卡片更新索引并刷新导航按钮状态 */
  function updateLightboxIndex(card) {
    state.lightboxVisibleCards = getVisibleCards();
    state.lightboxCurrentIndex = state.lightboxVisibleCards.indexOf(card);
    updateNavButtons();
  }

  /** 显示/隐藏左右导航按钮 */
  function updateNavButtons() {
    var idx = state.lightboxCurrentIndex;
    var total = state.lightboxVisibleCards.length;
    if (elements.lightboxPrev) {
      elements.lightboxPrev.style.display = (total > 1 && idx > 0) ? 'flex' : 'none';
    }
    if (elements.lightboxNext) {
      elements.lightboxNext.style.display = (total > 1 && idx < total - 1) ? 'flex' : 'none';
    }
  }

  /** 导航到上一个/下一个风格 */
  function navigateLightbox(direction) {
    var cards = state.lightboxVisibleCards;
    var idx = state.lightboxCurrentIndex;
    if (cards.length === 0) return;
    var newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= cards.length) return;
    var newCard = cards[newIdx];
    if (!newCard) return;
    state.lightboxCurrentIndex = newIdx;
    var data = extractCardData(newCard, newCard.dataset.id);
    renderLightboxContent(data);
    updateNavButtons();
    // 更新 hash
    if (data.id) {
      history.replaceState(null, '', '#' + data.id);
    }
    // 滚动到新卡片位置（保持浏览上下文）
    newCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // ========== URL Hash 路由 ==========
  /** 页面加载时根据 hash 打开对应风格 */
  function handleHashRoute() {
    var hash = window.location.hash.replace('#', '');
    if (!hash) return;
    var card = document.querySelector('.style-card[data-id="' + CSS.escape(hash) + '"]');
    if (card && card.classList.contains('hidden')) {
      // 如果卡片被筛选隐藏，清除筛选再打开
      clearFilters();
    }
    if (card) {
      // 确保卡片可见后再打开
      setTimeout(function() {
        openLightbox(card, true);  // skipHashUpdate=true，避免重复 pushState
      }, 50);
    }
  }

  // ========== 图片懒加载（已改为原生 loading="lazy"，保留空函数兼容） ==========
  function setupLazyLoading() {}

  // ========== 工具函数 ==========
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  // ========== 启动 ==========
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();