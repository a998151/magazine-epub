# magazine-epub

把一本已有的 EPUB 电子书，重排成可以直接上架的**杂志级成品**：结构语义化、每章配一张专属插画、生成刊头开篇页，按 EPUB 规范重新打包，可直接发到 Kindle。

这是一个跨 harness 的 **Agent Skill**（agents.md 规范），附带两个确定性脚本：体检器 + 配置驱动构建器。

![刊头开篇页](docs/01-opening.svg)

---

## 它解决什么

从各处流传来的 EPUB（尤其是经过转换器处理的中文旧书）通常有三个问题：

| 问题 | 表现 | 本 skill 的处理 |
| --- | --- | --- |
| 排版是转换器默认值 | 标题是 `<p>` 不是 `<h1>`；章节靠空行分隔；链接是写死的 `#00c` 蓝 | 标题语义化，样式表整体重写 |
| 夹带盗版推广 | 整页公众号广告页、版权页里的微信号 | 按关键词整段清除 |
| 没有视觉 | 纯文字，读起来像 txt | 每章配一张统一风格的插画 + 双语图注 + 刊头开篇页 |

外加一条容易被忽略的：**很多阅读器会把书里的样式盖掉**。epubjs 会用 `!important` 强制字体与行距，会给 `<h1>` 注入装饰，还会让首字下沉打到标题的第一个字上。这份样式表和配套文档都按这些坑设计过。

---

## 产出长什么样

**刊头开篇页** — 刊头条 / 巨标题 / 英文题名 / 导语 / 作者行 / 满幅主图 / 目录条

![章节扉页](docs/02-chapter.svg)

**章节扉页** — 朱砂章号 / 中英章名 / 专属插画（宽度与正文栏一致）/ 双语图注，正文保持原样往下排

![另一章](docs/03-chapter.svg)

**在 epubjs 阅读器里** — 样式表与阅读器注入的主题、字体、行距共存，夜间与护眼模式自动反色

![阅读器内效果](docs/04-reader-app.svg)

> 演示截图含少量受版权保护文本作为版式示例。

---

## 安装

仓库里的 skill 放在 `skills/magazine-epub/` 目录（目录名与 skill 名一致），结构符合 agents.md 规范。把它放进任意 harness 的 skills 根目录即可：

```bash
# 通用（Codex / Cursor / Claude Code / MCode 等读 ~/.agents/skills 的）
git clone https://github.com/a998151/magazine-epub.git
cp -R magazine-epub/skills/magazine-epub ~/.agents/skills/

# 或者直接解压 release 里的 magazine-epub-skill.zip
unzip magazine-epub-skill.zip -d ~/.agents/skills/
```

装完新开一个会话，说一句「把这个 epub 做成杂志版」就会触发。

---

## 用法

### 方式一：交给 agent（推荐）

直接说需求即可，触发词例如：

- 「把 `某书.epub` 做成杂志版排版」
- 「每章配一张插画，风格要统一」
- 「这本书要传 Kindle，帮我排一下版」
- 「给这本 EPUB 加刊头开篇页和章节插图」

agent 会自动走完：体检 → 确认章节表与插画意象 → 批量生成插画 → 构建 → 自检 → 截图验收 → 打包交付。

### 方式二：手动跑脚本

```bash
cd skill

# 1) 体检：章节表、样式类分布、推广词、重复目录页
python3 scripts/inspect_epub.py /path/to/book.epub

# 2) 按体检结果写配置
$EDITOR config.json

# 3) 构建（自带结构自检，不过则退出码非 0）
python3 scripts/build_epub.py --config config.json
```

配置字段全表见 [`skill/references/recipes.md`](skill/references/recipes.md)，最小示例：

```json
{
  "source": "/path/to/book.epub",
  "output": "/path/to/book_magazine.epub",
  "book": { "title": "书名", "title_accent": "高亮片段", "deck": "导语", "image": "illust-opener" },
  "drop_pages": ["1.html"],
  "ad_patterns": ["本书由", "公众号"],
  "chapters": [{
    "file": "index_split_003.html", "no": "01", "cn": "秋", "en": "Autumn",
    "image": "illust-coast", "alt": "插图描述",
    "caption_cn": "图注中文。", "caption_en": "Caption in English."
  }],
  "images": { "illust-coast": "/abs/path/illust-coast.jpg" }
}
```

---

## 工作原理

```
inspect_epub.py                build_epub.py
      │                              │
      ├─ spine 顺序 / 章节名          ├─ 清理推广段落
      ├─ 每章样式类分布               ├─ 标题 p → h1（语义化）
      ├─ 推广词命中                   ├─ 前置页标记 front-matter
      └─ 疑似重复目录页               ├─ 生成刊头开篇页 opener.html
                                     ├─ 章节扉页：章号 + 章名 + 插图 + 图注
                                     ├─ 插画压图入包 images/
                                     ├─ manifest / spine / NCX / guide 同步更新
                                     ├─ 注入 magazine.css
                                     ├─ 打包（mimetype 首条且不压缩）
                                     └─ 结构自检 → 不过则退出码非 0
```

自检里有一条**正文逐字比对**：构建脚本在动手改结构前给每章正文存底稿，打包后再逐字比一次，
不一致就报错。这是「不改正文」这条承诺的证据——正则改写很容易悄悄吃掉段落。

**插画怎么配**：先读每章首段和全文关键词计数，找出该章**最具体**的物象（"矿×37 + 教堂钟声" → 画矿与钟楼，而不是画风景），已有插画先复用，缺了才补。一次批量生成时重复同一段风格描述词，模型才会给出一套成图。

**一条硬规矩**：只改版式与结构，不改正文。抽言块、分栏、重排段落都属于改书，除非明确要求否则一律不做——读者要的是原文照原样读。

---

## 兼容性

| 阅读器 | 表现 |
| --- | --- |
| Kindle（KPF） | 独立转换引擎，不是浏览器。结构（插图、图注、章号、标题层级）保留；字体与分页由 KPF 重算，与浏览器预览必然有差异。**双栏在 Kindle 上体验很差**，本 skill 默认单栏 |
| epubjs（WebView） | 字号是 body 上的行内样式，能覆盖；font-family / line-height 被 `!important` 强制；`<h1>` 会被注入装饰伪元素；首字下沉默认命中页面第一个段落 |
| Apple Books / 微信读书 / Kobo | 基本按标准 CSS 走 |

完整踩坑记录见 [`skill/references/compatibility.md`](skill/references/compatibility.md)。

---

## 目录结构

```
magazine-epub/
├── README.md
├── docs/                      演示截图
└── skills/
    └── magazine-epub/         目录名 = skill 名，可直接 cp 到任意 skills 根目录
        ├── SKILL.md           触发条件 / 执行流程 / 输出契约 / 失败处理
        ├── agents/openai.yaml 跨 harness 展示元信息
        ├── scripts/
        │   ├── inspect_epub.py 体检器
        │   └── build_epub.py   配置驱动构建器（打包 + 自检）
        └── references/
            ├── magazine.css   杂志版样式表（构建时注入）
            ├── page.css       @page 分页样式
            ├── recipes.md     配置字段表 + 插画/图注策划方法
            └── compatibility.md 阅读器兼容要点
```

**依赖**：Python 3（标准库即可）。图片压缩优先 Pillow，其次 macOS `sips`，最后原样复制。插画生成走 `mcode-tools` 的 `connector__matrix__generate_image`。

---

## License

尚未指定 License。公开发布前请自行添加一个（如 MIT），或在 README 里注明保留所有权利。
