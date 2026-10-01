# chinese-novelist-skill：来源与适配声明

上游：PenglongHuang/chinese-novelist-skill
仓库：https://github.com/PenglongHuang/chinese-novelist-skill
固定提交：cb6c3e7d0563c6a685e6539ea642642ab98855d7
上游提交日期：2026-09-06T05:26:15Z
核验日期：2026-10-01 UTC
核验时 GitHub stars：3,258（时间点观察，不是质量证明）

## 许可证

Copyright (c) 2026 PenglongHuang
MIT License，全文按固定提交逐字保存在 [LICENSE](LICENSE)。
上游 LICENSE Git blob SHA：2f6b7e59b8c5af624617520313285dcfe0b47c28；1,070 字节。
本 NOTICE 由 Novel 添加，并不是声称上游有同名 NOTICE。

## 本次仅适配这两个明确部分

1. [references/guides/outline-template.md，第 22–30 行「设定词典」](https://github.com/PenglongHuang/chinese-novelist-skill/blob/cb6c3e7d0563c6a685e6539ea642642ab98855d7/references/guides/outline-template.md#L22-L30)
   - 完整文件 Git blob SHA：73644ec9d2fc1375ee2f2795332e773af4f3d05e
   - 直接采用五列语义：名词、首现章节、读者已知、完整真相、计划揭示
   - 未复制上游「蓝晶」故事示例

2. [references/guides/chapter-guide.md，第 519–529 行「新名词首现管理」](https://github.com/PenglongHuang/chinese-novelist-skill/blob/cb6c3e7d0563c6a685e6539ea642642ab98855d7/references/guides/chapter-guide.md#L519-L529)
   - 完整文件 Git blob SHA：cb1d4d1c369bc9f90a820eaee9e546516a817b25
   - 适配写前核对、首现定位线索和已知/未揭示边界
   - 上游的到期必须揭示，改为 Novel 的报告差异并由作者决定；不自动覆盖版本确认

适配产物：[docs/READER_REVEAL_LEDGER.md](../../docs/READER_REVEAL_LEDGER.md) 与 [writing_templates/reader_reveal_ledger.template.json](../../writing_templates/reader_reveal_ledger.template.json)。

Novel 添加的部分：稳定 term_id、candidate / confirmed 隔离、来源与基础版本、稿件接受引用、记忆更新和确认引用、失效/幂等/保存读回/私有导出约束，以及「潮铃」原创教学例。

本次未复制或适配 SKILL.md 的自动完成全书/禁止后续作者确认指令，未采用静默累积偏好、机械禁词替换、统一字数门槛、全章强制重写或整套应用运行时。没有把查阅过的所有内容都宣称为已融合。

Git blob SHA 是 Git 对象标识，不能当作 SHA-256。精确元数据见 [provenance.json](provenance.json)。
