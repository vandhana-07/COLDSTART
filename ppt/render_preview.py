"""
render_preview.py -- draws an approximate picture of each slide in the generated
.pptx so we can check for text overflow / overlaps WITHOUT PowerPoint.

v2: flows mixed-colour runs inside ONE paragraph as a single wrapped paragraph
(the way PowerPoint does it), instead of wrapping each run separately.
Only shapes tagged "CC_*" (created by build_ppt.py) are checked for overflow --
the template's own title boxes are left alone.

Run:  python3 render_preview.py
Out:  preview/slide1.png ... slide6.png  +  a layout report
"""
import os
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.util import Emu
from pptx.enum.text import MSO_ANCHOR

PPTX = "COLDSTART_SEDHACKS26.pptx"
BG = "bg.png"
OUT = "preview"
PX_PER_IN = 100.0

FONTS = {
    ("HK Grotesk Bold", True): "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ("HK Grotesk Bold", False): "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ("DM Serif Display", True): "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ("DM Serif Display", False): "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ("Calibri", True): "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ("Calibri", False): "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
}


def font_for(name, bold, size_pt):
    path = FONTS.get((name, bool(bold))) or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, max(6, int(round(size_pt * PX_PER_IN / 72.0))))


def scale(emu):
    return None if emu is None else Emu(emu).inches * PX_PER_IN


def layout_paragraph(draw, runs, max_px):
    """runs = [(text, font, colour, size_pt)]. Returns (lines, line_height_px)
    where each line = [(word, font, colour, x_offset, width), ...]."""
    tokens = []
    for text, f, colour, size in runs:
        parts = text.split(" ")
        for i, w in enumerate(parts):
            tok = w if i == len(parts) - 1 else w + " "
            if tok:
                tokens.append((tok, f, colour, size))
    lines, cur, x = [], [], 0.0
    max_size = max((r[3] for r in runs), default=12)
    for tok, f, colour, size in tokens:
        tw = draw.textlength(tok, font=f)
        if x + tw > max_px and cur:
            lines.append(cur)
            cur, x = [], 0.0
            if tok.strip() == "":
                continue
        cur.append((tok, f, colour, x, tw))
        x += tw
    if cur:
        lines.append(cur)
    lh = max_size * PX_PER_IN / 72.0 * 1.24
    return lines, lh


def main():
    os.makedirs(OUT, exist_ok=True)
    prs = Presentation(PPTX)
    W = int(scale(prs.slide_width))
    H = int(scale(prs.slide_height))
    bg = Image.open(BG).convert("RGB").resize((W, H))
    problems = []

    for idx, slide in enumerate(prs.slides, start=1):
        img = bg.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        for sh in slide.shapes:
            x, y = scale(sh.left), scale(sh.top)
            w, h = scale(sh.width), scale(sh.height)
            if None in (x, y, w, h):
                continue

            # draw OUR card backgrounds
            if sh.name == "CC_card":
                try:
                    c = sh.fill.fore_color.rgb
                    draw.rounded_rectangle([x, y, x + w, y + h], radius=9,
                                           fill=(c[0], c[1], c[2], 240),
                                           outline=(60, 100, 175, 255), width=1)
                except Exception:
                    draw.rounded_rectangle([x, y, x + w, y + h], radius=9,
                                           fill=(11, 23, 48, 240),
                                           outline=(60, 100, 175, 255), width=1)
                continue
            if sh.name == "CC_arrow":
                draw.polygon([(x, y + h * 0.3), (x + w * 0.6, y + h * 0.3),
                              (x + w * 0.6, y), (x + w, y + h / 2),
                              (x + w * 0.6, y + h), (x + w * 0.6, y + h * 0.7),
                              (x, y + h * 0.7)], fill=(77, 163, 255, 255))
                continue

            if not sh.has_text_frame or not sh.text_frame.text.strip():
                continue

            tf = sh.text_frame
            pad_l = scale(tf.margin_left) or 0
            pad_r = scale(tf.margin_right) or 0
            pad_t = scale(tf.margin_top) or 0
            pad_b = scale(tf.margin_bottom) or 0
            avail = w - pad_l - pad_r

            blocks = []      # (lines, lh, sb, sa)
            total = 0.0
            for p in tf.paragraphs:
                runs = []
                for r in p.runs:
                    if not r.text:
                        continue
                    if "\n" in r.text:
                        # defensive: treat an embedded newline as a paragraph split
                        for piece in r.text.split("\n"):
                            pass
                    name = r.font.name or "Calibri"
                    size = r.font.size.pt if r.font.size else 14
                    f = font_for(name, bool(r.font.bold), size)
                    colour = (220, 230, 245, 255)
                    try:
                        if r.font.color and r.font.color.type is not None:
                            c = r.font.color.rgb
                            colour = (c[0], c[1], c[2], 255)
                    except Exception:
                        pass
                    runs.append((r.text, f, colour, size))
                if not runs:
                    continue
                lines, lh = layout_paragraph(draw, runs, avail)
                sb = (p.space_before.pt if p.space_before else 0) * PX_PER_IN / 72.0
                sa = (p.space_after.pt if p.space_after else 0) * PX_PER_IN / 72.0
                total += sb + len(lines) * lh + sa
                blocks.append((lines, lh, sb, sa))

            cy = y + pad_t
            if tf.vertical_anchor == MSO_ANCHOR.MIDDLE:
                cy = y + (h - total) / 2.0

            for lines, lh, sb, sa in blocks:
                cy += sb
                for line in lines:
                    for tok, f, colour, tx, _tw in line:
                        draw.text((x + pad_l + tx, cy), tok, font=f, fill=colour)
                    cy += lh
                cy += sa

            if sh.name.startswith("CC_") and total > (h - pad_t - pad_b) + 1:
                snippet = tf.text.strip().replace("\n", " ")[:56]
                problems.append(f"slide {idx}: OVERFLOW {total:5.0f}px in {h:5.0f}px box "
                                f"@({x/PX_PER_IN:.2f},{y/PX_PER_IN:.2f})in :: {snippet!r}")

        # ---- NEW: detect two TEXT boxes that overlap each other ----
        boxes = []
        for sh in slide.shapes:
            if not sh.has_text_frame or not sh.text_frame.text.strip():
                continue
            if not sh.name.startswith("CC_"):
                continue
            x, y = scale(sh.left), scale(sh.top)
            w, h = scale(sh.width), scale(sh.height)
            if None in (x, y, w, h):
                continue
            boxes.append((x, y, w, h, sh.text_frame.text.strip().replace("\n", " ")[:44]))
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                ax, ay, aw, ah, at = boxes[i]
                bx, by, bw, bh, bt = boxes[j]
                ox = min(ax + aw, bx + bw) - max(ax, bx)
                oy = min(ay + ah, by + bh) - max(ay, by)
                if ox > 3 and oy > 3:
                    problems.append(
                        f"slide {idx}: TEXT OVERLAP {ox/PX_PER_IN:.2f}x{oy/PX_PER_IN:.2f}in "
                        f":: {at!r} <> {bt!r}")

        img.save(os.path.join(OUT, f"slide{idx}.png"))

    print("---- LAYOUT CHECK (only boxes we created) ----")
    if problems:
        for p in problems:
            print("  " + p)
        print(f"\n  {len(problems)} issue(s) to fix")
    else:
        print("  clean -- no overflow in any box we added")


if __name__ == "__main__":
    main()
