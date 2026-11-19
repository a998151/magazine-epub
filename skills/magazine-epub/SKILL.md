---
name: magazine-epub
description: |
  把已有 EPUB 电子书重排成杂志级排版：清理盗版推广页、章节标题语义化（p→h1）、
  按用户选择配统一风格的 AI 插画与双语图注、生成带图刊头开篇页，
  并按 EPUB 规范重新打包（mimetype 首条不压缩 + 结构自检）。Use this skill when the user
  says "调整 epub 样式"、"做成杂志版"、"排版成电子书"、"每章配一张插画"、"图文并茂"、
  "给这本书配插图"、"传 Kindle 前先排版"、"epub 美化 / 重排版"。也适用于用户给出一个
  解压后的 .epub 目录或 zip 并希望重做版式。不适用于 EPUB→PDF/MOBI 格式转换、
  DRM 移除、正文改写/翻译，或只做几行 CSS 微调而不涉及结构与配图的需求。
---

# Magazine EPUB

把一本现有电子书重排成杂志版：结构语义化、可选插画与带图刊头页、规范打包。

**边界**：只改版式与结构，不改正文。抽言块、分栏、段落重排、删句改写都属于"改书"，
除非用户明确要求，默认一律不做——读者要的是原文照原样读。

## Inputs to collect

- **源文件路径**：`.epub`（zip）或已解压目录都行；两者 build 脚本都能吃
- **版式方向**：单栏（Kindle 首选）还是双栏；是否要刊头开篇页
- **版式预设**：按 [版式预设](references/layouts.md) 选择；常规排版外可选黑场开篇、错页开篇、纵轴画册或画入纸面。版式与插画画风分别选择
- **章节表**：每章的中文名、英文名（若有）、序号、对应源文件
- **是否清理推广内容**：盗版电子书常有公众号/卖书广告页，默认清理

源文件是解压目录时先确认：目录里往往同时存在正文目录和 `content.opf`，直接把目录当源传即可。
目录名带 `.epub` 后缀不代表它是 zip 包——**先 `file` 看一眼**，别假设。

## Procedure

### 版式试样与换版

用户尚未指定版式时，提供 [版式预设](references/layouts.md) 中的选项。看效果时，用 `layout_style.py --preview` 从同一源 EPUB 临时打包各预设，再渲染各包里的同一实际页面。用户选定后，从该源 EPUB 用同一构建路径另存成品。画入纸面会把已有插画的横幅取景、原湿边和章题花饰做进 EPUB，并把图注移到首个章页末尾。新书先完成 EPUB 构建再应用预设。

### 0. 开工前确认是否生成插画

先问用户是否需要生成插画，等待答复后再处理 EPUB。已明确确认的选项可直接沿用，包括由 `magazine-html` 传入的选择。

- **不生成**：保留原书已有插图及其图注，跳过新图、提示词和新图注；继续清理、排版、打包和校验。
- **生成**：给出以下九个风格，等用户选定后再按统一风格生成。
  - **默认 · 经典黑白木刻版画**：粗粝刀痕、强明暗对比和大块留白，保留原有凸版印刷风格。
  - **黑白木刻 · 细线版**：用细刻线和交叉排线呈现层次，画面更细密。
  - **低饱和水彩**：用柔和色块、淡彩晕染和纸纹表现氛围。
  - **黑白水墨叙事（国风志怪）**：用水墨晕染铺出浓淡灰阶和雾气，以细线描清人物与关键物件，适合古风悬疑与志怪故事。
  - **维多利亚小说蚀刻风**：黑白细线与分层交叉排线塑造明暗，人物动作富戏剧性，场景边缘自然收进留白。
  - **石墨铅笔素描**：细颗粒与柔和灰阶，呈现纸上铅笔手稿质感。
  - **黑白钢笔线描**：清晰的黑色轮廓、轻重有别的线条和大面积留白。
  - **彩色木版套印**：用少量套色组织平面色块，保留刀痕和手工印刷感。
  - **水粉插画**：哑光、不透明的层叠色块，保留刷痕和厚实的笔触。

### 1. 先体检，别先动手

```bash
python3 scripts/inspect_epub.py <book.epub | 目录>
```

拿到四样东西：spine 顺序与章节名、每章样式类分布（calibre 转换的书全是 `calibre_8` 这类类名）、
推广关键词命中、疑似重复目录页。配置表里的 `chapters[].file` 必须来自这份输出，不能凭猜。

体检脚本会列出"疑似重复目录页"，**删之前先人眼确认**：译者注释页、书单页也是"一条链接配一段文字"，
很容易被误判成目录页，删掉就丢整页内容。

### 2. 定章节表与插画

两种模式都要定章节表。下列插画策划仅在用户选择生成后执行。

每章的插画必须对得上原文的意象，否则就是装饰噪音。做法：

- 读每章首段 + 全文关键词统计（地名、器物、季节、天气）
- 挑出该章**最具体**的那个物象（"矿×37 + 教堂钟声" → 画矿与钟楼，不是画风景）
- 已有插画先复用，不要删；不够的再补

生成前，为会在多张图中出现的角色整理一套基于原文的外形设定。按 [配图写法](references/recipes.md#跨图角色一致性) 复用角色描述和可用的参考图。开篇页用 16:9，正文插图用 3:2。

### 3. 生成插画

仅在用户确认生成且选定风格后执行此步。整套图复用所选风格的描述词，同一角色每次出场时沿用其外形设定。有反复出场的角色且工具支持参考图时，先选定一张形象清楚的图作为参考，再生成其余场景。插图入包前，把同一角色的各张图并排核对，单独修正或重生成走样的图，再复核。

```bash
# 一次一批，requests 数组里每项一个 prompt；风格描述词整批复用
mcode-tools connector call connector__matrix__generate_image --args-file args.json
# 产物是 node_id，用 mcode-tools get_asset_url <node_id> 取地址后 curl 落盘
```

### 4. 写配置并构建

配置字段说明见 [references/recipes.md](references/recipes.md)。骨架：

```json
{
  "source": "/abs/path/book.epub",
  "workdir": "/abs/path/work",
  "output": "/abs/path/book_magazine.epub",
  "book": { "title": "…", "title_accent": "…", "deck": "…", "byline": ["…"], "image": "illust-opener" },
  "toc_entries": [{"no": "01", "title": "秋"}],
  "drop_pages": ["1.html"],
  "front_matter": ["index_split_000.html"],
  "ad_patterns": ["本书由", "公众号", "ireadweek"],
  "chapters": [{
    "file": "index_split_003.html", "no": "01", "cn": "秋", "en": "Autumn",
    "image": "illust-coast", "alt": "…", "caption_cn": "…", "caption_en": "…"
  }],
  "images": {"illust-opener": "/abs/path/illust-opener.jpg", "illust-coast": "/abs/path/illust-coast.jpg"}
}
```

上面是配图配置示意。无新增插画时保留章节表，省略 `images` 和新增配图的 `image`、`image_alt` / `alt`、`caption_cn`、`caption_en` 字段。现有构建脚本要求新增刊头页带图，此模式下省略 `opener` 或设为 `false`，保留原书卷首内容。配图模式下需要新增刊头页时设 `opener: true`，并确保 `book.image` 对应 `images` 中的资源。

```bash
python3 scripts/build_epub.py --config config.json
```

脚本会清理推广段、将标题 p→h1、标记前置页并排版章节扉页。配置了图片时才插入和压缩图片，启用了带图刊头页时才生成刊头页。两种模式都会同步更新 manifest/spine/NCX/guide、注入样式、打包并执行结构自检。**自检不过不要交付**。

自检里包含一条**正文逐字比对**：构建脚本会在动手改结构前给每章正文存一份底稿，打包后再逐字比一次，
不一致就报错。这是"不改正文"这条承诺的证据，不是口号——正则改写很容易悄悄吃掉段落。

序、跋这类非虚构章节也可以写进 `chapters`（不填 `image` 即可），这样它们的标题样式与正文章节一致。

抽言（`pull_quote`）是**可选字段，默认不填**：用户没明确要就别加。填了的话脚本会从正文原段落里
把那句摘出来排成独立块——摘走句子等于改动原文，所以只在用户明确要求时才做。
填了但逐字匹配不上时脚本会告警，此时回原文核对字，不要放宽成模糊匹配。

### 4.1 Kindle 成品轻量化

目标是 Kindle 时，在完成所有版式修改之后、预览之前，用 `scripts/kindle_compact.py` 从已打包 EPUB 另存轻量版。已有 EPUB 只需减小体积时也直接运行这一步。

```bash
python3 scripts/kindle_compact.py book.epub -o book_kindle.epub
```

依赖 Pillow。非封面 JPG/PNG 默认长边最多 1100 px、单张最多 160 KiB，并在写出前核对最终体积。画入纸面的原湿边合成到浅纸色 JPEG，章题花饰保留，包内仅清理可确认已替换且无引用的原图副本。`--no-outer-margins` 清除书内外边距和画入纸面章首容器的外圈留白，并取消有编号的第 1 小节或独立配图章首正文额外的段落左右留白。交付时称为「书内零外边距」，实机贴屏须单独验证。详见 [Kindle 轻量化参数](references/layouts.md#kindle-轻量化)。

### 5. 视觉验证（不能跳）

从最终交付的 EPUB 取页面做截图核对。用 [版式预览命令](references/layouts.md#给用户选版) 指定 `--layouts original`，或把实际成品解包到临时目录后起本地服务：

```bash
cd <unpacked-final-epub> && python3 -m http.server 8767 --bind 127.0.0.1
```

用浏览器截图检查卷首和至少一个正常章节，核对插画、正文连续性和首字下沉。画入纸面额外检查窄屏通栏、湿边、章题花饰、图注位置，以及目录是否跳到图前。浏览器结果作为网页预览交付，实际观察到的设备分页另行记录。

Kindle 轻量版以最终压缩包为验收输入，检查正文左右留白、插画细节和目录链接，并记录压缩前后整包体积与最大单张插图体积。书内零外边距模式同时检查章首图铺满可用版心，以及章首正文相对自身容器的段落边距。有编号小节时，再对照同章第 1、2 小节。浏览器结果只记录为书内版心验证。Kindle 的设备边距设置见 [亚马逊显示设置说明](https://digprjsurvey.amazon.com/csad/help/node/T5Y94BzSCGwm0vd75W)。

### 6. 交付

给出 `.epub` 成品。Kindle 交付优先提供轻量 EPUB，可通过 [Send to Kindle](https://www.amazon.com/sendtokindle) 上传。按用户要求附 ZIP 时，使用 Python `zipfile` 保留压缩包里的中文文件名。

## Output contract

- 一个 `.epub`（两种模式均通过正文逐字比对、结构自检和从成品包取页的截图验收；`mimetype` 必须是首条且 `ZIP_STORED`，manifest/spine 的引用目标均有效）
- 插画按用户选择验收：生成模式检查新图风格、同一角色的跨图辨识度、图注、显示及入包引用；不生成模式检查无新增插图、图注或空图引用，原有图片仍可显示
- Kindle 成品默认通过轻量化和成品预览，交付时注明压缩前后体积；有明确整包预算时使用 `--max-book-mib` 校验
- 一个同名 `.zip` 包装（用户需要时提供）
- 一个可重跑的构建目录。新书保留配置 JSON、构建脚本和样式表。换版保留输入 EPUB 路径、所选预设和构建命令。
- 交付时说明：图数 / 体积 / 哪些页做了结构改动 / Kindle 上的已知差异

## Failure handling

- **自检报 XML 解析失败**：多半是 `&nbsp;` 这类 XHTML 未定义实体，换成真实字符（`\u00a0`）
- **自检报 manifest/spine 目标缺失**：删了文件但没同步改 `content.opf`，或反之——两者必须一起改
- **抽言未匹配**：回原文逐字核对，不是脚本 bug
- **章节文件没找到标题**：源书的标题可能是 `<p class="calibre_6">` 而不是 `<h1>`，脚本会自动升级；
  若仍失败说明该文件结构特殊，手工确认后再改
- **图片体积超标**：在 Kindle 轻量化阶段调整 `--max-side` 或 `--max-image-kib`，用最终 EPUB 联合检查图像细节和整包体积。其他版式的初次构建可调 `image_max_width` 与 `image_quality`
- **Kindle 上排版走样**：KPF 是独立转换引擎，不是浏览器，字体与分页由它重算。
  需要像素级一致就用 WebView 阅读器（epubjs）；Kindle 上只能保证结构（插图、图注、抽言、章号）在

## 阅读器兼容性要点

阅读器会用自己的样式盖掉书里的 CSS，动样式前先读 [references/compatibility.md](references/compatibility.md)：
epubjs 的行内字号、强制 font-family/line-height、h1 伪元素注入、首字下沉命中范围、
Kindle KPF 对双栏/多栏与 @page 的支持差异。

## Windows (win32) platform notes

脚本使用 Python 3，路径用正斜杠或 `Path` 对象。Kindle 轻量化和画入纸面需要 Pillow，Windows 可用 `py -m pip install Pillow` 安装。
起预览服务的命令在 Windows 上是 `py -m http.server 8767 --bind 127.0.0.1`。

## Examples

Input: "把 /books/某书.epub 做成杂志版，每章配一张插画，我要传到 Kindle 看"

Output:
1. 确认生成插画并等用户选定风格
2. `inspect_epub.py` 输出 → 确认 7 个正文章节、2 个盗版广告页、1 页重复英文目录
3. 抽 7 章意象 → 复用已有 4 张、按所选风格补 3 张 → 落盘
4. 写配置 → `build_epub.py` → 结构和正文自检通过
5. 打包后先另存 Kindle 轻量版 → 从轻量版做截图验收 → 交付 EPUB 和体积对比
