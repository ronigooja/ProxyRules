# ProxyRules

ACL4SSR 的 `Online Full` 提供规则和地区节点匹配条件；本仓库的生成脚本统一安排分流组职责、成员和初始选择。[Rules/Custom.list](Rules/Custom.list) 收录国内 AI 等自定义规则，支持 `DIRECT`、`REJECT`、`Proxy` 策略，插入位置在应用广告拦截规则之后、一般国内直连规则之前。生成脚本使用同一上游版本生成 XBoard 的 Sing-box、Clash、Clash Meta、Stash、Surge、Surfboard 模板和独立的 Shadowrocket 配置。请通过 XBoard 用户订阅导入，仓库模板本身不含节点。独立 Shadowrocket 配置使用其内置的 `DIRECT`、`REJECT`、`PROXY` 出口，没有这些应用选择组。

## 分流组逻辑

显示顺序为：默认代理 → 自动优选 → 手动选择 → 国家／地区组 → 应用分流组 → 广告拦截／应用净化 → 其他流量。

| 分组 | 职责及候选项 | 初始选择 |
| --- | --- | --- |
| 🚀 默认代理 | 自动优选、六个地区组、手动选择、DIRECT | 自动优选 |
| ♻️ 自动优选 | 全部代理节点，按延迟自动选择 | 自动 |
| 🚀 手动选择 | 全部代理节点，由用户指定 | 首个节点 |
| 国家／地区组 | 按节点名称和地区旗帜筛选，按延迟自动选择 | 对应地区节点 |
| 各应用分流组 | 默认代理、六个地区组、全部具体节点、DIRECT | 按应用用途设置 |
| 广告拦截／应用净化 | REJECT、DIRECT | REJECT |
| 🐟 其他流量 | 默认代理、DIRECT | 默认代理 |

所有应用组提供相同的候选项，不再嵌套额外的自动优选或手动选择。默认项置于首位，其余引用项按统一顺序排列，订阅节点随后追加；Sing-box 同时写入显式 `default`。部分客户端通过首项决定初始选择，因此不同默认值的应用组顺序略有差异。客户端已保存的选择可能继续保留，默认值主要用于首次导入。

| 应用组 | 初始选择 |
| --- | --- |
| 电报、国外媒体 | 默认代理 |
| AI 平台 | 新加坡组 |
| 油管、奈飞视频 | 美国组 |
| 巴哈姆特 | 台湾组 |
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

Shadowrocket 完整规则配置：`https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Shadowrocket/nodnsleak-pk.ini`。其中不含节点，DNS 使用阿里 DoH，IPv6 已开启；实际 DNS 行为取决于设备和客户端设置。

DNS 出口要求见 [AGENTS.md](AGENTS.md)。[Surfboard 官方配置文档](https://getsurfboard.com/docs/profile-format/general/doh_server)说明 DoH 查询目前默认直连，未提供指定 DoH 代理出口的配置项。因此 Surfboard 模板中的阿里 DoH 只覆盖直连侧，不能保证代理流量按本仓库要求经代理使用 Cloudflare／Google DoH。需要严格按此要求使用时，请选用 Clash Meta（Mihomo）配置，并在客户端自行启用所需的流量接管功能。

Sing-box 的 DNS 直连例外按固定域名规则生成，尚未随应用组实时选择切换。应用组选 DIRECT 时，相关域名仍可能通过代理向 Cloudflare／Google DoH 查询；默认直连应用改选代理时也不能保证 DNS 路径同步改变。这不满足本仓库要求的动态出口对应关系，不能仅凭代理组配置认定所有客户端均已实现 DNS 目标。

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
