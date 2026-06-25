# ST0151 电影蒙太奇三镜头运动海报
<!-- auto-gen: do not edit image URLs manually -->

## 基础信息

- **编号**: ST0151
- **名称**: 电影蒙太奇三镜头运动海报
- **作者**: Vigo Zhao (@VigoCreativeAI)
- **来源**: https://x.com/VigoCreativeAI/status/2069676060753432769
- **类型**: 创意 / 运动人物 / 黑白胶片风
- **比例**: 16:9 横版

## 特征

- **三格蒙太奇布局**: 左 ECU 特写占 60% 宽度 + 右上动作全景 + 右下细节/道具
- **奶油颗粒底**: 复古纸质感背景，颗粒可见
- **全黑白高粒感**: 黑白高对比度，重度胶片颗粒，电影感
- **单词巨字**: 底部横向铺满大字号单词标题
- **Metadata 条**: 顶底两端小写元信息标签，档案风格
- **手写签名**: 右下手写体签名
- **油墨溅射**: 1-2 个边角油墨/笔刷纹理
- **格式**: 16:9 横版

## 适用场景

- 运动员/极限运动者人物海报
- 个人品牌/运动员社交媒体封面
- 纪录片风格视觉内容
- 品牌运动员代言素材

## 提示词模板

```json
{
  "style_rules": {
    "background": "cream aged paper with visible grain",
    "layout": "3-panel: large ECU portrait LEFT (60% width, full height), two stacked shots RIGHT (WS action top, CU detail bottom)",
    "photo_style": "black and white, extreme high contrast, heavy film grain, cinematic",
    "typography": "one word title at bottom, massive distressed condensed black type, full-width",
    "metadata": "small caps tags top + bottom strip, case file aesthetic",
    "signature": "unique handwritten script bottom-right",
    "texture": "ink splatter or brush marks at 1-2 corners",
    "format": "16:9 horizontal"
  },
  "negative": "color, clean digital, multiple people, text overlaid on face, centered portrait",
  "variables": {
    "subject": "[one person + their discipline]",
    "ecl_shot": "[extreme close-up face, sweat/intensity, emotion fills frame]",
    "action_shot": "[wide/medium action shot in their environment]",
    "detail_shot": "[hands, equipment, or signature object of their craft]",
    "title_word": "[one word that names their world or quality]"
  }
}
```

## 生成要点

1. **ECU 优先**: 极近特写出现时，全景动作还没让人看见运动——但情绪已建立
2. **情绪先于动作**: 极近人像建立情绪连接，动作出现时变成"他的"动作而非"一个运动员的"动作
3. **三镜头叙事**: ECU 建立情绪 → WS 建立行动 → CU 建立技艺，剪辑师手法压缩进静帧
4. **模板不变换元素**: 风格锁死（奶油颗粒底、三格布局、单词巨字、metadata 条、签名、油墨溅射），只换运动类型/标题/metadata 内容
5. **负面提示**: 禁止彩色、干净数码感、多人、面部叠加文字、居中肖像

## 预览

![预览](https://malongan.github.io/style-source/images/styles_previews/vigo_film_montage_sport_poster_9f354591.webp)
