"""Static checks on the paper source before it goes anywhere.

Catches the three things that silently break an arXiv build: a macro the prose
uses that numbers.tex never defines (renders as nothing, so a sentence loses its
number), a \\cite key missing from the bibliography, and a missing figure or
\\input file.
"""

import re
import sys
from pathlib import Path

PAPER = Path(__file__).resolve().parent.parent / "paper"
BS = chr(92)


def main() -> int:
    tex = (PAPER / "main.tex").read_text(encoding="utf-8")
    numbers_path = PAPER / "numbers.tex"
    nums = numbers_path.read_text(encoding="utf-8") if numbers_path.exists() else ""

    defined = set(re.findall(re.escape(BS) + r"newcommand\{" + re.escape(BS) + r"([A-Za-z]+)\}", nums))
    used = set(re.findall(re.escape(BS) + r"([a-z][A-Za-z]*)\{\}", tex))

    # LaTeX builtins that also match the backslash-name-braces shape
    BUILTINS = {"date", "maketitle", "noindent", "centering", "small", "toprule",
                "midrule", "bottomrule", "columnwidth", "today"}
    problems = 0
    missing = sorted(used - defined - BUILTINS)
    print(f"macros defined: {len(defined)}   used in prose: {len(used)}")
    if missing:
        print(f"  MISSING (sentence would lose its number): {missing}")
        problems += len(missing)
    else:
        print("  all macros used by the prose are defined")
    unused = sorted(defined - used)
    if unused:
        print(f"  defined but unused (harmless): {unused}")

    keys = set()
    for group in re.findall(r"cite\{([^}]+)\}", tex):
        keys.update(k.strip() for k in group.split(","))
    bib = set(re.findall(r"@\w+\{([^,]+),", (PAPER / "references.bib").read_text(encoding="utf-8")))
    print(f"\ncitations used: {len(keys)}   bib entries: {len(bib)}")
    missing_cites = sorted(keys - bib)
    if missing_cites:
        print(f"  MISSING from references.bib: {missing_cites}")
        problems += len(missing_cites)
    else:
        print("  every cited key resolves")
    if sorted(bib - keys):
        print(f"  in bib but never cited: {sorted(bib - keys)}")

    print("\nincluded files:")
    for name in re.findall(r"input\{([^}]+)\}", tex):
        path = PAPER / (name if name.endswith(".tex") else name + ".tex")
        ok = path.exists()
        print(f"  {path.name:18} {'ok' if ok else 'MISSING'}")
        problems += 0 if ok else 1
    for name in re.findall(r"includegraphics\[[^\]]*\]\{([^}]+)\}", tex):
        path = PAPER / name
        ok = path.exists()
        print(f"  {name:34} {'ok' if ok else 'MISSING'}")
        problems += 0 if ok else 1

    dashes = tex.count("---")
    print(f"\nem dashes in source: {dashes}")
    problems += dashes

    print("\n" + ("ALL CHECKS PASS" if problems == 0 else f"{problems} PROBLEM(S)"))
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
