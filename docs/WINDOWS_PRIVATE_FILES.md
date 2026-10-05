# 本地私有文件：Windows ACL 与 POSIX 权限分开验证

Windows 的 `st_mode == 0600` 不是访问控制证据。单个故事 JSON 和
ProjectStore 原子写入现在通过 `novel_ai/private_files.py` 在创建临时文件时
使用受保护的 DACL：仅有效调用账户 SID 的 FullControl，不继承父目录 ACE。
创建后在同一个真实句柄上检查 owner、保护标志、ACE 数量、类型、权限与 SID，
检查完成后才把句柄交给内容写入。现有文件不会被打开修改；原子发布仍使用
原有 replace 或 hard-link/no-clobber 顺序。ACL 不受支持或读取失败时拒绝写入。

POSIX 继续使用原有 `mkstemp`/`os.open` 权限和原有 0600 断言。Windows
对应断言改为独立 PowerShell `Get-Acl` 实际读回，不跳过这两个业务测试。
新增本机测试检查首字节前权限、发布后权限、替换、碰撞、ACL/句柄转移失败清理。
CI 增加 Windows × Python 3.11/3.12，保留 Linux 两项和所有原有检查。

范围：新创建的故事状态与默认 0600 原子写入。不会追溯修改已有文件、目录、
锁文件或 Drive 权限；调用者仍需可信父目录并协调写入。管理员/备份权限、
文件所有者自行修改 ACL、远程文件系统和断电持久性不在这个保证内。
测试全部使用合成资料，不构成作者接受、实际长篇完成或公开作品授权。

实现依据：[微软文件安全和访问权限](https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights)
与 [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)。
安全描述符在创建时传入，不在写入后运行 chmod 或放宽失败结果。
