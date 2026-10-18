# 来源、许可和边界

本技能包含通用代码和合成测试，不包含真实账号、联系人、密钥、数据库、
聊天内容、截图、音频、模型权重或安装包。功能验证不能替代每次真实数据验收。

## 参考

- Mac 取钥、SQLCipher 只读、WAL 和媒体兼容工具：
  https://gist.github.com/acmerfight/0a01249ef72970d07a2603dbb629e80f
  采用提交 `c98dbb10cf23c30e83d5d744905101b0880887a0` 的通用实现。
- SQLCipher 官方构建和 API：https://github.com/sqlcipher/sqlcipher
- SQLite WAL：https://www.sqlite.org/wal.html
- 微信消息结构参考：https://github.com/hicccc77/WeFlow
  只作为字段/格式研究参考，未复制其应用源码到本技能。
- RMFH 格式的原始研究：https://www.52pojie.cn/thread-2068774-1-1.html
- 本机语音识别可选工具：https://github.com/absadiki/pywhispercpp
- Codex 技能结构：https://learn.chatgpt.com/docs/build-skills

## 随附第三方代码许可

`bootstrap_keys.py`、`capture_keys.py`、`sqlcipher_probe.py`、`disk_inventory.py`
来自上述 Mac 工具；bootstrap 的恢复路径另外覆盖复制/签名失败。
`media_pipeline.py` 基于同一来源，调整了账号媒体路径、
保留解码原始图片、默认仅输出 WAV，以及图像摘要核验。这些文件保留以下许可：

MIT License

Copyright (c) 2026 Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

外部依赖各自保留其许可证。本包不分发 SQLCipher、Pillow、pilk、模型或
微信应用二进制，不能将第三方 MIT 许可视作所有外部依赖的许可。
