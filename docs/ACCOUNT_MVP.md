# 账号功能 MVP 设计

## 当前事实

项目目前只有浏览器 `localStorage` 数据，没有用户、会话、数据库或云端同步。现有 `AI_ACCESS_TOKEN` 只是保护模型接口的访问码，不能当作用户账号；把它复用成登录凭据会导致所有用户共享身份和数据。

账号功能的最小闭环必须同时包含：登录身份、服务端会话、按用户隔离的数据存储，以及本地数据迁移/冲突处理。只添加“登录”按钮而继续写 `localStorage`，不算账号功能。

## 推荐的最小范围

第一版只做以下能力：

1. 注册/登录后得到一个用户会话。
2. 将当前浏览器的任务、固定事项和变更记录导入该用户空间。
3. 在用户主动点击“同步”时上传和拉取数据。
4. 退出登录后清除会话，但保留本机导出备份。
5. 保留现有本地规则模式、AI 提取和 JSON 导入/导出作为离线回退。

暂不做会员等级、支付、配额、多人协作、自动微信同步和后台定时任务。

## 登录方式必须先选定

| 方案 | 优点 | 必要条件与风险 |
| --- | --- | --- |
| 微信网页授权 | 国内用户操作最顺手 | 需要已认证的微信公众号/开放平台应用、回调域名和 AppID/Secret；还要处理隐私说明与授权失败 |
| 邮箱魔法链接 | 不保存密码，开发较快 | 需要邮件服务和可用发信域名；国内收信速度、垃圾箱和服务商成本需实测 |
| 自建账号密码 | 不依赖第三方登录 | 必须自行处理密码哈希、验证、找回、限流和风控；没有邮件/短信渠道时无法可靠找回，不建议作为第一版 |

如果主要用户是国内学生，优先评估微信网页授权；如果暂时没有微信开放平台凭据，先做邮箱魔法链接的技术验证。没有登录方式和回调域名之前，不应开始线上账号接口开发。

## 建议的服务端结构

- Cloudflare Worker：登录回调、会话 Cookie、同步接口。
- Cloudflare D1：`users`、`sessions`、`task_snapshots` 三类数据。
- 会话使用 `HttpOnly`、`Secure`、`SameSite=Lax` Cookie；不要把长期 Token 放到 `localStorage`。
- 每条云端数据必须带 `user_id`，查询和写入都以会话用户为条件。
- 本地数据首次上传前显示摘要和条数，用户明确确认后才上传；服务端不接收微信登录凭据或 AI API Key。

当前代码已加入上述接口和 D1 迁移文件，但账号功能默认关闭：只有同时提供 D1 绑定、`WECHAT_APP_ID`、`WECHAT_APP_SECRET` 和 `AUTH_STATE_SECRET` 时，`/api/auth/wechat/start` 才会跳转到微信。当前 Worker 没有这些绑定，因此现有用户不会看到半成品登录入口，也不会影响 `/api/extract`。

启用前需要由项目维护者在 Cloudflare 中完成以下配置（值不要写进仓库）：

1. 创建 D1 数据库，将返回的 `database_id` 写入 `wrangler.jsonc` 的 `d1_databases` 绑定 `DB`。
2. 执行 `wrangler d1 migrations apply <数据库名> --remote`，应用 `migrations/0001_accounts.sql`。
3. 用 Wrangler Secret 输入 `WECHAT_APP_SECRET` 和 `AUTH_STATE_SECRET`；普通变量设置 `WECHAT_APP_ID`、`WECHAT_AUTH_MODE`（`website` 或 `official`）以及已在微信平台登记的 `WECHAT_REDIRECT_URI`。
4. 只有在微信开放平台审核通过并配置回调域名后，才部署并做真实授权测试。

网站应用扫码登录还需在微信开放平台登记“授权回调域”：只填写域名，例如 `app.example.com`，不要填 `https://`、路径或查询参数。代码中的 `WECHAT_REDIRECT_URI` 才填写完整回调地址，例如 `https://app.example.com/api/auth/wechat/callback`；两者必须属于同一域名。

登录和同步接口的实际调用必须在配置完成后再测试；不能用现有的 AI 访问码或个人微信登录状态代替微信开放平台授权。

建议接口：

```text
GET  /api/auth/me
GET  /api/auth/wechat/start
GET  /api/auth/wechat/callback
POST /api/auth/logout
GET  /api/sync/pull
PUT  /api/sync/push
```

同步先采用“用户主动同步 + 整体快照”模型，避免一开始引入逐条冲突合并。每个快照保存 `schema_version`、`updated_at` 和客户端设备标识；服务端拒绝跨用户访问。

## 发布前检查

- 需要一个可稳定访问的自有域名；当前 `workers.dev` 和 GitHub Pages 入口继续保留作回退。
- 需要创建 D1 数据库并把绑定写入 `wrangler.jsonc`，这会产生新的 Cloudflare 资源，不能在没有账号方案时猜测。
- 需要补充隐私说明：保存哪些任务字段、保存多久、如何删除账号和数据。
- 需要先在本地测试登录回调、退出、数据隔离、导入失败回滚和会话过期，再部署 Worker。

## 当前待定项

登录接口骨架已经完成，但上线前还缺以下外部条件：

1. 已审核通过的微信网站应用或公众号，以及对应的 AppID。
2. 用于回调的自有域名（以及 DNS 是否已接入 Cloudflare）。
3. Cloudflare D1 数据库和绑定。
4. 在 Cloudflare Secret 中录入 AppSecret 与状态签名密钥。

不要把 AppID、AppSecret、邮件服务密钥、Cloudflare Token 或 AI API Key 发到聊天；它们只能通过对应服务的 Secret/环境变量输入。
