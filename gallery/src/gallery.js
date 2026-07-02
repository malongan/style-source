/**
 * Gallery 功能脚本 v3
 * 包含：搜索过滤、标签筛选、收藏、Lightbox信息卡片、深色模式
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

  // ========== DOM 元素 ==========
  let elements = {};

  // ========== 初始化 ==========
  function init() {
    cacheElements();
    loadTheme();
    bindEvents();
    extractTags();
    extractCategories();
    renderSidebarTags();
    renderCategoryFilters();
    setupLazyLoading();
    // Hash 路由：页面加载后检查 URL hash
    setTimeout(handleHashRoute, 100);
  }

  function cacheElements() {
    elements = {
      searchInput: document.getElementById('searchInput'),
      searchClear: document.getElementById('searchClear'),
      themeToggle: document.getElementById('themeToggle'),
      filterFavorites: document.getElementById('filterFavorites'),
      clearFilters: document.getElementById('clearFilters'),
      sortSelect: document.getElementById('sortSelect'),
      galleryGrid: document.querySelector('.gallery-grid'),
      styleCards: document.querySelectorAll('.style-card'),
      lightbox: document.getElementById('lightbox'),
      lightboxCard: document.querySelector('.lightbox-card'),
      lightboxClose: document.getElementById('lightboxClose'),
      lightboxPrev: document.getElementById('lightboxPrev'),
      lightboxNext: document.getElementById('lightboxNext')
    };
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

  // ========== 标签提取 - 从 dataset 中提取 ==========
  function extractTags() {
    const tagsMap = { all: 0 };
    
    elements.styleCards.forEach(card => {
      const tagsStr = card.dataset.tags || '';
      const tags = tagsStr.split(',').filter(t => t.trim());
      tags.forEach(tag => {
        const tagText = tag.trim();
        if (tagText) {
          if (!tagsMap[tagText]) {
            tagsMap[tagText] = 0;
          }
          tagsMap[tagText]++;
        }
      });
    });
    
    // 按频次分类：高频（≥TAG_MIN_COUNT次）保留，低频折叠
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
    window.galleryTagsRaw = tagsMap; // 保留完整数据用于筛选
    // 保存低频标签列表（用于展开显示）
    window.galleryTagsLow = Object.entries(tagsMap)
      .filter(([tag, count]) => tag !== 'all' && count < TAG_MIN_COUNT)
      .sort((a, b) => b[1] - a[1]);
  }

  // ========== 分类提取 ==========
  function extractCategories() {
    const categoriesMap = { all: 0 };
    
    elements.styleCards.forEach(card => {
      const category = card.dataset.category || 'root';
      if (!categoriesMap[category]) {
        categoriesMap[category] = 0;
      }
      categoriesMap[category]++;
    });
    
    window.galleryCategories = categoriesMap;
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
      'typography': '🔤 字体设计'
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
        html += `<div id="otherTagList" class="other-tag-list" style="display:none;">`;
        (window.galleryTagsLow || []).forEach(([lowTag, lowCount]) => {
          html += `<button class="tag-item tag-item-low" data-tag="${lowTag}">
            ${lowTag} <span class="tag-count">${lowCount}</span>
          </button>`;
        });
        html += `</div>`;
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
    
    // 绑定"其他"标签展开/折叠
    var otherToggle = document.getElementById('otherTagToggle');
    var otherList = document.getElementById('otherTagList');
    if (otherToggle && otherList) {
      otherToggle.addEventListener('click', function(e) {
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

    // 图片点击 - 打开信息卡片（事件委托，支持动态加载的卡片）
    if (elements.galleryGrid) {
      elements.galleryGrid.addEventListener('click', (e) => {
        // 查找点击的卡片
        var card = e.target.closest('.style-card');
        if (!card) return;

        // 收藏按钮不打开详情
        if (e.target.closest('.favorite-btn')) return;
        // 链接按钮不打开详情
        if (e.target.closest('.card-link')) return;
        // 其他点击打开详情
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
    });

    // 回到顶部按钮
    var backToTop = document.getElementById('backToTop');
    if (backToTop) {
      window.addEventListener('scroll', debounce(function() {
        backToTop.classList.toggle('visible', window.scrollY > 400);
      }, 100));
      backToTop.addEventListener('click', function() {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }

    // 收藏按钮
    elements.styleCards.forEach(card => {
      const favBtn = card.querySelector('.favorite-btn');
      if (favBtn) {
        favBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          handleFavoriteToggle(card.dataset.id, favBtn);
        });
        updateFavoriteButton(card.dataset.id, favBtn);
      }
    });
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
    document.querySelectorAll(`.tag-item[data-tag="${state.currentTag}"]`).forEach(b => b.classList.add('active'));
    
    filterCards();
  }

  function handleSortChange(e) {
    state.currentSort = e.target.value;
    sortCards();
    filterCards();
  }

  function sortCards() {
    const grid = elements.galleryGrid;
    if (!grid) return;
    const cards = Array.from(grid.querySelectorAll('.style-card'));
    if (cards.length === 0) return;

    cards.sort(function(a, b) {
      if (state.currentSort === 'default') {
        // 保持原始顺序（按 data-original-index）
        return (parseInt(a.dataset.originalIndex) || 0) - (parseInt(b.dataset.originalIndex) || 0);
      } else if (state.currentSort === 'newest') {
        // 按创建时间倒序（最新添加的在前）
        var dateA = a.dataset.createdAt || '';
        var dateB = b.dataset.createdAt || '';
        if (dateA && dateB) {
          return dateB.localeCompare(dateA);
        }
        // fallback: 按 original-index 倒序
        return (parseInt(b.dataset.originalIndex) || 0) - (parseInt(a.dataset.originalIndex) || 0);
      } else if (state.currentSort === 'name-asc') {
        var nameA = (a.querySelector('.card-title')?.textContent || '').toLowerCase();
        var nameB = (b.querySelector('.card-title')?.textContent || '').toLowerCase();
        return nameA.localeCompare(nameB);
      } else if (state.currentSort === 'name-desc') {
        var nameA = (a.querySelector('.card-title')?.textContent || '').toLowerCase();
        var nameB = (b.querySelector('.card-title')?.textContent || '').toLowerCase();
        return nameB.localeCompare(nameA);
      } else if (state.currentSort === 'favorites') {
        var favA = state.favorites.includes(a.dataset.id) ? 0 : 1;
        var favB = state.favorites.includes(b.dataset.id) ? 0 : 1;
        return favA - favB;
      }
      return 0;
    });

    // 重新挂载排序后的卡片
    cards.forEach(function(card) {
      grid.appendChild(card);
    });

    // 刷新卡片引用
    elements.styleCards = document.querySelectorAll('.style-card');
    
    // 虚拟列表：刷新后继续渲染剩余卡片
    if (window.__virtualList) {
      var vl = window.__virtualList;
      var grid = document.querySelector('.gallery-grid');
      var sentinel = document.getElementById('virtual-sentinel');
      
      // 如果有未渲染的卡片，继续渲染
      if (vl.renderedCount < vl.styles.length) {
        var start = vl.renderedCount;
        var end = Math.min(start + vl.batchSize, vl.styles.length);
        var batchHTML = vl.styles.slice(start, end).map(function(s, i) {
          return buildCardHTML(s, start + i, vl.styles.length);
        }).join('');
        
        if (sentinel) {
          sentinel.insertAdjacentHTML('beforebegin', batchHTML);
        } else {
          grid.insertAdjacentHTML('beforeend', batchHTML);
        }
        vl.renderedCount = end;
        
        // 继续渲染直到全部完成
        if (vl.renderedCount < vl.styles.length) {
          requestAnimationFrame(function() {
            var vl2 = window.__virtualList;
            var grid2 = document.querySelector('.gallery-grid');
            var sentinel2 = document.getElementById('virtual-sentinel');
            var start2 = vl2.renderedCount;
            var end2 = Math.min(start2 + vl2.batchSize, vl2.styles.length);
            var batchHTML2 = vl2.styles.slice(start2, end2).map(function(s, i) {
              return buildCardHTML(s, start2 + i, vl2.styles.length);
            }).join('');
            if (sentinel2) sentinel2.insertAdjacentHTML('beforebegin', batchHTML2);
            else grid2.insertAdjacentHTML('beforeend', batchHTML2);
            vl2.renderedCount = end2;
          });
        }
      }
    }
  }

  function handleFavoriteFilter() {
    state.showFavoritesOnly = !state.showFavoritesOnly;
    elements.filterFavorites.classList.toggle('active', state.showFavoritesOnly);
    filterCards();
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

    // 重置排序 → 恢复原始顺序
    sortCards();

    // 重新过滤
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
  function filterCards() {
    // 先清除旧高亮
    document.querySelectorAll('.style-card .card-title .search-highlight').forEach(function(m) {
      var parent = m.parentNode;
      parent.replaceChild(document.createTextNode(m.textContent), m);
      parent.normalize();
    });
    
    elements.styleCards.forEach(card => {
      const cardId = card.dataset.id;
      const title = card.querySelector('.card-title')?.textContent.toLowerCase() || '';
      const tagsStr = card.dataset.tags || '';
      const triggers = card.dataset.triggers?.toLowerCase() || '';
      const category = card.dataset.category || '';
      const code = (card.dataset.code || '').toLowerCase();
      
      let visible = true;

      // 分类筛选
      if (state.currentCategory !== 'all') {
        visible = visible && category === state.currentCategory;
      }

      // 标签筛选
      if (state.currentTag !== 'all') {
        const cardTags = tagsStr.split(',').map(t => t.trim());
        visible = visible && cardTags.includes(state.currentTag);
      }

      // 搜索筛选
      if (state.searchQuery) {
        visible = visible && (
          title.includes(state.searchQuery) ||
          tagsStr.toLowerCase().includes(state.searchQuery) ||
          triggers.includes(state.searchQuery) ||
          code.includes(state.searchQuery)
        );
      }

      // 收藏筛选
      if (state.showFavoritesOnly) {
        visible = visible && state.favorites.includes(cardId);
      }

      card.classList.toggle('hidden', !visible);
      
      // 搜索高亮 - 只在有搜索词且卡片可见时执行
      var titleEl = card.querySelector('.card-title');
      if (state.searchQuery && visible && titleEl) {
        var origTitle = titleEl.dataset.origTitle || titleEl.textContent;
        if (!titleEl.dataset.origTitle) titleEl.dataset.origTitle = origTitle;
        var regex = new RegExp('(' + state.searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        titleEl.innerHTML = origTitle.replace(regex, '<mark class="search-highlight">$1</mark>');
      } else if (titleEl) {
        // 恢复原始文本
        if (titleEl.dataset.origTitle) {
          titleEl.textContent = titleEl.dataset.origTitle;
          delete titleEl.dataset.origTitle;
        }
      }
    });

    // 更新计数（显示 可见数/总数）
    const totalCards = document.querySelectorAll('.style-card').length;
    const visibleCards = document.querySelectorAll('.style-card:not(.hidden)').length;
    const counterVis = document.getElementById('countVisible');
    const counterTotal = document.getElementById('countTotal');
    if (counterVis) counterVis.textContent = visibleCards;
    if (counterTotal) counterTotal.textContent = totalCards;

    // 清除筛选按钮可见性
    const hasActiveFilter = state.currentTag !== 'all' || state.currentCategory !== 'all' || 
                            state.searchQuery !== '' || state.showFavoritesOnly ||
                            state.currentSort !== 'default';
    if (elements.clearFilters) {
      elements.clearFilters.style.display = hasActiveFilter ? 'inline-block' : 'none';
    }
    
    // 显示无结果提示（用可见卡片计数判断，不用 forEach 内部变量）
    let noResults = document.querySelector('.no-results');
    
    if (visibleCards === 0) {
      if (!noResults) {
        noResults = document.createElement('div');
        noResults.className = 'no-results';
        noResults.innerHTML = `
          <div class="no-results-icon">🔍</div>
          <p>没有找到匹配的风格</p>
        `;
        elements.galleryGrid.appendChild(noResults);
      }
      noResults.style.display = 'block';
    } else if (noResults) {
      noResults.style.display = 'none';
    }
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
    
    // 图片
    const img = card.querySelector('.lightbox-image');
    img.src = data.imageUrl;
    img.alt = data.title;
    
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
    return Array.from(elements.styleCards).filter(c => !c.classList.contains('hidden'));
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

  // ========== 图片懒加载（IntersectionObserver 增强） ==========
  function setupLazyLoading() {
    if (!('IntersectionObserver' in window)) return;
    var lazyImages = document.querySelectorAll('.card-image[data-src]');
    if (lazyImages.length === 0) return;
    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          var img = entry.target;
          img.src = img.dataset.src;
          img.removeAttribute('data-src');
          observer.unobserve(img);
        }
      });
    }, { rootMargin: '200px' });
    lazyImages.forEach(function(img) { observer.observe(img); });
  }

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