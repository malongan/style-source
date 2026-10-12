# Agent 自动配置指南 — style-source 仓库

> 任何 Agent 读取本文档后，可自动完成风格收集和提交所需的所有配置。
> 本文档按章节标题组织，Agent 可精准定位所需信息。
>
> ⚠️ **收集提示词的完整流程不在这里**——见 `style-collection` 技能
> （技能规范文件 `style-collection/SKILL.md`，位于 agent 技能目录 `dsh-skills/skills/`）。本文只讲仓库侧的配置与规范。
>
> 本文档数据基线：**2026-10-12**（300 个风格 / 12 个分类 / 600 个 WebP）。数字改动后请同步，或用
> `ls styles/*/*.yaml | wc -l` 现场核对，不要照抄本文的硬编码数字。

---

## 1. 仓库信息

| 项目 | 值 |
|------|-----|
| 仓库 | `malongan/style-source` |
| 克隆地址 | `git@github.com:malongan/style-source.git`（SSH）|
| GitHub Pages | `https://malongan.github.io/style-source/` |
| 画廊 | `https://malongan.github.io/style-source/gallery.html` |
| 数据 JSON | `https://malongan.github.io/style-source/data/styles.json` |
| 预览图 | `https://malongan.github.io/style-source/images/styles_previews/` |

**无需额外 Token** — 所有内容（.yaml + 图片 + gallery页面）在同一仓库，SSH 密钥即可 push。

---

## 2. 目录结构

```
style-source/
├── styles/                  ← 风格 .yaml 源文件（12 个分类）
│   ├── social_media/        ← 社交媒体分类
│   ├── brand_kv/            ← 品牌视觉
│   ├── e-commerce/          ← 电商
│   ├── editorial/           ← 编辑排版
│   ├── fashion/             ← 时尚美容
│   ├── ip_character/        ← IP/角色
│   ├── print/               ← 印刷品
│   ├── science/             ← 科研专业
│   ├── travel/              ← 旅行城市
│   ├── typography/          ← 字体排版
│   ├── creative/            ← 创意特殊
│   └── vigo_cookbook/       ← Vigo Cookbook
├── images/styles_previews/  ← 预览图 {id}_{8位后缀}.webp + .thumb.webp（与 .yaml 同仓库版本管理）
├── data/styles.json         ← 风格数据（本地 generate_data.py 生成后提交，CI 校验一致性）
├── gallery.html/css/js      ← 画廊产物（本地 build_gallery.py 生成后提交）
├── styles/_index.md         ← 索引（generate_index.py 重算，勿手改）
├── scripts/                 ← 工具脚本（完整清单见第 9 节）
├── .github/workflows/       ← CI/CD（4 个 workflow，见第 6 节）
├── CONTRIBUTING.md          ← 人类协作指南
└── 404.html                 ← 自定义 404
```

---

## 3. 分支保护规则

| 规则 | 说明 |
|------|------|
| 非管理员 | 必须通过 PR + CI 检查（`Validate styles`）+ 1 人审核 |
| 管理员 | 可用 PAT 直推 main |
| CI 检查 | 格式验证 + 查重 + 图片可达性 |

**禁止直接推 main** — 非管理员必须走分支 → PR → 审核 → 合并流程。

---

## 4. 风格文件规范

> ⚠️ **本仓库 2026-06-28 起已全面 YAML 化**。旧版本这里教的是 Markdown 模板
> （`**标签**：` / `![描述](...)`），已彻底废弃：`![]()` 是**非法 YAML**，会让 `yaml.safe_load()`
> 抛 `ScannerError` 并把该风格整条跳过（2026-06-29 事故）。字段级模板与更多要点见 `CONTRIBUTING.md`。

### 4.1 文件路径
```
styles/{分类}/{风格id}.yaml        # 必须是 .yaml（.yml 会被提示标准化），必须在分类子目录
```

### 4.2 文件名
全小写 snake_case，如 `inflatable_3d_flowers.yaml`，最长 60 字符，只能含字母数字下划线。

### 4.3 必填字段（`scripts/validate_all.py` 会检查）

```yaml
# {中文名}

id: inflatable_3d_flowers        # 与文件名一致
name: "{中文名}"
category: creative               # 12 个分类之一，见 references/categories.md

tags:                            # 3-6 个高信息量标签
  - {标签1}
  - {标签2}

triggers:                        # 中文别名
  - {触发词1}

features:                        # 3-5 条
  - "**{特点1}** — {详细描述}"

scene: "{适用场景}"
ratio: "3:4"
summary: "{一句话理解}"

prompt: |                        # 必填，≥80 字符，详情页「复制提示词」用它
  {完整生图 Prompt，含 {变量} 占位符}
  不要水印，不要真实Logo，不要电商广告感。

variables:                       # 标准形态，[{kv_var, style_var}]，两键必填
  - kv_var: 画面-主体
    style_var: "{主体描述}"
    desc: "示例值"

source_url: "{原始链接}"          # 无链接时必须填 source_author，两者不能同时为空
source_author: "@{作者名}"

# 配图: images/styles_previews/inflatable_3d_flowers_{8位后缀}.webp
```

**注意**：
- `source_url` / `source_author` **不能同时为空**（`validate_style.py` 报 error）。
- `yml` 里的 `code` 字段无效——编号由 `generate_data.py` 重算并存入 `data/style_numbers.json`。
- 不要在 yaml 里写图片 URL：配图按 `{id}_{8位后缀}.webp` **整段锚定**从 `images/styles_previews/` 解析。
- CI 闸门：`validate_all.py --strict` **有 error 即失败**（2026-10-12 前它恒 exit 0，闸门是空的）；只想看报告用 `--no-strict`。

### 4.4 变量格式

| 位置 | 格式 | 示例 |
|------|------|------|
| `prompt` 内 | `{变量}`（单花括号） | `{主体描述}` |
| `variables[].kv_var` | KV 变量名（中文标签或上游英文占位符名） | `画面-主体` / `` `SUBJECT` `` |
| `variables[].style_var` | 模板里的替换值 | `{主体描述}` / `main person` |

不要用 `{{变量}}`（双花括号）。详见技能侧 `references/variables.md`。

### 4.5 配图命名

```
images/styles_previews/{风格id}_{8位后缀}.webp        ← 全尺寸（最长边 1000px）
images/styles_previews/{风格id}_{8位后缀}.thumb.webp  ← 缩略图（400px，必需）
```

8 位后缀 = md5(原图)[:8]，或 X/Twitter media id。**两个文件都要有**，缺缩略图封面会 404。
用 `python3 scripts/convert_to_webp.py --input <图> --style-id <id> --output images/styles_previews/` 一次生成两个。

---

## 5. 收集流程

> **完整流程已技能化，共 10 步（Step 1 抓取 / Step 1.5 机械核对归属 / Step 2–10；Step 1.5 不读图识别）**：
> 技能目录下的 `style-collection/SKILL.md`（`dsh-skills/skills/style-collection/`）
> （`~/.agents/skills/style-collection` 是指向它的软链；**不要引用任何工作区内的同名副本**）
>
> 本节只保留角色边界。旧版本这里的 6 步流程（含已删除的 `jimeng_extractor.py`）已废止。

> ⚠️ 重要：Painter Agent 只负责生成内容（`.yaml` 文件 + 原始配图），Git 操作交给 GitHub Manager。

### 角色分工

```
用户给链接
   ↓
GitHub Manager（style-collection 技能）
   Step 1    新闻助手抓取正文 + 下载原始配图到 /tmp/
   Step 1.5  图片归属机械核对（按 alt/DOM 顺序；对不上问用户，不读图）
   Step 2–3  语义转化 + 分类判断
   Step 4    convert_to_webp.py 转 WebP（全尺寸 + 缩略图）
   Step 5    写 styles/{分类}/{id}.yaml
   Step 6    generate_index.py 重算索引
   Step 7    validate_style.py → generate_data.py → build_gallery.py
   Step 8    分支 → 安全检查 → commit → push
   Step 9    gh pr create
   Step 10   squash 合并 → 拉取 → 验证线上 Pages 200
```

**不要自己 git push 到 main。** 一切走 PR + squash 合并（分支保护要求）。

### 触发方式

直接说「收集提示词 + 链接」即可。说「收集全部提示词」时才逐张处理页面所有图片，否则只处理第一张。

---

## 6. CI 检查清单

创建 PR 前本地先验证：

```bash
python3 scripts/validate_all.py --strict               # 全量格式检查（有 error 即失败）
python3 scripts/generate_data.py                       # 生成 JSON 数据
python3 scripts/build_gallery.py                       # 生成画廊页面 + CSS/JS
python3 scripts/generate_index.py                      # 重算索引
python3 scripts/check_style_previews.py --strict       # 配图完整性（缩略图/孤儿/串号）
# 发布前安全扫描由 .git/hooks/pre-push 自动调用（脚本在 agent 侧 scripts/github-manager/）
bash .git/hooks/pre-push
git status --short                                      # 确认生成物都已 git add
```

| Workflow | 触发 | 检查内容 |
|----------|------|---------|
| `on-push-styles.yml` | PR（`styles/**`） | `validate_all.py --strict` + `check_duplicate.py --pr-mode` + `--check-images --no-strict` |
| `on-merge-main.yml` | PR 合并到 main **以及直推 main** | `validate_all.py --strict` + 重算并断言 `styles.json` / `gallery.html` / `_index.md` 零 diff（含未跟踪索引文件）+ `check_style_previews.py --strict` |
| `check-images.yml` | 图片/数据变动 + 每日 3 点 | 预览图 URL 可达性 |
| `manual-deploy.yml` | 手动触发 | 全量验证 + 一致性 |

> ⚠️ CI **不会**替你生成文件回 main——生成物必须由你在 PR 分支跑完脚本并提交。

---

## 7. 分类判断

共 **12** 个分类（权威清单：`scripts/validate_style.py` 的 `VALID_CATEGORIES`）：

| 分类 | 目录 | 适用场景 |
|------|------|----------|
| 社交媒体 | `social_media` | 小红书、朋友圈、头像、Y2K |
| 品牌视觉 | `brand_kv` | 品牌KV、公益海报、杂志封面 |
| 电商 | `e-commerce` | 产品主图、电商海报、美食 |
| 编辑排版 | `editorial` | 编辑风海报、杂志封面感、字体实验排版 |
| 时尚美容 | `fashion` | 时尚大片、美妆海报 |
| IP/角色 | `ip_character` | 吉祥物、Q版角色、3D头像 |
| 印刷品 | `print` | 书籍封面、电影海报、浮世绘 |
| 科研专业 | `science` | 信息图、期刊封面、报告 |
| 旅行城市 | `travel` | 城市海报、旅行拼贴 |
| 字体排版 | `typography` | 文字为主的标题设计 |
| 创意特殊 | `creative` | 融合、复古、手绘、实验性 |
| VigoCookbook | `vigo_cookbook` | Vigo Cookbook 来源 |

默认：不确定时选 `creative/`。

---

## 8. ❌ 禁止做的事

| 禁止 | 原因 |
|------|------|
| 不要直接推 main | 分支保护会拦截，必须走 PR |
| 不要手动修改 `_index.md` | 由 `generate_index.py` 从磁盘重算；`on-merge-main.yml` 会断言零 diff |
| 不要手动修改 `_collection_log.md` | 由 `update_collection_log.py` 维护 |
| 不要**手写** `data/styles.json` | 必须由 `generate_data.py` 生成，并**在本 PR 里提交**（CI 校验一致性，不替你在 CI 里生成回 main） |
| 不要手动改 `gallery.html/css/js` | 由 `build_gallery.py` 生成，同样必须提交 |
| 不要用 `{{变量}}`（双花括号） | 不识别，变量用单花括号 |
| 不要上传到旧 images 仓库 | 图片直接放 style-source 内（`malongan/images` 已归档、URL 全 404） |
| 不要在 yaml 里写图片 URL | 配图按 `{id}_{8位后缀}` 整段锚定从 `images/` 解析；旧域名一律无效 |
| 不要用**前缀**模糊匹配找配图 | 2026-10-10 串号事故根因（`doodle_style` 命中 `doodle_style_poster_*`） |

---

## 9. 脚本速查

| 脚本 | 用途 | 调用方式 |
|------|------|---------|
| `validate_style.py` | 校验单个文件（有 error 退出码 1） | `python3 scripts/validate_style.py 文件路径` |
| `validate_all.py` | 校验全部文件（**有 error exit 1**） | `python3 scripts/validate_all.py --strict`（只报告用 `--no-strict`） |
| `--check-images` | 附加：预览图 URL 可达性（只报不失败） | `python3 scripts/validate_all.py --check-images --no-strict` |
| `check_duplicate.py` | 查重 | `--url URL` / `--name 名称` / `--pr-mode` |
| `generate_data.py` | 生成 `data/styles.json` + `styles_list.txt` | `python3 scripts/generate_data.py` |
| `build_gallery.py` | 构建 `gallery.html` + `gallery.css` + `gallery-runtime.js` | `python3 scripts/build_gallery.py` |
| `generate_index.py` | 重算 `styles/_index.md` + 各分类索引 | `python3 scripts/generate_index.py` |
| `check_style_previews.py` | 配图完整性（缩略图/孤儿/**串号**）；CI 用 `--strict` | `python3 scripts/check_style_previews.py --strict` |
| `check_image_urls.py` | 预览图 URL 可达性（日检） | `python3 scripts/check_image_urls.py` |
| `convert_to_webp.py` | 原图 → WebP 全尺寸 + 缩略图 | `--input 图 --style-id id --output images/styles_previews/` |
| `upload_preview.py` | 旧脚本：图片哈希命名处理 | `图片路径 风格名` |
| `md_to_yaml.py` | 旧脚本：Markdown → YAML 迁移 | `python3 scripts/md_to_yaml.py` |
| `fetch_twitter.py` / `run_fetch.py` | X/Twitter 采集入口 | `python3 scripts/run_fetch.py` |
| `update_collection_log.py` | 更新收集日志 | `python3 scripts/update_collection_log.py` |
| `deploy_gallery.py` | 部署画廊 | `python3 scripts/deploy_gallery.py` |
| `glossary.yml` | 词汇表数据 | 非脚本 |
| 安全检查 | 推送前扫描（**不在本仓库 scripts/**，在 agent 侧 `scripts/github-manager/`） | 推送时由 `.git/hooks/pre-push` 自动调用 |

> 依赖：`pyyaml`、`Pillow`。用 uv 可直接注入：`uv run --with pyyaml --with pillow python3 scripts/<脚本>.py`

---

## 10. 常见报错

### git push 失败（non-fast-forward）
```bash
git pull --rebase origin main
git push origin 分支名 --force-with-lease
```

### CI 校验失败
```bash
python3 scripts/validate_style.py styles/xxx/文件.yaml
# 根据报错修改 → git add → git commit --amend → git push --force
```

### 比例错误
以**页面实际显示为准**（即梦等平台页面图片下方的标注），不要依赖任何提取脚本的推断。
