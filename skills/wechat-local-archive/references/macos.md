# Mac 读取与初始化

## 环境

主要路径是 Apple Silicon macOS + WeChat 4.x，不能推定其他版本兼容。
用 `Path.home()` 动态寻找
`Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/*/db_storage`。
账号目录带后缀，不应直接将完整目录名当作自身微信 ID。

读取需要 Python 3.10+ 与启用 codec 的 SQLCipher 4 动态库；Python 3.14 的
标准库支持 Zstandard，较低版本安装 `zstandard`。媒体另外需要
`cryptography`、`Pillow`、`pilk`。安装到工作目录的虚拟环境，依赖和模型
不放入技能目录。SQLCipher 通过 `SQLCIPHER_LIBRARY` 指定，或使用常见
Homebrew 安装位置；系统普通 SQLite 不能替代。

SQLCipher 源码构建需要 `SQLITE_HAS_CODEC`、`SQLITE_TEMP_STORE=2`、
`SQLITE_EXTRA_INIT=sqlcipher_extra_init`、
`SQLITE_EXTRA_SHUTDOWN=sqlcipher_extra_shutdown`，并正确链接 crypto provider。
具体构建以当前官方 README 为准。构建和虚拟环境留在用户的工作目录。

## 先复用密钥

`keys.json` 是外部私有文件，权限 0600，格式为 `keys` 对象，键为数据库相对
路径、值为含 `enc_key` 的对象。`enc_key` 为该库的 32 字节 raw key 的十六进制
表示。文件不存在、权限过宽、条目歧义或验证失败均停止该项读取。
密钥不通过命令行参数、聊天消息或标准输出传递。

复制数据库时包含 WAL/SHM。`archive.py snapshot` 检查复制前后元数据是否
变化；即使稳定也不等于跨库事务一致。先检查 SQLCipher 结构与 quick_check，
必要时正常退出微信后重新复制。副本可能被 SQLite 更新 SHM，原数据只读。

## 需要初始化时

先核查当前用户是否已经授权退出微信、临时副本重签及调试登录。若没有，
解释具体影响后申请授权，不把查看目录的许可扩大为初始化许可。

`bootstrap_keys.py`：
- 要求原版已正常退出，不自动终止原进程，不使用 sudo。
- 复制原版至私有状态目录并只签副本；默认原版位置是 `/Applications/WeChat.app`。
- 用 Apple Python 和相匹配的 LLDB Python 模块运行 `capture_keys.py`。
- 观察 CommonCrypto PBKDF2：SHA-512、16 字节盐、已知 256000/2 轮路径，
  用所选数据库第一页 HMAC 验证后保存逐库 raw key。
- 仅清理自己启动的调试子进程；核对原版签名、停用副本、请求启动原版。

副本仍访问同一账号文件，微信可能正常更新缓存和数据库；可能需要扫码。
调试、副本签名与账号影响不可承诺完全透明。权限拒绝时保留诊断，不关闭 SIP。

捕获等待可以在已满足目标数据覆盖时结束；使用针对自建捕获控制进程的
正常中断，让其 finally 清理。中断退出码不是成功证明，随后独立核验恢复
状态和已保存的密钥。不要为一个未打开的迁移辅助库不断重启微信。

如果初始化中途失败，检查临时进程是否仍在、原版签名是否匹配、原版实际
执行路径以及用户是否重新进入账号。不要只依据“启动请求成功”宣称已登录。

## 数据库和字段

- `contact/contact.db`：contact.username/nick_name/remark。
- `session/session.db`：SessionTable，记录可包含隐藏或旧会话。
- `message/message_N.db`：`Msg_` 加会话内部 ID 的 MD5。分库内 local_id 不是
  全局 ID，用数据库名 + 表名 + local_id 标识。
- `Name2Id.rowid` 对应 real_sender_id；未知发送者保持未知。
- `message_content` 可能为明文或 Zstandard；不能把无法解码的字节解释为空。
- `local_type` 可能将 appmsg 子类型放在高 32 位，例如 `(subtype << 32) | 49`。

以上为已观察到的布局，运行时核对表结构，不适配时报告差异。
