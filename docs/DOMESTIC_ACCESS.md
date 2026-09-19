# 国内访问优化记录

## 当前结论（2026-09-19）

- Worker 同时托管 `dist-campus/` 和 `/api/*`，网页中的 API 请求使用相对路径。因此把同一个 Worker 绑定到自有域名后，不需要改前端，也不会引入跨域代理。
- 当前 Worker 地址 `https://kexu-campus-mvp.richeng.workers.dev` 和 GitHub Pages 地址仍作为回滚入口；两者都不应在优化过程中删除或覆盖。
- 本次检查中 Worker 首页与 `/api/health` 均返回 HTTP 200，`/api/health` 报告 `aiConfigured: true`。这只能证明当前部署可用，不能证明中国大陆各运营商都能稳定访问。
- `workers.dev` 或 GitHub Pages 域名是否能在大陆访问，取决于当地网络、运营商和时间变化；代码改动本身不能保证免 VPN。

## 第一阶段：低改动自有域名入口

准备一个已经拥有的域名或子域名，例如 `app.example.com`，并确认它所在的 DNS zone 已加入同一个 Cloudflare 账号。然后在 Cloudflare 控制台为 `kexu-campus-mvp` 添加 Worker Custom Domain。不要手动把 CNAME 指向 `workers.dev` 后就认为绑定完成；Custom Domain 需要在 Worker 中建立关联并由 Cloudflare 管理证书。

绑定后按以下顺序验证：

1. `https://app.example.com/` 返回页面。
2. `https://app.example.com/assets/...` 返回静态资源。
3. `https://app.example.com/api/health` 返回 `ok: true`，且不显示任何密钥。
4. 在中国大陆的手机流量和家庭宽带各打开一次，分别记录是否能打开、首屏时间和 `/api/health` 状态。
5. 保留 `workers.dev` 和 GitHub Pages 入口，确认新域名异常时可以回退。

这一步只改变入口，不改变 AI Secret、任务本地存储或 GitHub Pages 工作流。

## 仍无法稳定访问时

如果自有域名仍在大陆出现超时或间歇性不可达，继续改 Worker 代码通常不会解决网络路径问题。下一阶段需要评估中国大陆可达的 CDN/静态托管和 API 部署，并确认域名备案、服务商地区和合规要求；这不是本仓库内一次配置能自动完成的事情，也不应在没有测量数据时先购买付费服务。

## 当前阻塞信息

仓库和当前 Cloudflare 登录页中没有可用于绑定的自有域名记录。继续执行第一阶段前，需要提供“域名或子域名 + DNS 由哪家管理”这两项信息；不要发送 Cloudflare API Token、OpenAI API Key 或其他密钥。
