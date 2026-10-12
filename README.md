# ProxyRules

ACL4SSR 的 `Online Full` 提供规则和地区节点匹配条件；本仓库的生成脚本统一安排分流组职责、成员和初始选择。[Rules/Custom.list](Rules/Custom.list) 收录国内 AI 等自定义规则，支持 `DIRECT`、`REJECT`、`Proxy` 策略，插入位置在应用广告拦截规则之后、一般国内直连规则之前。生成脚本使用同一上游版本生成 XBoard 的 Sing-box、Clash、Clash Meta、Stash、Surge、Surfboard 模板和独立的 Shadowrocket 配置。请通过 XBoard 用户订阅导入，仓库模板本身不含节点。独立 Shadowrocket 配置使用其内置的 `DIRECT`、`REJECT`、`PROXY` 出口，没有这些应用选择组。

## 分流组逻辑

显示顺序为：默认代理 → 自动优选 → 手动选择 → 国家／地区组 → 应用分流组 → 广告拦截／应用净化 → 其他流量。

| 分组 | 职责及候选项 | 初始选择 |
| --- | --- | --- |
| 🚀 默认代理 | 自动优选、手动选择、六个地区组、DIRECT | 自动优选 |
| ♻️ 自动优选 | 全部代理节点，按延迟自动选择 | 自动 |
| 🚀 手动选择 | 全部代理节点，由用户指定 | 首个节点 |
| 国家／地区组（香港地区、台湾地区、新加坡地区、日本地区、美国地区、韩国地区） | 按节点名称和地区旗帜筛选，按延迟自动选择 | 对应地区节点 |
| 各应用分流组 | 默认代理、六个地区组、DIRECT、全部具体节点（初始选择置顶） | 按应用用途设置 |
| 广告拦截／应用净化 | REJECT、DIRECT | REJECT |
| 🐟 其他流量 | 默认代理、DIRECT | 默认代理 |

自动优选和六个国家／地区组的测速间隔固定为 1800 秒（30 分钟），由本仓库生成脚本统一设置，不随上游间隔变化。实际测速时机受客户端运行状态和按需测速行为影响。

所有应用组提供相同的候选项，不再嵌套额外的自动优选或手动选择。默认项置于首位，其余引用项按“默认代理 → 香港地区 → 台湾地区 → 新加坡地区 → 日本地区 → 美国地区 → 韩国地区 → DIRECT”的顺序排列，并跳过已置顶的默认项；全部具体节点最后追加；Sing-box 同时写入显式 `default`。部分客户端通过首项决定初始选择，因此不同默认值的应用组顺序略有差异。客户端已保存的选择可能继续保留，默认值主要用于首次导入。

| 应用组 | 初始选择 |
| --- | --- |
| 电报、国外媒体 | 默认代理 |
| AI 平台 | 新加坡地区 |
| 油管、奈飞视频 | 美国地区 |
| 巴哈姆特 | 台湾地区 |
| 哔哩哔哩 | DIRECT |
| 谷歌 FCM、微软各服务、苹果服务、游戏平台 | DIRECT |

国内媒体、网易音乐保留分类规则，但固定映射为 DIRECT，不显示选择组。哔哩哔哩默认直连，保留选择组，供港澳台地区内容按需切换。固定直连分类在生成时也纳入对应的 DNS 直连规则。

“奈飞节点”已并入“奈飞视频”，取消奈飞和网易音乐的解锁名称筛选。地区组只按节点名称筛选，不保证真实地理位置或服务解锁能力。无匹配节点时地区组拒绝连接，用户可在应用组改选其他地区或具体节点；不会自动使用其他地区的节点。

Clash、Clash Meta、Stash 使用 XBoard 可识别的正则节点占位；默认代理、拦截组和其他流量组使用不匹配节点的占位，阻止 XBoard 追加全部节点。地区组保留 REJECT，以免无匹配时被 XBoard 删除并留下无效引用。Surge、Surfboard 使用 `include-all-proxies` 和 `policy-regex-filter` 筛选地区节点，REJECT 仅作为不可连接的占位。Sing-box 使用 XBoard 的 `include` 条件和 `fallback=block`，筛选字段由 XBoard 在生成订阅时移除。

规则从上往下首次命中生效，先决定进入哪个组，再使用该组当前选择。应用组选择“默认代理”时跟随该组当前选择；选择地区或具体节点时独立生效。明确的 DIRECT／REJECT 规则直接执行对应动作。上游规则顺序保持不变，分组映射与默认值集中在 `scripts/build_rules.py`；上游新增或删除分组时生成器会提示更新映射。

Sing-box 模板沿用 `block` 出站。已查看的 XBoard 上游代码在适配 Sing-box 1.13 及以上时会删除 `block`，但未同步替换选择组内的引用；使用该组合时需先修复 XBoard 的适配逻辑，否则包含拒绝选项的组可能产生无效引用。

## 独立规则链接

独立的个人规则在 [Rules/Personal.list](Rules/Personal.list)，收录原 `DirectIP.list` 的两个 IP 直连规则，不含策略字段，可作为客户端的补充规则集：

- Surge、Shadowrocket：`https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Rules/Personal.list`
- Clash、Clash Meta（classical rule-provider）：`https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Rules/Personal.clash.yaml`

Clash 文件由 `Rules/Personal.list` 生成，无需单独编辑。使用时为规则集指定 `DIRECT`。Shadowrocket 配置包含个人规则链接；XBoard 模板只合并 `Rules/Custom.list`，个人规则链接可按需补充。

Shadowrocket 完整规则配置：`https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Shadowrocket/nodnsleak-pk.ini`。其中不含节点，代理 DNS 使用 Cloudflare／Google IP DoH 并指定 `#proxy`，直连域名及节点地址使用阿里 IP DoH，IPv6 已开启；实际 DNS 行为仍需对应客户端版本验证。

DNS 出口要求见 [AGENTS.md](AGENTS.md)：全部使用 IP 形式的 DoH 地址（阿里 `https://223.5.5.5/dns-query`、Cloudflare `https://1.1.1.1/dns-query`、Google `https://8.8.8.8/dns-query`）。代理 DNS 必须跟随业务连接实际使用的节点，直连 DNS 使用阿里并直连。

Clash／Clash Meta 现按域名分流规则的原始顺序生成 DNS 策略，Cloudflare／Google 查询绑定对应业务组；固定 DIRECT 域名使用阿里直连。未命中域名规则的查询绑定其他流量组，取消原来统一使用自动优选的 DNS 与备用出口。该配置使用 Mihomo 的 inline classical rule-provider 扩展，旧 Clash 内核不能假定兼容。

Sing-box 同样按原始顺序为业务域名选择 DNS 服务器，服务器的 `detour` 绑定对应业务组，包含先于直连后缀的代理例外。代理侧默认查询绑定其他流量组，全局代理模式的 DNS 绑定默认代理组。

**这些修改尚未满足完整的同节点要求。** 官方 Mihomo 1.19.32 实测：新建查询连接可经过应用组选中的节点，但切换节点后可能复用旧节点的 DoH 连接；应用组选 DIRECT 后，普通真实 DNS 查询仍使用 Cloudflare／Google，而非自动切换到阿里。`direct-nameserver` 只处理对应的直连出口解析，不覆盖所有提前发生的 DNS 查询。Sing-box 的静态 DNS 规则也不能按组选 DIRECT 自动改变解析器。按目标 IP、进程等分流时，不能仅根据 DNS 中的域名确定最终业务出口。

逐客户端的依据及实测方法见 [DNS 查询出口审计](docs/dns-routing.md)。校验脚本检查规则顺序、业务组绑定及 IP DoH 地址，不把通过结构校验表述为完整运行时出口保证。此前直接阻断所有客户端发布的硬编码检查已撤掉，本次没有调用远端发布 API。

Stash、Surge 仍通过 DNS 服务器 IP 的规则指定查询出口，未实现继承业务节点；[Surfboard 官方配置文档](https://getsurfboard.com/docs/profile-format/general/doh_server)说明 DoH 查询当前默认 DIRECT，未提供按业务节点指定查询出口的配置。因此这些客户端不能当作已经满足仓库 DNS 要求。

## XBoard 模板更新

月度工作流在每月 1 日运行，也支持手动运行。生成阶段下载 ACL4SSR 同一 Git 提交的配置和规则，校验并提交生成结果；发布阶段调用 XBoard 已有的管理 API，更新六个订阅模板。生成文件位于 `XBoard/`，规则版本记录在 `Upstream/ACL4SSR-REVISION`。Clash Meta 使用与 Clash 相同的规则，另有 Mihomo TUN 自动路由和 DNS 劫持配置；Stash 使用相同的分流规则和独立的 DNS 配置。Sing-box 使用 JSON 路由规则；Surfboard 使用兼容的 Surge 式配置。

为每个 XBoard 建立一个 GitHub Environment，并设置：

| 类型 | 名称 | 值 |
| --- | --- | --- |
| Secret | `XBOARD_ADMIN_TOKEN` | 管理员登录响应 `auth_data` 中去掉 `Bearer ` 的令牌 |
| Variable | `XBOARD_API_URL` | 站点 HTTPS 根地址，不带 `/api` 路径 |
| Variable | `XBOARD_ADMIN_PATH` | 站点管理路径，单个路径段 |

工作流当前使用 `xboarddev.nodemgr.uk` 和 `my.surabbit.com` 两个 Environment。若某个值缺失，该站点的发布任务会明确失败，不会尝试空令牌请求。站点模板只会在内容变化时更新；生成或校验失败时不会调用任何站点 API。

本地生成与校验：

```sh
python3 scripts/build_rules.py
python3 scripts/validate_outputs.py
```

只调整分组而保留当前规则版本时，可以使用 `python3 scripts/build_rules.py --revision <Upstream/ACL4SSR-REVISION 中的提交号>`，再运行校验。

校验脚本需要 PyYAML。工作流会安装固定版本。独立规则链接和 XBoard 模板都来自仓库生成文件，部署新工作流后可在 Actions 页面手动运行一次，使站点模板与仓库版本一致。
