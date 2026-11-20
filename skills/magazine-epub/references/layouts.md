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

错页和纵轴在窄屏回退单栏，竖题依赖 CSS `:has()` 和竖排。

## 应用已选预设

```bash
python3 scripts/layout_style.py book.epub --preset amber -o book_amber.epub
```

输入使用已在 OPF 登记的 `magazine.css` 或 `stylesheet.css`。普通预设替换样式层，画入纸面还会更新章首页面和资源清单。对比预设时从同一个未做结构换版的 EPUB 开始。

### 画入纸面与电纸书兼容

安装 Pillow 后运行 `python3 scripts/layout_style.py book.epub --preset paper-wash -o book_wash.epub`。横图取景约为 2:1，窄图保留原比例。下缘留白较多时优先取上部，预览确认主体未被切掉。版式阶段生成带原湿边的透明 PNG 和章题花饰，既有的章题锚点移到图前。保留这一阶段的 EPUB，供不同设备版重新打包。

## Kindle 轻量化

```bash
python3 scripts/kindle_compact.py book_wash.epub -o book_kindle.epub
python3 scripts/layout_style.py book_kindle.epub --preview kindle.html --layouts original
python3 scripts/kindle_compact.py book_wash.epub --wet-edge alpha -o book_alpha.epub
```

默认将非封面 JPG/PNG 限制在长边 1100 px、单张 160 KiB 内。封面使用至少 1600 px 和 256 KiB 的预算。`--max-side` 和 `--max-image-kib` 可调，`--max-book-mib` 用于明确的整包上限。

画入纸面的默认 `--wet-edge white` 清掉边缘极淡的残影，保留窄过渡，并将清除区以纯白写入索引 PNG。浅色页面也使用纯白。PNG 保留原路径和 MIME 类型，脚本仅清理已替换且无引用的原图副本。`--wet-edge alpha` 供其他阅读器使用，清除区保留完全透明。已压成浅纸色 JPEG 的旧版需要从含原始透明湿边 PNG 的 EPUB 重新打包。

需要书内零外边距时加 `--no-outer-margins`。脚本清零书内页边距与章首容器外圈间距。有编号的第 1 小节和带 `chapter-page` 标记的独立配图章首，会取消样式额外加给段落的左右留白。Kindle 的设备留白由阅读器设置控制。[亚马逊显示设置说明](https://digprjsurvey.amazon.com/csad/help/node/T5Y94BzSCGwm0vd75W)
