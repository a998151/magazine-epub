#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_epub.py — 把现有 EPUB 重排成杂志级排版并重新打包

用法:
    python3 build_epub.py --config config.json [--dry-run]

配置见同目录 references/recipes.md。流水线阶段：
    清理推广内容 → 标题语义化 → 前置页标记 → 刊头开篇页 → 章节扉页+插图+抽言
    → 插图入包 → manifest/spine/NCX 更新 → 样式注入 → 打包 → 结构自检
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CSS = SKILL_DIR / "references" / "magazine.css"
DEFAULT_PAGE_CSS = SKILL_DIR / "references" / "page.css"

P_RE = re.compile(r'<p([^>]*class="calibre_(?:8|10)"[^>]*)>(.*?)</p>', re.S)
TITLE_RE = re.compile(r'<p([^>]*class="calibre_(?:6|2|)"[^>]*)>(.*?)</p>', re.S)
H1_RE = re.compile(r"<h1([^>]*)>(.*?)</h1>", re.S)

report = []


def say(msg):
    report.append(msg)
    print(msg)


# ------------------------------------------------------------------ 工具
def unzip_or_copy(source: Path, workdir: Path):
    if workdir.exists():
        shutil.rmtree(workdir)
    if source.is_dir():
        shutil.copytree(source, workdir)
    else:
        with zipfile.ZipFile(source) as z:
            z.extractall(workdir)
    for junk in list(workdir.rglob(".DS_Store")):
        junk.unlink()


def compress_image(src: Path, dst: Path, max_width: int, quality: int):
    """优先 Pillow，其次 macOS sips，最后原样复制"""
    try:
        from PIL import Image
        im = Image.open(src)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if im.width > max_width:
            im = im.resize(
                (max_width, max(1, round(im.height * max_width / im.width))),
                Image.LANCZOS,
            )
        im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)
        return "pillow"
    except Exception:
        pass
    if shutil.which("sips"):
        subprocess.run(
            ["sips", "-Z", str(max_width), "-s", "format", "jpeg",
             "-s", "formatOptions", str(quality), str(src), "--out", str(dst)],
            capture_output=True,
        )
        if dst.exists():
            return "sips"
    shutil.copyfile(src, dst)
    return "copy"


def split_parts(inner):
    return re.split(r"(<[^>]+>)", inner)


def plain_of(parts):
    return "".join(p for p in parts if not p.startswith("<"))


def split_paragraph(inner, start, end):
    """按字符区间把段落 HTML 切成 quote 前后两段"""
    before, after = [], []
    consumed = 0
    for part in split_parts(inner):
        if part.startswith("<"):
            (before if consumed <= start else after).append(part)
            continue
        s, e = consumed, consumed + len(part)
        consumed = e
        head = part[: max(0, min(e, start) - s)] if s < start else ""
        tail_start = max(s, end)
        tail = part[max(0, tail_start - s):] if e > tail_start else ""
        if head:
            before.append(head)
        if tail:
            after.append(tail)
    return "".join(before), "".join(after)


# -------------------------------------------------------------- 各阶段
def strip_ads(work: Path, patterns):
    if not patterns:
        return
    for path in sorted(work.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        original = text
        for kw in patterns:
            text = re.sub(r"<p[^>]*>[^<]*" + re.escape(kw) + r".*?</p>", "", text, flags=re.S)
        if text != original:
            path.write_text(text, encoding="utf-8")
            say(f"清理推广段落：{path.name}")


def promote_titles(work: Path):
    total = 0
    for path in sorted(work.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        new, n = TITLE_RE.subn(r"<h1\1>\2</h1>", text)
        if n:
            path.write_text(new, encoding="utf-8")
            total += n
    say(f"标题升级为 h1：{total} 处")


def mark_front_matter(work: Path, names):
    for name in names:
        path = work / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        new = text.replace('<body class="calibre">',
                           '<body class="calibre front-matter">', 1)
        if new != text:
            path.write_text(new, encoding="utf-8")


def add_notes_title(work: Path, page_name: str, title: str):
    """给指定的前置页补标题（必须是具体文件名，否则会加错页）"""
    if not page_name or not title:
        return
    path = work / page_name
    if not path.exists():
        say(f"  ! 注释页不存在：{page_name}")
        return
    text = path.read_text(encoding="utf-8")
    if title in text[:3000]:
        return
    marker = '<body class="calibre front-matter">'
    if marker not in text:
        marker = '<body class="calibre">'
    if marker in text:
        text = text.replace(marker, marker + f'\n<h1 class="calibre_6">{title}</h1>', 1)
        path.write_text(text, encoding="utf-8")
        say(f"为 {page_name} 补标题「{title}」")


def build_opener(work: Path, book: dict, toc_entries):
    items = "\n".join(
        f'    <div class="item"><span class="no">{e.get("no","")}</span>'
        f'<span class="t">{e.get("title","")}</span></div>'
        for e in toc_entries
    )
    byline = " ".join(
        f'<span class="role">{b}</span><span class="sep">|</span>' for b in book.get("byline", [])
    )
    title = book.get("title", "")
    accent = book.get("title_accent")
    if accent and accent in title:
        head, _, tail = title.partition(accent)
        title_html = f"{head}<em>{accent}</em>{tail}"
    else:
        title_html = title
    html = f"""<?xml version='1.0' encoding='utf-8'?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>{title}</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  <link href="stylesheet.css" rel="stylesheet" type="text/css"/>
<link href="page_styles.css" rel="stylesheet" type="text/css"/>
</head>
  <body class="calibre front-matter">

<div class="masthead">
  <span class="series">{book.get("masthead_left","")}</span>
  <span class="right">{book.get("masthead_right","")}</span>
</div>

<div class="hero">
  <div class="kicker">{book.get("subtitle_en","")}</div>
  <div class="book-title">{title_html}</div>
  <div class="book-title-en">{book.get("title_en","")}</div>
  <p class="deck">{book.get("deck","")}</p>
  <div class="byline">{byline}</div>
</div>

<figure class="plate">
<img src="images/{book.get("image","")}.jpg" alt="{book.get("image_alt","")}" />
<figcaption><span class="cn">{book.get("caption_cn","")}</span><span class="en">{book.get("caption_en","")}</span></figcaption>
</figure>

<div class="toc-strip">
{items}
</div>

</body>
</html>
"""
    (work / "opener.html").write_text(html.replace("&nbsp;", "\u00a0"), encoding="utf-8")
    say("生成刊头开篇页 opener.html")


def apply_pull_quote(text: str, quote: str, src: str):
    """把 quote 从所在段落摘出，改排成抽言块"""
    for m in P_RE.finditer(text):
        inner = m.group(2)
        plain = plain_of(split_parts(inner))
        idx = plain.find(quote)
        if idx < 0:
            continue
        before_html, after_html = split_paragraph(inner, idx, idx + len(quote))
        before_text = plain_of(split_parts(before_html)).strip()
        after_text = plain_of(split_parts(after_html)).strip()
        if len(before_text) < 30 and len(after_text) < 30:
            continue
        attrs = m.group(1)
        blocks = []
        if before_text:
            blocks.append(f"<p{attrs}>" + before_html + "</p>")
        blocks.append(
            f'<div class="pullquote"><p>{quote}</p>'
            f'<div class="cite">— {src}</div></div>'
        )
        if after_text:
            blocks.append('<p class="calibre_8 cont">' + after_html + "</p>")
        return text[: m.start()] + "\n".join(blocks) + text[m.end():], True
    return text, False


def build_chapter(work: Path, meta: dict):
    path = work / meta["file"]
    if not path.exists():
        say(f"  ! 缺少章节文件：{meta['file']}")
        return False
    text = path.read_text(encoding="utf-8")

    m = H1_RE.search(text)
    if m:
        idm = re.search(r'id="([^"]+)"', m.group(1))
        anchor = f' id="{idm.group(1)}"' if idm else ""
        opener = f"""
<div class="chapter-opener">
<div class="chapter-index">{meta.get("no","")}</div>
<h1{anchor}><span class="bold">{meta.get("cn","")}</span></h1>
<div class="chapter-en">{meta.get("en","")}</div>
</div>
<figure class="plate">
<img src="images/{meta.get("image","")}.jpg" alt="{meta.get("alt","")}" />
<figcaption><span class="cn">{meta.get("caption_cn","")}</span><span class="en">{meta.get("caption_en","")}</span></figcaption>
</figure>
"""
        text = text[: m.start()] + opener + text[m.end():]

    quote = meta.get("pull_quote")
    if quote:
        text, ok = apply_pull_quote(text, quote, meta.get("pull_source", meta.get("cn", "")))
        if not ok:
            say(f"  ! 「{meta.get('cn')}」抽言未在正文中逐字匹配到，已跳过：{quote[:20]}…")

    text = text.replace('<div id="calibre_pb_', '<div class="endmark">❋</div>\n<div id="calibre_pb_')
    path.write_text(text, encoding="utf-8")
    return True


def install_images(work: Path, images: dict, max_width: int, quality: int):
    imgdir = work / "images"
    if imgdir.exists():
        shutil.rmtree(imgdir)
    imgdir.mkdir()
    total = 0
    for name, src in images.items():
        srcp = Path(src).expanduser()
        dst = imgdir / f"{name}.jpg"
        compress_image(srcp, dst, max_width, quality)
        total += dst.stat().st_size
    say(f"插图入包：{len(images)} 张，合计 {total / 1024:.0f} KB")


def fix_opf(work: Path, drop_ids, drop_pages, image_names, has_opener):
    path = work / "content.opf"
    text = path.read_text(encoding="utf-8")

    # 先算出要删的 manifest id（按 href 反查），删文件后 spine 里的 itemref 也要跟着删
    id_of_href = {}
    for m in re.finditer(r'href="([^"]+)"[^>]*id="([^"]+)"', text):
        id_of_href.setdefault(m.group(1), m.group(2))
    doomed = set(drop_ids)
    for href in drop_pages:
        if href in id_of_href:
            doomed.add(id_of_href[href])

    out = []
    for line in text.splitlines():
        m = re.search(r'href="([^"]+)"[^>]*id="([^"]+)"', line)
        if m and (m.group(1) in doomed or m.group(2) in doomed):
            continue
        if "<itemref" in line:
            m2 = re.search(r'idref="([^"]+)"', line)
            if m2 and m2.group(1) in doomed:
                continue
        out.append(line)
    text = "\n".join(out)

    items = "\n".join(
        f'    <item href="images/{n}.jpg" id="img_{n.replace("-","_")}" media-type="image/jpeg"/>'
        for n in image_names
    )
    if has_opener:
        items = ('    <item href="opener.html" id="opener" media-type="application/xhtml+xml"/>\n'
                 + items)
        text = text.replace('    <itemref idref="titlepage"/>',
                            '    <itemref idref="titlepage"/>\n    <itemref idref="opener"/>')
    text = text.replace("  </manifest>", items + "\n  </manifest>")
    path.write_text(text, encoding="utf-8")
    say("content.opf：清理条目 + 登记插图与开篇页")


def fix_ncx(work: Path, extra_entries):
    path = work / "toc.ncx"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if not extra_entries:
        return
    text = re.sub(r'playOrder="(\d+)"', lambda m: f'playOrder="{int(m.group(1)) + 1}"', text)
    blocks = []
    for i, e in enumerate(extra_entries):
        blocks.append(f"""    <navPoint class="chapter" id="num_x{i}" playOrder="{i+1}">
      <navLabel>
        <text>{e.get("label","")}</text>
      </navLabel>
      <content src="{e.get("src","")}"/>
    </navPoint>
""")
    if "  <navMap>\n" in text:
        text = text.replace("  <navMap>\n", "  <navMap>\n" + "\n".join(blocks), 1)
        path.write_text(text, encoding="utf-8")
        say("toc.ncx：新增导航条目 " + "、".join(e.get("label", "") for e in extra_entries))


def install_css(work: Path, css_path, page_css_path):
    shutil.copyfile(css_path, work / "stylesheet.css")
    shutil.copyfile(page_css_path, work / "page_styles.css")
    say(f"样式注入：{Path(css_path).name}")


def package(work: Path, output: Path):
    if output.exists():
        output.unlink()
    files = sorted(p for p in work.rglob("*")
                   if p.is_file() and p.name not in (".DS_Store", "mimetype"))
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo("mimetype", date_time=(2024, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_STORED
        zi.external_attr = 0o644 << 16
        z.writestr(zi, b"application/epub+zip")
        for p in files:
            zi = zipfile.ZipInfo(p.relative_to(work).as_posix(), date_time=(2024, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, p.read_bytes())
    say(f"打包完成：{output.name}（{output.stat().st_size / 1024 / 1024:.2f} MB，{len(files) + 1} 个条目）")


def validate(output: Path, chapters, image_names, ad_patterns, has_opener):
    errors = []
    with zipfile.ZipFile(output) as z:
        names = z.namelist()
        if names[0] != "mimetype":
            errors.append("首个条目不是 mimetype")
        if z.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            errors.append("mimetype 未以 stored 方式存放")
        if z.read("mimetype") != b"application/epub+zip":
            errors.append("mimetype 内容错误")
        for n in names:
            if n.endswith((".html", ".xhtml", ".opf", ".ncx")):
                try:
                    ET.fromstring(z.read(n))
                except ET.ParseError as e:
                    errors.append(f"XML 解析失败 {n}: {e}")
        opf = ET.fromstring(z.read("content.opf"))
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        manifest = {i.get("id"): i.get("href") for i in opf.findall(".//opf:manifest/opf:item", ns)}
        spine = [r.get("idref") for r in opf.findall(".//opf:spine/opf:itemref", ns)]
        for sid in spine:
            if sid not in manifest:
                errors.append(f"spine 引用不存在的 id：{sid}")
            elif manifest[sid].split("#")[0] not in names:
                errors.append(f"spine 目标缺失：{manifest[sid]}")
        for href in manifest.values():
            if href.split("#")[0] not in names:
                errors.append(f"manifest 目标缺失：{href}")
        for n in names:
            if n.endswith((".html", ".xhtml")) and n not in manifest.values():
                errors.append(f"未被 manifest 引用：{n}")
        ncx = next((n for n in names if n.endswith(".ncx")), None)
        if ncx:
            nns = {"n": "http://www.daisy.org/z3986/2005/ncx/"}
            for c in ET.fromstring(z.read(ncx)).findall(".//n:content", nns):
                if c.get("src").split("#")[0] not in names:
                    errors.append(f"NCX 目标缺失：{c.get('src')}")
        for meta in chapters:
            f = meta["file"]
            if f not in names:
                errors.append(f"章节文件缺失：{f}")
                continue
            html = z.read(f).decode("utf-8")
            if meta.get("image") and f'images/{meta["image"]}.jpg' not in html:
                errors.append(f'{meta.get("cn")} 缺少插图 {meta["image"]}')
            if meta.get("pull_quote") and "pullquote" not in html:
                errors.append(f'{meta.get("cn")} 缺少抽言')
        imgs = {n for n in names if n.startswith("images/")}
        if len(imgs) != len(image_names):
            errors.append(f"插图数量不符：包内 {len(imgs)}，应为 {len(image_names)}")
        if has_opener:
            if "opener.html" not in names:
                errors.append("缺少开篇页 opener.html")
            else:
                op = z.read("opener.html").decode("utf-8")
                if "book-title" not in op:
                    errors.append("开篇页缺少刊头标题")
        for n in names:
            if n.endswith((".html", ".xhtml")):
                txt = z.read(n).decode("utf-8", "ignore")
                for kw in ad_patterns:
                    if kw in txt:
                        errors.append(f"{n} 仍含推广关键词：{kw}")
    if errors:
        print("\n自检未通过：")
        for e in errors:
            print("  ✗", e)
        return False
    print("\n自检通过：包结构 / XML / manifest / spine / NCX / 插图 / 推广内容 全部正常")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="配置 JSON 路径")
    ap.add_argument("--dry-run", action="store_true", help="只构建不打包")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    source = Path(cfg["source"]).expanduser().resolve()
    work = Path(cfg.get("workdir", "./epub_build")).expanduser().resolve()
    output = Path(cfg["output"]).expanduser().resolve()

    book = cfg.get("book", {})
    chapters = cfg.get("chapters", [])
    images = cfg.get("images", {})
    drop_pages = set(cfg.get("drop_pages", []))
    front_matter = cfg.get("front_matter", [])
    ad_patterns = cfg.get("ad_patterns", [])
    has_opener = bool(cfg.get("opener", False)) and book.get("image") in images

    unzip_or_copy(source, work)
    for name in drop_pages:
        p = work / name
        if p.exists():
            p.unlink()
            say(f"删除页面/资源：{name}")
    strip_ads(work, ad_patterns)
    promote_titles(work)
    mark_front_matter(work, front_matter)
    add_notes_title(work, cfg.get("notes_page", ""), cfg.get("notes_title", ""))
    if has_opener:
        build_opener(work, book, cfg.get("toc_entries", []))
    say(f"构建 {len(chapters)} 个章节扉页：")
    for meta in chapters:
        build_chapter(work, meta)
    if images:
        install_images(work, images, cfg.get("image_max_width", 1400), cfg.get("image_quality", 80))

    drop_ids = set(cfg.get("drop_ids", []))
    fix_opf(work, drop_ids, drop_pages, list(images.keys()), has_opener)
    extra = []
    if has_opener:
        extra.append({"label": "卷首", "src": "opener.html"})
    if cfg.get("toc_page"):
        extra.append({"label": cfg.get("toc_label", "目录"), "src": cfg["toc_page"]})
    fix_ncx(work, extra)
    install_css(work, cfg.get("css") or DEFAULT_CSS, cfg.get("page_css") or DEFAULT_PAGE_CSS)

    if args.dry_run:
        print("\n[dry-run] 已跳过打包与自检")
        return
    package(work, output)
    ok = validate(output, chapters, list(images.keys()), ad_patterns, has_opener)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
