import pytest

from novel_ai.outline_markdown import parse_markdown_outline


OUTLINE = """# 夜航者
全书承诺
## 第一卷
卷的目标
### 旧案
情节线笔记
#### 夜班电话
章的任务
##### 确认身份
  保留两个缩进。

对白\t也保持原样。\x20\x20
##### 被迫选择
第二场笔记
#### 门外的人
章二笔记
"""


def test_import_author_outline_preserves_hierarchy_notes_and_explicit_premise():
    outline = parse_markdown_outline(OUTLINE, title="项目名", premise="作者设定")
    assert outline.title == "项目名"
    assert outline.premise == "作者设定"
    assert outline.root.title == "夜航者"
    assert [n.level for n in outline.flatten()] == [
        "series", "volume", "arc", "chapter", "scene", "scene", "chapter"
    ]
    scene = outline.root.children[0].children[0].children[0].children[0]
    assert scene.promise == "  保留两个缩进。\n\n对白\t也保持原样。  "
    assert scene.metadata["author_notes"] == scene.promise
    assert scene.metadata["source_line"] == 9
    assert scene.metadata["outline_position"] == "1.1.1.1.1"
    for node in outline.flatten():
        assert node.conflict == node.outcome == ""
        assert node.promise == node.metadata["author_notes"]


def test_duplicate_headings_and_header_only_sections_remain_distinct():
    text = "# 书\n## 卷\n### 线\n#### 同章\n##### 同场\n##### 同场\n#### 同章\n"
    first = parse_markdown_outline(text, title="书")
    second = parse_markdown_outline(text, title="书")
    rows = first.flatten()
    assert len(rows) == 7
    assert len({node.id for node in rows}) == 7
    assert [node.id for node in rows] == [node.id for node in second.flatten()]
    assert all(node.promise == "" for node in rows)
    assert len(rows[2].children) == 2
    assert len(rows[3].children) == 2


@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~~"])
def test_fenced_headings_and_deep_markers_are_retained_as_body(fence):
    body = f"{fence}text\n# 不是真根节点\n###### 不是真六级\n{fence}"
    outline = parse_markdown_outline(f"# 真根\n{body}\n## 真卷", title="书")
    assert outline.root.promise == body
    assert len(outline.flatten()) == 2
    assert outline.root.children[0].title == "真卷"


def test_fence_requires_matching_character_length_and_bare_close():
    body = "````python\n```\n~~~~\n````python\n# 都是代码\n````"
    outline = parse_markdown_outline(f"# 书\n{body}\n## 卷", title="书")
    assert outline.root.promise == body
    assert len(outline.flatten()) == 2


def test_inline_backticks_do_not_start_a_fence():
    outline = parse_markdown_outline("# 书\n```这是行内```\n## 卷", title="书")
    assert outline.root.promise == "```这是行内```"
    assert len(outline.flatten()) == 2


def test_upstream_stack_pops_all_deeper_headers_on_new_volume():
    text = OUTLINE + "## 第二卷\n新卷笔记\n### 新线\n#### 新章"
    outline = parse_markdown_outline(text, title="书")
    assert [n.title for n in outline.root.children] == ["第一卷", "第二卷"]
    second = outline.root.children[1]
    assert second.promise == "新卷笔记"
    assert second.children[0].children[0].title == "新章"
    assert second.metadata["outline_position"] == "1.2"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "全书标题"),
        (" \n\t", "全书标题"),
        ("正文不能丢\n# 书", "标题前存在正文"),
        ("```\n# 假标题\n```\n# 书", "标题前存在正文"),
        ("## 卷", "根节点开始"),
        ("# 书\n### 跳过卷", "层级不连续"),
        ("# 书\n## 卷\n### 线\n##### 跳过章", "层级不连续"),
        ("# 书\n# 第二根", "只能有一个"),
        ("#", "标题不能为空"),
        ("# 书\n##   ", "标题不能为空"),
        ("# 书\n## ###", "标题不能为空"),
        ("# 书\n###### 六级", "五级标题"),
        ("# 书\n####### 七级", "五级标题"),
        ("# 书\n```\n## 被吞掉的标题", "围栏未闭合"),
        ("# 书\n~~~~\n~~~\n## 仍在代码内", "围栏未闭合"),
    ],
)
def test_malformed_outline_fails_closed(text, message):
    with pytest.raises(ValueError, match=message):
        parse_markdown_outline(text, title="书")


def test_whitespace_preamble_line_endings_and_optional_closing_hashes():
    outline = parse_markdown_outline("\r\n \r\n# 全书 ###\r\n##\t卷名 ##\r\n笔记", title="")
    assert outline.title == outline.root.title == "全书"
    assert outline.root.children[0].title == "卷名"
    assert outline.root.children[0].promise == "笔记"
    assert outline.root.metadata["source_line"] == 3


def test_unsupported_markdown_and_indented_code_are_preserved_not_invented():
    body = "小标题\n======\n- 卷一\n    # 缩进代码\n#标签"
    outline = parse_markdown_outline(f"# 书\n{body}", title="书")
    assert len(outline.flatten()) == 1
    assert outline.root.promise == body


@pytest.mark.parametrize("separator", ["\u200d", "\u2028", "\v", "\f"])
def test_interior_nonprintable_character_is_not_deleted_as_upstream_rag_does(separator):
    notes = f"作者{separator}笔记"
    outline = parse_markdown_outline(f"# 书\n{notes}", title="书")
    assert outline.root.promise == notes


@pytest.mark.parametrize("field", ["text", "title", "premise"])
def test_non_text_inputs_rejected_with_validation_error(field):
    kwargs = {"text": "# 书", "title": "书", "premise": "设定"}
    kwargs[field] = None
    with pytest.raises(ValueError, match="文本"):
        parse_markdown_outline(**kwargs)
