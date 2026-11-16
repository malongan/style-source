# 本地编辑器（`tools/editor/`）— 使用与维护手册

> **一句话**：给 `styles/**.yaml` 挂一个本地图形界面（列表 + 配图 + 表单），改完显式「重建生成物」，再按 `CONTRIBUTING.md` 走 PR。**它从不执行 git 写操作。**
>
> **读者**：接手这个项目的人或 AI。只想把活干完 → 看第 2、3、4 节；出问题了 → 第 8 节；要改代码 → 第 9、13 节。

浏览器打开 `http://127.0.0.1:8765`。默认只监听本机；开局域网要显式加 `--lan`（强制口令）。

---

## 1. 边界：它做什么、不做什么

| 做 | 不做 |
|---|---|
| 读 / 改 / 新建 / 删除 `styles/{分类}/{id}.yaml` | `git add` / `commit` / `push` / 建 PR |
| 生成并替换配图（full + thumb 两份 WebP） | 手改 `data/styles.json`、`gallery.*` 等生成物 |
| 调 `scripts/` 下既有校验脚本做体检 | 重写任何校验规则（一律 subprocess 调用既有脚本） |
| 显式「重建生成物」= 跑 `scripts/preflight.py` | 在后台自动跑 CI / 部署 Pages |
| 只读展示发布前检查（git 状态 + 生成物新鲜度） | 提交、合并、发布 |

三条设计原则，改代码时必须守住：

1. **单一真源**：`styles/**.yaml` 是唯一的真源，其余都是生成物。
2. **不重写规则**：格式 / 变量语义 / 查重全部 `subprocess` 调 `scripts/` 里的脚本，工具只做壳。
3. **写盘先算后写、失败整体回滚**：先算出全部改动 → 写入 → 跑校验 → 任一失败全部还原；写操作前后各做一次全库快照（变更中心可 diff / 单文件还原）。

---

## 2. 30 秒上手

### 2.1 图形方式（推荐）

双击 `/Applications/风格编辑器.app`：

| 当前状态 | 弹框 | 点默认按钮的结果 |
|---|---|---|
| 没在跑 | 编辑器没有在运行 | 启动 + 自动开浏览器（自带口令，不用手输） |
| 正跑着 | 编辑器正在运行 | 打开编辑器 / 停止服务 / 取消 |
| 进程在但接口异常 | 数据接口异常 | 重启服务 |

图标是 `tools/editor/make_app.py` 生成的（Pillow 画图标 → `iconutil` 出 icns → ad-hoc 签名）。**仓库搬家后要重跑一次**：

```bash
/usr/bin/python3 tools/editor/make_app.py          # 装到 /Applications
/usr/bin/python3 tools/editor/make_app.py --dir ~/Applications
```

### 2.2 命令行（`tools/editor/editorctl`）

```bash
cd /path/to/style-source          # 换成你本地的仓库根目录
./tools/editor/editorctl up        # 启动 + 开浏览器（已在跑则跳过）
./tools/editor/editorctl start     # 只启动
./tools/editor/editorctl stop      # 停止
./tools/editor/editorctl restart   # 重启（口令不变）
./tools/editor/editorctl status    # 进程 / 地址 / 口令 / 风格数 / 生成物新鲜度
./tools/editor/editorctl state     # 只输出 stopped | running-ok | running-bad（给图标用）
./tools/editor/editorctl open      # 只开浏览器
./tools/editor/editorctl url        # 打印访问地址与口令
./tools/editor/editorctl token      # 打印当前口令
./tools/editor/editorctl logs       # tail 日志
./tools/editor/editorctl last-error # 日志里最像原因的一行（排障用）
```

环境变量：`EDITOR_PORT`（默认 8765）、`EDITOR_MODE=local`（只监听 127.0.0.1 且免口令）、`EDITOR_PYTHON`（默认 `/usr/bin/python3`）。

**服务必须由你自己的 Terminal / 图标启动**，不要用 agent 沙箱的后台任务托管（见 8.2）。

### 2.3 直接跑 python（调试用）

```bash
/usr/bin/python3 tools/editor/server.py                 # 本机模式，免口令
/usr/bin/python3 tools/editor/server.py --lan           # 局域网 + 随机口令（写入 .state/lan_token）
/usr/bin/python3 tools/editor/server.py --port 8766     # 换端口
```

依赖只有 **Pillow**（`/usr/bin/python3` 自带环境里已有）。注意 `scripts/` 下的校验脚本还需要 **PyYAML**，跑 `preflight` 时用的是同一个解释器。

### 2.4 口令

- 口令存在 `tools/editor/.state/lan_token`（gitignore），`editorctl` 复用它，**重启不变**。
- 局域网下所有 `/api/` 请求都要带 `X-Editor-Token: <口令>`；静态资源、配图、`/api/auth/status` 放行。
- 前端支持 `#t=<口令>` 自动登录：打开 `http://127.0.0.1:8765/#t=xxx` 会写 localStorage 再清地址栏。`editorctl open` 就是这么做的。
- `--host 0.0.0.0` 而不给口令会被直接拒绝启动（拒绝无口令开放监听）。

---

## 3. 界面速览（顶栏按钮 → 动了什么）

| 入口 | 作用 | 影响文件 |
|---|---|---|
| 左侧列表 | 搜索（名称 / id / 编号 / 提示词）、按分类筛、加载更多 | — |
| 编辑区 5 个 tab | 基本信息 / 特征 / 提示词与变量 / 原始 YAML / 校验结果 | 保存时只改对应字段 |
| **保存** | 字段级文本替换（保留注释、字段顺序、引号风格），先跑 `validate_style --require-desc` + `lint_hygiene --strict`，失败回滚 | 目标 yaml |
| **+ 新建风格** | 结构化表单 → 渲染完整 yaml，必须带 1 张配图（自动转 full + thumb），编号取 `max+1` | 新 yaml、2 个 WebP、`style_numbers.json`、`style_timestamps.json` |
| **删除** | 移入回收区（不是真删），配图一起移走 | yaml + 配图 → `.trash/<批次>/` |
| **改名 / 迁移** | 改 `id` 或 `category` 的向导（见第 5 节） | yaml 路径、yaml 内字段、配图文件名、两个 json 的 key |
| **替换配图** | 上传新图 → 生成新 WebP、旧图进回收区、改 `# 配图` 注释 | 配图 + yaml 注释 |
| **导入 YAML** | 粘贴现成 yaml，两种模式：规范化 / 保真；写盘前查重 | 新 yaml |
| **草稿箱** | 无图草稿（不满足新建条件时先存着），发布时才要求配图 | `.drafts/` |
| **回收区** | 看批次内容、一键还原、彻底删除 | yaml + 配图 |
| **批量编辑** | 左侧勾选多个 → 批量改 `tags` / `triggers`（加 / 删 / 替换） | 多个 yaml |
| **格式体检** | 全库格式体检 + 7 个分级选项，逐文件 diff 预览，应用前跑全库校验 | 多个 yaml（可选） |
| **重建生成物** | 跑 `scripts/preflight.py`，重算全部生成物并刷新基线 | 见第 6 节生成物 |
| **发布检查** | 纯只读：git 状态 + 生成物新鲜度 + 6 步建议命令（命令只是文本，不会执行） | 不改任何文件 |
| **变更中心** | 写操作历史（跨会话保存），可看 diff、按文件还原 | `.state/history.json` |

顶栏「生成物已过期」徽标 = 源文件的 sha256 与 `.state/snapshot.json` 基线不一致。用**内容基线**而不是 mtime（git 操作会刷新 mtime，用时间戳必然误报）。

---

## 4. 功能地图（分三批交付）

| 批次 | 内容 |
|---|---|
| **P0** | 只读盘点、字段级保存、新建（含配图）、删除进回收区、锁定身份字段、单文件校验、重建生成物 |
| **P1** | YAML 导入（规范化/保真 + 查重）、无图草稿区、批量改 tags/triggers、回收区详情与彻底删除、生成物过期检测 |
| **P2** | 改名/改分类迁移向导、配图替换、历史格式规范化（体检→分级→应用）、变更历史对比与还原、发布前检查面板、局域网 + 口令、桌面图标与 `editorctl` |

---

## 5. 身份字段与保号（最容易踩的地方）

`id` / `category` 是**锁定字段**，表单里不能直接改（要走「改名 / 迁移」向导）；`preview` / `code` 是历史遗留字段，UI 不提供编辑（`code` 由 `generate_data.py` 重算，`preview` 已废弃，规范化的可选项会清掉）。

锁定的原因：它们不是普通字段，而是散落在 **6 处**的身份：

1. `styles/{category}/{id}.yaml` 的路径
2. yaml 内的 `id`、`category`
3. yaml 末尾 `# 配图: images/styles_previews/{id}_{8位}.webp` 注释
4. `images/styles_previews/{id}_{8位}.webp` + `.thumb.webp`
5. `data/style_numbers.json` 的 **key**（编号按 id 保号）
6. `data/style_timestamps.json` 的 key

**为什么必须用迁移向导**：`generate_data.py` 是**按 `style_numbers.json` 的 key 认风格**的。只改 yaml 文件名而不同步这个 key，重建时旧条目会被当成「已删除」清掉，新 id 拿到 `max+1` 的新编号 —— 站点上 `?style=STxxxx` 的分享链接就废了。向导会一次性改完 6 处，失败整体回滚。

其它两条硬规则：

- **编号不回收**：删除后 `style_numbers.json` 留空洞是正常的，新风格永远 `max+1`。
- **迁移 / 换图后即时校验不要跑 `check_style_previews.py`**：它读生成物 `data/styles.json`，重建前必然误报「配图缺失」。工具内部只跑 `validate_single` + 自己的配图断言，preflight 在重建时兜底。

---

## 6. 数据与目录边界

```
styles/{分类}/{id}.yaml        ← 唯一真源（当前 373 条 / 12 分类，以 find 结果为准）
images/styles_previews/        ← {id}_{md5(原图)[:8]}.webp + .thumb.webp
                                 full 最长边 1000 / q85，thumb 最长边 400 / q75
data/style_numbers.json        ← id → 编号（generate_data 写，编号不回收）
data/style_timestamps.json     ← id → 时间戳
data/styles.json               ← 生成物（勿手改）
data/styles_list.txt           ← 生成物
gallery.html / gallery.css / gallery-runtime.js   ← 生成物
styles/_index.md + styles/{分类}/_index.md        ← 生成物
tools/editor/                   ← 工具本体
  .state/                       ← 运行态：editor.log、app.log、history.json、snapshot.json、lan_token（全部 gitignore）
  .trash/<批次>/                 ← 回收区 + manifest（可一键还原）
  .drafts/                      ← 无图草稿
```

草稿、回收区、快照都在 `tools/editor/` 下，**不进 `styles/`，不参与 preflight**。运行时目录全部 gitignore。

配图文件名后缀必须**整段锚定**（`{id}_{8位}.webp`），禁止前缀模糊匹配——历史上出过配图串号事故。

---

## 7. 局域网访问

```bash
./tools/editor/editorctl start          # 默认就是局域网 + 口令
./tools/editor/editorctl url            # 打印 http://<内网IP>:8765 与口令
```

- 手机 / 另一台机器：浏览器打开 `http://<内网IP>:8765` → 输口令，或直接用 `http://<内网IP>:8765/#t=<口令>`。
- ≤720px 有窄屏布局（列表 / 编辑区堆叠）。
- 口令在自定义头 `X-Editor-Token`，用常数时间比较；`do_OPTIONS` 直接 403，顺带挡 CSRF。
- 口令想固定不变：`--lan --token <原口令>`（随机口令只在没传 `--token` 时生成）。只有**自动生成**的口令才回写 `.state/lan_token`，避免临时实例覆盖正式口令。

---

## 8. 故障排查（按症状查）

### 8.1 双击图标永远弹「编辑器没有在运行」

**先看日志**：`tools/editor/editorctl last-error`（或 `.state/app.log`）。

最常见的是 Pillow 架构错配：

```
ImportError: dlopen(.../PIL/_imaging.cpython-39-darwin.so):
  mach-o file, but is an incompatible architecture (have 'arm64', need 'x86_64')
```

原因：脚本型 `.app` 被 Finder 启动时可能被 Rosetta 翻译成 x86_64，子进程继承翻译，于是 python 加载不了 `~/Library/Python` 里 arm64 的 Pillow。已修，三道防线：

1. `Contents/MacOS/run` 是 `clang -arch arm64 -arch x86_64` 编译的**原生启动器**（脚本在 `Resources/run.sh`），不再是 shell 脚本；
2. `editorctl` 发现自己在被翻译的进程里，会 `exec /usr/bin/arch -arm64` 重入（被翻译时 `uname -m` 会撒谎报 x86_64，判硬件只看 `sysctl -n hw.optional.arm64`）；
3. 起服务前 `preflight_python` 体检，缺库 / 架构不对会直接说原因和修复命令。

还不行就重装依赖：

```bash
/usr/bin/arch -arm64 /usr/bin/python3 -m pip install --user --force-reinstall pillow
/usr/bin/python3 tools/editor/make_app.py     # 重建 app
```

### 8.2 页面能开，但列表 / 配图全 500

`/api/auth/status` 返回 200 而 `/api/bootstrap` 500，错误体是 `_BrokerProtocolError: execution attempt 不存在或已关闭` → 这个服务实例是**被 agent 沙箱的子进程启动的**，执行结束后它的文件 I/O 代理失效了。

处理：停掉，在**你自己的 Terminal** 里重新 `editorctl start`（或双击图标）。不要改服务端代码。

### 8.3 顶栏提示「生成物已过期」

源文件改了但生成物没同步：点「重建生成物」（内部跑 `scripts/preflight.py`）。成功后自动刷新基线。

### 8.4 401 / 一直弹口令框

- 口令与 `.state/lan_token` 不一致：`editorctl token` 看当前值，`editorctl restart` 后重新用 `#t=` 打开。
- 顶栏 LAN 徽标点一下可以清掉本机存的口令，重新输入。
- `editorctl status` 里口令状态 `ok / bad / unknown`，`unknown` 说明服务本身异常，不是口令错。

### 8.5 端口被占

`editorctl start` 会先判断端口占用者是不是自己：是自己且健康就跳过，是自己但接口异常就重启，不是自己就提示「端口被 xxx 占着但不是编辑器」。手动处理：`lsof -ti tcp:8765 -sTCP:LISTEN`。

### 8.6 迁移 / 换图后马上校验报错

预期行为，见第 5 节：先「重建生成物」再跑 `check_style_previews.py`。

---

## 9. 代码地图

| 文件 | 职责 | 改动注意 |
|---|---|---|
| `server.py` | HTTP 路由、口令校验、静态资源、`tracked()` 包住所有写操作 | 新路由要同时考虑 GET/POST/DELETE 与鉴权分支 |
| `ops.py` | 仓库操作层：只读盘点、跑既有脚本、影响面分析、git 状态；`path()` 支持 `STYLE_SOURCE_ROOT` 沙箱 | 不要在这里实现校验逻辑 |
| `yaml_patch.py` | **字段级**文本替换（按顶层 key 切块） | 不能整文件 `safe_dump`，会毁注释 / 顺序 / 引号 |
| `yaml_template.py` | 新建时整份渲染 yaml（字段顺序、必填项、id 正则） | 新建可整份渲染，编辑必须走 `yaml_patch` |
| `extensions.py` | 导入 / 草稿 / 批量标签 / 回收区 / 新鲜度 | 写盘一律先算后写、失败回滚 |
| `migrate.py` | 改名、改分类、换图（6 处身份一次改完，整体回滚） | 见第 5 节，保号是硬约束 |
| `normalize.py` | 格式体检 + 7 个分级选项 + 逐文件 diff + 全库校验失败回滚 | 「收敛格式」不是纠错；风险项默认关 |
| `history.py` | 写操作前后全库快照、diff、按文件还原 | 只快照源文件，生成物交给 git |
| `image_pipeline.py` | 上传图 → full + thumb WebP | 文件名后缀整段锚定 |
| `release.py` | 发布前检查（纯只读，产出建议命令文本） | 绝不允许在这里执行 git 写命令 |
| `editorctl` | 启动/停止/状态/口令/日志（bash 3.2 兼容） | 见 13 节的 bash 坑 |
| `make_app.py` | 生成 `.app`（图标 + 原生启动器 + plist + 签名） | 改图标参数见第 13 节 |
| `static/` | 单页前端（`index.html` / `app.js` / `style.css`），无构建步骤 | 扁平 vanilla JS，别引入框架 |

---

## 10. API 速查

`GET`

| 路径 | 作用 |
|---|---|
| `/api/auth/status` | 是否需要口令、是否局域网、可用地址（免鉴权） |
| `/api/bootstrap` | 汇总：总数、分类、锁定字段、生成物新鲜度、草稿数、回收区批次数 |
| `/api/styles?q=&cat=` | 列表（搜索 + 分类） |
| `/api/style/{id}` | 单条详情（含原始 yaml） |
| `/api/impact/{id}` | 改动的「影响面」分析 |
| `/api/trash`、`/api/trash/{batch}` | 回收区批次列表 / 详情 |
| `/api/drafts`、`/api/draft/{id}` | 草稿列表 / 详情 |
| `/api/changes`、`/api/history`、`/api/history/{id}` | 变更中心列表 / 某次操作明细（diff） |
| `/api/freshness` | 生成物是否过期（内容基线比对） |
| `/api/normalize/scan` | 全库格式体检 |
| `/api/git` | 只读 git 状态 |
| `/api/release/check` | 发布前检查（只读） |

`POST`

| 路径 | 作用 |
|---|---|
| `/api/style` | 保存已有风格（字段级） |
| `/api/style/check-new` | 新建前检查（id 是否占用、查重） |
| `/api/import/check`、`/api/import/commit` | 导入 YAML 的预检 / 落盘 |
| `/api/draft`、`/api/draft/{id}/publish` | 存草稿 / 草稿发布成正式风格 |
| `/api/batch/tags` | 批量改 tags / triggers |
| `/api/migrate/check`、`/api/migrate/commit` | 迁移预检 / 执行 |
| `/api/image/check`、`/api/image/replace` | 配图预检 / 替换 |
| `/api/normalize/preview`、`/api/normalize/apply` | 规范化预览 / 应用 |
| `/api/history/revert`、`/api/history/clear` | 按文件还原 / 清空历史 |
| `/api/rebuild` | 重建生成物（跑 preflight） |
| `/api/restore` | 从回收区还原 |
| `/api/freshness/snapshot` | 手动「标记为已同步」 |

`DELETE`

| 路径 | 作用 |
|---|---|
| `/api/style/{id}` | 删除 → 进回收区 |
| `/api/draft/{id}` | 删草稿 |
| `/api/trash/{batch}?confirm=1` | 彻底删除回收批次 |

---

## 11. 自测与回归

工具自带 Python 自测脚本，用 `STYLE_SOURCE_ROOT` 指向 `/tmp` 沙箱跑，**不碰真实仓库**：

```bash
export STYLE_SOURCE_ROOT=/tmp/style_sandbox     # server 启动时打印「[沙箱]」即生效
```

历史脚本（曾放在 `/tmp/style_editor_*.py`，如已丢失需重建）：

| 脚本 | 覆盖 | 依赖 |
|---|---|---|
| `style_editor_selftest.py` | P0：编辑 / 新建 / 删除 / 锁定字段 / 校验 | 沙箱 + 服务 |
| `style_editor_p1_selftest.py` | P1：导入 / 草稿 / 批量 / 回收区 / 过期检测 | 接 P0 产生的状态，必须**按序**跑 |
| `style_editor_p2_selftest.py` | P2：迁移 / 换图 / 规范化 / 历史还原 | 同上 |
| `style_editor_lan_selftest.py` | 口令、401、`#t=`、OPTIONS 403 | 8766 默认模式 + 8767 LAN 模式同时在跑 |
| `style_editor_release_selftest.py` | 发布检查判定与命令生成 | 8768 干净沙箱 + 8767 LAN |

顺序固定：`P0 → P1 → P2 → LAN → release`，且每次都要重置沙箱（后一批依赖前一批留下的状态）。

---

## 12. 与 CI / 发布的关系

编辑器不发布任何东西。真正的链路是 `CONTRIBUTING.md` 那套：**分支 → 改 yaml → `scripts/preflight.py` → PR → squash 合 `main` → Pages**。

`preflight.py` 的顺序（点「重建生成物」就是跑它）：

1. `validate_all.py --strict --require-desc`
2. `generate_data.py` → `data/styles.json`、`data/styles_list.txt`、重算 `style_numbers.json` / `style_timestamps.json`
3. `audit_variables.py --strict`
4. `build_gallery.py` → `gallery.html`、`gallery.css`、`gallery-runtime.js`
5. `generate_index.py` → `styles/_index.md` + 各分类 `_index.md`
6. `check_style_previews.py --strict`（配图完整性 / 串号 / 孤儿）
7. `test_teaser_detector.py`
8. `lint_hygiene.py --strict`
9. `check_duplicate.py --pr-mode`

「发布检查」面板只把 SOP 里的命令整理成可复制的清单（Step 0/7/8/9/10），判定规则：生成物过期 / 落后 `origin/main` / 无源文件改动 = **fail**；在 `main` 上 / 生成物未提交 / 杂项未跟踪 = **warn**。

---

## 13. 已知坑（改代码前必读）

- **bash 3.2（macOS 自带）+ `set -u`**：空数组 `"${arr[@]}"` 会 unbound；`$var` 紧跟中文全角括号会被吃进变量名，必须写 `${var}`；`case` 分支要把 `$?` 存进 `rc` 再 `exit "$rc"`，否则被末尾 `exit 0` 吞掉。
- **`nohup` 在本环境活不过一次调用**：要用 `subprocess.Popen(..., start_new_session=True)` 才能真正脱离进程组。
- **`ops.run()` 会整体 strip**：`git status --porcelain` 首行前导空格会丢，禁止 `line[3:]` 取路径，用正则 `^\s*([MADRCU?!]{1,2})\s+(.+)$`。
- **`yaml_patch.render_field()`** 对 `tags` / `triggers` 会跟随原区块的引号风格；身份字段（`id` / `category`）不要用它，走 `migrate._set_identity_field`。
- **`normalize._indent_lists()`** 遇到顶层 key 必须停止缩进，否则会把末尾 `# 配图` 注释一起缩进。
- **图标四角星**用 `|cos t|^2.45`（p>1）；p<1 会在对角线外侧鼓出来糊成白方块。
- **判架构用 `sysctl -n hw.optional.arm64`**，被 Rosetta 翻译时 `uname -m` 会撒谎。
- **`server.py` 只监听 `127.0.0.1`**：要开放必须 `--lan`（绑 0.0.0.0 + 强制口令），裸 `--host 0.0.0.0` 会被拒绝启动。
- **别把工具放进 `scripts/`**：`on-merge-main.yml` 监听 `scripts/**`，放错会每次改工具都触发全库校验与 Pages 部署。

---

> 相关文档：`CONTRIBUTING.md`（人）、`AGENT_SETUP.md`（Agent 配置与字段规范）、`docs/PROMPT_VARIABLES_SPEC.md`（变量语义）、`docs/GALLERY_FEATURES.md`（画廊）、`docs/PERF_PLAN.md`（性能）。
