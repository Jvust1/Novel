# 质量门与剩余审计项

本候选接在 `fix/memory-acceptance-gates-20261002` / Draft PR #59 之上。目标不是为了把所有静态诊断数字清零，而是把**会直接影响运行正确性与可复现性**的检查变成持续 CI 硬门，同时把已有格式/维护债务保留成可见、可逐步下降的基线。

当前候选分支：`chore/quality-gates-audit-20261002`。未合入 main，不自动部署。

## 1. 新的 CI 硬门

Linux Python 3.11 / 3.12 每个 job 按顺序执行：

1. `pip install -r requirements-dev.txt`
2. `python -m pip check`
3. `ruff check app.py novel_ai scripts tests --select E9,F63,F7,F82`
4. `python -m compileall app.py novel_ai scripts`
5. `python scripts/check_integrations.py`
6. `pytest -q`

其中：

- `pip check` 检查**该 CI 干净环境实际安装后的依赖一致性**，避免把当前共享开发容器中别的项目造成的依赖冲突误算到 Novel；
- Ruff 的 `E9,F63,F7,F82` 只作为高风险静态错误硬门，覆盖语法/名称/明显运行时风险；compileall 继续保留独立检查；
- pytest 仍是完整核心回归门；
- optional integration probe 只报告已安装/未安装能力，不把可选重依赖全部安装成核心前置条件。

`requirements-dev.txt` 固定 `ruff==0.16.9`，让静态规则版本不随 runner 漂移。

## 2. 默认 Ruff 维护性基线

CI 额外执行：

`ruff check app.py novel_ai scripts tests --output-format json --exit-zero`

然后报告：

- 默认 Ruff 诊断总数；
- 诊断最多的规则前 12 项。

这一项**不阻断 CI**。原因是当前仓库已经存在一批历史格式/维护性诊断，直接把默认 Ruff 全部设成硬门会把“本轮是否引入真实运行风险”和“旧代码风格债务”混为一谈。

2026-10-01 的上一轮交接记录曾报告该限定范围有 320 条默认 Ruff 诊断。2026-10-02 本候选首次干净 CI 用固定 Ruff 0.16.9 重新测得 **329 条**；两套 Python job 数字一致。前 12 项为：I001 93、BLE001 32、UP035 26、F401 23、TRY004 20、UP031 16、C408 15、SIM117 15、PLW1510 12、S110 10、UP037 7、FURB167 7。高风险硬门 E9/F63/F7/F82 为 0。

后续清理原则：

- 先保证硬门永不回退；
- 新改动尽量不增加默认 Ruff 总数；
- 再按高频规则批量、小范围清理；
- 不为追求数字归零去重写稳定业务逻辑。

## 3. 依赖审计边界

核心 CI 只安装 `requirements-dev.txt` → `requirements.txt`，然后运行 `pip check`。

这能证明当前核心环境中的包依赖声明彼此一致，但不等于：

- 安装并验证了所有 `requirements-extras/*`；
- 验证了所有外部模型、向量数据库或本地服务；
- 做了 CVE / 供应链漏洞扫描；
- 证明任意用户机器上已有的全局包不会冲突。

本轮**不安装全部可选依赖**。可选能力由 `scripts/check_integrations.py` 输出 installed/missing 矩阵；缺失可选包本身不是核心 CI 失败。

本地共享容器当前的 `pip check` 报告 MoviePy 与 Pillow 冲突，但 Novel 的核心 requirements 不声明 MoviePy；因此这只能说明共享容器被其他工作负载污染，不能作为 Novel 依赖失败证据。真正结论以 GitHub Actions 的干净 job 为准。

## 4. 治理与代码一致性

新增 `tests/test_governance_alignment.py` 检查：

- 当前候选分支在 project_state / artifact_manifest 中一致；
- README / AGENTS / GPT_WRITING_ENTRY / HANDOFF 都指向同一候选分支；
- requirements-dev 固定 Ruff 版本；
- CI 确实包含 pip check、致命 Ruff、默认 Ruff 报告、compileall、integration probe 和 pytest；
- 本文档存在且明确区分硬门与维护性基线。

这不是把聊天变成权威状态，而是防止“治理写着已启用某门，但 workflow 实际没跑”的漂移。

## 5. 已有许可证/来源门

已有测试继续验证多个直接复用来源的许可证文件、固定提交/哈希与接入 provenance，包括 GPT writing source pins、eventsourcing、boltons、HTTPX runtime reuse 等。

本轮不重复复制上游代码，也不把“open_source_registry 中有条目”误称为所有可选项目均已实际运行。许可与实际采用状态继续分开记录。

## 6. 仍然开放的审计边界

以下不因本轮 CI 绿色而自动变成“已完成”：

- 默认 Ruff 全量诊断尚未清零；
- 全部可选依赖矩阵没有一次性安装测试；
- 条件性的共享/多用户部署风险没有真实部署环境验证；
- 没有新增通用 CVE/SBOM 扫描服务；
- 没有真实付费模型、真实 Qdrant SDK、真人文学质量评审；
- GitHub CI 证明工程回归，不证明数十万字小说文学质量或市场表现。

## 7. 验收方式

发布本分支后，以 GitHub Actions 为准核对：

- Python 3.11 / 3.12 均通过 pip check；
- 高风险 Ruff 规则 0 条；
- compileall 通过；
- integration probe 正常执行；
- 全量 pytest 通过；
- 默认 Ruff 当前诊断数量及规则分布被日志真实报告。

若硬门失败，先修真实风险再继续；若只有默认 Ruff 维护性基线非零，本轮可保持候选状态并把精确数字记录为后续清理起点。
