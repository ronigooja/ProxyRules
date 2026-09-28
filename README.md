# ProxyRules

仓库中的 Shadowrocket 配置会从上游地址自动同步，并在 `[Rule]` 段最前面以 `RULE-SET` 形式引用本仓库的 `Rules/ChinaAI.list` 和 `Rules/DirectIP.list`。

`Rules/` 是不带策略字段的规则集，由配置中的 `RULE-SET` 统一指定为 `DIRECT`。规则集地址使用 GitHub Raw，因此 Shadowrocket 会额外下载它们。

生成文件：[Shadowrocket/nodnsleak-pk.ini](Shadowrocket/nodnsleak-pk.ini)。推送到 `main` 后，可在 Shadowrocket 中使用下面的远程配置地址：

```text
https://raw.githubusercontent.com/ronigooja/ProxyRules/main/Shadowrocket/nodnsleak-pk.ini
```

手动更新：

```sh
python3 scripts/update_shadowrocket_rules.py
```

GitHub Actions 每天自动运行，也可以在 Actions 页面手动运行 `Update Shadowrocket rules`。修改本仓库的规则文件并推送后，下一次同步会自动带入生成文件。首次使用前请确保仓库的 Actions 工作流拥有读写权限，以便自动提交更新。
