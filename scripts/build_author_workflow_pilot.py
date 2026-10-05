"""Build an original synthetic, offline author-workflow review sample.

No provider, network, real manuscript, filled human score or platform submission.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novel_ai.author_workflow import load_author_corpus, release_bundle_bytes, save_chapter_plan
from novel_ai.models import ChapterPlan, SceneBeat
from novel_ai.outline_markdown import parse_markdown_outline
from novel_ai.release_pack import MarketProfile, build_release_pack
from novel_ai.storage import ProjectStore

SAMPLE_NOTE = "原创合成工程验证样本；不是用户原稿，不是完成小说；未调用模型，未取得真人盲评或平台发布资格。"
CHAPTERS = [
    ("001", "旧灯室", "寻找旧灯芯", "借出唯一的钥匙", "欠下一次修船的人情", "拿到旧灯芯", """林澄到灯塔时，门锁还在滴水。

守塔人把钥匙放在窗台上，没有松手。“船修好了吗？”

“桅杆好了。船底还漏。”

“那就不是好了。”

她掏出一枚铁钉。钉头磨平了一边，是她昨晚从舱底拔出来的。守塔人看了看，终于推过钥匙。

灯室里没有她想象中的黑。石墙裂开一道窄缝，天光正照着桌上的空盒。林澄把湿袖口卷起来，在抽屉背后找到灯芯。底下压着一小片航图，外港那道浅滩被人划去了。

她没有把航图塞进口袋。她连同盒子一起抱下楼，问守塔人：“这条线是谁画的？”

守塔人的手停在修船锤上。外头，第一声风铃响了。"""),
    ("002", "半张航图", "核对被划去的浅滩", "把发现交给旧船主", "暴露私自进过灯室", "确认航图有两份", """船主正在补渔网。林澄把盒子放在他脚边。

他没有去看灯芯，只问：“老贺让你拿的？”

“钥匙是他给的。航图不是。”

船主抽出一根断线，绕在指上。林澄等他绕完，才把那片纸摊开。纸边少了两个角，不够盖住她的掌心。

“浅滩还在。”他说。

“那为什么划掉？”

“这张图是给空船看的。”

林澄想起船舱里的三桶压舱石。她原想赶在涨水前装上最后一桶，如今那只空桶正在岸上等她。船主从网底取出另一片纸，缺口恰好能对上，却把它压在自己手下。

“先把船底补好。”

她把铁钉递过去。他没有接，指了指棚里的木料。林澄脱下湿外衣，选了一块最长的板。"""),
    ("003", "回港", "在风暴前选定航线", "放弃走浅滩的捷径", "错过原定交货时辰", "两人共同承担延误", """最后一块补板钉上去时，潮水已经漫过最下面的石阶。

船主把两片航图压在油布底下。林澄伸手去拿，他指了指外港。灰白的浪头沿着那条被划掉的线，一次次露出尖角。

“绕过去要多半天。”

“我知道。”

“货主不会等。”

林澄把空桶滚回棚下。“那就让他看见一条还能再出海的船。”

船主蹲下来，替她解开最后一根缆绳。绳结泡紧了，他拆了两次才拆开。林澄没有催。

船离岸后，她在交货单上写了新的时辰。写完，递给船主。他看了很久，在她名字下面添上自己的名字。

塔上的灯亮了。不是他们原先约定的两下，是三下。船主站起身，转向港里。林澄随他的目光望去，看见另一条船正从雾里慢慢退回来。"""),
]


def build_sample() -> bytes:
    with tempfile.TemporaryDirectory(prefix="novel-author-pilot-") as temporary:
        store = ProjectStore(temporary)
        project = "归航-原创合成验证样本"
        markdown = "# 归航\n" + SAMPLE_NOTE + "\n## 第一卷\n风暴前作出返航选择\n### 航图线\n三个选择与连续后果\n"
        for chapter_id, title, goal, choice, cost, outcome, text in CHAPTERS:
            markdown += f"#### {title}\n{goal}\n##### 核心场景\n{goal}\n"
            plan = ChapterPlan(chapter_title=title, chapter_promise=goal, scenes=[SceneBeat(
                scene_no=1, pov="林澄", objective=goal, opposition="时间与信息不足",
                choice=choice, cost=cost, state_change=outcome,
            )])
            store.write_chapter(project, chapter_id, text)
            save_chapter_plan(store, project, chapter_id, plan, text)
        outline = parse_markdown_outline(markdown, title=project, premise="返航者必须对自己的航线选择负责。")
        ids = [row[0] for row in CHAPTERS]
        corpus = load_author_corpus(store, project, ids, "opening_3", audience="工程验收读者（非市场抽样）", genre="原创合成悬疑样本")
        corpus.review_note = SAMPLE_NOTE
        profile = MarketProfile(genre=corpus.genre, audience=corpus.audience,
                                platform="本地工程审阅", content_policy_notes=[SAMPLE_NOTE])
        pack = build_release_pack(
            corpus, profile, title=project, one_line_hook="一份缺角航图，让返航者重新选择代价。",
            short_blurb="三段原创短章验证大纲、正文、评分表与发布候选包之间的资料流。",
            content_warnings=[SAMPLE_NOTE],
            manual_checks=["尚待真人审读", "未做模型生成效果或冻结 A/B 评测", "未核查真实平台投稿规则"],
        )
        return release_bundle_bytes(corpus, pack, chapter_ids=ids, scores=None, outline=outline)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New ZIP path; existing files are never overwritten")
    args = parser.parse_args()
    try:
        bundle = build_sample()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("xb") as handle:
            handle.write(bundle)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"无法创建样本包：{exc}\n")
    print(f"Wrote synthetic review candidate: {args.out}")
    print(SAMPLE_NOTE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
