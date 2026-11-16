# AGENTS.md

> **给接手本仓库的 AI 的入口页。** 先读完这一页，再按第 2 节的指针跳转，别一上来就翻代码。
> 人类读者请看 `README.md` / `CONTRIBUTING.md`。

---

## 1. 30 秒理解这个仓库

- `styles/{分类}/{id}.yaml` 是**唯一真源**（当前 373 条 / 12 分类，以 `find styles -name '*.yaml' | wc -l` 为准）。
- `data/styles.json`、`data/styles_list.txt`、`style_numbers.json`、`style_timestamps.json`、`gallery.html|css|runtime.js`、`styles/**/_index.md` 全是**生成物，禁止手改**。
- CI：PR 跑格式 + 变量语义 + 配图完整性 + 查重 + 生成物一致性；合入 `main` 后重算生成物并部署 GitHub Pages 画廊。
- 本地有一套图形编辑器 `tools/editor/`：改 yaml、换配图、迁移、规范化、重建生成物都在里面点，**它从不执行 git 写操作**。

---

## 2. 文档地图（按任务选，别全读）

| 我要做的事 | 读这份 |
|---|---|
| 加 / 改一个风格，走完 PR | `CONTRIBUTING.md`（人）· `AGENT_SETUP.md`（Agent，含字段规范、分类判断、报错速查） |
| 写 `variables`（`{槽位}` 语义） | `docs/PROMPT_VARIABLES_SPEC.md` |
| 用 / 改 / 排障本地编辑器 | **`docs/EDITOR.md`**（本仓唯一编辑器手册） |
| 改画廊前端 / 性能 | `docs/GALLERY_FEATURES.md`、`docs/PERF_PLAN.md` |
| 发布链路、版本记录 | `CONTRIBUTING.md` 的 PR 流程、`CHANGELOG.md` |

---

## 3. 常用命令（复制即用，`cd` 到仓库根）

```bash
# 一条命令跑完全部闸门（= 编辑器里的「重建生成物」）
/usr/bin/python3 scripts/preflight.py

# 只校验、不重算生成物
/usr/bin/python3 scripts/preflight.py --skip-generate

# 校验单个 / 全部文件
/usr/bin/python3 scripts/validate_style.py styles/{分类}/{id}.yaml
/usr/bin/python3 scripts/validate_all.py --strict --require-desc

# 查重（新条目撞车高发；--prompt 需要传提示词内容）
/usr/bin/python3 scripts/check_duplicate.py --pr-mode                  # PR 新增 vs 已有库
/usr/bin/python3 scripts/check_duplicate.py --name "风格名" --url "来源链接"

# 配图完整性（串号 / 缩略图 / 孤儿）
/usr/bin/python3 scripts/check_style_previews.py --strict

# 单个生成物
/usr/bin/python3 scripts/generate_data.py      # styles.json + list + 编号/时间戳
/usr/bin/python3 scripts/build_gallery.py      # gallery.html/css/runtime.js
/usr/bin/python3 scripts/generate_index.py     # styles/**/_index.md

# 本地编辑器
./tools/editor/editorctl up         # 启动 + 开浏览器（默认局域网 + 口令）
./tools/editor/editorctl status     # 进程 / 地址 / 口令 / 风格数 / 生成物新鲜度
./tools/editor/editorctl last-error # 起不来时看这个
```

解释器统一用 `/usr/bin/python3`（自带 PyYAML + Pillow）。换别的解释器要先装这两个依赖。

---

## 4. 本地编辑器（`tools/editor/`）要点

完整手册见 **`docs/EDITOR.md`**，这里只放接手时必须知道的部分。

**三种启动方式**：双击 `/Applications/风格编辑器.app`（没有就 `/usr/bin/python3 tools/editor/make_app.py` 重建）· `./tools/editor/editorctl up` · `/usr/bin/python3 tools/editor/server.py`（调试用）。

**能做什么**：列表/搜索 → 字段级编辑与保存 → 新建（必须带 1 张配图，自动生成 full + thumb 两份 WebP）→ 删除进回收区 → 改名/改分类迁移 → 换配图 → 导入 YAML → 无图草稿 → 批量改 tags/triggers → 格式体检 → 变更历史 diff 与还原 → 重建生成物 → 发布检查（只读）。

**接手必记的四条**：

1. **锁定字段** `id` / `category` / `preview` / `code` 不能在表单里直接改，必须走「改名 / 迁移」向导 —— 它们是散在 6 处的身份（yaml 路径、yaml 字段、`# 配图` 注释、配图文件名、`style_numbers.json` 的 key、`style_timestamps.json` 的 key）。
2. **保号**：`generate_data.py` 按 `style_numbers.json` 的 **key** 认风格。只改文件名不同步 key，重建会把旧号清掉、新 id 拿 `max+1`，线上 `?style=STxxxx` 链接失效。编号**不回收**，删除留空洞是正常的。
3. **迁移 / 换图后不要立刻跑 `check_style_previews.py`**：它读生成物 `styles.json`，重建前必然误报。先点「重建生成物」。
4. **别用 agent 后台任务托管这个服务**：沙箱子进程启动的实例会失去文件 I/O 代理（`/api/auth/status` 200 但 `/api/bootstrap` 全 500，报 `_BrokerProtocolError`），必须由用户自己的 Terminal / 图标启动。这是环境限制，不是代码 bug。

---

## 5. 硬约束（做了就是事故）

- **不手改生成物**（`data/*.json`、`gallery.*`、`_index.md`），只能由脚本重算。
- **不直推 `main`**：走分支 → PR → squash 合并。发布前扫描由 `.git/hooks/pre-push` 触发。
- **编辑器不许加 git 写操作**：不 `add`、不 `commit`、不 `push`、不部署。发布检查面板只产出可复制的命令文本。
- **不在 `styles/` 里放草稿 / 临时文件 / 备份**：草稿在 `tools/editor/.drafts/`，回收区在 `.trash/`，都不进 preflight。
- **工具放 `tools/`，不要放 `scripts/`**：`.github/workflows/on-merge-main.yml` 监听 `scripts/**`，放错会让每次改工具都触发全库校验 + Pages 部署。
- **配图文件名后缀整段锚定** `{id}_{8位}.webp`，禁止前缀模糊匹配（历史上有串号事故）。
- **一个链接只收一张图、一个风格**（见第 7 节）。

---

## 6. 常见坑（细节见 `docs/EDITOR.md` 第 13 节）

- 生成物「过期」判定用**内容 sha256 基线**，不用 mtime（git 操作会刷新 mtime，用时间戳必误报）。
- 编辑存量 yaml 必须做**字段级文本替换**（`tools/editor/yaml_patch.py`），整文件 `safe_dump` 会毁注释、顺序和引号，diff 爆炸。
- macOS 自带 bash 3.2：空数组 `"${arr[@]}"` 在 `set -u` 下 unbound；`$var` 紧跟中文全角括号会被吃进变量名，写 `${var}`。
- Apple Silicon 上判硬件用 `sysctl -n hw.optional.arm64`；进程被 Rosetta 翻译时 `uname -m` 会撒谎报 x86_64。
- `ops.run()` 会对输出整体 `strip`，解析 `git status --porcelain` 不能用 `line[3:]`。

---

## 7. 风格收集

- 每条链接只收一张图、一个风格，不要拆成多图或多风格（用户明确要求过）。
