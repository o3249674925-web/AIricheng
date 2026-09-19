# 个人微信本地桥接

这个目录把已经验证过的个人微信 UI 读取能力接到现有 Cloudflare Worker。桥接进程只在电脑本机运行：它只注册一个完全匹配的群聊名称，接收新来的文字消息，筛选出疑似任务后调用 Worker 的 `/api/extract`，并把原文和返回候选保存在 `%LOCALAPPDATA%\AIricheng\wechat-bridge`。

启动时只读取目标群当前窗口里可见的近期消息来建立去重基线，这些旧消息不会上传或生成候选。桥接不处理图片、语音或文件，不发送或回复微信消息，也不把微信登录信息上传到云端。浏览器里的任务仍由用户手动确认，任务数据仍保存在浏览器本地。

## 先做本地自测

在项目根目录打开 PowerShell，运行：

```powershell
& "$env:USERPROFILE\wxauto-test\Scripts\python.exe" .\wechat-bridge\bridge.py --self-test
```

看到 `self-test passed` 就表示筛选、白名单和去重逻辑通过。这个命令不会打开微信，也不会访问网络。

## 启动连续监听

保持个人微信登录并保持窗口可见。新手直接双击 `wechat-bridge\\start-bridge.cmd`，然后在黑色窗口里输入 Worker 接口访问码并按回车。输入时屏幕不会显示任何字符，这是正常的。

也可以在项目根目录的 PowerShell 中运行：

```powershell
& "$env:USERPROFILE\wxauto-test\Scripts\python.exe" .\wechat-bridge\bridge.py --poll --prompt-access-token
```

也可以直接运行 `.\wechat-bridge\start-bridge.ps1`。它已经填好测试群和 Worker 地址，只会在终端询问一次 Worker 接口访问码。

`start-bridge.cmd` 不依赖 PowerShell 脚本执行策略；不需要输入 `&`、`$env:...` 或任何 Python 命令。这里输入的是 Worker 访问码，不是 OpenAI API Key。

如果不想让桥接持续运行，双击 `wechat-bridge\\scan-once.cmd`。第一次只建立当前窗口的本地基线并退出；以后再次运行时只扫描基线之后的新文字，发送完成后自动退出。每次运行仍需在窗口中隐藏输入 Worker 访问码。

单次扫描直接读取微信主窗口中的目标群，不要求提前打开独立聊天窗口。已在目标群时不会重复切换；否则只尝试一次精确切换。读取前后都会检查群名，切到其他聊天会停止本次扫描。看到 `[POLL_ONCE_DONE]` 只表示读取完成；随后出现“已发送到 Worker”才表示收到提取结果。成功结果会另外汇总到 `%LOCALAPPDATA%\\AIricheng\\wechat-bridge\\latest-batch.json`，网页只需导入这一个文件；`done` 子目录仍保留逐条记录。`scan-once.cmd` 已启用 UTF-8，避免中文提示乱码。

如果启动成功但一直没有任务提示，可先停止桥接，再用下面的只读诊断命令。它不会把消息发给 Worker，只显示是否收到回调摘要：

```powershell
& "$env:USERPROFILE\wxauto-test\Scripts\python.exe" .\wechat-bridge\bridge.py --chat "微信接入测试" --diagnostic --poll
```

看到 `[DIAGNOSTIC_ONLY]` 后，让群内另一位成员发送一条文字；若出现 `[CALLBACK_SEEN]` 或 `[POLL_SEEN]`，说明至少有一条读取通道正常，下一步只需调整筛选规则。若完全没有该行，则是微信版本、群名或监听回调本身的问题。`--poll` 只读取指定群当前消息窗口并先建立不上传的基线，启动时已有消息不会被当成新任务。

如果 Worker 配置了 `AI_ACCESS_TOKEN`，桥接进程需要同一个 Worker 访问码。访问码只在电脑本地隐藏输入，不能写进脚本、命令参数、Git 或聊天；这里输入的是 Worker 访问码，不是 OpenAI API Key。当前的一键启动器会安全询问它。

启动器会先发送一个不含消息文字的空请求验证访问码。看到 `[WORKER_READY]` 表示访问码正确，且这一步不会调用模型或消耗模型额度。访问码只保留在本次进程内存中，不写入文件。随后看到 `[BRIDGE_READY] chat=微信接入测试` 和 `[BRIDGE_WAITING] waiting for new text messages` 即已进入连续监听。收到符合任务特征的新文字时，终端会显示 `[EVENT_TASK]` 和发送状态；候选结果会留在本机数据目录，网页中的“待确认通知”仍需人工核对后确认。按 `Ctrl+C` 停止，程序不会关闭微信。部分微信版本不会把“自己发出的消息”作为新消息回调；测试时最好让群内另一位成员发送通知。

## 失败重试和隐私

待发送事件会先写入本机 outbox，只有 Worker 成功返回后才记入去重状态。网络错误最多自动重试三次，失败记录也只保留在本机；修好配置后可追加 `--retry-failed` 重试这些记录。日志不会打印任何 API Key 或访问码；不要把 `%LOCALAPPDATA%\AIricheng\wechat-bridge` 目录上传到仓库。

当前脚本优先使用已安装的 `wxauto4`。如果微信版本或 UI 结构变化导致 wxauto4 无法启动，脚本会停止并报告原因，不会切换到聊天数据库、内存修改或其他协议。
