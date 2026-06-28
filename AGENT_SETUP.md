# Agent 自动配置指南 — style-source 仓库

> 任何 QwenPaw Agent 读取本文档后，可自动完成风格收集和提交所需的所有配置。
> 本文档按章节标题组织，Agent 可精准定位所需信息。

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

**无需额外 Token** — 所有内容（.md + 图片 + gallery页面）在同一仓库，SSH 密钥即可 push。

---

## 2. 目录结构

```
style-source/
├── styles/                  ← 风格 .yaml 源文件
│   ├── social_media/        ← 社交媒体分类
│   ├── brand_kv/            ← 品牌视觉
│   ├── e-commerce/          ← 电商
│   ├── science/             ← 科研专业
│   ├── print/               ← 印刷品
│   ├── ip_character/        ← IP/角色
│   ├── travel/              ← 旅行城市
│   ├── fashion/             ← 时尚美容
│   ├── creative/            ← 创意特殊
│   └── vigo_cookbook/       ← Vigo Cookbook
├── images/styles_previews/  ← 预览图（与 .yaml 同仓库版本管理）
├── data/styles.json         ← 风格数据（CI 自动生成）
├── gallery.html             ← 画廊页面（内联 CSS/JS）
├── scripts/                 ← 工具脚本
│   ├── validate_style.py    ← 单文件格式校验
│   ├── validate_all.py      ← 全量格式校验
│   ├── generate_data.py     ← 生成 data/styles.json
│   ├── build_gallery.py     ← 构建 gallery.html
│   ├── check_duplicate.py   ← 查重检测
│   └── upload_preview.py    ← 图片哈希命名处理
├── .github/workflows/       ← CI/CD
│   ├── on-push-styles.yml   ← PR 格式检查
│   └── on-merge-main.yml    ← 合并后验证
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

### 4.1 文件路径
```
styles/分类/风格名.yaml
```

### 4.2 文件名
全小写 snake_case，如 `inflatable_3d_flowers.yaml`，最长 60 字符。

### 4.3 必填字段（CI 会严格检查）

```markdown
# 中文展示名

**标签**：#标签1 #标签2 #标签3
**触发词**：关键词1、关键词2
**适用场景**：场景描述
**比例**：3:4
**来源**：@作者名
**链接**：https://原始链接

---

## 一句话理解

一句话概括，不超过 30 字。

---

## 核心特点

- **名称** — 详细描述

---

## 完整模板

```
原始提示词原文保留，{变量}用单花括号标记
```

---

## 变量使用指南

| KV套用时的变量 | 对应风格文件变量 | 说明 |
|---------------|-----------------|------|
| 画面-主体 | 主体 | 变量说明 |

---

## 参考配图

![描述](https://malongan.github.io/style-source/images/styles_previews/风格名_8位哈希值.jpg)

---

*来源：平台 - 作者名*
```

**注意**：`**来源链接**` 是可选的（CI 仅建议不报错），但 `**链接**` 必须填。

### 4.4 变量格式

| 位置 | 格式 | 示例 |
|------|------|------|
| 模板中 | `{变量}`（单花括号） | `{主体描述}` |
| 变量指南第二列 | `变量`（无花括号） | `主体描述` |

不要用 `{{变量}}`（双花括号），CI 不识别。

### 4.5 配图 URL

必须是 Pages URL：
```
https://malongan.github.io/style-source/images/styles_previews/风格名_8位哈希值.jpg
```

---

## 5. 收集流程

> ⚠️ 重要：Painter Agent 只负责生成内容（.md 文件 + 预览图），Git 操作交给 GitHub Manager。

### Step 1：克隆并拉取最新
```bash
git clone git@github.com:malongan/style-source.git
cd style-source
git checkout main && git pull
```

### Step 2：查重
```bash
python3 scripts/check_duplicate.py --url "来源链接"
python3 scripts/check_duplicate.py --name "建议风格名"
```

### Step 3：下载配图

**通用流程：**
```bash
curl -L -o /tmp/preview.jpg "图片URL"
```

**即梦特殊流程：**
```bash
# 1. 用 jimeng_extractor.py 提取 workId
# 2. 从 window._ROUTER_DATA 获取原图 URL：
#    路径: commonAttr.coverUrl（2048px 原图）
# 3. 用 curl 下载（必须加 Referer 头）：
curl -H "Referer: https://jimeng.jianying.com/" "coverUrl" -o /tmp/preview.webp
```

**压缩到 1000px：**
```bash
sips -Z 1000 /tmp/preview.webp --out /tmp/preview.jpg
```

### Step 4：计算哈希并保存到 style-source
```bash
HASH=$(python3 -c "import hashlib; print(hashlib.md5(open('/tmp/preview.jpg','rb').read()).hexdigest()[:8])")
cp /tmp/preview.jpg style-source/images/styles_previews/风格名_${HASH}.jpg
```

### Step 5：创建风格文件
按第 4 节模板创建 `.md` 文件到 `styles/分类/`。

### Step 6：通知 GitHub Manager
```python
chat_with_agent(
  to_agent="github-manager",
  text="新风格已就绪：styles/分类/风格名.yaml + 配图路径，请处理后续"
)
```

**不要自己 git push。** GitHub Manager 负责：生成数据 → 创建分支 → push → PR。

---

## 6. CI 检查清单

创建 PR 前本地先验证：

```bash
python3 scripts/validate_all.py           # 全量格式检查
python3 scripts/generate_data.py          # 生成 JSON 数据
python3 scripts/build_gallery.py          # 生成画廊页面
git diff --name-only data/styles.json gallery.html  # 确认生成文件已更新
```

PR 提交后 CI 自动运行 `on-push-styles.yml`，必须通过才能合并。

---

## 7. 分类判断

| 分类 | 目录 | 适用场景 |
|------|------|----------|
| 社交媒体 | `social_media` | 小红书、朋友圈、头像、Y2K |
| 品牌视觉 | `brand_kv` | 品牌KV、公益海报、杂志封面 |
| 电商 | `e-commerce` | 产品主图、电商海报、美食 |
| 科研专业 | `science` | 信息图、期刊封面、报告 |
| 印刷品 | `print` | 书籍封面、电影海报、浮世绘 |
| IP/角色 | `ip_character` | 吉祥物、Q版角色、3D头像 |
| 旅行城市 | `travel` | 城市海报、旅行拼贴 |
| 时尚美容 | `fashion` | 时尚大片、美妆海报 |
| 创意特殊 | `creative` | 融合、复古、手绘、实验性 |
| VigoCookbook | `vigo_cookbook` | Vigo Cookbook 来源 |

---

## 8. ❌ 禁止做的事

| 禁止 | 原因 |
|------|------|
| 不要直接推 main | 分支保护会拦截 |
| 不要手动修改 `_index.md` | CI 自动生成 |
| 不要手动修改 `_collection_log.md` | CI 自动维护 |
| 不要修改 `data/styles.json` | CI 自动生成 |
| 不要用 `{{变量}}`（双花括号） | CI 不识别这种格式 |
| 不要上传到旧 images 仓库 | 图片直接放 style-source 内 |

---

## 9. 脚本速查

| 脚本 | 用途 | 调用方式 |
|------|------|---------|
| `validate_style.py` | 校验单个文件 | `python3 scripts/validate_style.py 文件路径` |
| `validate_all.py` | 校验全部文件 | `python3 scripts/validate_all.py` |
| `check_duplicate.py` | 查重 | `--url URL` 或 `--name 名称` |
| `generate_data.py` | 生成 JSON 数据 | `python3 scripts/generate_data.py` |
| `build_gallery.py` | 构建画廊页面 | `python3 scripts/build_gallery.py` |
| `generate_index.py` | 生成索引 | `python3 scripts/generate_index.py` |
| `upload_preview.py` | 图片哈希命名处理 | `图片路径 风格名` |

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
即梦提取器有时把 9:16 输出为 16:9。**以页面实际显示为准**，打开即梦页面看图片下方的标注。
