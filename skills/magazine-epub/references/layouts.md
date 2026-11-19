# 版式预设

版式与插画画风分别选择。预设以现有杂志 CSS 为底，保留正文与原有阅读顺序。全书正文沿用阅读器主题；黑场开篇只在章节题头和插图区域使用成对的深底浅字。

| 预设 | ID | 视觉特征 |
| --- | --- | --- |
| 经典杂志 / 原版 | 默认 | 现有杂志排版，供对照 |
| 青墨留白 | `ink` | 居中宋体标题、内收插图、居中双语图注与较大的留白 |
| 琥珀档案 | `amber` | 琥珀边线、左齐标题、框线围合的插图和图注 |
| 现代书刊 | `modern` | 左齐黑体标题、粗细横线、满栏插图和紧凑图注 |
| 黑场开篇 | `stage` | 大标题与插画合成炭黑开篇，正文回到纸面 |
| 错页开篇 | `spread` | 宽屏图右文左，越过插图后恢复整栏 |
| 纵轴画册 | `axis` | 宽屏竖排章题和横图并列，正文在图下展开 |
| 画入纸面 | `paper-wash` | 章首通栏大图，下缘湿墨淡入纸面，接居中楷体章题、细线花饰和单栏正文 |

## 给用户选版

以已排过的 EPUB 为输入，生成可离线打开的 HTML 样张。默认显示原版对照和七款可选预设，使用同一章、同一张原图和同一组正文节选。黑场、错页、纵轴和画入纸面占整行。用 `--layouts` 可挑选并排列要比较的样张。

```bash
python3 scripts/layout_style.py book.epub --preview comparison.html
# 默认选首个带刊物插图的章节。若需指定，用 --page OEBPS/chapter.xhtml
python3 scripts/layout_style.py book.epub --preview bold.html --layouts stage spread axis
python3 scripts/layout_style.py book.epub --preview wash.html --layouts paper-wash
```

样张展示排版方向。正式交付仍按主流程视觉验收，检查卷首和至少一个正常章节。错页和纵轴在窄屏回退单栏，竖题还要求支持 CSS `:has()` 和竖排。阅读器字体、主题和分页可能覆盖部分表现，不能把浏览器样张当作 Kindle 的实际分页。

## 应用已选预设

```bash
python3 scripts/layout_style.py book.epub --preset amber -o book_amber.epub
```

输入需为使用 `magazine.css` 或 `stylesheet.css` 的杂志版 EPUB，且该样式表已在 OPF 登记。支持样式表位于包根目录或 `OEBPS/` 等子目录。新书先用 `build_epub.py` 构建并自检，再对产物应用所选预设。脚本只更新样式表，替换本工具此前写入的版式层，校验 ZIP 条目及其他资源的 CRC，并拒绝覆盖输出。

### 画入纸面与电纸书兼容

`--preset paper-wash` 在支持 `:has()`、Flex 和遮罩的阅读器中可把旧书的章首图提至章题上方，并显示湿墨边。图宽服从阅读器的可用栏宽。面向 Kindle 且要求图在标题上方时，在可重跑的源 XHTML 中把章首插图块提前到章题之前，并加 `paper-wash-lead` 类，检查目录链接跳到章首。湿边优先使用本身带淡出留白的原画，让该效果不依赖 CSS 遮罩。换版工具保留正文、目录和插画文件；未做对应源页调整时，部分阅读器会按原有图文顺序显示。
