"""Offline tests for verify.py's content-level cross-checks (no API, no network).

Covers the free metadata checks added for roadmap #5: a matrix row that attributes
a paper to the wrong author (張冠李戴) or states a year conflicting with the real
metadata is flagged, while cosmetic author differences (surname-only, listing a
co-author, "et al.") are not. Runs under pytest or as a plain script.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import verify  # noqa: E402


def _matrix(rows: str) -> str:
    return (
        "## 文獻矩陣\n\n"
        "| 標題 | 作者 | 年份 | 期刊/會議 | 引用數 | 研究方法 | 主要發現 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n" + rows + "\n"
    )


_PAPERS = [
    {
        "title": "Tasks and Technologies",
        "authors": ["Daron Acemoglu", "Pascual Restrepo"],
        "year": 2021,
    },
    {"title": "GPTs are GPTs", "authors": ["Tyler Cowen"], "year": 2023},
]


# --- name tokenization --------------------------------------------------------

def test_name_tokens_drops_initials_and_stopwords():
    assert verify._name_tokens("Daron Acemoglu") == {"daron", "acemoglu"}
    assert verify._name_tokens("D. Acemoglu et al.") == {"acemoglu"}
    assert verify._name_tokens("") == set()


def test_name_tokens_ignores_cjk():
    assert verify._name_tokens("李明") == set()


# --- author consistency -------------------------------------------------------

def test_author_consistent_surname_only():
    assert verify._author_consistent("Acemoglu", ["Daron Acemoglu", "Pascual Restrepo"])


def test_author_consistent_second_author_is_fine():
    # Listing a different but real author of the paper is not 張冠李戴.
    assert verify._author_consistent("Restrepo", ["Daron Acemoglu", "Pascual Restrepo"])


def test_author_consistent_with_et_al():
    assert verify._author_consistent("Acemoglu et al.", ["Daron Acemoglu"])


def test_author_inconsistent_when_no_overlap():
    assert not verify._author_consistent("Smith", ["Daron Acemoglu", "Pascual Restrepo"])


def test_author_consistent_when_claimed_only_initial():
    # A bare initial isn't judgeable -> don't accuse.
    assert verify._author_consistent("D.", ["Daron Acemoglu"])


def test_author_consistent_when_no_authors_metadata():
    assert verify._author_consistent("Whoever", [])


def test_author_consistent_when_claimed_is_cjk():
    # CJK claimed name vs romanized metadata can't be compared -> don't flag.
    assert verify._author_consistent("阿西莫格魯", ["Daron Acemoglu"])


# --- year conflict ------------------------------------------------------------

def test_year_conflicts_true_when_differ():
    assert verify._year_conflicts("2019", 2021)


def test_year_conflicts_false_when_same_or_decorated():
    assert not verify._year_conflicts("2021", 2021)
    assert not verify._year_conflicts("2021年", 2021)


def test_year_conflicts_false_when_one_missing():
    assert not verify._year_conflicts("", 2021)
    assert not verify._year_conflicts("n/a", 2021)
    assert not verify._year_conflicts("2021", None)


# --- verify_matrix integration ------------------------------------------------

def test_matrix_flags_author_attribution_error():
    md = _matrix(
        "| Tasks and Technologies | Smith | 2021 | V | 5 | 實證 | 發現 |\n"
        "| GPTs are GPTs | Cowen | 2023 | V | 9 | 實證 | 發現 |"
    )
    result = verify.verify_matrix(md, _PAPERS)
    assert result.checked
    assert result.matched_rows == 2
    assert [m.claimed for m in result.author_mismatches] == ["Smith"]
    assert result.author_mismatches[0].title == "Tasks and Technologies"
    assert "Acemoglu" in result.author_mismatches[0].actual
    assert not result.ok


def test_matrix_flags_year_drift():
    md = _matrix(
        "| Tasks and Technologies | Acemoglu | 2018 | V | 5 | 實證 | 發現 |\n"
        "| GPTs are GPTs | Cowen | 2023 | V | 9 | 實證 | 發現 |"
    )
    result = verify.verify_matrix(md, _PAPERS)
    assert [m.claimed for m in result.year_mismatches] == ["2018"]
    assert result.year_mismatches[0].actual == "2021"
    assert result.author_mismatches == []
    assert not result.ok


def test_matrix_clean_has_no_content_issues():
    md = _matrix(
        "| Tasks and Technologies | Acemoglu | 2021 | V | 5 | 實證 | 發現 |\n"
        "| GPTs are GPTs | Cowen, T. | 2023 | V | 9 | 實證 | 發現 |"
    )
    result = verify.verify_matrix(md, _PAPERS)
    assert result.author_mismatches == []
    assert result.year_mismatches == []
    assert result.ok


def test_matrix_existence_check_still_works():
    md = _matrix("| A Totally Invented Paper | Ghost | 2020 | V | 0 | 實證 | 發現 |")
    result = verify.verify_matrix(md, _PAPERS)
    assert result.unmatched_titles == ["A Totally Invented Paper"]
    # An unmatched row isn't content-checked (no paper to compare against).
    assert result.author_mismatches == []
    assert not result.ok


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
