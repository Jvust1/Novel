# 提交后的质量检查与当前工程入口

本轮把已在本仓库另一条候选验证过的检查接到当前完整功能链。每次草稿 PR 的 Python 3.11/3.12 CI 都运行依赖兼容检查、固定版本 Ruff 致命错误检查、原有编译与完整测试。历史接受、作者日志、记忆候选、调用预算和接受稿导出测试继续属于完整矩阵，没有删减来换取通过。

## 当前工程身份

[current_candidate.json](../governance/current_candidate.json) 是不含私有归档标识的当前公开工程指针，指定分支、阅读顺序、上一已验证提交及本轮候选记录。README、AGENTS 顶部和 GPT 写作入口的当前声明必须与它一致；旧启动提示即使出现在新标题后面也会被检查拒绝。`scripts/check_current_entry.py` 真实解析当前记录与活动入口，旧 AGENTS 历史区段保留。

`governance/project_state.json` 与 `artifact_manifest.json` 保留历史信息，不作为最新分支、最新测试或访问私有作品的授权。新指针既不是小说状态，也不认证当前 GitHub head：接手者仍应真实读取 ref、PR 与该提交 CI。候选自己的 head/CI 在发布后通过 PR 及交付回执核对，避免往未完成提交里预写成功。

## 哪些失败会阻止 CI 通过

- `python -m pip check`：已安装包声明的依赖缺失或版本不兼容时失败
- Ruff 0.16.9 的 `E9,F63,F7,F82`：语法、无效控制流、可疑元组条件及未定义名称/导出/局部变量等指定错误时失败
- 编译、当前公开入口检查、集成探测脚本异常、完整 pytest 失败仍会使该矩阵项失败

脚本 `python scripts/check_integrations.py` 现在从其他工作目录直接运行也能找到项目；`python -m scripts.check_integrations` 保持可用。探测结果只是可选 Python 包的可发现性，缺失可选集成会报告 MISS 并正常返回，不能称为真正运行了 45 套上游或通过其模型测试。

## 哪些结果只是报告

默认 Ruff 规则仍用 `--exit-zero` 生成诊断摘要，不能把默认规则问题数量叫作零错误或强制门禁。冻结 #61 的实测基线为 448 条；当前分支计数见 [本轮记录](../governance/quality_gates_candidate.json)。只按风险逐项处理，不批量改格式、隐藏规则或降低已有测试覆盖。

`pip check` 不是漏洞扫描、SBOM 审计或可重复解析证明。当前只固定开发工具 Ruff；核心/间接依赖仍使用原有范围，没有声称完成锁文件、包哈希约束或所有可选依赖组合验证。CI 通过也不证明分支保护强制要求这些状态，更不证明真人文学质量或发表效果。

## 实际复用与来源

复用本仓库 [PR #60](https://github.com/Jvust1/Novel/pull/60) 的 CI 步骤和直接脚本启动修复，固定 head `bc87ef1f87c2d789a44e9364f65e095e360a0cf1`；该源提交的 [CI 36900527262](https://github.com/Jvust1/Novel/actions/runs/36900527262) 已验证两版本成功。这只是小范围适配，另一条 #55/#58/#59 的历史/预算/记忆实现没有被合入，源分支的 1228 项测试和 329 条默认 Ruff 诊断不挪用到本分支。

[Ruff](https://github.com/astral-sh/ruff) 在 2026-10-01 核实 49,870 星、MIT，实际运行固定 0.16.9，精确源提交 `0be08a206f9c3180afd3e93bcc792ed5cb1f4db1`。完整许可证、衍生项目许可段及来源记录保存在 [NOTICE](../third_party/ruff-dev-tool/NOTICE.md)。这是新增持续运行的开发检查工具，不宣称搬入其完整源库，也不增加小说运行时框架。
