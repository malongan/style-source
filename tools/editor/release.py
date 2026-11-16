#!/usr/bin/env python3
"""发布前检查面板的数据聚合（纯只读）。

只调用 git 的查询子命令和现有只读接口，产出检查项与「建议命令」文本。
绝不执行 git add / commit / push、preflight、部署；命令只是给用户复制的字符串。
"""
from __future__ import annotations

import os
import re
import shlex

import extensions
import ops
import yaml_patch

GALLERY = ('gallery.html', 'gallery.css', 'gallery-runtime.js')
ONLINE = 'https://malongan.github.io/style-source'
# 发布前安全扫描脚本位于 agent 侧，不在本仓库；用环境变量提供，缺省给可移植占位，
# 仅作为复制用的建议命令字符串（本面板纯只读、绝不执行）。也可由 .git/hooks/pre-push 自动跑。
SECURITY_SCAN = os.environ.get(
    'STYLE_SECURITY_SCAN',
    'python3 /path/to/agent/scripts/github-manager/pre-push-security-scan.py .')


def _git(*args, timeout=20) -> str:
    r = ops.run(['git'] + list(args), timeout=timeout)
    return r['output'].strip() if r['ok'] else ''


def git_info() -> dict:
    branch = _git('rev-parse', '--abbrev-ref', 'HEAD') or '(detached)'
    head = _git('rev-parse', '--short', 'HEAD')
    # 左数是 origin/main 独有（本地落后），右数是 HEAD 独有（本地领先）
    lr = _git('rev-list', '--left-right', '--count', 'origin/main...HEAD')
    m = re.match(r'^(\d+)\s+(\d+)', lr)
    behind, ahead = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return {'branch': branch, 'head': head, 'ahead': ahead, 'behind': behind,
            'has_upstream': bool(m)}


def _classify(p: str) -> str:
    if p.startswith('images/styles_previews/'):
        return 'source'
    if p.startswith('styles/'):
        if p.endswith('_index.md'):
            return 'generated'
        if p.endswith(('.yaml', '.yml')):
            return 'source'
        return 'other'
    if p.startswith('data/') or p in GALLERY:
        return 'generated'
    return 'other'


def status_groups() -> dict:
    """把工作区改动分成源文件 / 生成物 / 杂项三组，杂项永不进建议命令。"""
    r = ops.run(['git', 'status', '--porcelain'], timeout=30)
    out = {'source': [], 'generated': [], 'other': [], 'raw': []}
    # ops.run 会整体 strip()，首行 " M .gitignore" 的前导空格会丢，
    # 所以不能固定切 line[3:]；按「状态区 + 空白 + 路径」解析才稳。
    for line in r['output'].split('\n'):
        if not line.strip():
            continue
        m = re.match(r'^\s*([MADRCU?!]{1,2})\s+(.+)$', line)
        p = m.group(2).strip() if m else line[2:].strip()
        if ' -> ' in p:                       # rename: old -> new
            p = p.split(' -> ', 1)[1].strip()
        p = p.strip('"')
        if not p:
            continue
        out['raw'].append(line.rstrip())
        out[_classify(p)].append(p)
    for k in ('source', 'generated', 'other'):
        out[k] = sorted(set(out[k]))
    return out


def _primary_style(groups: dict) -> dict:
    """取第一个改动的 yaml，推出 id / 分类 / 名称，用于填命令里的占位符。"""
    for p in groups['source']:
        parts = p.split('/')
        if len(parts) < 3 or parts[0] != 'styles' or not p.endswith('.yaml'):
            continue
        sid = os.path.splitext(parts[-1])[0]
        name = sid
        try:
            with open(ops.path(p), encoding='utf-8') as fh:
                name = (yaml_patch.parse(fh.read()) or {}).get('name') or sid
        except Exception:
            pass                              # 删除场景文件已不在磁盘
        return {'id': sid, 'category': parts[1], 'name': str(name), 'path': p}
    return {}


def _commands(git: dict, groups: dict, fresh: dict, primary: dict) -> list:
    placeholder = not primary
    sid = primary.get('id') or 'STYLE_ID'
    name = str(primary.get('name') or sid).replace('"', '').replace("'", '')
    branch = git['branch']
    target = ('feat/' + sid) if branch == 'main' else branch
    steps = []

    base = []
    if git['behind'] > 0:
        base.append('git checkout main && git pull origin main --ff-only')
    if branch == 'main':
        base.append('git checkout -b feat/%s' % sid)
    if not base:
        base.append('# 已在 %s，且与 origin/main 同步，跳过基线步骤' % branch)
    base_note = '先拉基线、再重建生成物；顺序反了 PR diff 会被别人的改动污染。'
    if placeholder:
        base_note += ' 本次未检测到风格文件改动，命令里的 STYLE_ID 需替换成实际 id。'
    steps.append({
        'title': '1 · 站好 main 基线并开分支', 'cmd': '\n'.join(base),
        'note': base_note,
    })

    steps.append({
        'title': '2 · 重建生成物',
        'cmd': '# 在编辑器点「重建生成物」（等价命令：/usr/bin/python3 scripts/preflight.py）',
        'note': '跑 9 项闸门并重算 styles.json / ST 编号 / gallery / 索引。编辑器按钮与命令行二选一，不要重复跑。',
    })

    adds = []
    if groups['source']:
        adds.append('git add ' + ' '.join(shlex.quote(p) for p in groups['source']))
    else:
        adds.append('# 本次没有源文件改动')
    adds += [
        'git add data/',
        'git add gallery.html gallery.css gallery-runtime.js',
        'git add styles/_index.md styles/*/_index.md',
    ]
    steps.append({
        'title': '3 · 精确暂存', 'cmd': '\n'.join(adds),
        'note': 'data/ 必须目录通配（style_numbers.json 最容易漏）；杂项文件不在这条命令里，别用 git add -A。',
    })

    title = shlex.quote('feat: add %s (%s)' % (name, sid))
    steps.append({
        'title': '4 · 安全检查、提交、推送',
        'cmd': '\n'.join([SECURITY_SCAN, 'git commit -m ' + title,
                          'git push origin ' + target]),
        'note': '本地 pre-push 钩子还会再跑一次敏感信息扫描；commit message 按实际风格名调整。',
    })

    steps.append({
        'title': '5 · 开 PR 并 squash 合并',
        'cmd': '\n'.join([
            'gh pr create --base main --head %s --title %s --body "见 SKILL.md Step 9 模板"' % (target, title),
            'gh pr merge <PR号> --squash --admin --subject ' + title,
            'git checkout main && git pull origin main --ff-only',
        ]),
        'note': 'PR 会跑 on-push-styles.yml；合并后 on-merge-main.yml 重算生成物并断言零 diff。',
    })

    total = fresh.get('total', 0)
    steps.append({
        'title': '6 · 等 Pages 部署并验线上',
        'cmd': '\n'.join([
            'curl -sL "%s/data/styles.json?v=$(date +%%s)" -o /tmp/online_styles.json' % ONLINE,
            "/usr/bin/python3 -c \"import json;d=json.load(open('/tmp/online_styles.json'));print('线上条目数',len(d['styles']))\"",
        ]),
        'note': ('部署 45 秒～2 分钟，每 45 秒轮询一次，条目数达到 %d 再停（最多 3 轮）；'
                 '然后打开 %s/gallery.html?style=STxxxx 验详情页与复制按钮。') % (total, ONLINE),
    })
    return steps


def check(session_changes: list, generated_files: list, lan: bool = False) -> dict:
    git = git_info()
    groups = status_groups()
    fresh = extensions.freshness()
    primary = _primary_style(groups)
    items = []

    def add(level, title, detail='', action=''):
        items.append({'level': level, 'title': title,
                      'detail': detail, 'action': action})

    if not git['has_upstream']:
        add('warn', '拿不到 origin/main', '无法判断本地是否落后；发布前先手动同步一次', 'git fetch origin')
    elif git['behind'] > 0:
        add('fail', '本地落后 origin/main %d 个提交' % git['behind'],
            '在落后基线上重建生成物，PR diff 会混进别人的改动', 'git pull origin main --ff-only')
    else:
        add('ok', '本地与 origin/main 同步',
            'HEAD %s · 分支 %s · 领先 %d 个提交' % (git['head'], git['branch'], git['ahead']))

    if git['branch'] == 'main':
        add('warn', '当前在 main 上',
            '仓库要求通过 PR 合并；SOP 用 feature 分支，直推 main 会跳过 PR 查重闸门',
            'git checkout -b feat/<风格id>')
    else:
        add('ok', '在 feature 分支', git['branch'])

    if not fresh['baseline']:
        add('warn', '未建立生成物内容基线',
            fresh.get('note', ''), '点「重建生成物」或「标记为已同步」')
    elif fresh['stale']:
        n = len(fresh['changed']) + len(fresh['added']) + len(fresh['removed'])
        add('fail', '生成物已过期（%d 处源文件变动）' % n,
            '合并后 CI 会重算生成物并断言零 diff，现在提交必红', '点「重建生成物」')
    else:
        add('ok', '生成物与源文件一致',
            '内容基线 %s · %d 个 yaml' % (fresh.get('snapshot_time', ''), fresh.get('total', 0)))

    if groups['generated']:
        add('warn', '生成物有 %d 项未提交改动' % len(groups['generated']),
            '、'.join(groups['generated'][:4]) + ('…' if len(groups['generated']) > 4 else ''),
            '这些必须一起进 PR，尤其 data/style_numbers.json')
    elif not fresh['stale']:
        add('ok', '生成物没有遗留改动')

    if groups['source']:
        add('ok', '待提交源文件 %d 项' % len(groups['source']),
            '、'.join(groups['source'][:3]) + ('…' if len(groups['source']) > 3 else ''))
    else:
        add('fail', '没有检测到源文件改动',
            '没有任何 yaml / 配图改动可发布；本次可能只是查看，或改动还没保存',
            '先在编辑器里新建或编辑风格并保存')

    if groups['other']:
        add('warn', '另有 %d 项其它改动 / 未跟踪' % len(groups['other']),
            '、'.join(groups['other'][:4]) + ('…' if len(groups['other']) > 4 else ''),
            '不要用 git add -A；按需逐项判断是否该进这次提交')
    else:
        add('ok', '工作区没有其它杂项')

    add('info', '本次会话 %d 次写操作' % len(session_changes),
        '变更中心有精确路径清单；这里只读取仓库当前状态')

    if lan:
        add('info', '当前是局域网模式',
            '改动落在运行服务的这台机器；git / gh 命令必须在这台机器执行')

    fails = [i for i in items if i['level'] == 'fail']
    warns = [i for i in items if i['level'] == 'warn']
    return {
        'ok': True, 'ready': not fails,
        'summary': ('检查通过，可以进入提交流程' if not fails
                    else '有 %d 项必须先处理' % len(fails)),
        'counts': {'fail': len(fails), 'warn': len(warns),
                   'ok': len([i for i in items if i['level'] == 'ok'])},
        'git': git, 'groups': groups, 'freshness': fresh,
        'primary': primary, 'checks': items,
        'commands': _commands(git, groups, fresh, primary),
        'generated_files': list(generated_files),
        'session_changes': len(session_changes), 'lan': bool(lan),
        'note': ('本面板纯只读：没有执行任何 git 写命令、没有重建生成物、没有提交或部署。'
                 '命令只是建议文本，需你自行复制执行。'),
    }
