#!/usr/bin/env python3
"""Build Kytoon One from Nunito: offset contours outward, round corners, clean up overlaps."""

import argparse
import math

import ufoLib2
from ufoLib2.objects import Contour, Point
from pathops import Path, union


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1])

def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1])

def vscale(v, s):
    return (v[0] * s, v[1] * s)

def vlen(v):
    return math.hypot(v[0], v[1])

def vnorm(v):
    l = vlen(v)
    return (v[0] / l, v[1] / l) if l > 1e-10 else (0, 0)


def _sanitize_contours(glyph):
    """Fix bad contour data from pathops (degenerate cubics, stray qcurves)."""
    new_contours = []
    for contour in glyph:
        pts = list(contour.points)
        if not pts:
            continue

        # Parse contour into segments.  A segment = (off-curves..., on-curve).
        # The contour is cyclic: points before the first on-curve belong to
        # the segment that ends with the LAST on-curve (wrap-around).
        segments = []
        buf = []
        for p in pts:
            if p.type is not None:
                segments.append((list(buf), p))
                buf = []
            else:
                buf.append(p)
        # Leftover off-curves wrap to the first segment
        if buf and segments:
            first_off, first_on = segments[0]
            segments[0] = (buf + first_off, first_on)

        # Fix each segment
        fixed_pts = []
        for off_curves, on_pt in segments:
            seg_type = on_pt.type
            n_off = len(off_curves)

            if seg_type == "qcurve":
                # Promote to cubic: if 1 off-curve, duplicate it
                if n_off == 1:
                    ocp = off_curves[0]
                    fixed_pts.append(Point(ocp.x, ocp.y))
                    fixed_pts.append(Point(ocp.x, ocp.y))
                elif n_off == 0:
                    pass  # will become a line
                else:
                    fixed_pts.extend(off_curves)
                fixed_pts.append(Point(on_pt.x, on_pt.y,
                                       type="curve" if n_off > 0 else "line",
                                       smooth=on_pt.smooth, name=on_pt.name))

            elif seg_type == "curve":
                if n_off == 0:
                    fixed_pts.append(Point(on_pt.x, on_pt.y, type="line",
                                           smooth=on_pt.smooth, name=on_pt.name))
                elif n_off == 1:
                    ocp = off_curves[0]
                    fixed_pts.append(Point(ocp.x, ocp.y))
                    fixed_pts.append(Point(ocp.x, ocp.y))
                    fixed_pts.append(on_pt)
                else:
                    fixed_pts.extend(off_curves)
                    fixed_pts.append(on_pt)
            else:
                # line or move, no off-curves expected, but include if present
                fixed_pts.extend(off_curves)
                fixed_pts.append(on_pt)

        nc = Contour()
        for p in fixed_pts:
            nc.points.append(p)
        new_contours.append(nc)

    glyph.contours.clear()
    for c in new_contours:
        glyph.contours.append(c)


def _decompose_and_remove_overlaps(glyph, font):
    """Decompose components + remove overlaps via pathops."""
    path = Path()
    glyph.draw(path.getPen(), font)
    result = Path()
    union([path], result.getPen())
    glyph.contours.clear()
    glyph.components.clear()
    result.draw(glyph.getPen())
    _sanitize_contours(glyph)


def _remove_overlaps(glyph):
    """Remove self-intersections after offset."""
    path = Path()
    glyph.draw(path.getPen())
    result = Path()
    union([path], result.getPen())
    glyph.contours.clear()
    glyph.components.clear()
    result.draw(glyph.getPen())
    _sanitize_contours(glyph)


def _offset_glyph(glyph, offset):
    """Push each contour outward along averaged vertex normals."""
    for contour in glyph:
        pts = list(contour)
        if len(pts) < 3:
            continue

        on_idx = [i for i, p in enumerate(pts) if p.type is not None]
        on_coords = [(pts[i].x, pts[i].y) for i in on_idx]
        n_on = len(on_coords)
        if n_on < 2:
            continue

        # Per-edge outward normals
        edge_normals = []
        for j in range(n_on):
            p0 = on_coords[j]
            p1 = on_coords[(j + 1) % n_on]
            d = vsub(p1, p0)
            edge_normals.append(vnorm((d[1], -d[0])))

        # Per-vertex: average flanking edge normals
        deltas = {}
        for j, idx in enumerate(on_idx):
            n_prev = edge_normals[(j - 1) % n_on]
            n_curr = edge_normals[j]
            avg = vadd(n_prev, n_curr)
            if vlen(avg) < 1e-6:
                avg = n_prev
                scale = offset
            else:
                avg = vnorm(avg)
                dot = n_prev[0] * n_curr[0] + n_prev[1] * n_curr[1]
                cos_half = math.sqrt(max(0.5 * (1.0 + dot), 0.01))
                scale = min(offset / cos_half, offset * 3)
            deltas[idx] = vscale(avg, scale)

        def nearest_delta(off_i):
            n = len(pts)
            for step in range(1, n):
                for candidate in ((off_i + step) % n, (off_i - step) % n):
                    if candidate in deltas:
                        return deltas[candidate]
            return (0, 0)

        for i, pt in enumerate(pts):
            dx, dy = deltas.get(i, nearest_delta(i))
            pt.x += dx
            pt.y += dy


def _round_corners(glyph, radius):
    """Replace sharp line corners with cubic arcs."""
    new_contours = []
    for contour in glyph:
        pts = list(contour)
        if len(pts) < 3:
            new_contours.append(contour)
            continue

        on_idx = [i for i, p in enumerate(pts) if p.type is not None]
        if len(on_idx) < 3:
            new_contours.append(contour)
            continue

        n_on = len(on_idx)
        n_pts = len(pts)
        new_pts = []

        for seg_i in range(n_on):
            curr_oci = on_idx[seg_i]
            prev_oci = on_idx[(seg_i - 1) % n_on]
            next_oci = on_idx[(seg_i + 1) % n_on]
            pt = pts[curr_oci]

            # Collect preceding off-curve points for this segment
            if seg_i == 0:
                prev_end = on_idx[-1]
            else:
                prev_end = on_idx[seg_i - 1]
            preceding = []
            j = (prev_end + 1) % n_pts
            while j != curr_oci:
                preceding.append(pts[j])
                j = (j + 1) % n_pts

            # Only round line-type, non-smooth corners
            should_round = False
            r = 0
            if pt.type == "line" and not pt.smooth:
                p_prev = (pts[prev_oci].x, pts[prev_oci].y)
                p_curr = (pt.x, pt.y)
                p_next = (pts[next_oci].x, pts[next_oci].y)

                v_in = vsub(p_prev, p_curr)
                v_out = vsub(p_next, p_curr)
                len_in = vlen(v_in)
                len_out = vlen(v_out)

                if len_in > 1e-6 and len_out > 1e-6:
                    vin_n = vnorm(v_in)
                    vout_n = vnorm(v_out)
                    dot = vin_n[0] * vout_n[0] + vin_n[1] * vout_n[1]
                    dot = max(-1.0, min(1.0, dot))
                    angle = math.acos(dot)
                    if angle > math.radians(15):
                        r = min(radius, len_in * 0.4, len_out * 0.4)
                        if r >= 0.5:
                            should_round = True

            if not should_round:
                new_pts.extend(preceding)
                new_pts.append(pt)
            else:
                v_in_n = vnorm(v_in)
                v_out_n = vnorm(v_out)
                p_curr = (pt.x, pt.y)
                p_start = vadd(p_curr, vscale(v_in_n, r))
                p_end = vadd(p_curr, vscale(v_out_n, r))
                kappa = 0.55
                cp1 = vadd(p_start, vscale(v_in_n, -r * kappa))
                cp2 = vadd(p_end, vscale(v_out_n, -r * kappa))

                new_pts.extend(preceding)
                new_pts.append(Point(p_start[0], p_start[1], type="line"))
                new_pts.append(Point(cp1[0], cp1[1]))
                new_pts.append(Point(cp2[0], cp2[1]))
                new_pts.append(Point(p_end[0], p_end[1],
                                     type="curve", smooth=True))

        new_contour = Contour()
        for p in new_pts:
            new_contour.points.append(p)
        new_contours.append(new_contour)

    glyph.contours.clear()
    for c in new_contours:
        glyph.contours.append(c)


COPYRIGHT = (
    "Copyright 2026 The Kytoon One Project Authors "
    "(https://github.com/michaelsfonts/kytoon)"
)


def main():
    parser = argparse.ArgumentParser(
        description="Build Kytoon One from a UFO source."
    )
    parser.add_argument(
        "input", nargs="?", default="Nunito-Bold.ufo",
        help="Input UFO path (default: Nunito-Bold.ufo)",
    )
    parser.add_argument(
        "-o", "--output", default="Kytoon-Regular.ufo",
        help="Output UFO path (default: Kytoon-Regular.ufo)",
    )
    parser.add_argument(
        "--offset", type=float, default=28,
        help="Outward contour offset in units (default: 28)",
    )
    parser.add_argument(
        "--radius", type=float, default=12,
        help="Corner rounding radius in units (default: 12)",
    )
    parser.add_argument(
        "--spacing-compensation", type=float, default=20,
        help="Extra sidebearing added to each side (default: 20)",
    )
    args = parser.parse_args()

    print(f"Loading {args.input} ...")
    font = ufoLib2.Font.open(args.input)

    font.info.familyName = "Kytoon One"
    font.info.styleName = "Regular"
    font.info.postscriptFontName = "Kytoon-Regular"
    font.info.openTypeNamePreferredFamilyName = "Kytoon One"
    font.info.openTypeNamePreferredSubfamilyName = "Regular"
    font.info.styleMapFamilyName = "Kytoon One"
    font.info.styleMapStyleName = "regular"
    font.info.openTypeNameUniqueID = "Kytoon-Regular"
    font.info.copyright = COPYRIGHT

    processed = 0
    skipped = 0
    errors = []
    glyph_names = list(font.keys())
    total = len(glyph_names)

    for i, name in enumerate(glyph_names):
        glyph = font[name]

        has_contours = bool(glyph.contours)
        has_components = bool(glyph.components)

        if not has_contours and not has_components:
            skipped += 1
            continue

        # Component-only glyphs: skip (they'll reference the inflated base)
        if not has_contours and has_components:
            skipped += 1
            continue

        try:
            _decompose_and_remove_overlaps(glyph, font)

            if not glyph.contours:
                skipped += 1
                continue

            _offset_glyph(glyph, args.offset)

            _remove_overlaps(glyph)

            _round_corners(glyph, args.radius)

            bounds = glyph.getBounds(font)
            if bounds is not None:
                for contour in glyph:
                    for pt in contour:
                        pt.x += args.spacing_compensation
                glyph.width += 2 * args.spacing_compensation

            processed += 1
            if (i + 1) % 100 == 0 or (i + 1) == total:
                print(f"  [{i+1}/{total}] {name}")

        except Exception as e:
            errors.append((name, str(e)))
            if len(errors) <= 10:
                print(f"  ERR {name}: {e}")

    print(f"\nSaving {args.output} ...")
    font.save(args.output, overwrite=True)

    print(f"\nDone. {processed} processed, {skipped} skipped, {len(errors)} errors.")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
