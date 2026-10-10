# 风格库 features/summary 中文化方案

> 编制日期：2026-10-10
> 状态：**待用户确认**（第 6 节有 5 个决策点，未确认前不执行）
> 背景：2026-10-10 曾执行一次机器翻译，损坏 71 个风格，已通过 PR #178 回退。本方案是重做版。

---

## 1. 目标

把风格库（300 个风格）中**混排/纯英文的展示文案**中文化，使 Gallery 详情页（lightbox）呈现为中文。

**明确不做的事**（本次范围外）：

- 不改 `prompt` 字段（生图用，翻译会破坏出图效果）
- 不改 `ratio` / `category` / `code` 等结构化字段
- 不改任何图片资源

---

## 2. 现状调研（真实数据，非估算）

### 2.1 数据规模

| 项目 | 数量 |
|:--|--:|
| 风格总数 | 300 |
| features 总条数 | 1,568（dict 结构 817 / 字符串结构 751） |
| 已归零（无待译内容） | 129 个文件 |
| summary 总条数 | 300 |

> `generate_data.py:164-172` 会把 dict 结构 `{title, desc}` 归一化成字符串 `**title** — desc` 写入 `data/styles.json`，前端只读产物。
> 因此**翻译必须改 `styles/**/*.yaml` 源文件**，改 `data/` 会被下次生成覆盖。

### 2.2 待译内容分三类（关键）

| 类别 | 定义 | features | summary | 合计 | 正确方法 |
|:--|:--|--:|--:|--:|:--|
| **A 术语混排** | 中文为主，夹少量英文术语<br>例：`**编辑级Typography** — 标题…` | 120 | 39 | **159** | 术语表精确替换 |
| **B 纯英文/英文为主** | 整段英文需翻译<br>例：`Place PRODUCT_OR_PROP in LOCATION as the restrained hero object.` | 426 | 65 | **491** | LLM 逐条翻译 |
| **C 非展示字段** | `variables`(911) / `prompt`(278) — 前端 0 引用 | — | — | (911) | 默认不动 |

**待译英文净字符量：约 58,000 字符。**

### 2.3 B 类工作量高度集中

- 纯英文内容分布在 **64 个文件**，共 384 条
- 其中 **`vigo_cookbook` 目录占 282 条（73%）**，来自英文 Prompt Cookbook 导入的 51 个风格
- 每个 vigo 风格的 features 恰好 6 条，本质是英文 prompt 的切片
- 例：`vigo_analog_editorial_poster` 的 6 条 features + summary 全英文

**这是最大的范围决策点** —— 见 6.1。

### 2.4 其他含英文的展示字段

| 字段 | 含非白名单英文 | 前端是否展示 | 备注 |
|:--|--:|:--|:--|
| `features` | 546 | ✅ lightbox 列表 | 主战场 |
| `summary` | 104 | ✅ lightbox | 主战场 |
| `name` | 92 | ✅ lightbox 标题 + 卡片标题 | vigo 的 name 全是英文 |
| `triggers` | 165 | ✅ lightbox | |
| `tags` | 140 | ✅ 侧栏筛选 + URL 参数 | **改动词条会破坏已分享链接** |
| `variables` | 911 | ❌ 不展示 | vigo 的变量说明 |
| `prompt` | 278 | ❌ 不展示 | 生图用，禁改 |

### 2.5 术语表规模

- 中文混排中出现的英文术语：**132 个**（`Image`/`Logo`/`Typography`/`Editorial`/`campaign`…）
- 纯英文段落的不同词形：1,579 个（出现 ≥5 次的 411 个，仅出现 1 次的 641 个）
- 结论：**A 类可用术语表覆盖；B 类必须靠翻译引擎**（逐词替换不可能覆盖 1,579 个词形）

---

## 3. 上次失败复盘（方案为什么不同）

### 3.1 事实

2026-10-10 提交 `e48280b`，later 回退（`af3e13a`）：

| 原文 | 损坏结果 |
|:--|:--|
| `Large white extruded block letters remain the main background architecture.` | `Large 白 extruded 方块字 re主要 the 主要 背景 建筑.` |
| `…angled diagonally and cropped with impact.` | `…angled 对角线ly and 裁切 with impact.` |

### 3.2 三条根因

1. **工具错配** —— 用 `str.replace()` 逐词替换去做整段翻译。只能处理 A 类的方法，被硬套到 B 类
2. **无词边界** —— `remain` 里的 `main`、`diagonally` 里的 `diagonal` 被命中，单词拦腰截断
3. **验证用计数指标** —— 只看「206/300 文件已修改」「100% 含中文」，而**损坏的内容同样满足「含中文」**

### 3.3 本方案的对应改进

| 上次问题 | 本次对策 |
|:--|:--|
| 工具错配 | **分轨**：A 类用术语表（新增），B 类用 LLM 逐条翻译 |
| 无词边界 | 术语表全部 `re.sub(r'\b…\b')`，**长词优先排序** |
| 计数指标验证 | **抽样人工验收**：每批打印 5 条完整内容，逐条看语义 |
| 直接在真实库反复试错 | 每批独立 commit + `/tmp/` 脚本 + 禁用 `git add -A` |

---

## 4. 方案架构：三轨分流

```
待译语料
   │
   ├── 轨道 A：术语混排（159 条）
   │      → glossary.yml 术语表 + re.sub(\b...\b)
   │      → 长词优先，避免子串命中
   │      → 脚本可批量、可复现、零外部依赖
   │
   ├── 轨道 B：纯英文/英文为主（491 条）
   │      → 由我（LLM）逐条翻译
   │      → 保留 {SUBJECT} / PRODUCT_OR_PROP / MAIN_TEXT 等占位符
   │      → 按术语表统一译名
   │      → 分批写入，每批独立 commit
   │
   └── 轨道 C：不处理
          → prompt（生图用）
          → variables（前端不展示）
          → 技术白名单（WebP/CMYK/3D/Nike/Didone…）
```

### 4.1 为什么轨道 B 用 LLM 而不是翻译引擎

**实测结论（2026-10-10）：**

| 引擎 | 状态 |
|:--|:--|
| `deep_translator` (GoogleTranslator) | 已安装，端点返回 **HTTP 429** |
| MyMemory (deep_translator) | 1.5s/条，491 条需 12 分钟，历史上反复超时 |
| `argostranslate` | 未安装 |
| `translate` / `googletrans` | 未安装 |
| LLM API Key（OPENAI / DASHSCOPE / DEEPL / 百度 / 腾讯…） | **均未设置** |

**⇒ 唯一可用且高质量的翻译引擎是我自己。**

除可用性外，LLM 在这个任务上还有三个机翻无法替代的优势：

1. **术语一致性** —— `Editorial`/`Typography`/`Serif` 在同一译法下贯穿 300 个风格
2. **上下文感知** —— 机翻会把 `Editorial` 译成「社论」、`Meme` 译成「模因」，此处应为「编辑设计」「迷因/梗」
3. **占位符保全** —— `PRODUCT_OR_PROP`、`{MAIN_TEXT}`、`BACKGROUND_ELEMENTS` 必须原样保留（机翻会拆碎它们）

---

## 5. 分批实施计划

### 5.1 批次划分（按目录/前缀，便于独立回退）

| 批次 | 范围 | 条数 | 轨道 |
|:--|:--|--:|:--|
| P0 | 建立 `glossary.yml` + 校验脚本 | 0 | 准备 |
| P1 | vigo_cookbook 前 17 个风格 | ~102 | B |
| P2 | vigo_cookbook 中 17 个风格 | ~102 | B |
| P3 | vigo_cookbook 后 17 个风格 | ~78 | B |
| P4 | 非 vigo 的纯英文/英文为主（13 个文件） | ~107 | B |
| P5 | A 类术语混排 features（120 条） | 120 | A |
| P6 | A 类术语混排 summary（39 条） | 39 | A |
| P7 | （可选）name / triggers / tags | 依决策 | — |
| P8 | 全库残留扫描 + 术语一致性校验 + 发布 | — | 验收 |

> **P1–P3 是范围决策点**：若确认 vigo 整体翻译，则执行；若跳过，工作量从 491 条降至 209 条。

### 5.2 每批的标准流程

```
1. git checkout -b translate/<批次名>   （或当前分支 + 记录起点 commit）
2. 脚本写到 /tmp/ ，不进仓库
3. 生成译文 → 写入 styles/**/*.yaml（原地改，保持 dict/str 原结构）
4. 抽样 5 条完整内容打印 → 我逐条人工核对语义
5. python3 scripts/generate_data.py && python3 scripts/build_gallery.py
6. python3 scripts/pre-push-security-scan.py
7. 显式列出文件路径 git add（禁 -A）→ commit
8. 记录本批 diff 统计，进入下一批
```

---

## 6. 决策记录

### 6.0 ✅ 已定（2026-10-10 用户确认）

> 用户指示：**「只用翻译前端那些样式说明，提示词本身不用翻译」**

**前端展示契约**（取自 `gallery.html` 实际 DOM）：

| 前端元素 | 页面小节标题 | 源字段 | 待译 | 本次范围 |
|:--|:--|:--|--:|:--|
| `lightbox-summary` | 💡 一句话理解 | `summary` | 104 | ✅ 翻 |
| `lightbox-features` | ✨ 核心特点 | `features` | 546 | ✅ 翻 |
| `lightbox-triggers` | 🎯 触发词 | `triggers` | 165 | ⏳ 待确认 |
| `lightbox-tags` | 🏷️ 标签 | `tags` | 140 | ⏳ 待确认（见 6.5） |
| `lightbox-title` / `.card-title` | — | `name` | 92 | ⏳ 待确认 |
| `.lightbox-copy-btn`（**仅按钮，不显示正文**） | — | `prompt` | 278 | ❌ **不翻** |
| **无任何前端引用**（`gallery-runtime.js` grep 0 处） | — | `variables` | 911 | ❌ **不翻** |

**已定的两条：**

1. **`prompt` 不翻** —— 前端仅以「📋 复制提示词」按钮形式提供，复制内容是给生图用的，翻译会破坏出图效果
2. **`variables` 不翻** —— 前端零引用，翻译后页面无任何视觉变化

**核减效果**：排除 prompt(278) + variables(911) 后，不再需要处理 1,189 条非展示内容。

---

### 6.1 ⭐ vigo_cookbook 的 51 个风格要不要翻？

| 选项 | 影响 |
|:--|:--|
| **A. 翻** | 工作量 491 条（+73%），vigo 风格在 Gallery 上完全中文化 |
| **B. 跳过** | 工作量降至 209 条；vigo 的 summary/features 保持英文 |
| **C. 只翻 summary** | 每风格 1 条，共 51 条；卡片/详情页简介中文，features 留英文 |

> 注意：vigo 的英文 features 是「英文 prompt 的切片」（`Place PRODUCT_OR_PROP in LOCATION…`），
> 翻译后中文读者的可读性大幅提升，但它和下方 `prompt` 字段的英文不再字面对应。

### 6.2 术语策略：完全中文化 vs 保留英文术语

| 选项 | 说明 | 示例 |
|:--|:--|:--|
| **A. 完全中文化** | 所有术语译中文 | `Typography` → 字体排版 / `Editorial` → 编辑设计 / `Serif` → 衬线体 |
| **B. 中文为主 + 保留通用术语**（设计圈习惯） | 保留辨识度高的英文 | `Typography` 保留 / `Editorial` 保留 / `Meme` → 迷因 / `Risograph` → 孔版印刷 |
| **C. 中文 + 英文括注** | 首次出现括注 | 排版（Typography） |

> 影响 132 个术语、约 1,000+ 处替换。**这个决策定了才能写术语表。**

### 6.3 `name` 字段（92 条）要翻吗？

例：`Soft Analog Future Editorial Poster` → `柔和模拟未来编辑设计海报`

- 翻：卡片标题 + lightbox 标题全中文
- 不翻：标题保留英文原名（便于对照英文 prompt）

### 6.4 `variables` 要翻吗？（911 条，前端不展示）

- vigo 的变量说明全是英文（`main person, field, discipline, audience…`）
- 前端 `gallery-runtime.js` 中 **0 处** 引用 variables ⇒ 翻了对 Gallery 无视觉效果
- 但它是**给人生图时填变量用的说明**，翻成中文对使用者（你）有实际价值
- 建议：**单独作为第二批任务**，不与 features/summary 混做

### 6.5 `tags`（140 条）要翻吗？

- tags 参与**侧栏标签筛选**，且作为 URL 查询参数（`?tag=xxx`）
- 改动词条会让**已分享的筛选链接失效**
- tags 有 3 种形态：技术标签（`3d`/`webp`）、分类标签（`editorial`）、风格描述词（`oversized`）
- 建议：**不改**，或只改风格描述词且同步更新 tag 白名单

---

## 7. 验证方案（直接针对上次教训）

### 7.1 五道校验（每批执行）

| # | 校验 | 方法 | 通过标准 |
|:--|:--|:--|:--|
| 1 | **语义人工验收** | 随机抽 5 条，打印 `原文 → 译文` 完整内容 | 我逐条确认语义正确，**不看统计数字** |
| 2 | **残留英文扫描** | 扫描非白名单英文词 | 目标批次内归零 |
| 3 | **占位符保全** | 统计 `[A-Z][A-Z_]{3,}` token 前后数量 | 数量完全一致 |
| 4 | **结构契约** | 校验 dict/str 结构与翻译前一致 | 0 处结构变化 |
| 5 | **无截断/无替换污染** | 检测 `re主要` / `对角线ly` 类模式 | 0 处 |

### 7.2 全库终检（P8）

```bash
# 结构一致性：翻译前后 features 的 dict/str 分布必须一致
#   翻译前：dict 文件 154 / str 文件 146  → 翻译后必须相同

# 术语一致性：同一英文术语在 300 个风格中的译法必须唯一
#   扫描 glossary 中每个词的全部出现位置的译文，人工复核

# 产物与线上一致性
python3 -c "import json; d=json.load(open('data/styles.json')); print(len(d['styles']))"
```

### 7.3 明确禁止的验证方式

- ❌ 「N/N 文件已修改」这类计数结论
- ❌ 「100% 含中文」这类覆盖率结论
- ❌ 只看 diff 行数不看内容

---

## 8. 风险控制与回退

| 风险 | 对策 |
|:--|:--|
| 译文质量不达标 | 每批独立 commit，单批可 `git revert` |
| 术语译法不统一 | 先定术语表（P0），再翻译；P8 做一致性校验 |
| 占位符被破坏 | 校验 #3 强制拦截 |
| 误改无关文件 | **禁用 `git add -A`**，显式列路径 |
| 临时脚本入库 | 脚本一律 `/tmp/` |
| 产物与源不一致 | 每批跑 `generate_data.py` + `build_gallery.py`（产物在 .gitignore？需确认提交策略） |
| 中途要放弃 | `git checkout <干净commit> -- styles/ data/` + `git diff <干净commit> -- styles/` 验证 0 差异 |

**干净回退基线：`af3e13a`（即当前 HEAD，回退后的干净状态）**

---

## 9. 附录 A：术语表草案（前 40 高优先）

> 待 6.2 决策后定稿。此处按「选项 B：中文为主 + 保留通用术语」预排。

| 英文 | 频次 | 建议译法 |
|:--|--:|:--|
| Typography | 6+ | 排版 / 保留 |
| Editorial | 5+ | 编辑设计 |
| campaign | 5 | 营销企划 |
| Logo | 6 | 标识 |
| Image | 6 | 图像 |
| grid | 2+ | 网格 |
| Serif | 2+ | 衬线体 |
| Didone | 2 | 迪多尼体（保留） |
| Grotesk | 1+ | 怪诞体 |
| Condensed | 1+ | 窄体 |
| Oversized | 2+ | 超大号 |
| Royal Blue | 2 | 宝蓝 |
| Meme | 2 | 迷因 |
| Risograph | 2 | 孔版印刷 |
| screen-print | 2 | 丝网印刷 |
| Nouveau | 2 | 新艺术 |
| Deco | 2 | 装饰艺术 |
| Grayscale | 2 | 灰度 |
| Hyper-real | 2 | 超写实 |
| Pixar | 4 | 皮克斯 |
| Kodak | 2 | 柯达 |
| Portra | 2 | 柯达人像（胶片） |
| bokeh | 1 | 背景虚化 |
| Chibi | 1 | Q 版 |
| mood | 1 | 氛围 |
| pastel | 1 | 粉彩 |
| noir | 1 | 黑色电影感 |
| matte | — | 哑光 |
| negative space | — | 负空间 / 留白 |
| halftone | — | 半色调 |
| ransom-zine | — | 拼贴勒索信风 |
| fisheye | — | 鱼眼 |
| HUD | — | 平视显示界面 |
| macro | — | 微距 |
| still life | — | 静物 |
| artisanal / handmade | 1 | 手工感 |
| print-on-demand | — | 按需印刷 |

> 完整 132 词表在 P0 阶段产出。

---

## 10. 附录 B：样本翻译演示（轨道 B 实测）

以下为我（LLM）对真实条目的翻译，供质量判断：

**样本 1** — `vigo_analog_editorial_poster.summary`

- 原文：`A quiet analog-future editorial poster style using warm cream paper, oversized black neo-grotesk typography, strict grid rules, retro technology still life, pale-blue translucent interface panels, botanical foreground accents, and tiny bilingual information design.`
- 译文：`安静的模拟未来编辑设计海报风格：暖米色纸张、超大号黑色新怪诞体排版、严谨的网格规则、复古科技静物、淡蓝色半透明界面面板、植物前景点缀，以及微小的双语信息设计。`

**样本 2** — `vigo_analog_editorial_poster.features[1]`

- 原文：`Place PRODUCT_OR_PROP in LOCATION as the restrained hero object.`
- 译文：`将 PRODUCT_OR_PROP 置于 LOCATION，作为克制的视觉主体。`
- ✅ 占位符 `PRODUCT_OR_PROP` / `LOCATION` 原样保留

**样本 3** — `vigo_analog_editorial_poster.features[4]`

- 原文：`Visual treatment: warm cream paper background, strict grid layout, thin rules, soft daylight, tactile matte materials, gentle paper grain, pale-blue translucent interface panel, botanical foreground accents, and quiet negative space.`
- 译文：`视觉处理：暖米色纸张背景，严谨的网格布局，细线分隔，柔和日光，触感哑光材质，细腻纸张颗粒，淡蓝色半透明界面面板，植物前景点缀，以及安静的留白。`

**样本 4** — 轨道 A 类型（`japanese_museum_editorial_poster`）

- 原文：`**大型 Typography** — 超大型汉字/日文/高对比 Serif，纵排/错位/切边与主视觉穿插`
- 译文：`**大型排版** — 超大型汉字/日文/高对比衬线体，纵排/错位/切边与主视觉穿插`

**样本 5** — 轨道 A 类型（`east_asian_enclosing_exhibition_poster`）

- 原文：`英文标题用 Grotesk/Condensed Sans，形成大字结构、中字主题、小字信息`
- 译文：`英文标题用怪诞体/窄体无衬线，形成大字结构、中字主题、小字信息`

**样本 6** — 需要判断的边界案例

- 原文：`**Vogue/Harper's Bazaar 风格** — 优雅高端时尚感，三分侧面人像`
- 译文：`**《Vogue》/《Harper's Bazaar》风格** — 优雅高端时尚感，三分侧面人像`
- ✅ 品牌名保留原文，只加书名号

---

## 11. 下一步

### 已定 ✅

- `prompt`（278 条）**不翻** —— 生图用
- `variables`（911 条）**不翻** —— 前端零引用
- 范围限定为**前端可见的样式说明文字**

### 仍待确认 ⏳

1. ❓ **术语策略**（6.2）—— **这是唯一阻塞项**，定了才能写术语表
   - 完全中文化 / 保留通用英文术语 / 中文+英文括注
2. ❓ **vigo_cookbook**（282 条，占 73% 工作量）—— 翻 / 跳过 / 只翻 summary？
   - 注：按其 summary/features 在前端可见的事实，按「只翻前端说明」的规则它**在范围内**
3. ❓ **`name`**（92 条）—— 翻 / 不翻？例：`Soft Analog Future Editorial Poster`
4. ❓ **`triggers`**（165 条，前端「🎯 触发词」小节）—— 翻 / 不翻？
5. ❓ **`tags`**（140 条）—— ⚠️ 改动词条会让已分享的 `?tag=xxx` 筛选链接失效，建议不改

**确认后我按 P0 → P1 … 逐批推进，每批交付后向你展示抽样验收结果。**

### 11.1 术语表存放位置（已实测确认）

**结论：术语表放 `scripts/glossary.yml`，不放进 `styles/`。**

实测 `scripts/generate_data.py` 的扫描逻辑：

| 位置 | 脚本行为 | 能否放术语表 |
|:--|:--|:--|
| `styles/` **根目录** | `generate_data.py:219-224` 只判断 `.yaml`/`.yml` 后缀，**不跳过 `_` 前缀**，会打印「⚠️ 发现错放的风格文件」 | ❌ 会报错 |
| `styles/<子目录>/` | `generate_data.py:227-233` 有 `entry.startswith('_')` 跳过（目录级）和 `f.startswith('_')` 跳过（文件级） | ⚠️ 可用但语义奇怪 |
| **`scripts/glossary.yml`** | 不在 `STYLES_DIR` 扫描范围内 | ✅ **推荐** |

术语表属于工具链资产（供翻译脚本读取），`scripts/` 是它正确的归属，无需修改 `generate_data.py`。

### 11.2 无需改动的既有机制

`generate_data.py` 已内置的两层 `_` 前缀保护，本次沿用即可，不引入新约定。
