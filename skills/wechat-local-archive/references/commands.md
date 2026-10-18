# 运行参数

在技能外创建私有工作目录，将以下路径替换为本次实际输入。
`SKILL` 为技能文件夹，`WORK` 为本次工作目录；这些变量不是用户身份。

```sh
python "$SKILL/scripts/archive.py" inventory --db-root "$DB_ROOT"
python "$SKILL/scripts/archive.py" snapshot --db-root "$DB_ROOT" --output "$WORK/snapshot"
python "$SKILL/scripts/archive.py" verify --db-root "$WORK/snapshot" --key-file "$WORK/keys.json" --output "$WORK/verification.json"
python "$SKILL/scripts/archive.py" resolve --db-root "$WORK/snapshot" --key-file "$WORK/keys.json" --name '演示联系人'
```

如确实需要且已获授权初始化，先正常退出原版；状态目录必须全新：

```sh
python "$SKILL/scripts/bootstrap_keys.py" --acknowledge-debug-copy --db-root "$DB_ROOT" --state-dir "$WORK/bootstrap"
```

精确 resolve 返回唯一候选后，使用返回的内部 ID，不要把昵称当 ID。

```sh
python "$SKILL/scripts/archive.py" export --db-root "$WORK/snapshot" --key-file "$WORK/keys.json" --chat-id "$CHAT_ID" --self-id "$SELF_ID" --timezone Asia/Shanghai --output "$WORK/archive.json"
```

可选 `--start YYYY-MM-DD`、`--end YYYY-MM-DD`（结束日期包含全天）。
默认最多 100000 条，超出时停止并要求缩小范围或明确提高 `--max-messages`，
不会静默截断。只查询选定会话，不自动导出整个账号。

可选 `--recover-media --account-dir "$ACCOUNT_DIR"` 为选定消息准备本地媒体。
恢复图片还需要 `--self-id`；可用 `--app-data` 指定统计文件目录。
`--account-dir` 是原账号目录，`--db-root` 仍指独立数据库副本。
下载/缺失的媒体和不支持的类型保留状态，不自动联网获取 CDN 内容。

```sh
python "$SKILL/scripts/render_html.py" "$WORK/archive.json" --media-root "$WORK" --output "$WORK/chat.html"
python "$SKILL/scripts/audit_html.py" "$WORK/chat.html" --expected-messages 12
```

`--expected-messages` 使用本次 export 的实际条数，不照抄示例数字。
HTML 最大内嵌媒体量默认 256 MiB，可显式调整 `--max-media-mib`。
输出文件拒绝覆盖，更新时选择新路径，或由 Agent 在明确授权范围内管理旧产物。

## 归一化归档格式

顶层包括 `title`、`selection`、`coverage`、`messages`。每条消息包括
`id`、`time`、`sender`、`kind`、`text`、`status`、`source`、`assets`。
`assets` 只接受含 `path` 和 `kind`（image/audio/video）的对象；可带
`note` 说明缩略图、完整性或转写限制。相对 path 相对于 JSON 所在目录，
最终解析必须留在 `--media-root` 内。

渲染器不导出任意顶层字段、原始 XML、内部 ID 或本机路径。图片格式检查
需要 Pillow；WAV 使用标准库检查。脚本不会自动执行资产或访问消息 URL。

## 合成测试与打包

```sh
python -B "$SKILL/scripts/test_archive.py"
python -B "$SKILL/scripts/package_skill.py" "$SKILL" --output /path/to/wechat-local-archive.zip
```

若已安装 SQLCipher，测试额外验证真实加密的人工数据库与消息导出。
没有动态库时明确显示该部分跳过，不能宣称端到端数据库测试通过。
打包可加 `--forbid-file`，指向包外 UTF-8 文件，每行一个本次敏感标识；
只报告命中文件，不打印标识值。分享前检查打包目录与 ZIP，不能打包整个工作区。
