# Style Source — 风格提示词源文件仓库

> 风格提示词的「唯一真相之源」。131 个 AI 绘画风格提示词，涵盖 10 个分类。
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
├── styles/              ← 风格 .yaml 源文件（131 个）
├── images/              ← 预览图
├── data/styles.json     ← 风格数据
├── gallery.html         ← 画廊页面
├── scripts/             ← 工具脚本
└── .github/workflows/   ← CI/CD
```

## 合作指南

| 你是谁 | 看这个 |
|--------|--------|
| **人类合作者** | `CONTRIBUTING.md` — 分支命名、模板格式、PR 流程 |
| **AI Agent** | `AGENT_SETUP.md` — 自动配置指引、脚本速查、分类规则 |
| **仓库 Owner** | 直接联系我（GitHub Manager） |

## 目录

- `styles/` — 所有风格文件，按分类存放
- `scripts/` — 验证、生成、构建脚本
- `.github/workflows/` — PR 检查 + 合并验证

---

> 由 malongan 维护 · 基于 GitHub Pages 部署
