# Pre-flight Checklist

重大修改前检查：

- [ ] 已读取 Drive 根目录 `00_全项目总入口_新AI先读此文件` 及动态发现的全部 `全项目_` 基线。
- [ ] 已读取 `governance/project_state.json`、North Star、Architecture Invariants、Current State、Decision/Evaluation Ledger。
- [ ] 本次修改解决的是写作质量或用户体验问题，而不是单纯增加架构复杂度。
- [ ] 若改变生成流水线，明确说明对情节、人物、连续性和语言的预期影响。
- [ ] 若改变 Style DNA，确认没有把参考正文持久化到 GitHub。
- [ ] 若处理用户原稿/参考小说，确认原始文件应进入 Drive 而非 GitHub。
- [ ] 若新增模型/本地运行时，遵守全项目本地模型存储规则（大型模型/缓存默认 D 盘）。
- [ ] API Key / Token / Cookie / 私密环境变量不会进入提交。
- [ ] 新状态字段有清晰 Schema 和迁移策略。
- [ ] 能用局部修复解决的问题，不默认整章重写。
- [ ] 有可执行的验证方法；如没有，明确标记为未验证假设。
- [ ] 修改完成后同步 CURRENT_STATE / project_state / relevant ledger。
