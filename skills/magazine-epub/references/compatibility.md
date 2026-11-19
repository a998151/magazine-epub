# 阅读器兼容性要点

排版类工作最费时间的不是写 CSS，而是"明明写了却不生效"。原因通常是阅读器用自己的方式盖掉了书的样式。
下面每一条都是实际踩过的。

---

## epubjs（基于 epubjs 的 WebView 阅读器，如 epub-reader）

### 字号是行内样式，不是样式表规则

epubjs 的 `rendition.themes.fontSize(size)` 走 `content.css(property, value)`，
最终是 `element.style.setProperty(...)`——写在 `<body>` 的**行内样式**上。

- 行内样式优先级高于任何选择器规则 → 书里 `body { font-size: 18px }` 会被阅读器设置直接覆盖，这是好事
- 但书里若写 `.calibre { font-size: 1em }`（类选择器挂在 body 上），**行内样式仍然赢**，
  所以 calibre 转换的书在 epubjs 里字号其实是能改的
- 结论：不要在 body 上叠加"看起来更精确"的类选择器字号，那是无效功；也不要指望它能覆盖阅读器

### font-family / line-height 被强制 !important

常见注入写法：

```css
body, body * { font-family: <用户选择> !important; line-height: <用户选择> !important; }
```

- `body *` 会命中每个后代元素 → 书里写什么字体行距都没用
- 推论：书内 CSS 的 font-family / line-height 只对**不用该阅读器**的场景有意义
- 推论：想让某个元素（如标题）有独立行距，必须同样写 `!important` 且特异性更高

### h1 会被注入伪元素装饰

有些阅读器给 `body h1::after` 注入印章/图标一类的装饰。要去掉：

```css
body h1::after { content: none !important; }
```

注入规则通常不带 `!important`，所以书里的 `!important` 能盖住。

### 首字下沉会命中页面的第一个段落

典型选择器：`body > p:first-of-type:not(:empty)::first-letter`

- 如果章节标题是 `<p>`（calibre 的默认做法），**首字下沉会落到标题的第一个字上**，标题被撑歪
- 修法一（推荐）：把标题升级成 `<h1>`，第一个 `<p>` 自然变成正文首段，下沉落回正文
- 修法二：给前置页（版权页/目录页/注释页）加一个类，用更高特异性关掉：

```css
body.front-matter > p:first-of-type:not(:empty)::first-letter {
    font-size: inherit !important; float: none !important;
    line-height: inherit !important; font-weight: inherit !important;
    margin: 0 !important; color: inherit !important; text-shadow: none !important;
}
```

`body.front-matter > p:first-of-type:not(:empty)::first-letter` 的特异性高于阅读器的
`body > p:first-of-type:not(:empty)::first-letter`（多一个类），配合 `!important` 稳定覆盖。

### 主题色由阅读器接管

阅读器通常注入 `body { color: <主题文字色>; background: transparent !important }`。

- 书里**不要写死前景色**（`#333`、`#000`），夜间模式下会变成"黑底黑字"
- 需要层次差异时用 `opacity`（对当前色生效，深浅底都协调），不要用另一个颜色
- 链接尤其危险：默认的 `a { color: #00c }` 在深色主题下会变成亮蓝 + 蓝底。
  一律 `a { color: inherit; }`

### 版心宽度

阅读器通常用 `--reader-content-width` 之类控制 iframe 宽度。
**书里不要设 `max-width`**，否则用户把版心拉到 100% 也没反应，看起来像 bug。

---

## Kindle（KPF 转换引擎）

- Kindle 用自己的引擎重排，**不是浏览器**：书里的 `@page`、`column-count`、伪元素基本不可靠
- **双栏在 Kindle 上阅读体验很差**（要来回跳视线）。要上 Kindle 就单栏
- `@page` 的 margin 只在部分设备生效，实际左右留白由 KPF 决定
- 图片：Kindle 轻量版按 [轻量化参数](layouts.md#kindle-轻量化) 处理；亚马逊说明透明区域在转换时会转为白色。[Kindle 重排版图像指南](https://kdp.amazon.com/en_US/help/topic/G75V4YX5X8GRGXWV)
- 章节插画会成为整页大图，Kindle 会自动缩放到屏宽，视觉上等价于"宽度等于正文栏"
- 字体：Kindle 自带中文衬线（"默认"字体），书里写 `Songti SC` 等系统字体在 Kindle 上不生效，
  会回落到 Kindle 自带字体——这通常是可接受的
- 首字下沉：KPF 支持 `:first-letter`，但只能作用于每章第一段，所以把标题做成 `<h1>` 同样重要
- 转换后版面与浏览器预览必然有差异，只能保证**结构**（插图、图注、章号、标题层级）在

---

## Apple Books / 微信读书 / Kobo 等

- 基本按标准 CSS 走，书里的相对单位、媒体查询、`:first-letter` 大多有效
- Apple Books 对 EPUB2 用 NCX 导航，对 EPUB3 用 `nav.xhtml`；两者都留着最保险
- 微信读书会用自己的主题色接管，同样适用"不写死颜色"原则

---

## 写 CSS 的通用原则（任何阅读器都成立）

1. 前景色一律继承，用 `opacity` 做层次
2. 字号、间距、行距用 `em`/`%` 相对单位
3. 不在 `body` 上叠类选择器字号
4. 图片 `max-width: 100%; height: auto;`，不要写死像素尺寸
5. `page-break-after: avoid` 保护标题不与正文分离
6. 需要覆盖阅读器注入的规则时，用**更高特异性 + `!important`**，并写注释说明覆盖对象
