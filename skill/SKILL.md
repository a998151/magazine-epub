---
name: magazine-epub
description: |
  把已有 EPUB 电子书重排成杂志级排版：清理盗版推广页、章节标题语义化（p→h1）、
  每章配一张统一风格的 AI 插画与双语图注、生成刊头开篇页，
  并按 EPUB 规范重新打包（mimetype 首条不压缩 + 结构自检）。Use this skill when the user
  says "调整 epub 样式"、"做成杂志版"、"排版成电子书"、"每章配一张插画"、"图文并茂"、
  "给这本书配插图"、"传 Kindle 前先排版"、"epub 美化 / 重排版"。也适用于用户给出一个
  解压后的 .epub 目录或 zip 并希望重做版式。不适用于 EPUB→PDF/MOBI 格式转换、
  DRM 移除、正文改写/翻译，或只做几行 CSS 微调而不涉及结构与配图的需求。
---

# Magazine EPUB

把一本现有电子书重排成"可以拿到书架上装帧"的成品：结构语义化 + 每章专属插画 + 刊头页 + 规范打包。

**边界**：只改版式与结构，不改正文。抽言块、分栏、段落重排、删句改写都属于"改书"，
除非用户明确要求，默认一律不做——读者要的是原文照原样读。

## Inputs to collect

- **源文件路径**：`.epub`（zip）或已解压目录都行；两者 build 脚本都能吃
- **版式方向**：单栏（Kindle 首选）还是双栏；是否要刊头开篇页
- **章节表**：每章的中文名、英文名（若有）、序号、对应源文件
- **插画风格**：默认黑白木刻版画（适合严肃文学）；也可换风格
- **是否清理推广内容**：盗版电子书常有公众号/卖书广告页，默认清理

源文件是解压目录时先确认：目录里往往同时存在正文目录和 `content.opf`，直接把目录当源传即可。
目录名带 `.epub` 后缀不代表它是 zip 包——**先 `file` 看一眼**，别假设。

## Procedure

### 1. 先体检，别先动手

```bash
python3 scripts/inspect_epub.py <book.epub | 目录>
```

拿到四样东西：spine 顺序与章节名、每章样式类分布（calibre 转换的书全是 `calibre_8` 这类类名）、
推广关键词命中、疑似重复目录页。配置表里的 `chapters[].file` 必须来自这份输出，不能凭猜。

### 2. 定章节表与插画

每章的插画必须对得上原文的意象，否则就是装饰噪音。做法：

- 读每章首段 + 全文关键词统计（地名、器物、季节、天气）
- 挑出该章**最具体**的那个物象（"矿×37 + 教堂钟声" → 画矿与钟楼，不是画风景）
- 已有插画先复用，不要删；不够的再补

风格统一的关键是**一次生成多张**：同一批 prompt 里重复同一段风格描述词（"黑白木刻版画 / 刀刻线条 / 凸版印刷肌理 / 无文字"），
模型才会给出一套成图。构图按用途定：开篇页用 16:9，正文插图用 3:2。

### 3. 生成插画

```bash
# 一次一批，requests 数组里每项一个 prompt；风格描述词整批复用
mcode-tools connector call connector__matrix__generate_image --args-file args.json
# 产物是 node_id，用 mcode-tools get_asset_url <node_id> 取地址后 curl 落盘
```

图片风格偏好转彩时，可以生成后用 CSS `filter: grayscale(1) sepia(.2)` 统一压成双色，比重新生成快。

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
  "images": {"illust-coast": "/abs/path/illust-coast.jpg"}
}
```

```bash
python3 scripts/build_epub.py --config config.json
```

脚本会依次完成：清理推广段 → 标题 p→h1 → 前置页标记 → 生成刊头页 → 章节扉页+插图 →
插图压图入包 → manifest/spine/NCX 更新 → 注入样式 → 打包 → 结构自检。**自检不过不要交付**。

抽言（`pull_quote`）是**可选字段，默认不填**：用户没明确要就别加。填了的话脚本会从正文原段落里
把那句摘出来排成独立块——摘走句子等于改动原文，所以只在用户明确要求时才做。
填了但逐字匹配不上时脚本会告警，此时回原文核对字，不要放宽成模糊匹配。

### 5. 视觉验证（不能跳）

排版类改动不做截图验证等于没做。起个静态服务，用浏览器截图逐页看：

```bash
cd <workdir> && python3 -m http.server 8767 --bind 127.0.0.1
```

浏览器打开 `http://127.0.0.1:8765/...` 后截图（fullPage），重点看：图有没有裂、图宽是否等于正文栏宽、
正文段落是否完整连续（没有被意外切开/挖空）、首字下沉有没有跑到标题上。**预览页的图片路径要和成品同层级**，
否则会出现"图裂了"但成品其实是好的误判（预览页用相对路径 `images/xxx.jpg` 时，
预览目录里必须有 `images/` 子目录）。

### 6. 交付

给出 `.epub` 成品；另附一个内含同名 epub 的 `.zip`（Kindle 的 Send to Kindle 邮件通道常拒收
epub 附件，收 zip 更稳）。zip 用 Python `zipfile` 写，并置 `flag_bits |= 0x800`（UTF-8 文件名标志），
否则中文名在部分环境下会乱码。

## Output contract

- 一个 `.epub`（`mimetype` 必须是首条且 `ZIP_STORED`；`content.opf` 的 manifest/spine 与实际文件一一对应）
- 一个同名 `.zip` 包装（可选，Kindle 邮件上传用）
- 一个可重跑的构建目录：配置 JSON + `build_epub.py` + 样式表。**改样式必须改样式表重跑，不要手改打包后的 HTML**
- 交付时说明：图数 / 体积 / 哪些页做了结构改动 / Kindle 上的已知差异

## Failure handling

- **自检报 XML 解析失败**：多半是 `&nbsp;` 这类 XHTML 未定义实体，换成真实字符（`\u00a0`）
- **自检报 manifest/spine 目标缺失**：删了文件但没同步改 `content.opf`，或反之——两者必须一起改
- **抽言未匹配**：回原文逐字核对，不是脚本 bug
- **章节文件没找到标题**：源书的标题可能是 `<p class="calibre_6">` 而不是 `<h1>`，脚本会自动升级；
  若仍失败说明该文件结构特殊，手工确认后再改
- **图片体积超标**：调小配置里的 `image_max_width`（默认 1400）与 `image_quality`（默认 80）重跑
- **Kindle 上排版走样**：KPF 是独立转换引擎，不是浏览器，字体与分页由它重算。
  需要像素级一致就用 WebView 阅读器（epubjs）；Kindle 上只能保证结构（插图、图注、抽言、章号）在

## 阅读器兼容性要点

阅读器会用自己的样式盖掉书里的 CSS，动样式前先读 [references/compatibility.md](references/compatibility.md)：
epubjs 的行内字号、强制 font-family/line-height、h1 伪元素注入、首字下沉命中范围、
Kindle KPF 对双栏/多栏与 @page 的支持差异。

## Windows (win32) platform notes

脚本本身是 Python 3 跨平台（图片压缩优先 Pillow，退回 macOS `sips`，再退回原样复制）。
路径用正斜杠或 `Path` 对象，不要拼 `\`。本机若没有 `sips` 且没有 Pillow，
安装 Pillow 即可：`py -m pip install pillow`。
起预览服务的命令在 Windows 上是 `py -m http.server 8767 --bind 127.0.0.1`。

## Examples

Input: "把 /books/某书.epub 做成杂志版，每章配一张插画，我要传到 Kindle 看"

Output:
1. `inspect_epub.py` 输出 → 确认 7 个正文章节、2 个盗版广告页、1 页重复英文目录
2. 抽 7 章意象 → 复用已有 4 张、补 3 张木刻版画 → 落盘
3. 写配置（单栏、刊头页、每章插图 + 抽言）→ `build_epub.py` → 自检通过，4.9 MB
4. 起本地服务截 4 张图自检 → 交付 epub + zip
