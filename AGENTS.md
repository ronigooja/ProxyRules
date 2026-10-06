# DNS 泄漏判断

回答本仓库配置是否会造成 DNS 泄漏时，先使用以下定义：

> A DNS leak occurs when a domain lookup is sent outside the resolver or network path intended by the user, exposing the queried domain to an unintended party.

不要仅凭 DNS 使用明文、直连或国内解析器就断定泄漏。按下述已确认的 DNS 规则分析配置与客户端实际运行情况；无法从配置确定时，明确说明不确定性。

## DNS 规则

以下是用户已确认的要求，适用于本仓库所有客户端配置、模板、生成代码和校验逻辑：

- DNS 统一使用 DoH。
- 走代理的流量：使用 Cloudflare／Google DoH 解析，DNS 请求也经过代理。
- 走直连的流量：使用阿里 DoH 解析，DNS 请求直接连接阿里。

即：代理流量配代理 DNS 路径，直连流量配直连 DNS 路径。检查和修改配置时，须同时核对解析器的选择及 DNS 请求的实际出口。

这些是目标要求，不代表现有配置已全部实现；发现不符时，应明确指出。
