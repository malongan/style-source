# Style Source — 风格提示词源文件仓库

> 风格提示词的「唯一真相之源」。373 个 AI 绘画风格提示词，涵盖 12 个分类。
> 所有 .yaml 风格文件在此维护，CI 自动校验格式，Pages 自动部署画廊。

---

## 画廊

https://malongan.github.io/style-source/gallery.html

搜索、筛选、收藏、深色模式全支持。

---

## 快速开始

```bash
git clone git@github.com:malongan/style-source.git
cd style-source
```

## 目录结构

```
├── styles/              ← 风格 .yaml 源文件（373 个，12 个分类）★ 唯一真源
├── images/              ← 预览图（styles_previews/{id}_{8位后缀}.webp + .thumb.webp）
├── data/                ← 生成物：styles.json / styles_list.txt / 编号 / 时间戳（勿手改）
├── gallery.html         ← 生成物：画廊页面（含 gallery.css / gallery-runtime.js）
├── scripts/             ← 校验、生成、构建脚本
├── tools/editor/        ← 本地图形编辑器（改 yaml / 换图 / 迁移 / 重建生成物）
├── docs/                ← 设计与规范文档
└── .github/workflows/   ← CI/CD
```

数量以实际文件为准：`find styles -name '*.yaml' | wc -l`。

## 本地编辑器（图形化）

不想手写 YAML 时用它：列表 + 配图预览 + 表单编辑，改完点「重建生成物」，再照常走 PR。

```bash
./tools/editor/editorctl up        # 启动 + 自动开浏览器（默认局域网 + 访问口令）
./tools/editor/editorctl status    # 进程 / 地址 / 口令 / 生成物新鲜度
```

图形入口：双击 `/Applications/风格编辑器.app`（懒人版，启动/打开/停止三合一；没有就 `/usr/bin/python3 tools/editor/make_app.py` 生成）。

支持：字段级编辑（保留注释）、新建（带配图自动转 WebP 双子图）、删除进回收区、改名/改分类迁移（保号）、替换配图、导入 YAML、无图草稿、批量改标签、格式体检、变更历史 diff 与还原、生成物过期检测、发布前只读检查。

**它不执行任何 git 写操作**：不 add / commit / push / 部署。

完整手册 → **`docs/EDITOR.md`**

## 文档地图

| 你是谁 / 要做什么 | 看这个 |
|--------|--------|
| **人类合作者**：加/改风格、走 PR | `CONTRIBUTING.md` — 分支命名、模板格式、PR 流程 |
| **AI / Agent 接手项目** | **`AGENTS.md`** — 项目速览、文档地图、常用命令、硬约束、坑位 |
| **AI Agent 配置与字段规范** | `AGENT_SETUP.md` — 自动配置指引、脚本速查、分类规则 |
| **用 / 排障本地编辑器** | `docs/EDITOR.md` — 启动、功能、API、故障排查 |
| **变量（`{槽位}`）语义** | `docs/PROMPT_VARIABLES_SPEC.md` |
| **画廊功能与性能** | `docs/GALLERY_FEATURES.md`、`docs/PERF_PLAN.md` |
| **仓库 Owner** | 直接联系我（GitHub Manager） |

## 目录

- `styles/` — 所有风格文件，按分类存放
- `scripts/` — 验证、生成、构建脚本（`preflight.py` 一条命令跑完全部闸门）
- `tools/editor/` — 本地编辑器（见上）
- `docs/` — 设计、规范与手册
- `.github/workflows/` — PR 检查 + 合并验证

---

> 由 malongan 维护 · 基于 GitHub Pages 部署
