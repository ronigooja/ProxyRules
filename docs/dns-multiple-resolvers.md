# 多 DNS 地址的调度行为

核对日期：2026-10-18。本文检查仓库模板、官方文档及可取得的源码，未对 iOS/macOS 客户端做抓包实测。

结论：地址的排列顺序不等于主备关系。Mihomo、Stash、Surfboard，以及 Surge 的全局加密 DNS 都有明确的并发查询依据。Sing-box 的服务器集合不自动构成并发组或故障切换组；Shadowrocket 的不同 DNS 字段应分别判断。

## 各客户端结论

| 客户端 | 多地址调度及依据 | 仓库当前直连配置 | 是否严格主备 |
| --- | --- | --- | --- |
| Clash / Clash Meta（实际按 Mihomo 分析） | Mihomo v1.19.32 的 `batchExchange` 为每个服务器启动并发任务，`Picker` 取第一个无错误的结果并取消其他任务。`SERVFAIL`、`REFUSED` 不作为成功结果。命中 `nameserver-policy` 的查询也进入这套逻辑。 | `default-nameserver`、`proxy-server-nameserver`、`direct-nameserver` 和 DIRECT 域名策略均列出两个 DNSPod IP DoH。 | 否。两个地址会参与并发竞争。旧版原始 Clash 的兼容性和行为不能据此保证。 |
| Stash | 官方文档明确：多 DNS 服务器并发查询，采用最先成功返回的结果；对 `proxy-server-nameserver` 和 `nameserver-policy` 数组也有明确说明。 | 启动解析、节点域名解析和 `geosite:cn` 策略均列出两个 DNSPod 地址。 | 否。列表顺序不是优先级。 |
| Surfboard | 官方 `doh-server` 文档明确：多个 DoH 并行查询，使用最快响应；DoH 默认 DIRECT。 | `doh-server` 列出两个 DNSPod 地址。该字段作用于全局 DNS，并非只有直连业务的查询；仓库原来即有此客户端能力缺口。 | 否。 |
| Surge | 官方 `encrypted-dns-server` 文档明确：多个地址并发查询，先返回的结果胜出。另一份官方文档明确：iOS 5.21.0+ / Mac 6.8.0+ 的 `[Host] server:` 支持逗号分隔多个 DNS；该段未单独说明专用服务器列表的调度，不能把它称为顺序主备。 | 直连域名的 `[Host] server:` 目前只指定一个 DNSPod 地址；全局 Cloudflare / Google 列表仍为并发查询。 | 当前没有直连备用。新版本支持填写多个专用 DNS，不能说 Surge 只能配置一个；但尚无此专用字段严格主备的依据。 |
| Sing-box | 官方 v1.12.0 文档：`servers` 声明服务器集合，DNS 规则的 `server` 指定一个目标标签，`final` 指定默认标签；`final` 为空才默认使用第一个服务器。仅增加条目不会自动轮询、并发或失败切换。 | `local` 是单个 DNSPod HTTPS DNS，`detour: direct`；直连规则指定 `local`，没有引用第二个 DNSPod 地址。 | 当前没有备用。需要显式规则设计并核对版本，不能把集合中的下一项当备用。 |
| Shadowrocket | 第三方 LOWERTOP 资料明确：`dns-server` 多地址并行查询，取最先返回；另有 `fallback-dns-server`，描述为覆写 DNS 失败或查询超过 2 秒后回退，且直连 DNS 失败也会回退。该资料没有充分说明 `direct-dns-server`、`proxy-dns-server` 多地址的调度细节。未取得官方说明、源码或对应版本实测。 | `direct-dns-server` 与解析节点域名的 `proxy-dns-server` 均填写两个 DNSPod 地址；`dns-server` 是 Cloudflare / Google 经代理。未显式填写 `fallback-dns-server`。 | 当前两个直连地址的主备关系未证实，也不能把多地址生效和并发行为视作已实测。专用 fallback 字段提供可能的实现方向，但需进一步核实。 |

## 与当前配置的关系

- DNSPod 的 `1.12.12.12` 与 `120.53.53.53` 属于同一服务商。对于已确认并发的字段，它们应称为“双地址冗余”，不能称为“主地址、故障后才启用的备用地址”。这不提供服务商之间的冗余。
- 并发描述针对需要访问上游的查询。命中缓存、Hosts、返回 Fake-IP 等情况，不一定产生上游查询；任务被取消也不意味着此前发出的请求能够撤回。A / AAAA 两类查询并行与同一查询发给多个解析器是两件事。
- Mihomo v1.19.32 命中域名 DNS 策略后会直接查询该策略的服务器列表，不能仅新增全局 `fallback` 就断言为这些直连策略实现了严格主备。Stash 的官方文档还明确：普通 `nameserver` / `fallback` 会同时查询，再按过滤条件选结果；`fallback` 这个名称本身不代表延迟发起。
- Shadowrocket 的 `fallback-dns-server` 是另一个字段，不能和逗号分隔的多地址混为一谈。第三方资料称空备用等于 `system`；仓库虽设置 `dns-fallback-system = false`，其与该字段的优先级仍需实测，不能保证失败时没有其他出口。也不应直接将全局备用设置为直连 DNSPod，否则可能使代理查询回退到非预期的直连解析器。
- Sing-box 的 testing 分支文档标注 1.14.0 增加 `evaluate`、`respond`、`race` 等能力，可用于设计更复杂的响应处理。仓库当前未使用这些能力，不能据此把现有配置描述为具备并发或自动备用，也不能未经版本核对直接加入。

按仓库定义，DNS 泄漏取决于查询是否发给非预期解析器或经过非预期网络路径。用户若接受两个 DNSPod 地址作为直连解析器，并且查询实际直连 DNSPod，并发本身不构成泄漏；它仍然不满足“正常只查第一个，失败才查第二个”的严格主备要求。

本次调查仅补充文档，没有修改 DNS 配置。闭源客户端的实际版本、失败重试、缓存和出口仍需运行时核实。

## 来源

1. Mihomo v1.19.32：[批量查询 `batchExchange`](https://github.com/MetaCubeX/mihomo/blob/v1.19.32/dns/util.go#L415)、[并发结果选择 `Picker`](https://github.com/MetaCubeX/mihomo/blob/v1.19.32/common/picker/picker.go)、[策略及 fallback 处理](https://github.com/MetaCubeX/mihomo/blob/v1.19.32/dns/resolver.go)。
2. [Stash 官方内置 DNS 文档](https://stash.wiki/features/dns-server)：自定义上游、节点域名解析、域名策略及回退 DNS。
3. [Surfboard 官方 `doh-server` 文档](https://getsurfboard.com/docs/profile-format/general/doh_server/)：逗号分隔多个地址、并发取最快及默认 DIRECT。
4. Surge 官方：[加密 DNS](https://manual.nssurge.com/dns/encrypted-dns.html)、[本地 DNS 映射与专用 DNS](https://manual.nssurge.com/dns/local-dns-mapping.html)。多地址专用 DNS 有 iOS 5.21.0+ / Mac 6.8.0+ 版本要求。
5. Sing-box v1.12.0：[DNS 配置文档](https://github.com/SagerNet/sing-box/blob/v1.12.0/docs/configuration/dns/index.md)、[DNS 规则动作](https://github.com/SagerNet/sing-box/blob/v1.12.0/docs/configuration/dns/rule_action.md)、[DNS 路由实现](https://github.com/SagerNet/sing-box/blob/v1.12.0/dns/router.go)。新能力另外参见 [testing 分支 DNS 规则动作](https://github.com/SagerNet/sing-box/blob/testing/docs/configuration/dns/rule_action.md)，不作为旧版能力保证。
6. [LOWERTOP / Shadowrocket 第三方资料](https://github.com/LOWERTOP/Shadowrocket/blob/main/README.md#通用参数)：DNS 覆写、直连 DNS、备用 DNS；[隐式参数](https://github.com/LOWERTOP/Shadowrocket/blob/main/README.md#隐式参数)：节点域名 DNS。该资料不是官方实现保证。
