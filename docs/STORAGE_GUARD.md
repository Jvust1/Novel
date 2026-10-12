# 存储路径检查：一次查询，不缓存安全结果

延续 PR #91 的小范围优化；此文档不是合并或全量 CI 通过回执。

## 变更

`novel_ai.storage_guard.reject_links` 对目标和每一级祖先各执行一次
`os.lstat`，用同一份元数据检查符号链接和 Windows junction。此前 Windows
Python 3.12 分别调用 `is_symlink` 和 `is_junction`，对普通路径重复查询。

Python 3.11 没有 `Path.is_junction`，原来的可选 helper 分支会漏掉 junction。
现在直接检查 `st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT`，不依赖这个
helper。测试包含真实 Windows junction，以及移除 helper 后的兼容性分支。
后者是 Python 3.12 上的兼容性模拟，不等于实际执行了完整 Python 3.11 测试。

不存在的目标或尚未创建的父目录仍允许继续；权限、I/O、循环路径及非法路径
异常不吞掉。符号链接（包括悬空链接）、祖先 junction 仍拒绝。其他 reparse tag
不会被一概误判为 junction。每次调用重新查询，不缓存检查结论，不改原子写入、
私有文件 ACL、项目锁、作者确认、状态 schema 或模型调用。

这仍不是防御恶意目录交换的文件系统沙箱：目录需可信，写入者需协作。

## 重现

```sh
python -m pytest -q tests/test_storage_guard_regression.py tests/test_storage_integrity.py tests/test_storage_recovery_adversarial.py tests/test_storage_atomic_json.py
python -m scripts.benchmark_storage_guard
```

微基准只创建并自动清理合成临时目录，不读取作品。每轮检查同一 11 级路径
500 次，共 5 轮。在本次 Windows / Python 3.12.14 环境，原版每次 22 次元数据
查询，候选 11 次；耗时中位数分别约 1.885 秒和 0.938 秒。时间受机器负载影响，
不设置脆弱的 CI 时间阈值；回归测试检查确定性的查询次数。不能将微基准收益
直接称为整个应用提升 50%。

实际结果、同输入基线失败与回滚记录见本轮交付的 `VERIFICATION.txt`，仓库摘要
保留在 [候选记录](../governance/voice_metrics_candidate.json)。完整回归和远端
平台矩阵未完成前，PR 保持 draft。
