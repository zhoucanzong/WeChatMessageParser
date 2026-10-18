# WeChatMessageParser

一个用于 **Mac 微信本地聊天归档** 的 Codex skill。Agent 负责选择会话、判断
授权与结果可信度；脚本负责只读查询、消息解析、可用媒体恢复和单文件 HTML 导出。

## 使用

技能入口：[skills/wechat-local-archive/SKILL.md](skills/wechat-local-archive/SKILL.md)。
将该目录放入本机 Codex 的技能发现目录，或建立指向它的符号链接，然后调用：

```text
使用 $wechat-local-archive，读取我指定的联系人和时间范围，
将可用图片、语音与聊天记录导出为自包含 HTML，并列出未还原的内容。
```

首次没有密钥时，初始化可能需要退出微信、运行临时副本并由本人确认登录。
技能会先核查本次授权和环境；已有有效密钥时直接复用。适配范围受微信版本、
系统权限与架构限制，不能承诺所有版本可用。

## 能力与边界

- 联系人精确匹配、日期筛选、跨消息分库读取及覆盖率统计。
- 普通文字、通话状态/时长、系统提示、小程序卡片元数据解析。
- 兼容格式下的本地 DAT 图片、SILK 语音恢复；未支持媒体保留明确状态。
- 图片、音频内嵌的离线 HTML，包含无外部引用与资源解码检查。
- 手机 RMFH 备份仅提供格式辨别与研究边界，不提供通用手机备份取钥。
- 不发送消息、不自动回复、不发布档案，不将失败的语音识别写成聊天原话。

本仓库只包含通用源码、说明和合成测试，不包含个人账号、密钥、聊天记录、
媒体、数据库副本或真实导出文件。运行产物应放在仓库外的私有目录。

## 验证

```sh
python -B skills/wechat-local-archive/scripts/test_archive.py
python -B skills/wechat-local-archive/scripts/package_skill.py skills/wechat-local-archive
```

图像测试需要 Pillow；数据库测试需要 SQLCipher，并在缺失时明确跳过。
依赖、命令和输入格式见技能的 references。随附第三方代码许可见
[来源与许可](skills/wechat-local-archive/references/sources.md)。
