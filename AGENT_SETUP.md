# Agent 自动配置指南 — 风格收集助手

> 任何 QwenPaw Agent 读取本文档后，可自动完成风格收集所需的所有配置。
> 文档结构固定，Agent 可按章节标题精准读取配置项。

---

## 1. Agent 身份

| 配置项 | 值 |
|--------|-----|
| Agent ID | `style-collector`（建议） |
| 职责 | 从推文/即梦/meigen 收集提示词，创建风格文件，提 PR |

---

## 2. 仓库信息

| 仓库 | 地址 | 权限需求 |
|------|------|---------|
| **源仓库** | `git@github.com:malongan/style-source.git` | 读写（提交代码） |
| **图片仓库** | `git@github.com:malongan/images.git` | 写入（上传配图） |
| **画廊仓库** | `git@github.com:malongan/style-gallery.git` | 只读，不要修改 |

---

## 3. 环境准备

### 3.1 Git 配置
```bash
# ★ 必须使用 SSH 方式克隆（git push 不需要 Token，依赖 SSH 密钥）
git clone git@github.com:malongan/style-source.git
cd style-source

# 确保 SSH 密钥已配置：
ssh -T git@github.com
# 检查退出码（0 = 成功，非 0 = 失败）
if [ $? -ne 0 ]; then
    echo "❌ SSH 密钥未配置或无法连接 GitHub，请先配置 SSH key"
    echo "参考：https://docs.github.com/zh/authentication/connecting-to-github-with-ssh"
    exit 1
fi
echo "✅ SSH 认证成功"
```

### 3.2 Token 配置
```bash
# 只需要一个 Token（仅用于上传图片到 images 仓库）
export IMAGES_TOKEN="ghp_yyy"    # images: Contents write

# git push 走 SSH 密钥，不需要 Token
# 仅 upload_preview.py 需要 IMAGES_TOKEN
```

### 3.3 Python 环境
```bash
# 仅需 Python 3 标准库，无第三方依赖
python3 --version  # ≥ 3.8
```

---

## 4. 收集流程（Agent 执行步骤）

### Step 1：拉取最新
```bash
git checkout main && git pull
```

### Step 2：查重
```bash
python3 scripts/check_duplicate.py --url "来源链接"
python3 scripts/check_duplicate.py --name "建议风格名"
```

### Step 3：开分支
```bash
git checkout -b add/风格名
```

### Step 4：创建风格文件
参考 `styles/` 下已有的 `.md` 文件格式，遵循以下模板结构：

```markdown
# [snake_case 风格名]

**标签**：#标签1 #标签2
**触发词**：关键词
**适用场景**：场景描述
**比例**：16:9（必填，CI 会校验）
**来源**：@作者
**来源链接**：URL

## 一句话理解
[20字以内核心描述]

## 核心特点
- 特点1
- 特点2

## 完整模板
```
原始提示词，{{变量}}用双花括号标记
```

## 变量使用指南
| 变量名 | 说明 |
|--------|------|
| {{title}} | 主标题 |

## 参考配图
![描述](https://malongan.github.io/images/styles_previews/风格名_8位哈希值.jpg)
```

### Step 5：上传配图
```bash
python3 scripts/upload_preview.py /tmp/preview.jpg 风格名
# 脚本自动：压缩 → 计算 MD5[:8] 哈希 → 上传 images 仓库 → 输出完整 URL
# 注意：此脚本依赖环境变量 IMAGES_TOKEN（仅需此一个 Token）
# 输出示例：https://malongan.github.io/images/styles_previews/bubble_card_a3f8c92e.jpg
```

### Step 6：写入配图 URL
将 Step 5 输出的完整 URL 直接填入风格文件的 `## 参考配图` 中，替换占位符。

### Step 7：提交
```bash
git add styles/xxx/风格名.md
git commit -m "feat: 新增[风格名]风格"
git push origin add/风格名
```

### Step 8：提 PR
输出 PR 链接给用户，等待审核。

---

## 5. 规则速查（CI 会检查，但 Agent 应预先遵守）

| 规则 | 要求 |
|------|------|
| 文件名 | `snake_case.md`，全小写，无空格 |
| 分类 | 判断规则见下方 |
| 必填字段 | 标签、触发词、场景、**比例**、完整模板、参考配图、来源链接 |
| 配图 URL | 必须以 `https://malongan.github.io/images/` 开头 |
| 变量闭环 | 模板中的 `{{变量}}` 必须在「变量使用指南」中有定义 |

### 分类判断规则

| 分类名 | 目录名（必须） | 什么风格放这里 |
|--------|---------------|---------------|
| 社交媒体 | `social_media/` | 小红书、朋友圈、头像、Y2K |
| 品牌视觉 | `brand_kv/` | 品牌KV、公益海报、杂志封面 |
| 电商 | `e-commerce/` | 产品主图、电商海报、饮料广告 |
| 科研专业 | `science/` | 期刊封面、信息图、商业报告 |
| 印刷品 | `print/` | 书籍封面、电影海报、浮世绘 |
| IP/角色 | `ip_character/` | 吉祥物、Q版角色、3D头像 |
| 旅行城市 | `travel/` | 城市海报、旅行拼贴 |
| 时尚美容 | `fashion/` | 时尚大片、美妆海报 |
| 创意特殊 | `creative/` | 融合、复古、手绘、实验性 |
| VigoCookbook | `vigo_cookbook/` | Vigo Cookbook 来源 |

### 变体命名规则

如果提示词与已有风格相似度 >80%，不直接新建同名，改为变体命名：
```
base_style_dark.md      ← 暗色变体
base_style_portrait.md  ← 人像变体
```

---

## 6. ❌ 禁止做的事

| 禁止 | 原因 |
|------|------|
| 不要直接推 main | 走分支 → PR |
| 不要修改 `_index.md` | CI 自动生成 |
| 不要修改 `_collection_log.md` | CI 自动维护 |
| 不要修改 `data/styles.json` | CI 自动生成 |
| 不要修改 `_scene_recommend.md` | 由仓库 Owner 人工维护 |
| 不要上传配图到非规范目录 | 统一用 `images/styles_previews/` |

---

## 7. 脚本速查

| 脚本 | 用途 | 调用方式 |
|------|------|---------|
| `check_duplicate.py` | 查重 | `--url URL` 或 `--name 风格名` |
| `collect_init.py` | 交互式创建风格文件 | 直接运行 |
| `upload_preview.py` | 上传配图（**依赖 `IMAGES_TOKEN`**） | `图片路径 风格名` |
| `validate_style.py` | 校验单个文件 | `文件路径` |

---

## 8. 常见报错处理（Agent 自我纠错）

当 Agent 执行过程中遇到错误，应按以下列表自动诊断和修正：

### 8.1 `git push` 失败：远程有新提交

```bash
# 错误信息： rejected (non-fast-forward)
# 原因：其他人先推送了更新到 main
# 修正：
git pull --rebase origin main
# 如果本地分支已经 push 到远端，rebase 后必须强制推送
git push origin add/风格名 --force-with-lease
# 使用 --force-with-lease（而非 --force），避免覆盖同事的新提交
# --force-with-lease 只覆盖你确认过的远程分支，不覆盖别人刚推的新提交
```

### 8.2 CI 校验失败

```
# 错误信息： PR 检查显示 ❌
# 原因：格式不符合规范
# 修正：
1. git checkout add/风格名
2. 本地运行 python3 scripts/validate_style.py styles/xxx/风格名.md
3. 根据报错信息修改文件
4. git add && git commit --amend && git push --force
# PR 会自动重新触发 CI 检查
```

### 8.3 `upload_preview.py` 报错

```
# 错误信息： 401 Unauthorized 或 403 Forbidden
# 原因：Token 未设置或权限不足
# 修正：
1. 检查环境变量 export | grep IMAGES_TOKEN
2. 如果为空，提示用户配置 IMAGES_TOKEN
3. Token 需有 malongan/images 仓库的 Contents: write 权限
```

### 8.4 查重发现风格已存在

```bash
# check_duplicate.py 输出已有风格名和收集者
# 修正：
1. 如果是完全相同的提示词 → 终止流程，告知用户「此风格已被 @xxx 收集」
2. 如果是高度相似但有差异 → 使用变体命名（见 §5 变体命名规则）
```
