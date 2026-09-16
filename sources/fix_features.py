#!/usr/bin/env python3
"""Restore the @Uppercase glyph class in the UFO's features.fea.

The Glyphs export occasionally writes `@Uppercase = [  ];` (empty) on a
partial save. That class is used by three substitution rules, and an empty
class in a contextual substitution makes fontmake abort with:

    features.fea:...: Empty glyph class in contextual substitution

which halts the whole build (no otf/ttf/woff produced). This guard detects
the blanked class and restores it from the committed snapshot in
`uppercase_class.fea`, so the export can never break the build.

It only acts when the class is clearly blanked (far below a healthy count).
A genuine future edit to the uppercase set stays non-empty and is left
untouched -- if that set ever changes for real, re-snapshot the line into
uppercase_class.fea.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
FEA = HERE / "KytoonOne-Regular.ufo" / "features.fea"
REF = HERE / "uppercase_class.fea"

# A healthy class has ~368 glyphs. Anything far below this means it was blanked.
MIN_GLYPHS = 300


def glyph_count(line: str) -> int:
    """Number of glyph tokens inside `@Uppercase = [ ... ];`."""
    inside = line.split("[", 1)[1].rsplit("]", 1)[0]
    return len(inside.split())


def main() -> int:
    ref_line = REF.read_text().strip()
    lines = FEA.read_text().splitlines(keepends=True)

    idx = next(
        (i for i, l in enumerate(lines) if l.lstrip().startswith("@Uppercase")),
        None,
    )
    if idx is None:
        print("fix_features: @Uppercase class not found in features.fea", file=sys.stderr)
        return 1

    count = glyph_count(lines[idx])
    if count >= MIN_GLYPHS:
        print(f"fix_features: @Uppercase OK ({count} glyphs) -- no change")
        return 0

    newline = "\n" if lines[idx].endswith("\n") else ""
    lines[idx] = ref_line + newline
    FEA.write_text("".join(lines))
    print(
        f"fix_features: @Uppercase was blanked ({count} glyphs) -- "
        f"RESTORED to {glyph_count(ref_line)} glyphs"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
