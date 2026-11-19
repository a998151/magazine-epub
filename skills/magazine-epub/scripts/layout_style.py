#!/usr/bin/env python3
"""Compare or apply CSS-only presets to an already typeset EPUB."""

import argparse
import base64
from copy import copy
import html
import mimetypes
import posixpath
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

LAYOUTS = {
    "original": ("原版对照", "沿用源书的标题、图片比例和图注。"),
    "ink": ("青墨留白", "宋体居中标题、内收插图和居中双语图注。"),
    "amber": ("琥珀档案", "左齐标题、琥珀色边线与档案式插画框。"),
    "modern": ("现代书刊", "左齐黑体标题、粗细横线和满栏插图。"),
    "stage": ("黑场开篇", "大号标题和原插画同置炭黑色块，正文从浅底重新起笔。"),
    "spread": ("错页开篇", "宽屏先并读左侧正文与右侧插图，窄屏自然回到单栏。"),
    "axis": ("纵轴画册", "宽屏竖排章题作书脊，横幅插画放在右侧，正文在图下展开。"),
    "paper-wash": ("画入纸面", "页顶一张通栏大图，墨边淡入纸白，下接居中章题与细线花饰。"),
}
WIDE_LAYOUTS = {"stage", "spread", "axis", "paper-wash"}
LAYOUT_DIR = Path(__file__).resolve().parent.parent / "references" / "layouts"
OVERLAY = "\n/* magazine-epub:layout */\n"


def member_path(document, reference):
    part = urlsplit(reference)
    if part.scheme or part.netloc or not part.path:
        return None
    return posixpath.normpath(posixpath.join(posixpath.dirname(document), unquote(part.path)))


def read_book(archive):
    container = ET.fromstring(archive.read("META-INF/container.xml"))
    opf_path = container.find(".//{*}rootfile").attrib["full-path"]
    package = ET.fromstring(archive.read(opf_path))
    title = package.findtext("./{*}metadata/{*}title") or "书籍样张"
    items = {item.attrib["id"]: (member_path(opf_path, item.attrib["href"]), item.get("media-type"))
             for item in package.findall("./{*}manifest/{*}item")}
    spine = [items[ref.attrib["idref"]][0] for ref in package.findall("./{*}spine/{*}itemref")]
    styles = [path for path, kind in items.values() if kind == "text/css" and path
              and posixpath.basename(path) in {"magazine.css", "stylesheet.css"}]
    if len(styles) != 1:
        raise ValueError("需要且只能有一份已登记的 magazine.css 或 stylesheet.css")
    return title, spine, styles[0]


def with_layout(css, layout):
    base = css.split(OVERLAY, 1)[0]
    if layout == "original":
        return base
    return base + OVERLAY + (LAYOUT_DIR / f"{layout}.css").read_text(encoding="utf-8")


def preview(archive, title, spine, stylesheet, target, page, layouts):
    if page is not None and page not in spine:
        raise ValueError("指定的样张不在 spine 中")
    # Use a single real chapter to keep book content and image constant across presets.
    for path in [page] if page else spine:
        if path is None:
            continue
        root = ET.fromstring(archive.read(path))
        body = root.find("{*}body")
        if body is None:
            continue
        classes = body.get("class", "").split()
        heading = body.find(".//{*}h1")
        plate = next((node for node in body.iter() if "plate" in node.get("class", "").split()), None)
        if heading is not None and (page or (plate is not None and "front-matter" not in classes)):
            break
    else:
        raise ValueError("没找到带插图的章节，可通过 --page 指定 spine 内含 h1 的页面")

    epub_title = "".join(heading.itertext()).strip()
    paragraphs = []
    for p in body.iterfind(".//{*}p"):
        text = "".join(p.itertext()).strip()
        if len(text) >= 45:
            excerpt = text[:175] + ("…" if len(text) > 175 else "")
            paragraphs.append(f"<p>{html.escape(excerpt)}</p>")
        if len(paragraphs) == 2:
            break
    image = plate.find(".//{*}img") if plate is not None else None
    img_markup = ""
    if image is not None:
        asset = member_path(path, image.get("src", ""))
        if asset in archive.namelist():
            mime = mimetypes.guess_type(asset)[0] or "application/octet-stream"
            data = base64.b64encode(archive.read(asset)).decode("ascii")
            caption = next((n for n in plate.iter() if n.tag.endswith("figcaption")
                            or "caption" in n.get("class", "").split()), None)
            lines = ["".join(n.itertext()).strip() for n in caption] if caption is not None else []
            if caption is not None and not lines:
                lines = ["".join(caption.itertext()).strip()]
            caption_html = "".join(
                f'<span class="{ "caption-en" if i else "caption-cn"}">{html.escape(line)}</span>'
                for i, line in enumerate(lines))
            img_markup = (f'<figure class="plate"><img src="data:{mime};base64,{data}" '
                          f'alt="{html.escape(image.get("alt", ""), quote=True)}">'
                          f'<figcaption class="caption">{caption_html}</figcaption></figure>')

    css = archive.read(stylesheet).decode("utf-8-sig")
    cards = []
    for key in layouts:
        label, description = LAYOUTS[key]
        page_css = css if key == "original" else with_layout(css, key)
        # Sandboxed srcdoc with access to inline CSS and embedded data images only.
        sample = ("""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<style>""" + re.sub(r"</style", r"<\\/style", page_css, flags=re.I) +
                  """\nhtml{background:#fffdf8;color:#25241f} body{margin:0;padding:20px 24px;box-sizing:border-box} img{max-width:100%;height:auto}</style></head>"""
                  f'<body><h1 class="chapter-title">{html.escape(epub_title)}</h1>'
                  f'{img_markup}{"".join(paragraphs)}</body></html>')
        card_class = ' class="sample--wide"' if key in WIDE_LAYOUTS else ""
        cards.append(f'<article id="{key}"{card_class}><h2>{label}</h2><p>{description}</p>'
                     f'<iframe sandbox title="{label}样张" srcdoc="{html.escape(sample, quote=True)}"></iframe></article>')
    navigation = " · ".join(f'<a href="#{key}">{LAYOUTS[key][0]}</a>' for key in layouts)
    document = f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · 版式样张</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#efebe2;color:#282722;font:15px/1.6 -apple-system,sans-serif}}
main{{max-width:1200px;margin:auto;padding:32px clamp(14px,4vw,50px) 48px}}h1{{font:700 clamp(27px,5vw,50px)/1.2 "Songti SC",serif;margin:0}}
header p{{margin:.6em 0 1.5em;color:#595344}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}
article{{background:#fffdf8;border:1px solid #d8d0c0;border-radius:8px;overflow:hidden}}
h2{{font-size:19px;margin:14px 20px 0}}article p{{margin:2px 20px 12px;color:#595344;font-size:13px}}
iframe{{display:block;width:100%;height:520px;border:0;border-top:1px solid #e4ddd0}}
.sample--wide{{grid-column:1/-1;width:100%;max-width:850px;justify-self:center}}
.sample--wide iframe{{height:710px}}
header a{{display:inline-block;color:#744531;text-underline-offset:3px}}article{{scroll-margin-top:16px}}
@media(max-width:640px){{.grid{{grid-template-columns:1fr}}}}
</style><main><header><h1>{html.escape(title)} · 版式样张</h1>
<p>同章、同图、同一组正文节选。{navigation}</p></header>
<div class="grid">{''.join(cards)}</div></main></html>"""
    with target.open("x", encoding="utf-8") as out:
        out.write(document)


def restyle(archive, stylesheet, target, layout):
    entries = archive.infolist()
    names = archive.namelist()
    if not entries or names[0] != "mimetype" or entries[0].compress_type != zipfile.ZIP_STORED:
        raise ValueError("源 EPUB 的 mimetype 必须为首条且不压缩")
    if len(names) != len(set(names)) or archive.read("mimetype") != b"application/epub+zip":
        raise ValueError("源 EPUB 有重复资源或 mimetype 不正确")
    updated = with_layout(archive.read(stylesheet).decode("utf-8-sig"), layout).encode("utf-8")
    with zipfile.ZipFile(target, "x") as out:
        for entry in entries:
            out.writestr(copy(entry), updated if entry.filename == stylesheet else archive.read(entry))
    with zipfile.ZipFile(target) as result:
        if result.testzip() or result.namelist() != names:
            raise ValueError("输出 EPUB 未通过压缩包校验")
        for original, written in zip(entries, result.infolist()):
            if original.filename != stylesheet and original.CRC != written.CRC:
                raise ValueError(f"非样式资源发生变化：{original.filename}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", type=Path, metavar="SAMPLES.html")
    mode.add_argument("--preset", choices=list(LAYOUTS)[1:])
    p.add_argument("--page", help="样张的 spine 内路径，例如 OEBPS/chapter.xhtml")
    p.add_argument("--layouts", nargs="+", choices=LAYOUTS, help="选取并排列样张，仅用于 --preview")
    p.add_argument("-o", "--output", type=Path)
    args = p.parse_args()
    if (args.preset and (not args.output or args.page or args.layouts)) or (args.preview and args.output):
        p.error("应用预设需指定 -o；--page 和 --layouts 仅用于 --preview")
    if args.layouts and len(args.layouts) != len(set(args.layouts)):
        p.error("--layouts 不可重复指定同一版式")
    try:
        with zipfile.ZipFile(args.source) as book:
            title, spine, stylesheet = read_book(book)
            if args.preview:
                preview(book, title, spine, stylesheet, args.preview, args.page, args.layouts or LAYOUTS)
            else:
                restyle(book, stylesheet, args.output, args.preset)
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as e:
        p.exit(1, f"排版失败：{e}\n")
    print(args.preview or args.output)


if __name__ == "__main__":
    main()
