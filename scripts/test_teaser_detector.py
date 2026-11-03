"""teaser 检测的回归测试。

语料 = 中文化之前的真实英文 prompt（git show 61a08d6^:data/styles.json 抽样）
+ 8 种 teaser 变体。规则迭代时必须跑它，确保：
  1) 真实完整 prompt 零硬报警（不误伤）
  2) 软提示只命中已知的[短且无槽位]边界（korean_illustration）
  3) teaser 变体 100% 命中（不漏报）

跑法：python3 scripts/test_teaser_detector.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_twitter import detect_teaser, looks_like_teaser

# 真实 prompt 抽样（自动生成，勿手改；来自 git show 61a08d6^:data/styles.json）
REAL_PROMPTS = [
    ('chibi_q_version_character', 'Chibi style, {character} {action} {opponent/situation}, in the style of {style_reference}, cute background, 2D game art, high resolution, in focus, {background/environment}, anime style, dynamic pose, Epic and dynamic\n'),
    ('retro_cel_animation', 'Retro cel animation style, {subject} in a {setting}, hand-painted background, visible cel lines, muted {color1} and {color2} palette, soft grain, gentle lighting, expressive character design, vintage animation frame aesthetic'),
    ('vigo_urban_transit_doodle_diary', 'Create a 16:9 image in urban-transit-doodle-diary-style featuring {SUBJECT} {SUBJECT_ACTION}, with {PRODUCT_OR_PROP}, set in {LOCATION}. Include {BACKGROUND_ELEMENTS}, main text "{MAIN_TEXT}", secondary text "{SECONDARY_TEXT}", {ACCENT_SYMBOL}, and {WARDROBE_STYLE}.'),
    ('korean_illustration', 'Korean illustration style, cute character having a picnic on the grass with friends, spring colors, soft green meadow, blooming flowers, checkered picnic blanket, baskets and food, line drawing with coloring, natural hand-drawn feel, delicate pencil lines, soft pastel colors, whimsical and cozy atmosphere. Maintain consistency with the reference character'),
    ('korean_illustration', 'Korean illustration style, cute character having a picnic on the grass with friends, spring colors, soft green meadow, blooming flowers, checkered picnic blanket, baskets and food, line drawing with coloring, natural hand-drawn feel, delicate pencil lines, soft pastel colors, whimsical and cozy atmosphere. Maintain consistency with the reference character'),
    ('vigo_folded_newspaper_product_ad', 'Create a 16:9 raster advertisement in the "Folded Newspaper Product Ad Style". Subject: {SUBJECT}. Subject action: {SUBJECT_ACTION}. Product or prop: {PRODUCT_OR_PROP}. Location or campaign context: {LOCATION}. Background newspaper elements: {BACKGROUND_ELEMENTS}. Main headline text: {MAIN_TEXT}. Secondary text and microcopy: {SECONDARY_TEXT}. Accent symbol: {ACCENT_SYMBOL}. Styling direction: {WARDROBE_STYLE}. Preserve these style fidelity anchors: the core visual anchors of this style. Avoid these source-content elements: watermarks, real logos, and commercial advertising. Build the image as a wrinkled off-white broadsheet newspaper page with visible folds, dense bilingual body-copy columns, rule lines, boxed captions, distressed black ink, antique-gold display headline blocks, one angled rubber-stamp coupon frame, one narrow red vertical editorial date tab, and one huge photorealistic commercial product hero overlapping the lower or central page. The product should be tactile, glossy or material-rich, partly supported by paper, cloth, foil, tray, wrapper, sleeve, or prop details. Keep the page graphics flat and printed while the product is realistic and foregrounded. The layout should feel crowded, promotional, newspaper-like, nostalgic, and tactile. Change all literal content from the reference while preserving the folded newspaper ad visual system.'),
]

# teaser 变体（实测 + 构造）
TEASER_VARIANTS = [
    ('实测真身', 'GPT-5.6 Sol / art-directed prompt system\n\nThe 3-variable prompt system for turning any word or UI command into a precision optical-glass 3D button - without rebuilding the geometry, material, reflections, lighting & camera setup\n\nPrompt 🔽'),
    ('箭头变体', 'A new prompt system for cinematic product shots.\n\nPrompt 👇'),
    ('冒号结尾', 'Full prompt for editorial poster design:\n\nPrompt:'),
    ('see below', 'Here is the complete prompt for a 3D button.\n\nSee below'),
    ('thread', 'Sharing my prompt system today.\n\nFull prompt in the thread 🧵'),
    ('纯箭头', 'New poster prompt dropping tomorrow.\n\n👇'),
    ('中文', '新的海报提示词分享。\n\n完整提示词见下方'),
    ('评论区', 'Prompt below! check the replies for the full version\n\nSee replies'),
]


def main():
    errors = []
    soft_allowed = {'korean_illustration'}
    for sid, p in REAL_PROMPTS:
        hard, soft = detect_teaser(p)
        if hard:
            errors.append('误报：真实 prompt [%s] 被硬报警 (len=%d)' % (sid, len(p.strip())))
        if soft and sid not in soft_allowed:
            errors.append('软提示命中非预期边界 [%s] (len=%d)' % (sid, len(p.strip())))
    for name, v in TEASER_VARIANTS:
        hard, soft = detect_teaser(v)
        if not hard:
            errors.append('漏报：teaser 变体 [%s] 未硬命中 (len=%d)' % (name, len(v)))
    for sid, p in REAL_PROMPTS:
        if looks_like_teaser(p):
            errors.append('looks_like_teaser 误报 [%s]' % sid)
    for name, v in TEASER_VARIANTS:
        if not looks_like_teaser(v):
            errors.append('looks_like_teaser 漏报 [%s]' % name)
    if errors:
        print('teaser 检测回归测试失败：')
        for e in errors:
            print('   -', e)
        sys.exit(1)
    print('teaser 检测回归测试通过：%d 条真实 prompt 零误报，%d 种 teaser 变体全命中' % (len(REAL_PROMPTS), len(TEASER_VARIANTS)))
    sys.exit(0)


if __name__ == '__main__':
    main()
