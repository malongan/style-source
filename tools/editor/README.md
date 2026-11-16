# tools/editor — 本地图形编辑器

给 `styles/**.yaml` 用的本地编辑界面（列表 + 配图预览 + 表单），纯标准库 `http.server`，唯一第三方依赖是 **Pillow**。

> **完整手册：`docs/EDITOR.md`**（启动、功能、API、故障排查、设计原则全在那边）。
> 本文件只给要改这个工具的人一张代码地图。

```bash
./tools/editor/editorctl up      # 启动 + 开浏览器（默认局域网 + 口令，端口 8765）
./tools/editor/editorctl status  # 状态 / 口令 / 生成物新鲜度
/usr/bin/python3 tools/editor/make_app.py   # 生成 /Applications/风格编辑器.app
```

## 代码地图

| 文件 | 职责 |
|---|---|
| `server.py` | HTTP 路由、口令校验、静态资源；所有写操作经 `tracked()` 包一层快照 |
| `ops.py` | 仓库操作层（只读盘点、调既有脚本、影响面）；`path()` 支持 `STYLE_SOURCE_ROOT` 沙箱 |
| `yaml_patch.py` | 字段级文本替换，保留注释 / 字段顺序 / 引号风格 |
| `yaml_template.py` | 新建时整份渲染 yaml（字段顺序、必填项、id 正则） |
| `extensions.py` | 导入 YAML、无图草稿、批量标签、回收区、生成物新鲜度 |
| `migrate.py` | 改名 / 改分类迁移、配图替换（6 处身份一次改完，保号） |
| `normalize.py` | 历史格式体检 → 分级预览 → 应用（全库校验失败整体回滚） |
| `history.py` | 写操作前后全库快照、diff、按文件还原 |
| `image_pipeline.py` | 上传图 → full + thumb 两份 WebP |
| `release.py` | 发布前检查（纯只读，只产出建议命令文本） |
| `editorctl` | 启动 / 停止 / 状态 / 口令 / 日志（bash 3.2 兼容） |
| `make_app.py` | 生成 `.app`：Pillow 画图标 + 原生启动器 + plist + ad-hoc 签名 |
| `static/` | 单页前端（`index.html` / `app.js` / `style.css`），无构建步骤 |

## 三条设计原则

1. **不重写校验规则**：格式、变量语义、查重一律 `subprocess` 调 `scripts/` 下的既有脚本。
2. **单一真源**：只改 `styles/**.yaml`；生成物由「重建生成物」显式跑 `scripts/preflight.py`。
3. **写盘先算后写、失败整体回滚**：写入后跑校验，任一失败全部还原。

## 运行时目录（全部 gitignore，不进 `styles/`、不参与 preflight）

```
.state/        editor.log · app.log · history.json · snapshot.json · lan_token
.trash/        回收区（<批次>/ + manifest，可一键还原）
.drafts/       无图草稿
```

## 改代码前必看

- 编辑存量 yaml 只能走 `yaml_patch`，整文件 `safe_dump` 会毁注释与格式。
- `id` / `category` / `preview` / `code` 是锁定字段，改它们必须走 `migrate.py`（保号：同步 `style_numbers.json` 的 key）。
- 迁移 / 换图后**不要**立刻跑 `check_style_previews.py`（读的是生成物，必误报）；先重建生成物。
- 这个目录必须在 `tools/`：CI 的 `on-merge-main.yml` 监听 `scripts/**`，放进去会让每次改工具都触发全库校验 + Pages 部署。
- 详细坑位清单见 `docs/EDITOR.md` 第 13 节。
