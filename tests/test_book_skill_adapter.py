from pathlib import Path
import pytest

from novel_ai.book_skill_adapter import vendored_book_to_skill_root, convert_documents_to_skill


def test_adapter_requires_initialized_submodule(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        vendored_book_to_skill_root(tmp_path)


def test_adapter_rejects_missing_input(tmp_path: Path):
    vendor = tmp_path / "vendor" / "book-to-skill" / "book_to_skill"
    vendor.mkdir(parents=True)
    (vendor / "__main__.py").write_text("", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        convert_documents_to_skill([tmp_path / "missing.txt"], repo_root=tmp_path)
