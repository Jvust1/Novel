"""Synthetic offline author workflow contracts and recovery boundaries."""
import csv
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from novel_ai.author_workflow import (
    chapter_plan_from_outline,
    chapter_revision_matches,
    list_author_chapter_ids,
    load_author_corpus,
    outline_chapter_context,
    release_bundle_bytes,
    save_chapter_plan,
    save_release_bundle,
    validate_chapter_target,
    write_author_chapter,
)
from novel_ai.market_eval import MARKET_RUBRIC, MarketChapter, MarketCorpus, MarketScore, parse_market_scores
from novel_ai.models import ChapterPlan, SceneBeat
from novel_ai.outline import build_hierarchical_outline
from novel_ai.release_pack import MarketProfile, build_release_pack
from novel_ai.storage import ProjectStore
from novel_ai.workflow_guard import validate_plan_stage


def plan(title="第一章"):
    return ChapterPlan(
        chapter_title=title, chapter_promise="查清来信", tension_curve="发现后作出选择",
        scenes=[SceneBeat(
            scene_no=1, pov="林舟", place="渡口", time="晨",
            objective="找到送信人", opposition="渡船已开", choice="借船追赶",
            cost="抵押行李", state_change="失去退路", information_release=["信封来自北岸"],
            foreshadowing=["红绳"], environment_function="雾阻挡辨认", end_hook="船上有人呼救",
        )], must_not_happen=["不能知道幕后人身份"],
    )


def outline_fixture():
    outline = build_hierarchical_outline("测试书", "一封信改变行程", [("卷一", [plan(), plan("其他章节秘密")])])
    chapter = outline.root.children[0].children[0].children[0]
    return outline, chapter


def saved_corpus(tmp_path, ids=None, project="Book", stage="opening_3"):
    store = ProjectStore(tmp_path)
    ids = ids or ["001", "010", "002"]
    for chapter_id in ids:
        store.write_chapter(project, chapter_id, f"测试正文 {chapter_id}。")
    corpus = load_author_corpus(store, project, ids, stage, audience="成人读者", genre="悬疑")
    return store, ids, corpus


def pack_for(corpus):
    return build_release_pack(
        corpus, MarketProfile(audience=corpus.audience or "成人读者", genre=corpus.genre or "悬疑"),
        title="渡口来信", one_line_hook="追一封来历不明的信", short_blurb="一封信引发追索。",
    )


def scores_for(corpus):
    return [MarketScore(
        project=corpus.project, stage=corpus.stage, corpus_sha256=corpus.fingerprint(),
        reviewer_id="human-reviewer", dimension=key, score=4, note="人工测试意见",
    ) for key, _, _ in MARKET_RUBRIC]


def unpack(bundle):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def test_selected_outline_roundtrip_preserves_authored_causality():
    outline, chapter = outline_fixture()
    assert chapter_plan_from_outline(outline, chapter.id) == plan()
    chapter.children[0].metadata["scene_no"] = 9
    chapter.children[0].metadata["choice"] = "作者改为留在岸边"
    restored = chapter_plan_from_outline(outline, chapter.id)
    assert restored.scenes[0].scene_no == 9
    assert restored.scenes[0].choice == "作者改为留在岸边"
    assert len(restored.scenes) == 1


def test_outline_missing_metadata_is_not_fabricated():
    outline, chapter = outline_fixture()
    chapter.children[0].metadata = {}
    restored = chapter_plan_from_outline(outline, chapter.id)
    assert restored.scenes[0].choice == ""
    assert restored.scenes[0].cost == ""
    assert restored.scenes[0].information_release == []
    assert not validate_plan_stage(restored).ok


@pytest.mark.parametrize("kind", ["duplicate_id", "wrong_level", "scene_selected", "unknown_id", "invalid_list", "invalid_scene_no", "duplicate_scene_no"])
def test_outline_rejects_ambiguous_or_malformed_conversion(kind):
    outline, chapter = outline_fixture()
    selected = chapter.id
    if kind == "duplicate_id":
        chapter.children[0].id = chapter.id
    elif kind == "wrong_level":
        chapter.level = "arc"
    elif kind == "scene_selected":
        selected = chapter.children[0].id
    elif kind == "unknown_id":
        selected = "missing"
    elif kind == "invalid_list":
        chapter.children[0].metadata["information_release"] = "不应拆成单字"
    elif kind == "invalid_scene_no":
        chapter.children[0].metadata["scene_no"] = True
    else:
        second = chapter.children[0].model_copy(deep=True)
        second.id = "distinct-scene"
        chapter.children[0].metadata["scene_no"] = second.metadata["scene_no"] = 1
        chapter.children.append(second)
    with pytest.raises(ValueError):
        chapter_plan_from_outline(outline, selected)


def test_outline_context_is_bounded_and_excludes_sibling_chapters():
    outline, chapter = outline_fixture()
    outline.root.children[0].metadata["author_notes"] = ["父层作者备注"]
    chapter.metadata["author_notes"] = "本章作者备注"
    context = outline_chapter_context(outline, chapter.id)
    assert "父层作者备注" in context and "本章作者备注" in context
    assert "其他章节秘密" not in context
    assert "卷一" in context and "第一章" in context
    for node in outline.flatten():
        node.promise = "长内容" * 20000
        node.metadata["author_notes"] = "长备注" * 20000
    bounded_context = outline_chapter_context(outline, chapter.id)
    assert len(bounded_context) <= 8000
    assert "截断" in bounded_context


def test_outline_context_carries_scene_only_author_notes_and_causal_metadata():
    outline, chapter = outline_fixture()
    scene = chapter.children[0]
    scene.promise = "SCENE_ONLY_OBJECTIVE 找到被藏起来的信"
    scene.metadata["author_notes"] = "SCENE_ONLY_NOTE 不得让船先靠岸"
    scene.metadata["choice"] = "SCENE_ONLY_CHOICE 先救岸边的人"
    scene.metadata["cost"] = "SCENE_ONLY_COST 错过渡船"
    scene.metadata["information_release"] = ["SCENE_ONLY_INFORMATION 谁改过地图"]
    sibling = outline.root.children[0].children[0].children[1]
    sibling.children[0].promise = "SIBLING_SCENE_MUST_NOT_ENTER"
    context = outline_chapter_context(outline, chapter.id)
    for marker in ("SCENE_ONLY_OBJECTIVE", "SCENE_ONLY_NOTE", "SCENE_ONLY_CHOICE", "SCENE_ONLY_COST", "SCENE_ONLY_INFORMATION"):
        assert marker in context
    assert "SIBLING_SCENE_MUST_NOT_ENTER" not in context


def test_large_selected_scene_set_has_explicit_budget_truncation():
    outline, chapter = outline_fixture()
    first = chapter.children[0]
    chapter.children = []
    for index in range(80):
        scene = first.model_copy(deep=True)
        scene.id = f"scene-{index}"
        scene.promise = f"本章场景{index}" + "长作者笔记" * 1000
        chapter.children.append(scene)
    context = outline_chapter_context(outline, chapter.id)
    assert len(context) <= 8000
    assert "本章场景0" in context
    assert context.endswith("…（上下文截断，请参阅可编辑计划）")


def test_corpus_uses_explicit_order_and_never_sorts_disk_stems(tmp_path):
    _, ids, corpus = saved_corpus(tmp_path)
    assert [chapter.title for chapter in corpus.chapters] == ids
    assert [chapter.number for chapter in corpus.chapters] == [1, 2, 3]
    assert [chapter.text for chapter in corpus.chapters] == [f"测试正文 {chapter_id}。\n" for chapter_id in ids]


def test_chapter_inventory_never_reads_text_and_ignores_links_and_invalid_names(tmp_path, monkeypatch):
    store, _, _ = saved_corpus(tmp_path / "store")
    directory = store.project_dir("Book") / "chapters"
    (directory / "unrelated.md").write_bytes(b"\xff\xfe")
    (directory / "broken.name.md").write_text("legacy invalid stem", encoding="utf-8")
    external = tmp_path / "private.md"
    external.write_text("private outside project", encoding="utf-8")
    (directory / "linked.md").symlink_to(external)
    (directory / "dangling.md").symlink_to(tmp_path / "missing.md")
    (directory / "directory.md").mkdir()
    def forbid_read(*args, **kwargs):
        raise AssertionError("inventory must not open any chapter")
    monkeypatch.setattr("novel_ai.author_workflow._read_bytes", forbid_read)
    monkeypatch.setattr(Path, "read_text", forbid_read)
    assert list_author_chapter_ids(store, "Book") == ["001", "002", "010", "unrelated"]


def test_chapter_inventory_does_not_create_missing_books_or_follow_directory_links(tmp_path):
    store = ProjectStore(tmp_path / "store")
    assert list_author_chapter_ids(store, "Missing") == []
    assert not (store.root / "projects").exists()
    directory = store.project_dir("Book") / "chapters"
    directory.rmdir()
    external = tmp_path / "external"
    external.mkdir()
    directory.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="符号链接"):
        list_author_chapter_ids(store, "Book")


def test_writer_preflight_is_nonmutating_and_overwrite_requires_explicit_boolean(tmp_path):
    store = ProjectStore(tmp_path)
    path = validate_chapter_target(store, "NewBook", "001")
    assert path == tmp_path / "projects" / "NewBook" / "chapters" / "001.md"
    assert not (tmp_path / "projects").exists()
    store.write_chapter("NewBook", "001", "must remain unchanged")
    original = path.read_bytes()
    with pytest.raises(ValueError, match="已有正文"):
        validate_chapter_target(store, "NewBook", "001")
    with pytest.raises(ValueError, match="明确确认"):
        validate_chapter_target(store, "NewBook", "001", allow_overwrite="false")
    assert validate_chapter_target(store, "NewBook", "001", allow_overwrite=True) == path
    assert path.read_bytes() == original


@pytest.mark.parametrize("project,chapter_id", [
    ("A B", "001"), (" A", "001"), ("", "001"), ("A" * 81, "001"),
    ("Book", "-001"), ("Book", "001-"), ("Book", "a" * 81), ("Book", "../001"),
])
def test_writer_preflight_rejects_normalization_and_length_aliases(tmp_path, project, chapter_id):
    store = ProjectStore(tmp_path)
    with pytest.raises(ValueError):
        validate_chapter_target(store, project, chapter_id)
    assert not (tmp_path / "projects").exists()


@pytest.mark.parametrize("component", ["projects", "project", "chapters", "file"])
def test_writer_preflight_rejects_links_before_creating_or_modifying_targets(tmp_path, component):
    store = ProjectStore(tmp_path / "store")
    external = tmp_path / "external"
    external.mkdir()
    if component == "projects":
        (store.root / "projects").symlink_to(external, target_is_directory=True)
    elif component == "project":
        (store.root / "projects").mkdir()
        (store.root / "projects" / "Book").symlink_to(external, target_is_directory=True)
    else:
        chapters = store.project_dir("Book") / "chapters"
        if component == "chapters":
            chapters.rmdir()
            chapters.symlink_to(external, target_is_directory=True)
        else:
            (chapters / "001.md").symlink_to(external / "not_created.md")
    with pytest.raises(ValueError, match="符号链接"):
        validate_chapter_target(store, "Book", "001", allow_overwrite=True)
    assert list(external.iterdir()) == []


def test_revision_match_requires_exact_saved_bytes_and_rejects_unsafe_or_missing_source(tmp_path):
    store, _, _ = saved_corpus(tmp_path / "store")
    path = store.project_dir("Book") / "chapters" / "001.md"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert chapter_revision_matches(store, "Book", "001", digest)
    assert chapter_revision_matches(store, "Book", "001", digest.upper())
    assert not chapter_revision_matches(store, "Other", "001", digest)
    assert not chapter_revision_matches(store, "Book", "missing", digest)
    assert not chapter_revision_matches(store, "Book", "../001", digest)
    assert not chapter_revision_matches(store, "Book", "001", "invalid")
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    assert not chapter_revision_matches(store, "Book", "001", digest)
    path.unlink()
    external = tmp_path / "external.md"
    external.write_bytes(original)
    path.symlink_to(external)
    assert not chapter_revision_matches(store, "Book", "001", digest)


def test_author_chapter_write_requires_explicit_overwrite_and_normalizes_text(tmp_path):
    store = ProjectStore(tmp_path)
    path = write_author_chapter(store, "Book", "001", "\n  原稿正文。\n")
    assert path.read_bytes() == "原稿正文。\n".encode()
    with pytest.raises(ValueError, match="已有正文"):
        write_author_chapter(store, "Book", "001", "不能覆盖")
    assert path.read_text() == "原稿正文。\n"
    assert write_author_chapter(store, "Book", "001", "新稿正文。", allow_overwrite=True) == path
    assert path.read_text() == "新稿正文。\n"
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("text", ["", " \n\t", None])
def test_empty_author_chapter_never_creates_output(tmp_path, text):
    store = ProjectStore(tmp_path)
    with pytest.raises(ValueError, match="正文不能为空"):
        write_author_chapter(store, "Book", "001", text)
    assert not (tmp_path / "projects").exists()


def test_concurrent_chapter_create_is_never_clobbered(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path)
    def racing_link(source, destination):
        Path(destination).write_bytes(b"other author edits must survive")
        raise FileExistsError("another writer won")
    monkeypatch.setattr("novel_ai.author_workflow.os.link", racing_link)
    with pytest.raises(ValueError, match="未覆盖"):
        write_author_chapter(store, "Book", "001", "generated candidate")
    path = tmp_path / "projects" / "Book" / "chapters" / "001.md"
    assert path.read_bytes() == b"other author edits must survive"
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("overwrite,operation", [(False, "fsync"), (False, "link"), (True, "fsync"), (True, "replace")])
def test_interrupted_author_chapter_write_leaves_no_partial_output(tmp_path, monkeypatch, overwrite, operation):
    store = ProjectStore(tmp_path)
    path = tmp_path / "projects" / "Book" / "chapters" / "001.md"
    if overwrite:
        store.write_chapter("Book", "001", "previous committed chapter")
    def fail(*args):
        raise OSError("simulated interrupted manuscript publication")
    monkeypatch.setattr(f"novel_ai.author_workflow.os.{operation}", fail)
    with pytest.raises(OSError):
        write_author_chapter(store, "Book", "001", "new candidate", allow_overwrite=overwrite)
    if overwrite:
        assert path.read_text() == "previous committed chapter\n"
        assert list(path.parent.iterdir()) == [path]
    else:
        assert not path.exists()
        assert list(path.parent.iterdir()) == []


@pytest.mark.parametrize("bad_id", ["../secret", "/tmp/secret", "a/b", "a\\b", "001.md", "", " 001", "001 ", "a\n", "a\x00", "-a", "a-"])
def test_corpus_rejects_paths_and_normalization_aliases(tmp_path, bad_id):
    store, _, _ = saved_corpus(tmp_path)
    with pytest.raises(ValueError):
        load_author_corpus(store, "Book", [bad_id, "010", "002"], "opening_3")


@pytest.mark.parametrize("ids,stage", [(["001", "001", "002"], "opening_3"), (["001", "002"], "opening_3"), (["001", "010", "002"], "retention_20"), (["001", "010", "002"], "unknown"), ("001,010,002", "opening_3")])
def test_corpus_rejects_ambiguous_selection(tmp_path, ids, stage):
    store, _, _ = saved_corpus(tmp_path)
    with pytest.raises(ValueError):
        load_author_corpus(store, "Book", ids, stage)


@pytest.mark.parametrize("kind", ["missing", "empty", "non_utf8", "symlink_file", "symlink_directory"])
def test_corpus_rejects_unreadable_or_external_chapters(tmp_path, kind):
    store, ids, _ = saved_corpus(tmp_path / "store")
    chapter_dir = store.project_dir("Book") / "chapters"
    path = chapter_dir / "001.md"
    if kind == "missing":
        path.unlink()
    elif kind == "empty":
        path.write_text(" \n", encoding="utf-8")
    elif kind == "non_utf8":
        path.write_bytes(b"\xff\xfe")
    elif kind == "symlink_file":
        external = tmp_path / "private.txt"
        external.write_text("不可导出的内容", encoding="utf-8")
        path.unlink()
        path.symlink_to(external)
    else:
        original = chapter_dir.with_name("original_chapters")
        chapter_dir.rename(original)
        chapter_dir.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError):
        load_author_corpus(store, "Book", ids, "opening_3")


def test_exact_twenty_chapter_corpus_and_pack(tmp_path):
    _, ids, corpus = saved_corpus(tmp_path, ids=[f"ch-{i}" for i in range(20)], stage="retention_20")
    entries = unpack(release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids))
    assert "chapters/020.md" in entries
    assert len(json.loads(entries["manifest.json"])["chapters"]) == 20


def test_saved_plan_title_survives_restart_and_binds_only_exact_disk_text(tmp_path):
    store, ids, _ = saved_corpus(tmp_path)
    path = save_chapter_plan(store, "Book", "001", plan("确认标题"), "测试正文 001。")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == hashlib.sha256(b"001").hexdigest() + ".json"
    assert record["chapter_id"] == "001"
    assert record["text_sha256"] == hashlib.sha256("测试正文 001。\n".encode()).hexdigest()
    assert "测试正文" not in path.read_text(encoding="utf-8")
    restarted = ProjectStore(tmp_path)
    assert load_author_corpus(restarted, "Book", ids, "opening_3").chapters[0].title == "确认标题"
    store.write_chapter("Book", "001", "作者后来修改了正文。")
    assert load_author_corpus(restarted, "Book", ids, "opening_3").chapters[0].title == "001"
    with pytest.raises(ValueError, match="已变化"):
        save_chapter_plan(store, "Book", "001", plan(), "测试正文 001。")
    assert json.loads(path.read_text(encoding="utf-8")) == record


@pytest.mark.parametrize("kind", ["wrong_id", "wrong_project", "broken_json", "missing_plan", "old_version"])
def test_unverified_plan_record_cannot_supply_chapter_title(tmp_path, kind):
    store, ids, _ = saved_corpus(tmp_path)
    path = save_chapter_plan(store, "Book", "001", plan("不应使用的标题"), "测试正文 001。")
    record = json.loads(path.read_text())
    if kind == "wrong_id":
        record["chapter_id"] = "002"
    elif kind == "wrong_project":
        record["project"] = "Other"
    elif kind == "missing_plan":
        record.pop("plan")
    elif kind == "old_version":
        record["version"] = "0"
    path.write_text("{" if kind == "broken_json" else json.dumps(record), encoding="utf-8")
    assert load_author_corpus(store, "Book", ids, "opening_3").chapters[0].title == "001"


def test_plan_save_failure_preserves_previous_record_and_cleans_temp(tmp_path, monkeypatch):
    store, _, _ = saved_corpus(tmp_path)
    path = save_chapter_plan(store, "Book", "001", plan("旧标题"), "测试正文 001。")
    original = path.read_bytes()
    def fail_replace(*args):
        raise OSError("simulated interrupted plan replacement")
    monkeypatch.setattr("novel_ai.author_workflow.os.replace", fail_replace)
    with pytest.raises(OSError):
        save_chapter_plan(store, "Book", "001", plan("新标题"), "测试正文 001。")
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


def test_release_bundle_contains_fixed_paths_and_exact_bound_provenance(tmp_path):
    _, ids, corpus = saved_corpus(tmp_path)
    outline, _ = outline_fixture()
    pack = pack_for(corpus)
    bundle = release_bundle_bytes(corpus, pack, chapter_ids=ids, outline=outline)
    assert bundle == release_bundle_bytes(corpus, pack, chapter_ids=ids, outline=outline)
    entries = unpack(bundle)
    manifest = json.loads(entries["manifest.json"])
    assert manifest["human_review_status"] == "awaiting_human_review"
    assert manifest["publishability_verdict"] is None
    assert manifest["chapter_order"] == "author_declared"
    assert manifest["corpus_sha256"] == corpus.fingerprint()
    assert manifest["project"] == "Book"
    assert manifest["audience"] == corpus.audience
    assert manifest["genre"] == corpus.genre
    assert [row["chapter_id"] for row in manifest["chapters"]] == ids
    for chapter, row in zip(corpus.chapters, manifest["chapters"]):
        assert entries[row["path"]].decode() == chapter.text
        assert hashlib.sha256(entries[row["path"]]).hexdigest() == row["text_sha256"]
    assert "human_scores.json" not in entries
    assert "not certified publishable" in entries["README.txt"].decode()
    assert "测试正文" not in entries["release_pack.json"].decode()
    with pytest.raises(ValueError, match="未填完"):
        parse_market_scores(entries["market_scoring.csv"].decode("utf-8-sig"), corpus)
    rows = list(csv.DictReader(io.StringIO(entries["market_scoring.csv"].decode("utf-8-sig"))))
    assert len(rows) == len(MARKET_RUBRIC)
    assert {row["corpus_sha256"] for row in rows} == {corpus.fingerprint()}


def test_complete_human_scores_are_recorded_without_publishability_verdict(tmp_path):
    _, ids, corpus = saved_corpus(tmp_path)
    scores = scores_for(corpus)
    bundle = release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids, scores=scores)
    assert bundle == release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids, scores=list(reversed(scores)))
    entries = unpack(bundle)
    summary = json.loads(entries["human_review_summary.json"])
    assert summary["mean_score"] == 4
    assert summary["publishability_verdict"] is None
    assert len(json.loads(entries["human_scores.json"])) == 10
    assert json.loads(entries["manifest.json"])["human_review_status"] == "human_review_recorded"


@pytest.mark.parametrize("kind", ["empty", "partial", "duplicate", "other_project", "other_stage", "wrong_digest", "other_reviewer", "bad_score"])
def test_release_bundle_rejects_incomplete_stale_or_mixed_scores(tmp_path, kind):
    _, ids, corpus = saved_corpus(tmp_path)
    scores = scores_for(corpus)
    if kind == "empty":
        scores = []
    elif kind == "partial":
        scores.pop()
    elif kind == "duplicate":
        scores[-1] = scores[0]
    elif kind == "other_project":
        for row in scores:
            row.project = "Other"
    elif kind == "other_stage":
        for row in scores:
            row.stage = "retention_20"
    elif kind == "wrong_digest":
        for row in scores:
            row.corpus_sha256 = "0" * 64
    elif kind == "other_reviewer":
        scores[0].reviewer_id = "different-person"
    else:
        scores[0].score = 7
    with pytest.raises(ValueError):
        release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids, scores=scores)


@pytest.mark.parametrize("field", ["text", "title", "audience", "genre", "review_note", "project"])
def test_changed_corpus_invalidates_both_pack_and_previous_scores(tmp_path, field):
    _, ids, corpus = saved_corpus(tmp_path)
    pack, scores = pack_for(corpus), scores_for(corpus)
    changed = corpus.model_copy(deep=True)
    if field in {"text", "title"}:
        setattr(changed.chapters[0], field, "新的内容")
    else:
        setattr(changed, field, "新的内容")
    with pytest.raises(ValueError, match="不匹配"):
        release_bundle_bytes(changed, pack, chapter_ids=ids)
    with pytest.raises(ValueError, match="不匹配"):
        release_bundle_bytes(changed, pack_for(changed), chapter_ids=ids, scores=scores)


@pytest.mark.parametrize("field", ["audience", "genre"])
def test_release_profile_cannot_change_review_context(tmp_path, field):
    _, ids, corpus = saved_corpus(tmp_path)
    pack = pack_for(corpus)
    setattr(pack.profile, field, "其他评审对象")
    with pytest.raises(ValueError, match=field):
        release_bundle_bytes(corpus, pack, chapter_ids=ids)


def test_release_revalidates_mutated_models_and_bad_id_mapping(tmp_path):
    _, ids, corpus = saved_corpus(tmp_path)
    for bad_ids in (["001"], ["001", "001", "002"], ["../escape", "010", "002"]):
        with pytest.raises(ValueError):
            release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=bad_ids)
    pack = pack_for(corpus)
    corpus.chapters[0].number = 2
    with pytest.raises(ValueError):
        release_bundle_bytes(corpus, pack, chapter_ids=ids)


def test_content_addressed_export_reuses_identical_file_across_restart(tmp_path):
    store, ids, corpus = saved_corpus(tmp_path)
    bundle = release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids)
    first = save_release_bundle(store, "Book", bundle)
    assert first.name == "release-" + hashlib.sha256(bundle).hexdigest() + ".zip"
    before = first.stat()
    second = save_release_bundle(ProjectStore(tmp_path), "Book", bundle)
    assert second == first
    assert first.read_bytes() == bundle
    assert first.stat().st_mtime_ns == before.st_mtime_ns
    assert list(first.parent.iterdir()) == [first]


def test_export_rejects_other_project_and_invalid_bytes_without_creating_artifact(tmp_path):
    store, ids, corpus = saved_corpus(tmp_path)
    bundle = release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids)
    with pytest.raises(ValueError, match="项目不匹配"):
        save_release_bundle(store, "Other", bundle)
    for invalid in (b"", b"not a zip", "wrong type"):
        with pytest.raises(ValueError):
            save_release_bundle(store, "Book", invalid)
    assert not list(tmp_path.rglob("release-*.zip"))


def test_existing_content_address_collision_is_never_overwritten(tmp_path):
    store, ids, corpus = saved_corpus(tmp_path)
    bundle = release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids)
    target = store.project_dir("Book") / "exports" / ("release-" + hashlib.sha256(bundle).hexdigest() + ".zip")
    target.write_bytes(b"existing evidence must survive")
    with pytest.raises(ValueError, match="保留原文件"):
        save_release_bundle(store, "Book", bundle)
    assert target.read_bytes() == b"existing evidence must survive"


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_export_rejects_symlink_target_or_directory(tmp_path, kind):
    store, ids, corpus = saved_corpus(tmp_path / "store")
    bundle = release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids)
    directory = store.project_dir("Book") / "exports"
    external = tmp_path / "external"
    external.mkdir()
    if kind == "directory":
        directory.rmdir()
        directory.symlink_to(external, target_is_directory=True)
    else:
        target = directory / ("release-" + hashlib.sha256(bundle).hexdigest() + ".zip")
        source = external / "evidence.zip"
        source.write_bytes(bundle)
        target.symlink_to(source)
    with pytest.raises(ValueError, match="符号链接"):
        save_release_bundle(store, "Book", bundle)


def test_failed_export_publication_cleans_temp_without_partial_artifact(tmp_path, monkeypatch):
    store, ids, corpus = saved_corpus(tmp_path)
    bundle = release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids)
    def fail_link(*args):
        raise OSError("simulated interrupted publication")
    monkeypatch.setattr("novel_ai.author_workflow.os.link", fail_link)
    with pytest.raises(OSError):
        save_release_bundle(store, "Book", bundle)
    assert list((store.project_dir("Book") / "exports").iterdir()) == []


def test_racing_identical_export_reuses_winner_and_cleans_temp(tmp_path, monkeypatch):
    store, ids, corpus = saved_corpus(tmp_path)
    bundle = release_bundle_bytes(corpus, pack_for(corpus), chapter_ids=ids)
    def racing_link(source, destination):
        Path(destination).write_bytes(bundle)
        raise FileExistsError("concurrent identical save")
    monkeypatch.setattr("novel_ai.author_workflow.os.link", racing_link)
    path = save_release_bundle(store, "Book", bundle)
    assert path.read_bytes() == bundle
    assert list(path.parent.iterdir()) == [path]
