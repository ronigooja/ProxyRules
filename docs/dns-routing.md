# DNS 查询出口审计

目标是查询经过业务连接实际选择的节点，而不是任意代理出口。代理解析器使用 Cloudflare／Google 的 IP DoH，直连解析器使用 DNSPod 的 IP DoH。当前原生模板尚不能保证这一完整关系，不能宣称全部客户端已支持。

直连地址现为 DNSPod `https://1.12.12.12/dns-query`，Clash／Clash Meta、Stash、Shadowrocket 和 Surfboard 的相关字段同时填写 `https://120.53.53.53/dns-query`（Shadowrocket 直连字段的多地址行为尚未确认）。这不是严格主备保证；Sing-box 与 Surge 暂只配置第一个地址。下文 Mihomo 历史实测使用的是替换前的阿里模拟解析器，尚未针对本次 DNSPod 地址调整重新实测。
多地址的并发、主备及证据范围见 [多 DNS 地址调度调查](dns-multiple-resolvers.md)。其中 Surge 新版本支持多个域名专用 DNS；Shadowrocket 直连字段的多地址行为尚未确认。

## 客户端结果

| 客户端 | 当前能力及缺口 |
| --- | --- |
| Clash / Clash Meta（Mihomo） | `#代理名称` 可以指定 DoH 出口。当前已按原始域名规则顺序绑定业务组，取消固定自动优选。官方 1.19.32 已实测首次节点正确，但节点切换会复用旧连接；该配置不能独自处理应用组选 DIRECT 时改用 DNSPod、真实 IP 查询、缓存与已建立 DoH 连接的出口切换。`respect-rules` 匹配的是 DNS 服务器连接，并非查询中的业务域名。旧 Clash 内核不能假定支持 Mihomo 的扩展。 |
| Sing-box | DoH `detour` 可以指定出口。当前已按域名规则绑定各业务组，固定直连规则使用 DNSPod，代理例外也保留原顺序。但静态 DNS 规则仍不能保证组选 DIRECT 时同步改变解析器；普通 DNS 请求发生时也不能假定已经选定业务连接的出口。 |
| Stash | `nameserver-policy` 选择解析器，`follow-rule` 将 DNS 连接交给规则处理。当前 DNS 服务器 IP 固定到自动优选，业务应用组的选择不会自动传递给这条连接。 |
| Surge | `encrypted-dns-follow-outbound-mode` 将 DoH 连接按普通请求匹配规则，不是按业务域名继承节点。官方文档还说明：DNS 连接选中的代理地址为域名时，存在递归解析导致回退 DIRECT 的情况。当前配置不能保证同节点。 |
| Surfboard | 官方文档说明 DoH 当前默认使用 DIRECT，未给出按业务节点指定 DoH 出口的配置，不能满足代理侧要求。 |
| Shadowrocket | 参考配置资料的 `#proxy` 表示默认节点，`#proxy=name` 表示指定节点；它不能直接证明任意应用策略组的业务节点会自动传给 DNS。仓库独立配置的代理查询现已指定 Cloudflare／Google IP DoH `#proxy`，直连域名与节点地址使用 DNSPod IP DoH，并关闭直连解析失败转代理。该配置仅使用内置 PROXY，没有应用组；未取得对应版本的运行时验证，缓存、连接复用与 IP 规则前置解析仍不能假定符合完整要求。 |

## 为什么不能简单替换代理组

应用组选择美国节点，而 DNS 固定走自动优选的日本节点，就是查询出口不一致。将自动优选改成默认代理，也会在应用组独立选节点时出现同一问题。

为各应用域名绑定 `#应用组` 或各组的 `detour` 也不等于完整实现：应用组改选 DIRECT 后，同一 Cloudflare 查询可能变成直连，而目标要求此时切换为 DNSPod DoH。根据目标 IP 选择出口的规则还可能需要先解析才能确定业务出口，不能只按 DNS 时的域名推断最终节点。

真正的实现需要客户端在业务路由确定后，把实际出口传给 DNS 解析过程，按出口选择解析器；代理 DNS 使用同一节点，直连 DNS 使用 DNSPod 并直连。切换节点时还需处理 DNS 缓存和旧 DoH 连接，解析失败时不能回退到其他出口。也需要明确并验证节点地址的启动解析。

## 实测与校验

`python3 scripts/validate_outputs.py` 校验域名规则的顺序、业务组与 DNS 绑定、IP DoH 地址。`python3 scripts/test_dns_policies.py` 覆盖应用独立绑定、代理例外、重叠域名、关键词优先级和拒绝规则。这些检查不替代实际查询出口验证。

可运行 `python3 scripts/probe_mihomo_dns.py --mihomo /path/to/mihomo` 进行真实查询出口诊断。需要 PyYAML 和 OpenSSL。诊断启动本机模拟节点与 HTTPS DNS 服务，通过 loopback IP 模拟 Cloudflare、Google 和 DNSPod，检查真正收到 DNS 请求的节点与解析器；生产配置的证书验证不会改变。退出码 2 表示同节点要求未满足，诊断不调用发布 API。

官方 Mihomo 1.19.32 的测试结果：AI 初始查询经过所选美国模拟节点，视频查询经过所选日本模拟节点；AI 改选日本后仍有查询经过旧美国节点；AI 改选 DIRECT 后也没有自动切换到阿里模拟解析器。固定 DIRECT 域名查询正确使用阿里模拟解析器并直连。即使 DNS 响应 TTL 为零、下一次查询使用新域名，旧 DoH 连接仍可能被复用；这不是仅清空 DNS 地址缓存就能解决的问题。

此前的硬编码全客户端发布阻断已移除。当前没有发布远端修改，也不将已实现的业务组绑定描述为已经实现完整同节点要求。完整实现需要客户端传递实际业务出口、按 DIRECT 动态切换解析器，并在节点变化时处理 DNS 客户端和连接复用。

## 依据

- [Mihomo DNS 文档](https://wiki.metacubex.one/config/dns/)；[DNS 连接实现](https://github.com/MetaCubeX/mihomo/blob/Meta/tunnel/dns_dialer.go)：构造的目标地址来自 DNS 服务器连接地址，`RULES` 对其执行路由。
- [Sing-box HTTPS DNS](https://sing-box.sagernet.org/configuration/dns/server/https/)、[DNS 规则](https://sing-box.sagernet.org/configuration/dns/rule/)、[域名解析选项](https://sing-box.sagernet.org/configuration/shared/dial/)。
- [Stash 内置 DNS](https://stash.wiki/features/dns-server)。
- [Surge 加密 DNS](https://manual.nssurge.com/dns/encrypted-dns.html)：`encrypted-dns-follow-outbound-mode` 的普通请求规则匹配和递归解析回退行为。
- [Surfboard DoH](https://getsurfboard.com/docs/profile-format/general/doh_server)。
- [Shadowrocket 配置参考](https://github.com/LOWERTOP/Shadowrocket#dns-over-proxy)是第三方资料，不能替代对应版本客户端的实际验证。
