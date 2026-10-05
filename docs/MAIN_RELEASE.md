# Main 工程集成与验收边界

本入口面向 Jvust1/Novel 的 `main`。当前指针为 [current_candidate.json](../governance/current_candidate.json)，精确集成基线为 PR75 的 `50f9ba2da535e985cefe9685ec3470f2e38fc862`，树 `c93e5ebdf4ce98e852bbb497e5c4d86ac405ca86`。

## 本次集成

- 保留已有 GPT 插件写作、私有 Drive、作者版本确认、来源绑定、历史重建、设定保存恢复等实现。
- 保留 Windows CLI 的 ASCII JSON 输出；中文解码内容及原字节 SHA-256 不变。
- 保留导出故障注入发生在暂存句柄真实关闭后的测试，不减少原有断言。
- 保留 Windows 新建私有文件的实际用户 SID、受保护单项 FullControl DACL 与失败关闭；POSIX 仍核对 0600。
- 仅把三个公开入口和机器指针对齐到 main；原历史治理记录保留，不作为当前分支权威。

## 合并门禁

作者已明确授权：四项完整 CI 全通过后，合并 main。合并前须对本次实际树运行 Ubuntu/Windows × Python 3.11/3.12 的四项完整 CI，保留 Ruff、编译、第三方许可/来源、公开入口和完整 pytest 检查。文档自身不证明已合并；合并状态、提交和 CI 必须从 GitHub 实际回执核对。

## 完成范围

本轮工程集成完成不代表任意真实小说已完成、正文被接受、独立真人盲评通过或获准投稿。未提供的作者确认、作品原件和读写回执仍不得代填；不公开私有稿件，不新增部署或付费调用。
