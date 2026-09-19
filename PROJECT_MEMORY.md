# 创新大赛 AI 日程项目记忆

更新时间：2026-09-17。

本文记录当前对话已确认的方向、竞品调研、MVP 与部署状态和工作边界。后续接续项目时先读本文，再读原规格文件；原规格中的长期目标不等于当前已批准实施的范围。

## 用户要求与当前状态

- 用户要求先调研可使用或二次开发的 GitHub 项目，核实维护、部署和复用情况，先交付 Word 初版计划书，等用户确认后再开发 MVP 和部署网页。
- 已完成规格文件与七页 Word 文件《创新大赛AI日程_初版计划书.docx》。此前规格文件包括 PRD、数据库 Schema、采集适配器接口和低保真页面说明。
- 已基于 dayGLANCE v5.2.0 建立 `dayglance-mvp` 的 `campus-mvp` 分支并完成可运行校园入口；代码已推送至公开仓库 [o3249674925-web/AIricheng](https://github.com/o3249674925-web/AIricheng)。
- 用户已确认方案并授权制作 MVP、通过 GitHub 部署网页；MVP 与 GitHub Pages 均已完成。
- Cloudflare Worker 已由用户在电脑端部署成功，线上检查通过；Worker 地址为 <https://kexu-campus-mvp.richeng.workers.dev>。
- 用户已完成 MVP 试用并确认“mvp没问题”；当前首版验收通过。
- 用户希望把进度与资料迁移到远程控制的电脑；尚待提供目标电脑连接方式与保存目录，未完成迁移。

## 项目定位

面向学生的群通知任务追踪与日程助手。主要场景为课程、作业、考试、社团与创新竞赛。

“AI 自动安排日程”“微信消息转待办”“任务变成日历时间块”已有相似产品，不能单独宣称为原创或市场空白。项目应聚焦群聊上下文中的任务变化，并把已确认任务安排进学生真实可用时间。

## 竞品结论

以下为 2026-09-16 对话中根据官方资料核实的能力，不代表已对竞品进行实际使用测试。

| 应用 | 已确认的相似能力 | 对项目的启示 |
| --- | --- | --- |
| Motion | 依据截止时间、优先级与可用时间自动排程、动态调整；从转发邮件提取任务 | 自动排程是成熟方向，需要更具体的场景差异 |
| Reclaim | 汇总任务工具中的待办，自动安排日历时间并处理冲突 | 单纯把待办放进日历不足以构成核心创新 |
| Akiflow | 多来源任务收件箱，将 Slack 消息与邮件转成任务并结合日历规划 | 信息汇总和消息转任务已有成熟产品 |
| 滴答清单 | 微信转发内容创建任务、文字时间识别和提醒 | 微信入口本身不是独有优势 |
| 飞书及自动化生态 | 工作流可创建任务和日程；官方 OpenClaw 插件提供消息读取、任务更新与日历操作 | 在飞书生态内可以组合类似流程，需纳入替代方案比较 |

尚未验证这些产品是否完整支持微信和 QQ 群聊中的连续改期、取消识别与学生个人排程。不能把“本轮未核实”写成“竞品肯定不支持”。商业竞品与可复用开源底座属于不同选型问题。

## 差异化重点

1. 追踪任务变化：识别新增、延期、取消与补充要求；同一事项更新原任务，减少重复创建和误合并。
2. 适配校园场景：结合课表、作业、考试和竞赛，理解“下节课前”“第八周”等时间表达；缺少必要上下文时询问用户。
3. 可核对的安排：保存任务来源和原文证据；不确定内容先确认；时间不足时明确告知，不伪造可执行计划。

这些是拟实现和验证的能力，不能表述为已经完成的功能。

代表性演示：老师先说“周五交报告”，随后说“改到下周一，只交电子版”。系统应关联同一任务，更新截止时间与提交要求，保留两条证据，确认后重新安排写报告时间，而不是创建两个待办。

## 验证价值的方法

- 使用同一组人工标注的脱敏群消息，对比本项目与“滴答清单加人工整理”的流程。
- 记录整理耗时、任务遗漏数、改期处理错误数；补充重复任务数与误合并数。
- 样例覆盖新增、重复、延期、取消、完成、模糊日期、同名不同任务与闲聊。
- 产品收益须由对照测试支持；不预先宣称节省比例或领先竞品。

## 技术与 MVP 建议的确认状态

- 用户已确认方案并授权开始 MVP。推荐路线已落实为基于 dayGLANCE 二次开发：复用日期运算与区间分栏算法，新增校园通知收件箱、人工确认、变更证据、本地保存和约束排程。
- dayGLANCE 近期发布证据：v5.2.0，2026-09-14；可复用任务管理、时间块交互和本地保存。若底座适配成本过高，先报告再讨论 React 加 FullCalendar Standard 备选。
- 原方案中的 WeChatFerry 已于 2026-07-10 归档，不能继续视为持续维护的微信接入底座。首版不依赖它。
- 最简 MVP 建议：粘贴文本或导入 TXT → AI 提取候选事件 → 人工确认 → 更新任务 → 避开固定事件排程 → 本地保存和 JSON 导出。
- 首版暂缓微信及 QQ 直连、复杂附件解析、多人同步、第三方日历读写与原生移动端。旧文档的 FastAPI、SQLite 和 OR-Tools 属于后续可选架构，不是已确定的首版依赖。
- GitHub Pages 已部署；Cloudflare Worker 仍提供 MVP 静态资源与 AI API。最近线上健康检查返回 `{"ok":true,"aiConfigured":true}`，说明服务端模型配置已存在；此前提取请求出现 `model_preflight_failed`，不能把“已配置”误写成“模型调用已验证成功”。
- 模型密钥只能在服务端保存。演示模式与真实 AI 模式必须清楚区分。
- Cloudflare 首次创建 `workers.dev` 子域名后，TLS 证书曾短暂未生效；等待约一分钟后恢复，首页、JS/CSS 静态资源和 `/api/health` 均为 HTTP 200。此为用户报告的线上验证结果。
- 后续启用 AI 时，用户需要在电脑终端通过 `wrangler secret put AI_API_KEY` 的交互输入配置密钥，并设置模型 URL 和模型名称；密钥不可进入源码、命令参数、Git 或聊天。可选访问码按 Worker 配置要求设置。
- 竞品跟踪自动化仅被建议，用户没有授权创建，目前未设置。

## 后续工作

用户已确认 MVP 范围与技术路线，并确认试用无问题。当前 MVP：`campus/` 中文响应式入口；粘贴/TXT 导入；本地规则识别；可选 Worker 服务端 AI；新增/改期/取消/完成确认；固定事项避让与 14 天排程；浏览器本地保存、撤销、JSON 备份恢复。复杂相对日期仍要求确认。

已验证：Worker 专项测试 5/5、`npm run test:campus` 4/4 通过；`npm run build:campus`、`node --check worker.js`、原 dayGLANCE `npm run build` 通过。全量基线测试有 5 个与本次无关的时区/日期环境敏感失败，未修改其代码。

发布状态：
- GitHub Pages 已启用，最新安全修复提交 `a70441b0d57b760fb677f9ed4f2cddcc940490d7` 对应的 workflow 运行成功（run `35140469770`）。地址：<https://o3249674925-web.github.io/AIricheng/>；GitHub Pages 工作流未因 Worker 部署而修改。
- Cloudflare Worker 已部署，地址：<https://kexu-campus-mvp.richeng.workers.dev>。首页、JS/CSS 静态资源和 `/api/health` 均通过 HTTP 200 检查；规则模式可用。
- 已修正 Cloudflare Account ID 与 API Token 权限；最新一次 GitHub Actions 手动发布 Worker 成功。
- 已将模型适配修复同步到 GitHub（Worker、页面错误提示和部署说明）。修复内容包括自动补全 `/v1/chat/completions`、默认不发送易引发兼容问题的 `response_format`、识别更多模型返回格式和可读诊断码。GitHub Pages 已更新；Cloudflare Worker 还需要用最新 `worker.js` 重新发布后，线上提取接口才会使用这份修复。受接口访问码保护，当前环境无法替代用户验证真实模型调用。
- 为支持仅移动端推进，已新增并激活手动 GitHub Actions 工作流 `.github/workflows/deploy-worker.yml`。配置 `CLOUDFLARE_API_TOKEN` 与 `CLOUDFLARE_ACCOUNT_ID` 两个 GitHub Secret 后，可直接在手机 GitHub Actions 页面手动发布 Worker；普通提交不会自动发布。部署说明已同步，GitHub Pages 最新 workflow 运行成功（run `35142633826`）。
- 日程任务仍只保存在浏览器本地；没有账号系统或云端数据同步。
- 当前没有额外人工配置步骤；仅在启用 AI 时需要用户在本机终端交互录入 API Key。

微信接入判断：当前 MVP 仅支持粘贴通知或导入 TXT，不会扫描个人微信。后续若拓展，优先评估企业微信官方机器人对指定群消息的接收流程，并保留人工确认环节；不建议依赖个人微信非官方协议或客户端抓取。

## 官方来源

- [Motion 自动排程](https://www.usemotion.com/help/time-management/auto-scheduling)
- [Motion 邮件任务提取](https://www.usemotion.com/blog/ai)
- [Reclaim 任务排程](https://reclaim.ai/features/tasks)
- [Akiflow 任务管理](https://akiflow.com/task-management)
- [滴答清单微信添加与时间识别](https://dida365.com/features?language=zh_cn)
- [飞书 OpenClaw 官方插件](https://www.feishu.cn/content/article/7613711414611463386)
- [dayGLANCE 发布记录](https://github.com/krelltunez/dayGLANCE/releases)
- [WeChatFerry 归档与版本记录](https://github.com/lich0821/WeChatFerry/releases)
- [GitHub Pages 服务范围](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [Workers 定价与免费计划](https://developers.cloudflare.com/workers/platform/pricing/)
- [Workers Secrets 配置](https://developers.cloudflare.com/workers/configuration/secrets/)

## 2026-09-19 本地微信桥接与构建链路

- 在保持 Worker 错误诊断和 GitHub Pages 工作流不变的前提下，新增 `wechat-bridge/` 本地桥接适配器，支持目标群文字筛选、去重、Worker 提取和本地 done 结果保存。
- 新增 `scan-once.cmd`，首次运行只建立当前窗口基线，后续运行处理基线后的新文字并自动退出，避免持续占用桌面。
- 网页新增“导入桥接结果”按钮；done JSON 会进入待确认收件箱，仍由用户逐条核对后写入浏览器本地任务。
- 补齐 Vite、pnpm 锁定依赖和 `dist-campus/index.html` 根目录构建；远程副本验证通过 6 项前端测试、6 项桥接测试、Worker 语法检查和 Python 编译。
- 当前变更已在独立远程副本中完成验证，尚未推送到 GitHub；现有 `pages.yml` 与 `deploy-worker.yml` 未修改。

## 2026-09-19 远程副本部署状态

- 独立远程副本提交 `ca1f125`（桥接与构建链路）及 `c0f8c1e`（Worker 请求标识）已通过验证。
- GitHub `main` 推送因认证连接无响应而停止，远程仓库尚未更新；本地提交仍保留在 `AIricheng-remote`。
- 同一验证副本已部署到 Cloudflare Worker，线上版本 `331bc004-ba94-43ff-a63b-5ba319a922b1`，首页、静态脚本和健康检查均通过。

## 2026-09-19 Pages 与 Worker 最终发布

- 提交 `ca1f125`、`c0f8c1e`、`862bff9`、`71a6bd0` 已推送到 GitHub `main`。
- GitHub Pages workflow `35437818545` 成功；资源改为相对路径，页面和脚本均可在 `/AIricheng/` 子路径加载，桥接导入入口已上线。
- Cloudflare Worker 已同步部署版本 `d38922b4-c7b8-4574-899d-6e31da00a66a`，首页、静态脚本和 `/api/health` 检查通过。

## 2026-09-19 单次扫描窗口修复（本地已验证）

- 用户两次看到 `WORKER_READY` 后出现 `POLL_UNAVAILABLE`。真实桌面验证：微信在线且主窗口已打开“微信接入测试”，`GetSubWindow` 返回空，但主窗口可读取消息。之前把故障归因于用户没有打开微信不准确。
- 修复单次扫描：直接使用主窗口；必要时只精确切换一次；读取前后校验目标群名；不注册连续监听。读取失败向调用者返回错误，不再静默当作成功结束。启动器增加 UTF-8 设置。
- 12 项桥接测试通过，Python 编译和 `git diff --check` 通过。真实 `--once --poll --diagnostic` 验证输出 `POLL_ONCE_BASELINE recent=13 uploaded=0`，退出码 0；使用独立测试目录后，又为正式本机目录建立同样的去重基线。未调用模型、未上传内容、未发送微信消息。
- 正式队列验证前为 done=6 / pending=0 / failed=0，旧状态仅有 version/seen；已建立新版 baseline_ready，防止下一次重新处理旧消息。
- 本次修改尚未提交/推送，不涉及 Worker 或 Pages 部署。随后用户发送新的验收通知并运行修复后的脚本，本机 `done` 从 6 增至 9，`pending=0`、`failed=0`；3 个新结果均来自目标群、各含 1 条候选及截止时间，确认“微信读取 → Worker `/api/extract` → 模型返回候选”已真实跑通。网页导入与人工确认仍由用户在浏览器完成；候选不会自动写入本地任务。

## 2026-09-19 单次导入简化

- 为减少用户逐个选择结果文件的操作，单次扫描成功发送后会在 `%LOCALAPPDATA%\\AIricheng\\wechat-bridge\\latest-batch.json` 写入本次成功结果数组；原有 `done` 逐条记录保留用于追溯。
- 桥接测试仍为 12 项通过，前端测试 6 项通过；本次只改本地桥接与文档，不需要重新发布 Worker。
