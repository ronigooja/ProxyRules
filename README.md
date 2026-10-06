# ProxyRules

ACL4SSR 的 `Online Mini` 是规则和代理组的上游。[Rules/Custom.list](Rules/Custom.list) 收录原 `ChinaAI.list` 的国内 AI 直连规则，并入上游；支持 `DIRECT`、`REJECT`、`Proxy` 策略，插入位置在广告拦截规则之后、一般国内直连规则之前。生成脚本使用同一上游版本生成 XBoard 的 Sing-box、Clash、Clash Meta、Stash、Surge、Surfboard 模板和独立的 Shadowrocket 配置。六种 XBoard 模板采用上游 `custom_proxy_group` 定义的组名、类型、成员和测速参数，`.*` 节点匹配由各客户端格式适配。XBoard 在响应用户订阅时自行填入该用户的节点。独立的 Shadowrocket 配置不含节点，规则仍使用其内置的 `DIRECT`、`REJECT`、`PROXY` 出口。

## 独立规则链接

独立的个人规则在 [Rules/Personal.list](Rules/Personal.list)，收录原 `DirectIP.list` 的两个 IP 直连规则，不含策略字段，可作为客户端的补充规则集：

- Surge、Shadowrocket：`https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Rules/Personal.list`
- Clash、Clash Meta（classical rule-provider）：`https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Rules/Personal.clash.yaml`

Clash 文件由 `Rules/Personal.list` 生成，无需单独编辑。使用时为规则集指定 `DIRECT`。Shadowrocket 配置包含个人规则链接；XBoard 模板只合并 `Rules/Custom.list`，个人规则链接可按需补充。

Shadowrocket 完整规则配置：`https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Shadowrocket/nodnsleak-pk.ini`。其中不含节点，DNS 使用阿里 DoH，IPv6 已开启；实际 DNS 行为取决于设备和客户端设置。

## DNS 泄漏定义

A DNS leak occurs when a domain lookup is sent outside the resolver or network path intended by the user, exposing the queried domain to an unintended party.

## XBoard 模板更新

月度工作流在每月 1 日运行，也支持手动运行。生成阶段下载 ACL4SSR 同一 Git 提交的配置和规则，校验并提交生成结果；发布阶段调用 XBoard 已有的管理 API，更新六个订阅模板。生成文件位于 `XBoard/`，规则版本记录在 `Upstream/ACL4SSR-REVISION`。Clash Meta 使用与 Clash 相同的规则，另有 Mihomo TUN 自动路由和 DNS 劫持配置；Stash 使用与 Clash 相同的 YAML 配置。Sing-box 使用 JSON 路由规则；Surfboard 使用兼容的 Surge 式配置。

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

校验脚本需要 PyYAML。工作流会安装固定版本。独立规则链接和 XBoard 模板都来自仓库生成文件，部署新工作流后可在 Actions 页面手动运行一次，使站点模板与仓库版本一致。
