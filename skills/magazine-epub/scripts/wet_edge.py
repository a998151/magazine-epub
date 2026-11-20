"""Prepare lossless, budgeted PNGs for paper-wash chapter openings."""

from io import BytesIO

from PIL import Image, ImageChops


FADE_FLOOR = 26
ALPHA_CURVE = [max(0, round((alpha - FADE_FLOOR) * 255 / (255 - FADE_FLOOR)))
               for alpha in range(256)]
WHITE_ONLY = [0] * 255 + [255]


def indexed_rgba(image, colors):
    alpha = image.getchannel("A")
    empty = alpha.point(lambda a: 255 if a == 0 else 0)
    opaque = alpha.point(WHITE_ONLY)
    partial = ImageChops.invert(ImageChops.lighter(empty, opaque))

    # Give solid ink, the soft transition and the clear perimeter separate palette entries.
    opaque_colors = colors - 64
    base = image.convert("RGB").quantize(colors=opaque_colors, method=Image.Quantize.FASTOCTREE)
    palette = base.getpalette("RGBA")[:4 * opaque_colors]
    if partial.getbbox():
        edge = Image.new("RGBA", image.size, (255, 255, 255, 0))
        edge.paste(image, mask=partial)
        edge = edge.quantize(colors=63, method=Image.Quantize.FASTOCTREE)
        palette.extend(edge.getpalette("RGBA")[:4 * 63])
        base.paste(edge.point([min(254, i + opaque_colors) for i in range(256)]), mask=partial)
    palette.extend([255] * (4 * 256 - len(palette)))
    palette[-4:] = [255, 255, 255, 0]
    base.paste(255, mask=empty)
    base.putpalette(palette, rawmode="RGBA")
    return base


def check_perimeter(data, empty, white):
    with Image.open(BytesIO(data)) as image:
        if white:
            if "transparency" in image.info or "A" in image.getbands():
                raise ValueError("Kindle 湿边 PNG 残留透明通道")
            residual = [ImageChops.invert(channel) for channel in image.convert("RGB").split()]
        else:
            residual = [image.convert("RGBA").getchannel("A")]
        if any(ImageChops.multiply(channel, empty).getbbox() for channel in residual):
            raise ValueError("湿边外围出现残留像素")


def encode(data, max_side, max_bytes, *, white):
    with Image.open(BytesIO(data)) as original:
        if original.format != "PNG" or getattr(original, "n_frames", 1) != 1:
            raise ValueError("湿边章首图须为单帧 PNG")
        transparent = "A" in original.getbands() or "transparency" in original.info
        if not transparent and not white:
            raise ValueError("请从保留湿边透明通道的 EPUB 构建透明版")
        # The layout script emits truecolor RGBA. The compact editions use indexed PNG.
        indexed = original.mode == "P"
        if (not transparent or indexed and not white) and max(original.size) <= max_side and len(data) <= max_bytes:
            return data
        image = original.convert("RGBA" if transparent else "RGB")
    if not transparent:
        red, green, blue = image.split()
        white_mask = ImageChops.darker(ImageChops.darker(red, green), blue).point(WHITE_ONLY)

    side = min(max(image.size), max_side)
    floor = min(side, 640)
    while True:
        resized = image.copy()
        resized.thumbnail((side, side), Image.Resampling.LANCZOS)
        if transparent:
            alpha = resized.getchannel("A")
            if not indexed:
                alpha = alpha.point(ALPHA_CURVE)
            empty = alpha.point(lambda a: 255 if a == 0 else 0)
            cleared = Image.new("RGBA", resized.size, (255, 255, 255, 0))
            cleared.paste(resized, mask=ImageChops.invert(empty))
            cleared.putalpha(alpha)
        else:
            cleared = resized
            empty = white_mask.resize(resized.size, Image.Resampling.NEAREST)
        if white and transparent:
            background = Image.new("RGBA", cleared.size, "white")
            cleared = Image.alpha_composite(background, cleared).convert("RGB")

        for count in ((255, 128, 80) if white else (256, 176, 128)):
            if white:
                candidate = cleared.quantize(colors=count, method=Image.Quantize.FASTOCTREE)
                # Reserve pure white so palette quantization cannot add a gray rim.
                palette = (candidate.getpalette() + [255] * 768)[:765] + [255, 255, 255]
                candidate.putpalette(palette)
                candidate.paste(255, mask=empty)
            else:
                candidate = indexed_rgba(cleared, count)
            output = BytesIO()
            candidate.save(output, format="PNG", optimize=True)
            if output.tell() <= max_bytes:
                result = output.getvalue()
                check_perimeter(result, empty, white)
                return result
        if side <= floor:
            raise ValueError(f"无法在 {floor}px 内达到 {max_bytes // 1024} KiB 图片预算")
        side = max(floor, round(side * .90))
