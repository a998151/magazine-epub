"""Build the real XHTML and raster assets used by the paper-wash preset."""

import hashlib
import io
import posixpath
from collections import Counter
from functools import lru_cache
from xml.dom import Node, minidom


LEAD = "paper-wash-lead"
READY = "paper-wash-ready"
ASSET_DIR = "paper-wash"
RULE = f"{ASSET_DIR}/ornament.png"
EDGE = (357, 349, 356, 352, 362, 359, 368, 365, 374, 370, 384, 378,
        383, 378, 383, 370, 376, 366, 369, 354, 360, 350, 361, 359, 365,
        361, 371, 367, 379, 376, 387, 384, 396, 394, 381, 387, 374, 378,
        366, 371, 358, 363, 357, 366, 372, 366, 380, 375, 383, 392, 386,
        385, 375, 379, 366, 373, 368, 373, 384, 378, 388, 382, 381, 369,
        375, 361, 364, 355, 358)


def elements(node):
    return [child for child in node.childNodes if child.nodeType == Node.ELEMENT_NODE]


def has_class(node, name):
    return name in node.getAttribute("class").split()


def add_class(node, name):
    if not has_class(node, name):
        node.setAttribute("class", (node.getAttribute("class") + " " + name).strip())


def text_parts(node, excluded=()):
    if node in excluded:
        return []
    if node.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE):
        return [node.data] if node.data.strip() else []
    return [text for child in node.childNodes for text in text_parts(child, excluded)]


def ids(node):
    return Counter(el.getAttribute("id") for el in node.getElementsByTagName("*")
                   if el.hasAttribute("id"))


def opening(body):
    children = elements(body)
    heading = next((node for node in children if node.localName == "h1"
                    or has_class(node, "chapter-opener") or has_class(node, "hero")), None)
    if heading is None:
        return None
    lead = next((node for node in children if has_class(node, LEAD)), None)
    if lead is None:
        # Leave illustrations later in the chapter where the author placed them.
        prose = next((index for index, node in enumerate(children)
                      if node.localName == "p" and text_parts(node)), len(children))
        lead = next((node for node in children[:prose] if has_class(node, "plate")), None)
    if lead is None:
        return None
    images = lead.getElementsByTagNameNS("*", "img")
    if len(images) != 1:
        return None
    return heading, lead, images[0]


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@lru_cache(maxsize=8)
def ink_alpha(size):
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    width, height = size
    border = Image.new("L", size)
    points = [(round(i * width / (len(EDGE) - 1)), round(y * height / 400))
              for i, y in enumerate(EDGE)]
    ImageDraw.Draw(border).polygon([(0, 0), (width, 0), *reversed(points)], fill=255)
    fade = Image.new("L", (1, height))
    ramp = []
    for row in range(height):
        y = row / max(1, height - 1)
        if y <= .80:
            opacity = 1
        elif y <= .91:
            opacity = 1 - (y - .80) * .12 / .11
        else:
            opacity = .88 * (1 - y) / .09
        ramp.append(round(255 * opacity))
    fade.putdata(ramp)
    return ImageChops.multiply(border.filter(ImageFilter.GaussianBlur(1)), fade.resize(size))


def wash_image(raw):
    from PIL import Image, ImageChops, ImageOps, ImageStat

    with Image.open(io.BytesIO(raw)) as file:
        image = ImageOps.exif_transpose(file).convert("RGBA")
    # For a tall original, keep its composition instead of cutting it into a strip.
    width = min(1080, image.width)
    ratio = 2.02 if image.width / image.height >= 1.35 else image.width / image.height
    size = (width, max(1, round(width / ratio)))
    gray = ImageOps.grayscale(image)
    lower_margin = gray.crop((0, image.height * 9 // 10, image.width, image.height))
    # Use the illustration's white lower margin for the crop before cutting the figures above it.
    vertical_focus = .04 if ImageStat.Stat(lower_margin).mean[0] >= 245 else .44
    image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(.5, vertical_focus))
    toned = image.convert("RGB")
    red, green, blue = toned.split()
    high = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    low = ImageChops.darker(ImageChops.darker(red, green), blue)
    if ImageStat.Stat(ImageChops.difference(high, low)).mean[0] < 10:
        paper = Image.new("RGB", size, "#b2bca9")
        neutral = ImageOps.grayscale(toned).convert("RGB")
        toned = Image.blend(paper, ImageChops.multiply(paper, neutral), .86)
    alpha = ImageChops.multiply(image.getchannel("A"), ink_alpha(size))
    toned.putalpha(alpha)
    return png(toned)


def ornament():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (280, 18))
    draw = ImageDraw.Draw(image)
    gold = "#8b7950"
    draw.line([(0, 9), (84, 9)], fill=(139, 121, 80, 140), width=2)
    draw.line([(196, 9), (279, 9)], fill=(139, 121, 80, 140), width=2)
    draw.line([(105, 9), (175, 9)], fill=gold, width=2)
    for x in (131, 149):
        draw.line([(x - 9, 9), (x, 2), (x + 9, 9), (x, 16), (x - 9, 9)], fill=gold, width=2)
    return png(image)


def update_page(doc, body, heading, lead, image, image_href, rule_href):
    def new_element(tag):
        name = f"{body.prefix}:{tag}" if body.prefix else tag
        return doc.createElementNS(body.namespaceURI, name)

    before_text = text_parts(body, excluded=(lead,))
    before_ids = ids(body)
    caption = next((node for node in elements(lead) if node.localName == "figcaption"
                    or has_class(node, "caption")), None)
    caption_text = text_parts(caption) if caption is not None else []
    add_class(body, READY)
    add_class(lead, LEAD)
    add_class(heading, "paper-wash-title")
    if lead is not body.firstChild:
        body.insertBefore(lead, body.firstChild)
    image.setAttribute("src", image_href)

    # Move existing chapter entry points above the art while preserving every ID.
    for node in [heading, *heading.getElementsByTagName("*")]:
        if node.hasAttribute("id"):
            anchor = new_element("span")
            anchor.setAttribute("id", node.getAttribute("id"))
            node.removeAttribute("id")
            lead.insertBefore(anchor, image if image.parentNode is lead else lead.firstChild)

    rule = new_element("div")
    rule.setAttribute("class", "paper-wash-rule")
    rule_image = new_element("img")
    rule_image.setAttribute("src", rule_href)
    rule_image.setAttribute("alt", "")
    rule.appendChild(rule_image)
    if heading.nextSibling is None:
        body.appendChild(rule)
    else:
        body.insertBefore(rule, heading.nextSibling)

    section = next((node for node in elements(body) if has_class(node, "kindle-cn-heading-3")), None)
    if section is not None:
        add_class(section, "paper-wash-first-section")

    caption_block = new_element("div")
    if caption is not None:
        for name in caption.attributes.keys():
            caption_block.setAttribute(name, caption.getAttribute(name))
        add_class(caption_block, "paper-wash-caption")
        while caption.firstChild is not None:
            caption_block.appendChild(caption.firstChild)
        lead.removeChild(caption)
        body.appendChild(caption_block)

    if (text_parts(body, excluded=(lead, rule, caption_block)) != before_text
            or text_parts(caption_block) != caption_text or ids(body) != before_ids):
        raise ValueError("画入纸面改版时，正文、图注或锚点发生意外变化")


def reflow(archive, opf_path, spine, member_path):
    known = set(archive.namelist())
    additions = {}
    replacements = {}
    folder = posixpath.dirname(opf_path)

    for path in dict.fromkeys(spine):
        if not path or not path.lower().endswith((".xhtml", ".html", ".htm")):
            continue
        doc = minidom.parseString(archive.read(path))
        bodies = doc.getElementsByTagNameNS("*", "body")
        if not bodies or has_class(bodies[0], READY):
            continue
        found = opening(bodies[0])
        if found is None:
            continue
        heading, lead, image = found
        original = member_path(path, image.getAttribute("src"))
        if original not in known:
            raise ValueError(f"{path} 的章首图需要是 EPUB 中的本地图像")
        raw = archive.read(original)
        asset = f"{ASSET_DIR}/lead-{hashlib.sha256(raw).hexdigest()[:24]}.png"
        asset_path = posixpath.join(folder, asset)
        if asset_path not in additions:
            additions[asset_path] = wash_image(raw)
        rule_path = posixpath.join(folder, RULE)
        update_page(doc, bodies[0], heading, lead, image,
                    posixpath.relpath(asset_path, posixpath.dirname(path) or "."),
                    posixpath.relpath(rule_path, posixpath.dirname(path) or "."))
        replacements[path] = doc.toxml(encoding="utf-8")

    if not replacements:
        return replacements, additions
    additions[posixpath.join(folder, RULE)] = ornament()
    if conflict := known & additions.keys():
        raise ValueError(f"画入纸面资源路径已被占用：{min(conflict)}")

    doc = minidom.parseString(archive.read(opf_path))
    manifest = doc.getElementsByTagNameNS("*", "manifest")[0]
    registered = {el.getAttribute("id") for el in elements(manifest)}
    name = f"{manifest.prefix}:item" if manifest.prefix else "item"
    for path in additions:
        item = doc.createElementNS(manifest.namespaceURI, name)
        identifier = "magazine-" + posixpath.basename(path).removesuffix(".png")
        if identifier in registered:
            raise ValueError(f"画入纸面资源 ID 已被占用：{identifier}")
        item.setAttribute("id", identifier)
        item.setAttribute("href", posixpath.relpath(path, folder or "."))
        item.setAttribute("media-type", "image/png")
        manifest.appendChild(item)
    replacements[opf_path] = doc.toxml(encoding="utf-8")
    return replacements, additions
