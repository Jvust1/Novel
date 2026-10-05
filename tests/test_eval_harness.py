from novel_ai.eval_harness import (
    CallableMetricAdapter,
    DeepEvalMetricAdapter,
    EvaluationCase,
    LangfuseScoreSink,
    promptfoo_config,
    run_evaluation,
)


def test_local_evaluation_report_and_threshold():
    case = EvaluationCase("c1", "目标", "正文")
    metric = CallableMetricAdapter(
        "continuity",
        lambda _: {"score": 0.8, "reason": "ok"},
        threshold=0.7,
    )
    report = run_evaluation([case], [metric])
    assert report.passed is True
    assert report.pass_rate == 1.0
    assert report.cases[0].metrics[0].reason == "ok"


def test_deepeval_adapter_can_use_injected_factory_without_dependency():
    class Metric:
        threshold = 0.6
        score = 0.75
        reason = "连贯"
        success = True

        def measure(self, test_case):
            assert test_case["actual_output"] == "正文"
            return self.score

    adapter = DeepEvalMetricAdapter(
        Metric(),
        test_case_factory=lambda case: {"actual_output": case.actual_output},
    )
    score = adapter.evaluate(EvaluationCase("c1", "输入", "正文"))
    assert score.passed is True
    assert score.score == 0.75


def test_promptfoo_export_keeps_case_assertions_explicit():
    case = EvaluationCase(
        "c1",
        "写一个开篇",
        "已有输出",
        metadata={
            "promptfoo_assert": [
                {"type": "llm-rubric", "value": "开篇必须快速建立冲突"}
            ]
        },
    )
    config = promptfoo_config([case], providers=["openai:chat:test"])
    assert config["prompts"] == ["{{input}}"]
    assert config["tests"][0]["vars"]["case_id"] == "c1"
    assert config["tests"][0]["assert"][0]["type"] == "llm-rubric"


def test_langfuse_sink_records_numeric_metric_with_threshold_metadata():
    class Client:
        def __init__(self):
            self.rows = []

        def create_score(self, **kwargs):
            self.rows.append(kwargs)

    case = EvaluationCase("c1", "输入", "正文")
    report = run_evaluation(
        [case],
        [CallableMetricAdapter("quality", lambda _: 0.9, threshold=0.8)],
    )
    client = Client()
    LangfuseScoreSink(client).record_case(report.cases[0], trace_id="trace-1")
    assert client.rows[0]["trace_id"] == "trace-1"
    assert client.rows[0]["name"] == "quality"
    assert client.rows[0]["metadata"]["passed"] is True
