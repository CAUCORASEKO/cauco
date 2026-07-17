from pathlib import Path

import pytest

from cauco_core.memory.exceptions import InvalidSearchQueryError
from cauco_core.memory.search import MemorySearch
from cauco_core.memory.service import MemoryService


def write(brain: Path, name: str, content: str) -> None:
    (brain / name).write_text(content, encoding="utf-8")


def test_search_scoring_is_weighted_and_deterministic(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    write(brain, "title.md", "# Atlas\nOther notes")
    write(brain, "heading.md", "# Notes\n## Atlas status\nOther")
    write(brain, "body.md", "# Notes\nThe atlas project appears in the body.")
    results = MemorySearch(MemoryService(brain)).search("ATLAS", limit=5)
    assert [result.relative_path for result in results] == [
        "title.md",
        "heading.md",
        "body.md",
    ]
    assert results[0].score > results[1].score > results[2].score
    assert all(result.matched_terms == ["atlas"] for result in results)


def test_search_limit_and_stable_tie_order(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    write(brain, "b.md", "project")
    write(brain, "a.md", "project")
    results = MemorySearch(MemoryService(brain)).search("project", limit=1)
    assert [result.relative_path for result in results] == ["a.md"]


def test_excerpt_is_bounded_and_contains_match(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    write(brain, "long.md", f"# Long\n{'x' * 300} project {'y' * 300}")
    result = MemorySearch(MemoryService(brain)).search("project")[0]
    assert "project" in result.excerpt
    assert len(result.excerpt) <= 242
    assert result.excerpt.startswith("…")
    assert result.excerpt.endswith("…")


@pytest.mark.parametrize("query", ["", "   ", "?!!", "x" * 201])
def test_invalid_search_query_rejected(tmp_path: Path, query: str) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    with pytest.raises(InvalidSearchQueryError):
        MemorySearch(MemoryService(brain)).search(query)
