# 课序 · AI 校园日程 MVP

本入口基于 dayGLANCE v5.2.0（MIT）二次开发，独立于原生桌面/移动入口。它复用了 dayGLANCE 的日期运算与 `assignLanes` 日历分栏算法；校园通知抽取、变更证据和约束排程属于新增代码。

## 本地运行

```bash
npm ci
npm run dev:campus
```

生产构建：`npm run build:campus`，产物为 `dist-campus/`。

## MVP 能力

- 粘贴通知或导入 TXT；每行生成候选，不确认不会写入任务。
- 本地规则模式识别带引号的事项名、明确日期/星期、延期/取消/完成关键词。
- 可选服务端 AI：前端不接触模型密钥，`worker.js` 只发送必要的通知文本和最多 100 项待办用于关联。
- 更新同一任务而非重复创建，保存来源、原文和前后值历史。
- 设置每日可用窗口与固定事项；按截止时间/优先级安排连续时间块，避开固定事项，不超过截止时间。
- 浏览器本地保存、撤销、JSON 导出与恢复。恢复时校验版本、日期、时长、重复 ID，并丢弃旧排程重新计算。

## Cloudflare Workers

1. `npm run build:campus`
2. `npx wrangler login`
3. 在 Cloudflare Worker Secrets 中设置 `AI_API_KEY`；变量中设置 `AI_API_URL`、`AI_MODEL`。可选 `AI_ACCESS_TOKEN` 保护 `/api/extract`。
4. `npx wrangler deploy`

`wrangler.jsonc` 使用 Workers Static Assets 直接托管 `dist-campus/`，Worker 同时提供 `/api/health` 与 `/api/extract`。未配置模型时接口返回 503，页面保持本地规则模式，不会伪装成 AI 已可用。

## GitHub Actions

仓库准备好后，把 Cloudflare 凭据放入 GitHub Actions Secrets（`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`），即可在 push 到 `main` 时运行构建与 `wrangler deploy`。本地发布前先用 `npm run test:campus` 和 `npm run build:campus`。
