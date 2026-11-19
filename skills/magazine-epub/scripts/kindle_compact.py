#!/usr/bin/env python3
"""Make a Kindle copy of a packaged EPUB with bounded raster image sizes."""

import argparse
import hashlib
import io
import posixpath
import re
import shutil
import tempfile
import zipfile
from copy import copy
from pathlib import Path
from urllib.parse import unquote
from xml.dom import minidom
from xml.parsers.expat import ExpatError
from xml.etree import ElementTree as ET

from layout_style import member_path, read_book, read_package


MIB = 1024 ** 2
IMAGE_TYPES = {".jpeg", ".jpg", ".png"}
TEXT_TYPES = {".xhtml", ".html", ".htm", ".xml", ".opf", ".ncx", ".svg", ".css", ".smil", ".js"}
LEAD = re.compile(r"(?:^|/)paper-wash/lead-([0-9a-f]{24})\.png$")
LINK = re.compile(r"""(\b(?:src|href|poster|data)\s*=\s*["'])([^"']+)(["'])""", re.I)
PAPER = "#f8f8ef"  # The light page color in the paper-wash stylesheet.
OUTER_EDGE = b"""
/* magazine-epub: zero authored outer margins */
@page { margin: 0 !important; }
html { margin: 0 !important; padding: 0 !important; }
body.paper-wash-ready,
body.paper-wash-ready > .paper-wash-lead {
  margin: 0 !important;
  padding: 0 !important;
}
"""
FIRST_SECTION_EDGE = b"""
/* Match the horizontal paragraph margins used on continuation pages. */
body.paper-wash-ready.chapter-first-section > p {
  margin-left: 0;
  margin-right: 0;
}
"""
BODY_CLASS = re.compile(rb"""(<(?:[\w.-]+:)?body\b[^>]*?\sclass\s*=\s*)(['"])([^'"]*)\2""")


def raster(data, output_type, max_side, max_bytes, matte, force=False):
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as source:
        transparent = "A" in source.getbands() or "transparency" in source.info
        rotation = source.getexif().get(274, 1)
        if (not force and not transparent and rotation == 1 and
                source.mode != "CMYK" and max(source.size) <= max_side and len(data) <= max_bytes):
            return data
        if getattr(source, "n_frames", 1) > 1:
            raise ValueError("遇到多帧 PNG，请先确认要保留的画面")
        image = ImageOps.exif_transpose(source)
        if transparent:
            foreground = image.convert("RGBA")
            image = Image.new("RGB", foreground.size, matte)
            image.paste(foreground, mask=foreground.getchannel("A"))
        elif image.mode not in {"L", "RGB"}:
            image = image.convert("RGB")

    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    floor = min(max(image.size), 640)
    while True:
        if output_type == ".png":
            candidates = (image, image.quantize(colors=256), image.quantize(colors=96))
            encodings = ((candidate, "PNG", {}) for candidate in candidates)
        else:
            encodings = ((image, "JPEG", {"quality": quality}) for quality in (82, 75, 68, 62))
        for candidate, format_name, opts in encodings:
            output = io.BytesIO()
            candidate.save(output, format=format_name, optimize=True, **opts)
            if output.tell() <= max_bytes:
                return output.getvalue()
        long_side = max(image.size)
        if long_side <= floor:
            raise ValueError(f"在 {floor}px 下无法达到 {max_bytes // 1024} KiB，请复核图中细节或调整预算")
        size = max(floor, round(long_side * .85))
        image.thumbnail((size, size), Image.Resampling.LANCZOS)


def change_links(text, document, renamed):
    def rewrite(match):
        part = match[2]
        old = member_path(document, part)
        if old not in renamed:
            return match[0]
        # Only the suffix of the generated name changes. Keep relative paths and fragments.
        name = posixpath.basename(old)
        return match[1] + part.replace(name, posixpath.basename(renamed[old]), 1) + match[3]

    return LINK.sub(rewrite, text)


def mark_chapter_opening(data):
    """Return a marked chapter opening, or None for other pages."""
    if b"paper-wash-ready" not in data:
        return None
    body = ET.fromstring(data).find("{*}body")
    if body is None:
        return None
    classes = body.get("class", "").split()
    if "paper-wash-ready" not in classes or "front-matter" in classes:
        return None
    number = next((heading for heading in body.findall("{*}h3")
                   if "paper-wash-first-section" in heading.get("class", "").split()), None)
    if number is not None:
        if "".join("".join(number.itertext()).split()) not in {"1", "１", "第1节", "第一节"}:
            return None
    else:
        heading = body.find("{*}h1")
        if ("chapter-page" not in classes or heading is None or
                "paper-wash-title" not in heading.get("class", "").split()):
            return None
    if "chapter-first-section" in classes:
        return data
    revised, count = BODY_CLASS.subn(
        lambda match: match[1] + match[2] + match[3] + b" chapter-first-section" + match[2],
        data, count=1,
    )
    if count != 1:
        raise ValueError("画入纸面章首页的 body 类无法更新")
    return revised


def apply_outer_edge(incoming, text_files, substitutions):
    _, spine, stylesheet = read_book(incoming)
    css = substitutions.get(stylesheet, incoming.read(stylesheet))
    if OUTER_EDGE not in css:
        css += OUTER_EDGE
    for path in dict.fromkeys(spine):
        if path not in text_files:
            continue
        original = substitutions.get(path, text_files[path].encode("utf-8"))
        revised = mark_chapter_opening(original)
        if revised is None:
            continue
        if revised != original:
            substitutions[path] = revised
        if FIRST_SECTION_EDGE not in css:
            css += FIRST_SECTION_EDGE
    substitutions[stylesheet] = css


def pack(source, target, max_side, max_bytes, book_cap, *, no_outer_margins=False):
    with zipfile.ZipFile(source) as incoming, tempfile.TemporaryFile() as packed:
        entries = incoming.infolist()
        names = incoming.namelist()
        if (not entries or len(names) != len(set(names)) or entries[0].filename != "mimetype"
                or entries[0].compress_type != zipfile.ZIP_STORED
                or incoming.read("mimetype") != b"application/epub+zip"):
            raise ValueError("源 EPUB 的 ZIP 结构或 mimetype 有误")

        opf_path, _ = read_package(incoming)
        package = minidom.parseString(incoming.read(opf_path))
        manifest = package.getElementsByTagNameNS("*", "manifest")[0]
        items = {member_path(opf_path, node.getAttribute("href")): node
                 for node in manifest.getElementsByTagNameNS("*", "item")}
        cover_ids = {node.getAttribute("content") for node in package.getElementsByTagNameNS("*", "meta")
                     if node.getAttribute("name") == "cover"}
        covers = {path for path, node in items.items() if path and
                  (node.getAttribute("id") in cover_ids or
                   "cover-image" in node.getAttribute("properties").split() or
                   Path(path).stem.casefold() == "cover")}
        leads = {name: match[1] for name in names if (match := LEAD.search(name))}
        renamed = {name: name[:-4] + ".jpg" for name in leads}
        if set(renamed.values()) & set(names):
            raise ValueError("湿边 JPEG 的目标路径已存在")
        suffixes = {name: Path(name).suffix.lower() for name in names}
        text_files = {name: incoming.read(name).decode("utf-8")
                      for name in names if name != opf_path and suffixes[name] in TEXT_TYPES}
        resource_text = "\n".join(map(unquote, text_files.values()))
        scripted = any(suffixes[name] == ".js" for name in names) or "<script" in resource_text.lower()
        package_nodes = list(package.getElementsByTagName("*"))
        substitutions = {}
        dropped = set()
        hashes = set(leads.values())

        for path, item in items.items():
            if path in renamed:
                item.setAttribute("href", item.getAttribute("href")[:-4] + ".jpg")
                item.setAttribute("media-type", "image/jpeg")
            elif (path in suffixes and suffixes[path] in IMAGE_TYPES and path not in covers
                  and not scripted and hashlib.sha256(incoming.read(path)).hexdigest()[:24] in hashes):
                item_id = item.getAttribute("id")
                basename = posixpath.basename(path)
                if basename in resource_text or any(
                    attr.value == item_id or basename in unquote(attr.value)
                    for node in package_nodes if node is not item
                    for attr in node.attributes.values()
                ):
                    continue
                manifest.removeChild(item)
                dropped.add(path)

        for path, original in text_files.items():
            updated = change_links(original, path, renamed) if renamed else original
            if original != updated:
                substitutions[path] = updated.encode("utf-8")
        if no_outer_margins:
            apply_outer_edge(incoming, text_files, substitutions)
        if renamed or dropped:
            updated_package = change_links(package.toxml(), opf_path, renamed)
            substitutions[opf_path] = updated_package.encode("utf-8")
            remaining = "\n".join(unquote(substitutions.get(path, original.encode()).decode())
                                  for path, original in text_files.items())
            if any(posixpath.basename(path) in remaining or posixpath.basename(path) in unquote(updated_package)
                   for path in renamed):
                raise ValueError("仍有旧章首 PNG 引用，需检查资源路径")

        stats = []
        with zipfile.ZipFile(packed, "w") as outgoing:
            for entry in entries:
                path = entry.filename
                if path in dropped:
                    continue
                out_entry = copy(entry)
                data = substitutions.get(path)
                if data is None:
                    data = incoming.read(entry)
                if suffixes[path] in IMAGE_TYPES:
                    filename = renamed.get(path, path)
                    out_entry.filename = out_entry.orig_filename = filename
                    is_cover = path in covers
                    limit = max(max_side, 1600) if is_cover else max_side
                    budget = max(max_bytes, 256 * 1024) if is_cover else max_bytes
                    paper_asset = "/paper-wash/" in f"/{path}"
                    try:
                        data = raster(data, Path(filename).suffix.lower(), limit, budget,
                                      PAPER if paper_asset else "#fff", force=path in renamed)
                    except (OSError, ValueError) as exc:
                        raise ValueError(f"{path}: {exc}") from exc
                    if not is_cover:
                        stats.append(len(data))
                outgoing.writestr(out_entry, data)

        with zipfile.ZipFile(packed) as result:
            if result.testzip() or result.namelist() != [renamed.get(name, name) for name in names if name not in dropped]:
                raise ValueError("压缩后的 EPUB 未通过 ZIP 校验")
            _, checked = read_package(result)
            old_spine = [ref.getAttribute("idref") for ref in package.getElementsByTagNameNS("*", "itemref")]
            new_spine = [ref.get("idref") for ref in checked.findall("./{*}spine/{*}itemref")]
            registered = {item.get("id"): member_path(opf_path, item.get("href"))
                          for item in checked.findall("./{*}manifest/{*}item")}
            if (old_spine != new_spine or not set(new_spine) <= registered.keys()
                    or not set(registered.values()) <= set(result.namelist())):
                raise ValueError("压缩后的 EPUB 未通过 manifest / spine 校验")
        size = packed.seek(0, io.SEEK_END)
        if book_cap and size > book_cap:
            raise ValueError(f"整本 {size / MIB:.2f} MiB，超过指定上限 {book_cap / MIB:g} MiB")
        packed.seek(0)
        with target.open("xb") as output:
            shutil.copyfileobj(packed, output)
    print(f"{source.stat().st_size / MIB:.2f} → {size / MIB:.2f} MiB；"
          f"非封面 JPG/PNG {len(stats)} 张，最大 {max(stats, default=0) / 1024:.0f} KiB；"
          f"移除无引用的原图副本 {len(dropped)} 张")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--max-side", type=int, default=1100, help="非封面 JPG/PNG 最长边")
    parser.add_argument("--max-image-kib", type=int, default=160, help="非封面 JPG/PNG 单张体积上限")
    parser.add_argument("--max-book-mib", type=float, help="可选的整本体积上限")
    parser.add_argument("--no-outer-margins", action="store_true",
                        help="清除书内外边距，以及画入纸面已识别的章首正文额外横向边距")
    args = parser.parse_args()
    if args.max_side < 1 or args.max_image_kib < 1 or (args.max_book_mib is not None and args.max_book_mib <= 0):
        parser.error("图片尺寸与体积限制须大于零")
    try:
        pack(args.source, args.output, args.max_side, args.max_image_kib * 1024,
             int(args.max_book_mib * MIB) if args.max_book_mib else None,
             no_outer_margins=args.no_outer_margins)
    except ModuleNotFoundError as exc:
        if exc.name != "PIL":
            raise
        parser.exit(1, "Kindle 轻量化需要 Pillow，请运行 python3 -m pip install Pillow\n")
    except (OSError, ValueError, KeyError, ET.ParseError, ExpatError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"压缩失败：{exc}\n")


if __name__ == "__main__":
    main()
