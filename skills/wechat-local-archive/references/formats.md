# 格式与媒体

## 结构化消息

通话 XML 可能包含多个根节点；用虚拟根节点解析，拒绝 DTD/实体声明。
读取 `VoIPBubbleMsg/msg`，必要时优先读取 `voiplocalinfo/diaplay_content`
（该拼写确实可能出现在数据中）。room_type 0/1 对应视频/语音；缺失时不猜。
显示文字含真实时长时，不用常为零的 duration 字段覆盖它。

系统提示保留文字。appmsg 提取 title/des/type/sourcedisplayname；type 33
为小程序卡片。不要导出 AES key、CDN 签名、鉴权字段，不自动打开分享链接。

## 图片

通过 MessageResourceInfo + MessageResourceDetail + ChatName2Id 按会话 ID、
server ID 查询 packed_info 中的资源名；在明确账号的 msg/attach 目录定位。
消息 XML MD5 不必等于资源文件名，不用该 MD5 直接猜磁盘文件。

常见 DAT V2：标志后记录 AES 段和 XOR 尾部长度，15 字节头，AES-ECB + PKCS7
头部、明文中段和 XOR 尾段。候选图片密钥可来自本机 app_data 中已知统计
文件名的数值与自身 ID 派生；这是版本相关的逆向兼容逻辑，不是数据库密钥。
`media_pipeline.py` 提供这一兼容路径。密钥仅在内存中使用，不能写入报告。

保存已解码原始 JPEG 等字节，避免只交付重新编码的图片。依次检查来源
关联、声明长度、图像解码、尺寸和可用哈希；无法核对某项要明确记录。
静态 WXGF 等不能由 Pillow 处理的格式可能需要额外解码器，不宣称通用支持。

## 语音

`media_*.db` 中 VoiceInfo 与 Name2Id 按会话 + server ID 唯一匹配。
`packed_info_data` 可能带微信已存转写，语义也需核对；它不是人工确认文本。
SILK 数据使用 pilk 解码为 PCM，再写为单声道 WAV。保留声明时长和解码时长；
没有原始摘要值时，不声称通过哈希核验。

优先交付可播放音频。按需采用本地 ASR；明确模型、是否人工听辨及不确定性。
字幕署名、跨文件重复句、空音频幻觉、与语音不符的内容应从聊天正文中排除。
失败识别结果只保留在私有诊断文件中。

## 表情和其他媒体

表情 XML 中的 md5、描述或尺寸可以解析，但加密缓存未必兼容当前解码器。
只能把经格式验证、且能核对的摘要一致的结果视为还原成功。卡片、视频号
链接、通话状态都不等于已经获得相应视频或录音。必要时单独研究，不猜内容。

## RMFH 手机备份

`Backup/.../ChatPackage`、Index、Media 下的 RMFH 文件不是 SQLite。
已发表的方法采用 128 字节头尾、nonce 在头部偏移 19 的 12 字节、tag 在尾部
偏移 10 的 16 字节、中间密文使用 AES-GCM；该布局仍需用实际样本验证。
手机备份密钥与 Mac 数据库密钥不能视作相同。没有正确密钥时只枚举文件和
可解析元数据，不把看似可读的乱码当作明文，也不跳过 GCM 认证。

Android 取钥的固定函数偏移不能搬到鸿蒙/iOS。没有经过验证的平台路径时
明确停在已知边界；本技能不包含手机备份取钥器。
