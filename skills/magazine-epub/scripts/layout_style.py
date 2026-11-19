#!/usr/bin/env python3
"""Apply EPUB layout presets and preview the resulting packaged pages."""

import argparse
from copy import copy
import html
import posixpath
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree as ET
from xml.parsers.expat import ExpatError

import paper_wash

LAYOUTS = {
    "original": ("当前 EPUB", "使用输入 EPUB 的实际页面。"),
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


def read_package(archive):
    container = ET.fromstring(archive.read("META-INF/container.xml"))
    opf_path = container.find(".//{*}rootfile").attrib["full-path"]
    return opf_path, ET.fromstring(archive.read(opf_path))


def read_book(archive):
    opf_path, package = read_package(archive)
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


def preview_page(archive, spine, page):
    if page is not None:
        if page not in spine or not page.lower().endswith((".xhtml", ".html", ".htm")):
            raise ValueError("指定的样张必须是 spine 中的 XHTML 页面")
        return page
    fallback = None
    for path in spine:
        if not path or not path.lower().endswith((".xhtml", ".html", ".htm")):
            continue
        root = ET.fromstring(archive.read(path))
        body = root.find("{*}body")
        if body is None or "front-matter" in body.get("class", "").split():
            continue
        heading = body.find(".//{*}h1")
        if heading is None:
            continue
        fallback = fallback or path
        if any({"plate", paper_wash.LEAD}.intersection(el.get("class", "").split())
               for el in body.iter()):
            return path
    if fallback is None:
        raise ValueError("未找到章节，使用 --page 指定 spine 中的 XHTML 页面")
    return fallback


def extract_page(archive, folder, page):
    names = archive.namelist()
    for name in names:
        if "\\" in name or name.startswith("/") or any(
            part in {"", ".", ".."} or ":" in part for part in name.rstrip("/").split("/")
        ):
            raise ValueError(f"EPUB 中存在无效路径：{name}")
    if len(set(names)) != len(names):
        raise ValueError("EPUB 中有重复资源路径")
    archive.extractall(folder)
    path = folder / page
    if path.suffix.lower() != ".xhtml":
        # EPUB declares XHTML even for .html members. Keep that parsing mode in the browser.
        alias = path.with_name(path.name + ".xhtml")
        while alias.exists():
            alias = alias.with_name(alias.name + ".xhtml")
        shutil.copyfile(path, alias)
        path = alias
    return path


def preview(archive, title, spine, stylesheet, target, page, layouts):
    selected = preview_page(archive, spine, page)
    assets = target.with_name(target.stem + "_files")
    if target.exists() or assets.exists():
        raise FileExistsError(f"预览文件或资源目录已存在：{target} / {assets}")
    cards = []
    with tempfile.TemporaryDirectory(prefix="epub-preview-") as workdir:
        work = Path(workdir)
        bundle = work / "files"
        for key in layouts:
            if key == "original":
                path = extract_page(archive, bundle / key, selected)
            else:
                candidate = work / f"{key}.epub"
                restyle(archive, stylesheet, candidate, key)
                with zipfile.ZipFile(candidate) as packaged:
                    path = extract_page(packaged, bundle / key, selected)
            url = quote(f"{assets.name}/{path.relative_to(bundle).as_posix()}")
            label, description = LAYOUTS[key]
            card_class = ' class="sample--wide"' if key in WIDE_LAYOUTS or len(layouts) == 1 else ""
            cards.append(f'<article id="{key}"{card_class}><h2>{label}</h2><p>{description}</p>'
                         f'<iframe sandbox="allow-same-origin" referrerpolicy="no-referrer" '
                         f'title="{label}预览" src="{url}"></iframe></article>')
        shutil.copytree(bundle, assets)
    write_preview(target, title, layouts, cards)


def write_preview(target, title, layouts, cards):
    navigation = " · ".join(f'<a href="#{key}">{LAYOUTS[key][0]}</a>' for key in layouts)
    title_class = ' class="long-title"' if len(title) > 36 else ""
    document = f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · EPUB 版式预览</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#efebe2;color:#282722;font:15px/1.6 -apple-system,sans-serif}}
main{{max-width:1200px;margin:auto;padding:32px clamp(14px,4vw,50px) 48px}}h1{{font:700 clamp(27px,5vw,50px)/1.2 "Songti SC",serif;margin:0}}
.long-title{{font-size:clamp(21px,3.2vw,30px)}}
header p{{margin:.6em 0 1.5em;color:#595344}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}
article{{background:#fffdf8;border:1px solid #d8d0c0;border-radius:8px;overflow:hidden}}
h2{{font-size:19px;margin:14px 20px 0}}article > p{{margin:2px 20px 12px;color:#595344;font-size:13px}}
iframe{{display:block;width:100%;height:520px;border:0;border-top:1px solid #e4ddd0}}
.sample--wide{{grid-column:1/-1;width:100%;max-width:850px;justify-self:center}}
.sample--wide iframe{{height:710px}}
header a{{display:inline-block;color:#744531;text-underline-offset:3px}}article{{scroll-margin-top:16px}}
@media(max-width:640px){{.grid{{grid-template-columns:1fr}}}}
</style><main><header><h1{title_class}>{html.escape(title)} · EPUB 版式预览</h1>
<p>各预览直接显示已打包 EPUB 的同一页面，可在框内继续阅读。{navigation}</p></header>
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
    updated = with_layout(archive.read(stylesheet).decode("utf-8-sig"), layout)
    replacements, additions = {}, {}
    if layout == "paper-wash":
        opf_path, _ = read_package(archive)
        _, spine, _ = read_book(archive)
        replacements, additions = paper_wash.reflow(archive, opf_path, spine, member_path)
    replacements[stylesheet] = updated.encode("utf-8")
    with tempfile.TemporaryFile() as packaged:
        with zipfile.ZipFile(packaged, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for entry in entries:
                payload = replacements.get(entry.filename)
                out.writestr(copy(entry), archive.read(entry) if payload is None else payload)
            for name, data in additions.items():
                entry = zipfile.ZipInfo(name)
                entry.compress_type = zipfile.ZIP_DEFLATED
                out.writestr(entry, data)
        with zipfile.ZipFile(packaged) as result:
            if result.testzip() or result.namelist() != [*names, *additions]:
                raise ValueError("输出 EPUB 未通过压缩包校验")
            for original, written in zip(entries, result.infolist()):
                if original.filename not in replacements and original.CRC != written.CRC:
                    raise ValueError(f"非目标资源发生变化：{original.filename}")
        packaged.seek(0)
        with target.open("xb") as out:
            shutil.copyfileobj(packaged, out)


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
    except ModuleNotFoundError as e:
        if e.name != "PIL":
            raise
        p.exit(1, "画入纸面需要 Pillow 处理已有插画，请运行 python3 -m pip install Pillow\n")
    except (OSError, ValueError, KeyError, ET.ParseError, ExpatError, zipfile.BadZipFile) as e:
        p.exit(1, f"排版失败：{e}\n")
    print(args.preview or args.output)


if __name__ == "__main__":
    main()
