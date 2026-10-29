"""The rule register in docs/scoring-rules.md stays honest against the code.

Part 1 of that page is a table per format, one row per rule, each naming
the tests that pin it. These checks keep it auditable: ids are unique and
stable in shape, every pinning test exists, and every article the engines
cite is in the register, so a rule can't be coded without being written down.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "scoring-rules.md"
PART_1_START = "## The rules as written"
PART_1_END = "## Where the program decides or departs"
RULE_ID = re.compile(r"^R-[A-Z]+-\d+$")
ARTICLES = (
    re.compile(r"USAC\s*\d+[A-Z]\d+(?:\([a-z0-9]+\))*"),
    re.compile(r"UCI\s*3\.\d+\.\d+(?:bis|ter)?"),
)


def _normalize(ref: str) -> str:
    return re.sub(r"\s+", " ", ref.replace("USAC", "USAC ").replace("UCI", "UCI ")).strip()


def _part_1() -> str:
    text = DOC.read_text(encoding="utf-8")
    start = text.index(PART_1_START)
    return text[start : text.index(PART_1_END, start)]


def _rows() -> list[list[str]]:
    rows = []
    for line in _part_1().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0].startswith("R-"):
            rows.append(cells)
    return rows


def _refs(text: str) -> set[str]:
    return {_normalize(m.group(0)) for pattern in ARTICLES for m in pattern.finditer(text)}


def test_rule_ids_are_unique_and_well_formed():
    ids = [row[0] for row in _rows()]
    assert ids, "no rule rows found in Part 1"
    assert all(len(row) == 4 for row in _rows()), "every rule row has four cells"
    bad = [i for i in ids if not RULE_ID.match(i)]
    assert not bad, f"malformed rule ids: {bad}"
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"duplicate rule ids: {dupes}"


def test_every_pinning_test_exists():
    # The engines' tests, and the multi-race layer's, whose rules (R-TEAM-4)
    # sit over the aggregate engine rather than in it.
    files = [
        *(ROOT / "tests" / "scoring").glob("*.py"),
        ROOT / "tests" / "control" / "test_multi_race.py",
    ]
    source = "\n".join(p.read_text(encoding="utf-8") for p in files)
    missing = []
    for rule, _articles, _says, pinned in _rows():
        for name in (n.strip().strip("`") for n in pinned.split(",")):
            if name != "unpinned" and f"def {name}(" not in source:
                missing.append(f"{rule}: {name}")
    assert not missing, f"Pinned by names no test in tests/scoring or test_multi_race: {missing}"


def test_every_article_the_engines_cite_is_in_the_register():
    # A code reference like "USAC 2P2" counts when the register cites it or
    # a subsection of it ("USAC 2P2(b)"); a bare substring match would let
    # "UCI 3.2.223" pass on "UCI 3.2.223bis" alone.
    documented = _refs(_part_1())
    code = "\n".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "madtracker" / "scoring").glob("*.py")
    )
    missing = sorted(
        ref
        for ref in _refs(code)
        if ref not in documented and not any(d.startswith(ref + "(") for d in documented)
    )
    assert not missing, f"articles cited in madtracker/scoring but not in Part 1: {missing}"


def test_the_register_names_the_edition_the_code_cites():
    from madtracker.scoring.rules import RULEBOOK_CITATION

    opening = DOC.read_text(encoding="utf-8").split("\n\n")[1]
    assert RULEBOOK_CITATION in opening
