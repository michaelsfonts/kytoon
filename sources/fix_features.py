#!/usr/bin/env python3
"""Heal the UFO's features.fea after a bad Glyphs export.

Two failure modes, both seen in practice, both fatal to the build:

1. `@Uppercase = [  ];` (empty). The Glyphs export occasionally writes the
   class blank on a partial save. That class is used by three substitution
   rules, and an empty class in a contextual substitution makes fontmake
   abort with:

       features.fea:...: Empty glyph class in contextual substitution

   This guard restores it from the committed snapshot in
   `uppercase_class.fea`.

   It only acts when the class is clearly blanked (far below a healthy
   count). A genuine future edit to the uppercase set stays non-empty and is
   left untouched -- if that set ever changes for real, re-snapshot the line
   into uppercase_class.fea.

2. The `frac` feature split apart. Glyphs relocates named lookups (and bare
   `lookup X;` references) out of a feature into a "Prefix" block, and drags
   the feature's closing `} frac;` along with them. The result is an orphan
   `}` at top level and a `frac` feature with no close:

       features.fea:28:1: Expected feature, languagesystem, lookup, markClass,
       table, or glyph class definition, got SYMBOL "}"

   The shipped `frac` is written as plain rules with no named lookups, which
   gives Glyphs nothing to hoist. If an export mangles it anyway, this guard
   deletes the stray Prefix block and restores the feature from the committed
   snapshot in `frac_feature.fea`.
"""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
FEA = HERE / "KytoonOne-Regular.ufo" / "features.fea"
REF = HERE / "uppercase_class.fea"
REF_FRAC = HERE / "frac_feature.fea"

# A healthy class has ~368 glyphs. Anything far below this means it was blanked.
MIN_GLYPHS = 300


def glyph_count(line: str) -> int:
    """Number of glyph tokens inside `@Uppercase = [ ... ];`."""
    inside = line.split("[", 1)[1].rsplit("]", 1)[0]
    return len(inside.split())


def fix_uppercase(text: str) -> tuple[str, str]:
    """Restore @Uppercase if the export blanked it."""
    ref_line = REF.read_text().strip()
    lines = text.splitlines(keepends=True)

    idx = next(
        (i for i, l in enumerate(lines) if l.lstrip().startswith("@Uppercase")),
        None,
    )
    if idx is None:
        return text, "@Uppercase class not found in features.fea"

    count = glyph_count(lines[idx])
    if count >= MIN_GLYPHS:
        return text, f"@Uppercase OK ({count} glyphs) -- no change"

    newline = "\n" if lines[idx].endswith("\n") else ""
    lines[idx] = ref_line + newline
    return (
        "".join(lines),
        f"@Uppercase was blanked ({count} glyphs) -- "
        f"RESTORED to {glyph_count(ref_line)} glyphs",
    )


def fix_frac(text: str) -> tuple[str, str]:
    """Delete a hoisted Prefix block and restore `frac` from the snapshot.

    Only acts when the file is actually broken: either Glyphs wrote a
    "# Prefix: Prefix" block, or the frac feature is missing/unclosed.
    """
    ref_frac = REF_FRAC.read_text().strip() + "\n"

    has_prefix_block = "# Prefix: Prefix" in text
    frac_open = re.search(r"^feature frac \{$", text, flags=re.M)
    frac_intact = bool(
        frac_open
        and re.search(r"^feature frac \{.*?^\} frac;$", text, flags=re.M | re.S)
    )

    if not has_prefix_block and frac_intact:
        return text, "frac OK -- no change"

    what = []

    if has_prefix_block:
        # Everything from the Prefix marker up to the next top-level block.
        text, n = re.subn(
            r"# Prefix: Prefix\n.*?(?=^feature [a-z]{3,4} \{$)",
            "",
            text,
            flags=re.M | re.S,
        )
        if n:
            what.append("removed hoisted Prefix block")

    if frac_intact:
        text = re.sub(
            r"^feature frac \{.*?^\} frac;\n",
            ref_frac,
            text,
            flags=re.M | re.S,
        )
        what.append("restored frac feature")
    elif frac_open:
        # Unclosed frac: replace from its opening line to the next feature.
        text, n = re.subn(
            r"^feature frac \{.*?(?=^feature [a-z]{3,4} \{$)",
            ref_frac + "\n",
            text,
            flags=re.M | re.S,
        )
        what.append("restored unclosed frac feature" if n else "frac feature unclosed and unrecoverable")
    else:
        what.append("frac feature missing entirely -- NOT restored")

    return text, "frac was mangled by the export -- " + ", ".join(what)


def main() -> int:
    original = FEA.read_text()

    text, msg_upper = fix_uppercase(original)
    if msg_upper.startswith("@Uppercase class not found"):
        print(f"fix_features: {msg_upper}", file=sys.stderr)
        return 1

    text, msg_frac = fix_frac(text)

    if text != original:
        FEA.write_text(text)

    print(f"fix_features: {msg_upper}")
    print(f"fix_features: {msg_frac}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
