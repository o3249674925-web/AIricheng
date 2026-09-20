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

## 已选择：恢复码同步

| 方案 | 优点 | 必要条件与风险 |
| --- | --- | --- |
| 恢复码同步（当前） | 零第三方登录，适合低成本 MVP | 恢复码丢失后无法找回；它是访问凭据，不代表实名身份 |
| 微信网页授权（暂缓） | 国内用户操作顺手 | 需要已认证的微信公众号/开放平台应用、回调域名和 AppID/Secret |
| 邮箱魔法链接（备选） | 不保存密码 | 需要邮件服务和发信域名，国内到达率需实测 |

恢复码只用于小规模测试和跨设备同步，不提供找回、实名、会员或支付能力。若未来需要正式公开账号，再单独评估微信或邮箱身份认证。

## 建议的服务端结构

- Cloudflare Worker：登录回调、会话 Cookie、同步接口。
- Cloudflare D1：`users`、`sessions`、`task_snapshots` 三类数据。
- 会话使用 `HttpOnly`、`Secure`、`SameSite=Lax` Cookie；不要把长期 Token 放到 `localStorage`。
- 每条云端数据必须带 `user_id`，查询和写入都以会话用户为条件。
- 本地数据首次上传前显示摘要和条数，用户明确确认后才上传；服务端不接收微信登录凭据或 AI API Key。

当前代码已加入恢复码接口和 D1 迁移文件，但账号功能默认关闭：只有提供 D1 绑定后，`/api/auth/recovery/create` 和 `/api/auth/recovery/login` 才会启用。当前 Worker 没有 D1 绑定，因此现有用户不会看到半成品登录入口，也不会影响 `/api/extract`。

启用前需要由项目维护者在 Cloudflare 中完成以下配置（值不要写进仓库）：

1. 创建 D1 数据库，将返回的 `database_id` 写入 `wrangler.jsonc` 的 `d1_databases` 绑定 `DB`。
2. 执行 `wrangler d1 migrations apply <数据库名> --remote`，应用 `migrations/0001_accounts.sql`。
3. 部署 Worker 后，在网站的「时间与数据 → 恢复码同步」中创建恢复码。任务快照会在浏览器端用恢复码派生的 AES-GCM 密钥加密，再上传到 D1。
4. 不要把恢复码发到聊天；它丢失后无法找回，建议复制到密码管理器或纸面备份。

同步接口的实际调用必须在配置完成后再测试；不能用现有的 AI 访问码或个人微信登录状态代替恢复码。

建议接口：

```text
GET  /api/auth/me
POST /api/auth/recovery/create
POST /api/auth/recovery/login
POST /api/auth/logout
GET  /api/sync/pull
PUT  /api/sync/push
```

同步先采用“用户主动同步 + 整体快照”模型，避免一开始引入逐条冲突合并。每个快照保存 `schema_version`、`updated_at` 和客户端设备标识；服务端拒绝跨用户访问。

## 发布前检查

- 恢复码模式可直接使用现有 `workers.dev` 地址；GitHub Pages 入口继续保留作静态回退。
- 需要创建 D1 数据库并把绑定写入 `wrangler.jsonc`，这会产生新的 Cloudflare 资源，不能在没有账号方案时猜测。
- 需要补充隐私说明：保存哪些任务字段、保存多久、如何删除账号和数据。
- 需要先在本地测试登录回调、退出、数据隔离、导入失败回滚和会话过期，再部署 Worker。

## 当前待定项

恢复码接口已经完成，但上线前还缺以下外部条件：

1. Cloudflare D1 数据库和绑定。
2. 确认恢复码仅用于测试和跨设备同步，不承诺账号找回。
3. 如果未来切换微信授权，再补充微信网站应用、回调域名和对应凭据。

不要把 AppID、AppSecret、邮件服务密钥、Cloudflare Token 或 AI API Key 发到聊天；它们只能通过对应服务的 Secret/环境变量输入。

## 恢复码上线步骤

恢复码模式不需要微信开放平台或自有域名，但仍需要 Worker 绑定 D1：

1. 创建一个 Cloudflare D1 数据库，并把绑定名称设为 `DB`。
2. 应用 `migrations/0001_accounts.sql`。
3. 部署当前 Worker。
4. 打开 Worker 网站，在「时间与数据 → 恢复码同步」点击「创建恢复码」。
5. 在另一台设备打开同一 Worker 网站，点击「输入恢复码」，登录后再手动下载云端数据。

云端只保存浏览器端加密后的快照；Worker 不需要知道恢复码明文。恢复码丢失时，仍可使用本机 JSON 备份恢复。

## 微信方案（暂缓）

GitHub Pages (`o3249674925-web.github.io/AIricheng`) 只能托管静态文件，不能执行 `/api/auth/wechat/callback`。若让 Pages 页面直接调用 Worker，还要额外处理跨域 Cookie 和两个站点的回跳，复杂度和失败点都会增加。

因此第一轮可以先尝试把现有 Worker 域名作为微信网站应用的官网和授权回调域：

```text
官网：https://kexu-campus-mvp.richeng.workers.dev
授权回调域：kexu-campus-mvp.richeng.workers.dev
完整回调地址：https://kexu-campus-mvp.richeng.workers.dev/api/auth/wechat/callback
```

微信平台是否接受 `workers.dev` 需要以创建/审核页面的实际结果为准；如果它要求可证明归属的自有域名、备案或拒绝共享托管域名，不能用 GitHub Pages 绕过，只能再评估自有域名或其他托管方案。GitHub Pages 继续保持现状，不作为账号回调服务器。
