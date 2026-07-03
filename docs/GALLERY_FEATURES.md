# 🎨 风格画廊 — 功能清单与优化路线图

> 最后更新: 2026-07-03（优化调查 v2）

---

## 📊 现状总览

| 指标 | 值 |
|------|----|
| 风格总数 | **168 个** |
| 分类数 | **11 个** |
| 标签总数 | ~880 个（去重） |
| 图片 | 168 全尺寸 WebP + 168 缩略图 ✅ **全部 1:1 对应** |
| 数据字段完整性 | id/name/code/tags/summary/features/triggers/preview_webp/ratio/prompt: **100%** |
| 数据源 | `styles/*.yml` → `generate_data.py` → `data/styles.json` |
| 构建工具 | `build_gallery.py` → `gallery.html` + `gallery.css` + `gallery-runtime.js` |
| 部署 | GitHub Pages (malongan.github.io/style-source/) |
| CI/CD | PR 合并自动校验 + 定时图片巡检 |
| 图片仓库 | **style-source/images/styles_previews/** （唯一数据源） |

### 分类分布

| 分类 | 数量 | 说明 |
|------|------|------|
| vigo_cookbook | 51 | Vigo 食谱书风格 |
| creative | 42 | 创意设计 |
| brand_kv | 18 | 品牌主视觉 |
| social_media | 13 | 社交媒体 |
| e-commerce | 10 | 电商 |
| print | 9 | 印刷品 |
| ip_character | 7 | IP 角色 |
| travel | 5 | 旅行 |
| science | 5 | 科研学术 |
| fashion | 5 | 时尚 |
| typography | 3 | 字体排版 |

---

## ✅ 已实现功能清单

### 📐 页面架构
| # | 功能 | 说明 |
|---|------|------|
| 1 | **瀑布流布局** | 5 列网格，`gallery-grid` CSS Grid |
| 2 | **骨架屏防 FOUC** | 首屏关键样式内联 `<style>`，JS 加载前骨架图占位 |
| 3 | **响应式设计** | `max-width: 1800px`，移动端自适应 |
| 4 | **SEO 元数据** | og:title/description/image, twitter:card, canonical, keywords |
| 5 | **404 页面** | 自定义 `404.html` |

### 🔍 搜索与筛选
| # | 功能 | 说明 |
|---|------|------|
| 6 | **🔍 搜索框** | 按风格名称/描述实时搜索，匹配高亮 `<mark>` |
| 7 | **🏷️ 标签筛选** | 左侧固定标签栏，频次 ≥ 3 展示，低频折叠到「其他」 |
| 8 | **📂 分类筛选** | 顶部分类按钮栏，点击切换分类 |
| 9 | **⬇️ 排序** | 下拉选择：默认 / A-Z / Z-A / 最新 |
| 10 | **❤️ 仅看收藏** | 筛选按钮切换，只显示已收藏风格 |
| 11 | **🔗 URL 参数路由** | 筛选状态同步到 `?q=&category=&tag=&sort=&fav=`，支持分享 URL |
| 12 | **🔄 清空筛选** | 一键清除所有筛选条件 |

### 🖼️ 图片与渲染
| # | 功能 | 说明 |
|---|------|------|
| 13 | **♾️ 无限滚动** | `IntersectionObserver`，批次 30 张渲染 |
| 14 | **🖼️ WebP 格式** | 全尺寸 ~90KB + 缩略图 ~17KB |
| 15 | **🖼️ 缩略图** | 列表展示缩略图，点击打开全尺寸（通过 Lightbox） |
| 16 | **📦 图片加载失败兜底** | `img-fallback` 占位 |
| 17 | **⚡ 预链接 CDN** | `<link rel="preconnect">` + `<link rel="preload">` |

### 💡 Lightbox 详情
| # | 功能 | 说明 |
|---|------|------|
| 18 | **🪟 Lightbox 信息卡** | 左图右文，展示完整风格信息 |
| 19 | **📋 编号展示** | 卡片显示 `#ST0001` 编号 |
| 20 | **📋 复制编号** | 点击编号一键复制到剪贴板 |
| 21 | **🔄 上下翻页** | Lightbox 内 Prev/Next 按钮切换 |
| 22 | **⌨️ 键盘导航** | `←` `→` 切换，`Esc` 关闭 |
| 23 | **🔗 Hash 路由** | `#style_id` 直达详情，支持前进/后退 |
| 24 | **📋 功能特性列表** | Lightbox 展示 `features` 字段 |
| 25 | **🏷️ 标签列表** | Lightbox 展示完整标签 |
| 26 | **🔗 源链接** | 跳转到即梦/原文 |

### 🌙 主题与收藏
| # | 功能 | 说明 |
|---|------|------|
| 27 | **🌙 深色模式** | 明暗双主题，CSS 变量驱动，`localStorage` 持久化 |
| 28 | **❤️ 收藏** | 点击星标收藏，`localStorage` 持久化 |
| 29 | **🔄 主题切换** | 点击月亮/太阳图标切换 |
| 30 | **🔄 主题过渡动画** | CSS `transition` 平滑切换 |

### ⚙️ 后端脚本与 CI
| # | 功能 | 说明 |
|---|------|------|
| 31 | **🔧 generate_data.py** | 从 yml 提取元数据，自动解析图片 URL，生成 styles.json |
| 32 | **🔧 build_gallery.py** | 生成 gallery.html + gallery.css + gallery-runtime.js |
| 33 | **🔧 validate_all.py** | 验证所有风格文件合法性 |
| 34 | **🔧 validate_style.py** | 单文件验证 |
| 35 | **🔧 check_duplicate.py** | 查重 |
| 36 | **🔧 check_image_urls.py** | 图片 URL 可达性检查 |
| 37 | **🔧 upload_preview.py** | 上传预览图，自动哈希命名 + WebP 转换 |
| 38 | **🔧 generate_index.py** | 生成 _index.md |
| 39 | **🔧 update_collection_log.py** | 更新收集日志 |
| 40 | **🔧 md_to_yaml.py** | Markdown 转 YAML |
| 41 | **🔧 deploy_gallery.py** | 部署画廊 |
| 42 | **🔧 fetch_twitter.py** | Twitter/X 采集 |
| 43 | **🔧 run_fetch.py** | 采集入口 |
| 44 | **🔐 pre-push-security-scan.py** | 发布前安全扫描 |
| 45 | **🔄 CI: on-merge-main.yml** | PR 合并后验证数据一致性 |
| 46 | **🔄 CI: check-images.yml** | 图片可达性日检 + PR 检查 |
| 47 | **🔄 CI: on-push-styles.yml** | 推送风格文件触发检查 |
| 48 | **🔄 CI: manual-deploy.yml** | 手动部署 |

### 📦 数据完整性
| # | 功能 | 说明 |
|---|------|------|
| 49 | **📦 prompt 字段** | 168/168 有完整提示词 |
| 50 | **📦 variables 字段** | 140/168 有变量模板 |
| 51 | **📦 source_author** | 167/168 有来源作者 |
| 52 | **📦 scene 字段** | 13/168 有场景描述 |
| 53 | **📦 preview_webp_thumb** | 168/168 有缩略图 |
| 54 | **📦 style_numbers.json** | 编号映射表 |
| 55 | **📦 style_timestamps.json** | 时间戳记录 |

---

## 📋 PERF_PLAN 优化进度

> 对照 `docs/PERF_PLAN.md`（2026-07-02 审计），标记完成状态

| # | 项目 | 优先级 | 状态 | 备注 |
|---|------|--------|------|------|
| 1 | 图片懒加载 `loading="lazy"` | P0 🔴 | ❌ **未做** | `setupLazyLoading()` 空函数占位 |
| 2 | 移除内联 FALLBACK_DATA | P0 🔴 | ✅ **已做** | 改为 `fetch('data/styles.json')` 异步加载 |
| 3 | JS/CSS 异步加载 | P0 🔴 | ⚠️ **部分** | CSS 已 `preload`；JS 仍同步 `<script>`（但 HTML 只有 9KB） |
| 4 | HTML 压缩 | P0 🔴 | ✅ **已做** | `gallery.html` 已压缩（1 行，9KB） |
| 5 | URL 参数过滤 | P1 🟡 | ✅ **已做** | `readURLParams()` + `updateURLParams()` |
| 6 | IntersectionObserver 优化 | P1 🟡 | ✅ **已做** | 无限滚动已用 IntersectionObserver |
| 7 | WebP 回退 `<picture>` | P1 🟡 | ❌ **未做** | 全部 WebP，无 JPEG fallback |
| 8 | 键盘导航增强 | P1 🟡 | ⚠️ **部分** | Lightbox 内 ← → Esc 已实现；Tab/Enter/快捷键未实现 |
| 9 | 无限滚动/分页 | P2 🔵 | ✅ **已做** | Batch 30 张，IntersectionObserver |
| 10 | 渐进式图片加载 | P2 🔵 | ❌ **未做** | 无模糊过渡/缩略图占位 |
| 11 | CDN 加速 | P2 🔵 | ❌ **未做** | 仍用 GitHub Pages |
| 12 | PWA / Service Worker | P3 ⚪ | ❌ **未做** | - |
| 13 | 分享功能 | P3 ⚪ | ❌ **未做** | - |
| 14 | 统计/分析 | P3 ⚪ | ❌ **未做** | - |
| 15 | 一键复制提示词 | P3 ⚪ | ❌ **未做** | 仅支持复制编号 |
| 16 | 图片放大镜 | P3 ⚪ | ❌ **未做** | - |
| 17 | 对比功能 | P3 ⚪ | ❌ **未做** | - |
| 18 | 随机发现 | P3 ⚪ | ❌ **未做** | - |
| 19 | 打印友好 CSS | P3 ⚪ | ❌ **未做** | - |

---

## ⚠️ 历史踩坑与经验教训

### 1. 🚨 2026-06-20: 图片 URL 全部 404
**问题**：`malongan/images` 仓库归档后，所有图片 URL 指向旧域名 `malongan.github.io/images/` 全部 404。
**根因**：`generate_data.py` 直接从 yml 提取图片 URL，yml 存的是旧域名旧路径。
**教训**：
- 不要依赖 yml 中的外部 URL，图片 URL 应自动从文件系统解析
- `generate_data.py` 新增 `resolve_image_url()` 函数，优先本地 glob 匹配
- 图片文件名格式：`{style_id}_{8位hash}.{ext}`
- **吸取 ✅ 已修复**

### 2. 🚨 2026-06-29: YAML 中 `![]()` 语法错误
**问题**：在 YAML 文件末尾写 Markdown 图片引用 `![](url)`，`yaml.safe_load()` 报 `ScannerError`。
**影响**：`generate_data.py` 读取失败，风格总数少算 1 个（156 vs 157）。
**教训**：
- YAML 文件里 **不能用** Markdown 语法，`![]()` 是非法 YAML
- 图片引用用注释：`# 配图: images/styles_previews/xxx.webp`
- 写完 YAML 先验证：`python3 -c "import yaml; yaml.safe_load(open('file.yaml'))"`
- **吸取 ✅ 已修复**

### 3. 🚨 2026-06-18: CSS/JS 路径引用错误
**问题**：根目录 `gallery.html` 引用 `gallery-runtime.js` 和 `gallery.css`，而 `styles/gallery.html`（旧版）引用不同路径。
**教训**：有两个 `gallery.html`！`gallery.html`（根目录）是当前版本，`styles/gallery.html` 是旧版残留。
**方案**：构建时 `build_gallery.py` 输出到根目录 `gallery.html`，`styles/gallery.html` 可考虑清理。

### 4. 🚨 发布前安全扫描
**问题**：曾向公开库提交包含敏感信息的文件。
**解决**：已加 `pre-push-security-scan.py`，每次 git push 前自动扫描 Token/密码/密钥等。
**教训**：**强制** — 每次 push 前必须扫。

### 5. 🚨 图片源仓库演变
**历史阶段**：
1. `malongan/images`（已归档，只读，URL 全部 404 ❌）
2. `malongan.github.io/images/`（已失效 ❌）
3. `malongan.github.io/style-source/images/styles_previews/` ✅ **当前唯一正确路径**

---

## 🗺️ 优化路线图（2026-07-03 审计更新）

> 基准 tag: `v0.7.0-before-opt`
> CSS 24KB + JS 43KB = **67KB 未压缩**

### ✅ 已完成（之前标记的已实现项）

| # | 项目 | 说明 | 完成时间 |
|---|------|------|---------|
| ✅ | **图片 `loading="lazy"`** | img 标签已加 `loading="lazy"` | 已实现 |
| ✅ | **JS 异步加载** | 已用 `<script defer>` | 已实现 |
| ✅ | **数据异步加载** | fetch('data/styles.json') | 已实现 |
| ✅ | **骨架屏 FOUC 防护** | 内联关键样式 | 已实现 |
| ✅ | **一键复制提示词** | Lightbox 有复制按钮 | 已实现 |
| ✅ | **支持搜索编号** | 搜索支持 code/number | 已实现 |

---

### P0 🔴 — 当前批次（已完成 ✅）

| # | 项目 | 说明 | 状态 |
|---|------|------|------|
| **P0-1** | **CSS/JS 压缩** | CSS 24KB→18KB，JS 43KB→29KB，合计 67KB→47KB ⬇️ 30% | ✅ **已完成** |
| **P0-2** | **渐进式图片加载（blur-up）** | 缩略图模糊背景占位 → 全尺寸渐入，168 张全部启用 | ✅ **已完成** |
| **P0-3** | **标签去重** | 合并 Flat/flat、Naive/naive、q版/Q版，清理 null 标签，881→878 | ✅ **已完成** |
| **P0-4** | **清理旧版 styles/gallery.html** | 删除 230KB 旧版残留 | ✅ **已完成** |

### P1 🟡 — 建议做

| # | 项目 | 说明 | 工作量 | 难度 |
|---|------|------|--------|------|
| **P1-1** | **WebP 回退 `<picture>`** | 兼容 Safari <14 / IE 等老旧浏览器 | 大 | ★★☆ |
| **P1-2** | **标签云重新设计** | 层级标签结构、标签搜索/过滤 | 大 | ★★★ |
| **P1-3** | **随机发现按钮** | 搜索栏附近加"🎲 随机"按钮 | 小 | ★☆☆ |

### P2 🔵 — 值得做

| # | 项目 | 说明 | 工作量 | 难度 |
|---|------|------|--------|------|
| **P2-1** | **CDN 加速（Cloudflare Pages）** | 迁移到 Cloudflare Pages，全球加速 | 大 | ★★☆ |
| **P2-2** | **统计/分析** | Umami / Plausible 自托管 | 小 | ★☆☆ |
| **P2-3** | **分享卡片功能** | 分享到 X/Twitter/微信等 | 中 | ★★☆ |
| **P2-4** | **缓存策略优化** | JS/CSS 长期缓存 + CDN 缓存头 | 小 | ★☆☆ |

### P3 ⚪ — 锦上添花

| # | 项目 | 说明 | 工作量 | 难度 |
|---|------|------|--------|------|
| **P3-1** | PWA / Service Worker | 离线缓存，可安装到桌面 | 大 | ★★★ |
| **P3-2** | 图片放大镜 | Lightbox 中鼠标悬停局部放大 | 中 | ★★☆ |
| **P3-3** | 风格对比功能 | 同时选中多个风格对比 | 大 | ★★★ |
| **P3-4** | 打印友好 CSS | `@media print` 优化打印排版 | 小 | ★☆☆ |
| **P3-5** | 键盘快捷键 | `S` 聚焦搜索、`F` 收藏筛选等 | 中 | ★★☆ |

---

## 🔧 构建与部署流程

```
styles/*.yml ──→ generate_data.py ──→ data/styles.json
                                           │
                              build_gallery.py（读取 gallery/src/ 源码）
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
              gallery.html           gallery.css          gallery-runtime.js
              （根目录）             （内联 CSS）          （编译后 JS）
                    │                      │                      │
                    └──────────────────────┴──────────────────────┘
                                           │
                                    git push → GitHub Pages
                                           │
                              https://malongan.github.io/style-source/gallery.html
```

### 本地更新命令
```bash
cd /Users/qiqi/.qwenpaw/workspaces/github-manager/style-source
python3 scripts/generate_data.py   # 从 yml 更新 styles.json
python3 scripts/build_gallery.py   # 构建 gallery.html + CSS + JS
```

---

## 📌 关键约定

1. **图片文件名格式**: `{style_id}_{8位hash}.webp`
2. **源仓库唯一**: `style-source/images/styles_previews/` 是唯一正确的图片存放位置
3. **新增图片用 `upload_preview.py`**: 自动哈希命名 + WebP 转换
4. **不要手动编辑 yml 中的图片 URL**: `generate_data.py` 会自动匹配本地文件
5. **收集提示词不要自动更新 Gallery**: 等用户明确说"更新页面"/"同步 Gallery"
6. **每次 push 前跑安全扫描**: `python3 scripts/pre-push-security-scan.py`
7. **有未提交修改时先 stash**: `git stash` → `git pull --ff-only` → `git stash pop`
