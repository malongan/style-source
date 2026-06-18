# maple_story_avatar（冒险岛角色精灵转换）

**标签**：#像素 #游戏 #冒险岛 #角色转换 #精灵 #2D #MMO
**触发词**：冒险岛风格、MapleStory、像素精灵、游戏角色转换  
**适用场景**：游戏角色转换、头像生成、像素艺术、游戏风格海报  
**比例**：1:1（1080x1080）  
**来源**：@20_v_e  
**链接**：https://x.com/20_v_e/status/2064627884086689912

---

## 一句话理解

将任意动漫/游戏/漫画角色转换为 **冒险岛（MapleStory）玩家精灵头像**，保持角色特征同时适配游戏角色比例和像素渲染风格。

---

## 核心特点

- **冒险岛角色比例**：2.0~2.3头身，头部+头发占 60~65%，躯干极小
- **像素渲染质感**：低分辨率游戏精灵放大感，禁止精细像素/HD像素
- **角色特征保留**：发型、发色、瞳色、服装、武器等核心特征必须保留
- **纯白底正方形**：1080x1080，纯白背景，单角色居中
- **图层规范**：Hair → Hat → Face Accessory → Top → Bottom → Shoes → Cape → Weapon

---

## 完整模板

```
[角色设定]
你是一位将动漫、游戏、漫画角色转换为 MapleStory 玩家角色精灵的像素艺术总监。

[输入]
角色名称 + 全身图片（推荐正面全身照）

[任务]
1. 分析 {角色名} 的代表外型特征：
   - 发型
   - 发色
   - 眼睛颜色
   - 代表服装
   - 代表配饰
   - 代表武器
   - 代表象征元素
   - 代表配色
2. 在保留上述特征的前提下，重新解读为 MapleStory 玩家角色结构。
3. 成品必须看起来像真正的 MapleStory 玩家角色精灵，而非通用像素艺术角色。

[规格一：冒险岛角色结构规范]
- 整体比例：头部+头发 60~65% / 躯干 15~18% / 腿部 20~25%，2.0~2.3 头身
- 视角：35~45 度 Quarter View，双眼均可见，近乎平面 2D 精灵
- 脸部：眼睛位于脸部下方，间距宽，横宽扁平眼，大瞳孔+高光，禁止画鼻子，嘴极小，带柔和腮红
- 颈部：禁止表现颈部，头部直接连接身体
- 头发：角色核心标识，体积比头骨大很多，优先轮廓，最小化发丝表达，存在顶部高光
- 身体：躯干极小，手臂短，腿部短，简化圆柱形四肢，最小化关节表达
- 装备图层顺序：Hair → Hat → Face Accessory → Top → Bottom → Shoes → Cape → Weapon
- 姿态：Idle Standing Pose，禁止跳跃/战斗/动作表演

[规格二：像素渲染规范]
禁止风格：
- 高分辨率像素艺术
- Ultra Detailed Pixel Art
- HD Pixel Art
- 精细像素艺术

目标效果（32~64px 游戏精灵放大感）：
- Low-resolution game sprite
- Enlarged MMORPG sprite
- Chunky pixel structure
- Grid-aligned pixel art
- Visible pixel blocks
- Clean 1px outline
- Limited color palette
- Flat color shading
- Solid tone pixel blocks
- Minimal shading
- No dithering
- No smooth gradients
- No airbrush effects

[规格三：输出条件]
- Canvas Size: 1080 x 1080
- Format: Perfect Square
- Background: Pure White (#FFFFFF)
- 角色数量：仅单角色
- 可见范围：全身可见
- 构图：居中，角色占画布高度约 75%
- 禁止元素：裁剪、额外角色、宠物、场景、背景物品、地面、文字、Logo、水印、UI

[规格四：绝对禁止风格]
Pokemon Style / Terraria Style / Stardew Valley Style
Ragnarok Online Style / JRPG Battle Sprite / Octopath Traveler Style
Western Cartoon / Disney Style / Realistic / Semi Realistic
3D Render / Illustration / Concept Art / Splash Art / Poster / Wallpaper
Anime Illustration / Digital Painting / Cinematic Lighting
Ultra Detailed Sprite / High Definition Pixel Art / Fine-Grained Pixel Art
Smooth Gradient Shading / Airbrush Shading

[收尾]
Create {角色名} as a true MapleStory player avatar sprite.
The result must look like an actual MapleStory player character converted from {角色名},
not a generic pixel-art character.
```

---

## 用户输入模板（简化版）

```
主题：{{角色名称}}
参考图：{{上传角色全身正面照}}
比例：{{1:1（1080x1080）}}
```

---

## 预设选项

| 变量 | 预设值 |
|------|--------|
| 角色来源 | 动漫角色、游戏角色、漫画角色、原创角色 |
| 角色类型 | 战士、法师、弓箭手、盗贼、通用 |
| 服装风格 | 休闲、正装、战斗服、礼服 |

---

## 风格锚点（必须保持）

- 2.0~2.3 头身比例，头部+头发占 60~65%
- 低分辨率像素块可见感，非 HD 像素
- 纯白底1080x1080 正方形
- 角色全身居中，占画布高度约 75%
- 特征保留：发型、发色、瞳色、服装等核心特征

---

## 🚫 避免风格

- HD 像素艺术、精细像素
- Pokemon/Stardew Valley/JRPG 战斗精灵风格
- 3D 渲染、数字绘画、电影光效
- 任何背景、场景、地面元素
- 跳跃/战斗/动作姿态

---

## 变量使用指南

> ⚠️ 此章节用于套用时的变量映射

| KV套用时的变量 | 对应风格文件变量 | 说明 |
|---------------|-----------------|------|
| 主标题（角色名） | {{角色名称}} | 用户输入的角色名称 |
| 角色参考图 | 参考图 + "保持角色一致性" | 不在变量里，用参考图保持一致 |
| 画面-场景 | 固定为纯白底 | 不变量，Canvas 必须 #FFFFFF |
| 色彩-主色 | 从参考图提取 | AI 自动保留角色配色 |
| IP形象 | 参考图 + "保持角色一致性" | 不在变量里，用参考图 |

> 📝 此风格不适用于 IP KV 套用 — 适合单角色头像/全身图生成

---


---

## 使用记录

| 日期 | 用户 | 场景 | 效果 | 备注 |
|------|------|------|------|------|
| - | - | - | - | - |

**评分标准**：
- ⭐⭐⭐⭐⭐ 优秀
- ⭐⭐⭐⭐ 良好
- ⭐⭐⭐ 一般
- ⭐⭐ 较差
- ⭐ 不推荐

**维度说明**：
- 稳定性：重复生成一致性
- 美观度：视觉效果
- 实用性：套用难易度

## 参考配图

![冒险岛角色精灵示例](https://malongan.github.io/images/styles_previews/maple_story_avatar.png)