# ProxyRules

仓库中的 Shadowrocket 配置会从上游地址自动同步，并在 `[Rule]` 段最前面加入本仓库的 `Rules/ChinaAI.list` 和 `Rules/DirectIP.list` 规则。

`Rules/` 存放带 `DIRECT` 策略的共用内联规则。若用于 Clash/Mihomo，请将规则加入配置的 `rules` 段；它们不是可直接作为 rule-provider 引用的列表。

生成文件：[Shadowrocket/nodnsleak-pk.ini](Shadowrocket/nodnsleak-pk.ini)。推送到 `main` 后，可在 Shadowrocket 中使用下面的远程配置地址：

```text
https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Shadowrocket/nodnsleak-pk.ini
```

手动更新：

```sh
python3 scripts/update_shadowrocket_rules.py
```

GitHub Actions 每天自动运行，也可以在 Actions 页面手动运行 `Update Shadowrocket rules`。修改本仓库的规则文件并推送后，下一次同步会自动带入生成文件。首次使用前请确保仓库的 Actions 工作流拥有读写权限，以便自动提交更新。
