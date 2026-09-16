#!/usr/bin/env python3
"""Render the Kytoon One specimen PNG from the built TTF.

Shapes the text with HarfBuzz (so kerning is applied) and rasterises each glyph
with FreeType. Matches the existing specimen layout: text "Kytoon One
Regular", black on white, ink box at left=130 / top=95, canvas height 416.

    ./venv/bin/python3 make_specimen.py
"""

import freetype
import uharfbuzz as hb
from PIL import Image

TTF = "../fonts/ttf/KytoonOne-Regular.ttf"
TEXT = "Kytoon One Regular"
TARGET_INK_H = 257      # ink height of the reference specimen
LEFT_PAD = 130
TOP_PAD = 95
RIGHT_PAD = 110
CANVAS_H = 416
OUTPUTS = ["../documentation/specimen.png", "../article/images/specimen.png"]


def shape(px):
    with open(TTF, "rb") as fp:
        data = fp.read()
    face = freetype.Face(TTF)
    face.set_pixel_sizes(0, px)

    hbface = hb.Face(data)
    hbfont = hb.Font(hbface)
    hbfont.scale = (px * 64, px * 64)  # 26.6 fixed point at pixel size
    buf = hb.Buffer()
    buf.add_str(TEXT)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, {"kern": True, "liga": True})

    pen_x = 0.0
    glyphs = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
        bmp = face.glyph.bitmap
        glyphs.append((
            info.codepoint,
            pen_x + pos.x_offset / 64.0 + face.glyph.bitmap_left,
            -(pos.y_offset / 64.0) - face.glyph.bitmap_top,  # top of bitmap rel. to baseline
            bmp.width, bmp.rows, bytes(bmp.buffer),
        ))
        pen_x += pos.x_advance / 64.0
    return glyphs


def render(px):
    glyphs = shape(px)
    big_h = px * 3
    baseline = px * 2
    canvas = Image.new("L", (int(shape_width(glyphs)) + px, big_h), 255)
    for gid, gx, gy, w, h, buf in glyphs:
        if w == 0 or h == 0:
            continue
        glyph_img = Image.frombytes("L", (w, h), buf)
        glyph_img = Image.eval(glyph_img, lambda v: 255 - v)  # ink = dark
        canvas.paste(glyph_img, (int(round(gx)), int(round(baseline + gy))),
                     Image.frombytes("L", (w, h), buf))
    return canvas


def shape_width(glyphs):
    right = 0
    for gid, gx, gy, w, h, buf in glyphs:
        right = max(right, gx + w)
    return right


def ink_bbox(img):
    return Image.eval(img, lambda x: 255 - x).getbbox()


def main():
    # Find the pixel size whose ink height matches the reference.
    px = TARGET_INK_H
    for _ in range(12):
        img = render(px)
        bb = ink_bbox(img)
        ink_h = bb[3] - bb[1]
        if abs(ink_h - TARGET_INK_H) <= 1:
            break
        px = max(1, round(px * TARGET_INK_H / ink_h))
    img = render(px)
    bb = ink_bbox(img)
    crop = img.crop(bb)

    out = Image.new("L", (crop.width + LEFT_PAD + RIGHT_PAD, CANVAS_H), 255)
    out.paste(crop, (LEFT_PAD, TOP_PAD))
    for path in OUTPUTS:
        out.save(path)
        print("wrote", path, out.size, "ink h", bb[3] - bb[1], "px", px)


if __name__ == "__main__":
    main()
