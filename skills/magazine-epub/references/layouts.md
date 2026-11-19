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
| 画入纸面 | `paper-wash` | 章首通栏大图，下缘湿墨淡入纸面，接居中宋体章题、细线花饰和单栏正文 |

## 给用户选版

以已排过的 EPUB 为输入，生成可离线打开的 HTML 预览。默认对比输入 EPUB 和七款预设。脚本先按正式构建路径把每个预设打包成临时 EPUB，再从包里读取同一 spine 页和相对路径资源。卡片显示实际章节，可在框内继续阅读。黑场、错页、纵轴和画入纸面占整行。交付预览时把 HTML 与同级的 `*_files` 资源目录一起保留。

```bash
python3 scripts/layout_style.py book.epub --preview comparison.html
# 默认选首个带章首插画的正文页。也可用 --page OEBPS/chapter.xhtml
python3 scripts/layout_style.py book.epub --preview bold.html --layouts stage spread axis
python3 scripts/layout_style.py book.epub --preview wash.html --layouts paper-wash
# 从正式交付包直接渲染，可分别指定卷首与章节
python3 scripts/layout_style.py book_wash.epub --preview final.html --layouts original
```

正式交付仍需打开预览检查卷首和至少一个正常章节。错页和纵轴在窄屏回退单栏，竖题依赖 CSS `:has()` 和竖排。浏览器可以验证包内实际结构、图片和样式，Kindle 等阅读器可能调整分页、字体和可用宽度。

## 应用已选预设

```bash
python3 scripts/layout_style.py book.epub --preset amber -o book_amber.epub
```

输入需为使用 `magazine.css` 或 `stylesheet.css` 的杂志版 EPUB，且该样式表已在 OPF 登记。支持样式表位于包根目录或 `OEBPS/` 等子目录。新书先用 `build_epub.py` 构建并自检，再对产物应用所选预设。普通预设替换样式层，画入纸面还会更新章首页面和资源清单。对比不同预设时从同一个未应用结构换版的源 EPUB 开始。脚本校验 ZIP 与其余资源，并拒绝覆盖输出。

### 画入纸面与电纸书兼容

安装 Pillow 后运行 `python3 scripts/layout_style.py book.epub --preset paper-wash -o book_wash.epub`。脚本复用已有章首插画，横图取景约为 2:1，窄幅原画保留自身比例。已有大面积下缘留白时优先裁取上部，保留人物和主体。透明湿边写入 PNG，章题花饰作为实图入包。实际 XHTML 按章首图、章题、花饰、正文的顺序排列，图注移到当前章页末尾。已有章首锚点移到图前，正文、图注内容和原始插画文件都保留。

预览和验收时检查横幅取景有没有切到主体、窄屏是否仍然通栏、目录到章首是否从大图开始。水墨边和花饰靠包内图片显示，阅读器设置会影响页边距和分页。
