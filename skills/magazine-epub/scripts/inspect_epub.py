#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inspect_epub.py — EPUB 体检器

用法:
    python3 inspect_epub.py <book.epub | 已解压目录> [--json]

输出:
    · spine 顺序与 toc.ncx 章节名
    · 每个正文文件的段落数、字数、样式类使用分布
    · 推广/盗版残留关键词命中位置
    · 图片资源、体积、封面页情况
    · 是否存在重复目录页 / 可用作开篇页的标题页

体检结论决定后续配置表怎么写，所以先跑它再动手。
"""

import argparse
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

AD_PATTERNS = [
    "本书由", "整理，如果你不知道读什么书", "公众号", "微信号", "加小编",
    "ireadweek", "2338856113", "版权信息",
]
CLASS_RE = re.compile(r'class="([^"]+)"')
TAG_RE = re.compile(r"<[^>]+>")
TEXT_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)


def load(path: Path):
    """返回 (文件字典 {相对路径: bytes}, 是否来自 zip)"""
    if path.is_dir():
        return {
            p.relative_to(path).as_posix(): p.read_bytes()
            for p in sorted(path.rglob("*"))
            if p.is_file() and p.name != ".DS_Store"
        }, False
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}, True


def spine_order(files):
    opf = next((v for k, v in files.items() if k.endswith(".opf")), None)
    if not opf:
        return [], {}
    text = opf.decode("utf-8", "ignore")
    manifest = dict(
        (m.group(2), m.group(1))
        for m in re.finditer(r'href="([^"]+)"[^>]*id="([^"]+)"', text)
    )
    order = [m.group(1) for m in re.finditer(r'<itemref[^>]*idref="([^"]+)"', text)]
    return order, manifest


def ncx_titles(files):
    ncx = next((v for k, v in files.items() if k.endswith(".ncx")), None)
    if not ncx:
        return {}
    text = ncx.decode("utf-8", "ignore")
    out = {}
    for m in re.finditer(
        r"<navPoint.*?</navPoint>", text, re.S
    ):
        block = m.group(0)
        src = re.search(r'<content[^>]*src="([^"]+)"', block)
        label = re.search(r"<text>(.*?)</text>", block, re.S)
        if src and label:
            out[src.group(1)] = TAG_RE.sub("", label.group(1)).strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="epub 文件或已解压目录")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    src = Path(args.path).expanduser().resolve()
    files, from_zip = load(src)

    order, manifest = spine_order(files)
    titles = ncx_titles(files)

    doc = {"source": str(src), "from_zip": from_zip, "files": len(files), "chapters": []}

    for idref in order:
        href = manifest.get(idref)
        if not href:
            continue
        name = href.split("#")[0]
        if name not in files:
            continue
        text = files[name].decode("utf-8", "ignore")
        paras = TEXT_RE.findall(text)
        plain = TAG_RE.sub("", text)
        classes = Counter(
            c for m in CLASS_RE.findall(text) for c in m.split()
        )
        hits = [kw for kw in AD_PATTERNS if kw in plain]
        doc["chapters"].append({
            "id": idref,
            "file": name,
            "title": titles.get(name, titles.get(href, "")),
            "paragraphs": len(paras),
            "chars": len(plain),
            "top_classes": classes.most_common(8),
            "ad_hits": hits,
            "has_img": "<img" in text,
        })

    doc["images"] = sorted(
        ({"file": k, "kb": round(len(v) / 1024, 1)} for k, v in files.items()
         if k.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))),
        key=lambda x: x["file"],
    )
    doc["css_files"] = sorted(k for k in files if k.endswith(".css"))
    doc["total_kb"] = round(sum(len(v) for v in files.values()) / 1024, 1)
    doc["has_titlepage"] = any("titlepage" in k for k in files)
    # 疑似重复目录页：多个文件都只含链接
    toc_like = [
        c["file"] for c in doc["chapters"]
        if c["top_classes"] and any(k.startswith("calibre_") for k, _ in c["top_classes"])
        and text_links(files.get(c["file"], b"").decode("utf-8", "ignore"))
    ]
    doc["toc_like_pages"] = toc_like

    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return

    print(f"文件：{src}{'（zip）' if from_zip else '（目录）'}  共 {doc['files']} 个条目 / {doc['total_kb']} KB")
    print(f"标题页：{'有' if doc['has_titlepage'] else '无'}    CSS：{', '.join(doc['css_files']) or '无'}")
    print()
    print(f"{'顺序':<4}{'文件':<28}{'章节名':<24}{'段落':>5}{'字数':>8}  推广词")
    for i, c in enumerate(doc["chapters"], 1):
        flag = ",".join(c["ad_hits"]) or "-"
        print(f"{i:<4}{c['file']:<28}{c['title'][:22]:<24}{c['paragraphs']:>5}{c['chars']:>8}  {flag}")
    if doc["images"]:
        print()
        print("图片：")
        for im in doc["images"]:
            print(f"  {im['file']}  {im['kb']} KB")
    if len(toc_like) > 1:
        print()
        print(f"疑似重复目录页（可删其一）：{', '.join(toc_like)}")


def text_links(text: str) -> bool:
    """目录页特征：链接多、段落全是短条目、整页字数很少。
    注意别把「译者注释页」误判成目录页——它也是一条链接配一段文字，
    但每段都很长、整页字数也多。"""
    links = len(re.findall(r"<a\s", text))
    paras = TEXT_RE.findall(text)
    if links < 3 or not paras:
        return False
    lens = [len(TAG_RE.sub("", p).strip()) for p in paras]
    avg = sum(lens) / len(lens)
    total = len(TAG_RE.sub("", text).strip())
    return avg < 32 and total < 600


if __name__ == "__main__":
    main()
