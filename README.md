# 羊毛switch 额度目录 / YangmaoSwitch Catalog

各平台大模型**免费额度**的结构化目录。[羊毛switch 官网](https://github.com/YangmaoSwitch/website)和[桌面端](https://github.com/YangmaoSwitch/app)都只读这份数据。

目前收录 83 家平台（2026-11-25）。条目由人工整理，并接受用户和平台方提交（提 PR 或 [Issue](https://github.com/YangmaoSwitch/catalog/issues/new/choose)），核实后上架；我们用 agent 实时检查国内外最新的免费 Token，辅助发现新活动、复查已上架条目，结论都要有平台官方页面的原文为据。

A structured catalog of free LLM API quotas, kept as current and complete as we can. The YangmaoSwitch website and desktop app are built from this data. Users and providers are welcome to submit new quotas or corrections; we verify them before listing.

## 收录什么

- 官方提供、能当 API 调用的免费额度：长期免费档、每日或每月赠送、新人赠金、限时免费模型。
- API 中转站、聚合平台提供的免费额度同样收录，在条目里写明平台类型。
- 只能在对方产品里使用的积分也收录，但标注 `api_usable: false`，桌面端的本地网关不会用它们。

**不收录**：

- 返利链接、邀请链接。
- 二手积分（转卖别人账号里的额度）。
- 需要使用虚拟号码、批量注册或一人多开账号才能获得的额度（这些做法违反多数平台条款）。

## 数据在哪

- `providers/<id>.yaml`：每个平台一个文件，字段说明见 [schema/provider.md](schema/provider.md)。
- 每条都要带**官方证据链接**和**最后核实日期**。只见于社区消息的，标 `status: unconfirmed`，不计入总数。
- 每条额度可带 `quote`：从证据页面逐字复制的一句原文。新上架的条目必须有；之后定期比对，原文不见了就优先复查。
- 只给新用户的活动标 `new_users: true`，页面显示“新用户活动”。
- 活动结束时**不删除、不下架**：官方公布了截止日期的写 `ends`，过期后自动显示“已下线”；已确认结束的写 `ended`（整个平台）或 `quotas[].ended`（某一项额度）。已下线的额度在排序中按付费计算。

## 发布

`main` 每次更新和每 6 小时，CI 运行 `scripts/build.py`（校验并生成 `catalog.json`）和 `scripts/build_models.py`（生成 `models.json`：各平台的模型、调用方式和标价，同一模型跨平台合并，并按“模型质量 × 免费可得程度”给模型和平台排序），发布到 `dist` 分支。官网和桌面端都读 `dist`：

- https://raw.githubusercontent.com/YangmaoSwitch/catalog/dist/catalog.json
- https://raw.githubusercontent.com/YangmaoSwitch/catalog/dist/models.json

调用方式只分两类显示：**免费**（免费模型，或用平台的免费额度调用）和**付费**。

## 平台入驻

欢迎各平台主动提 PR 入驻，接入分三级：

| 级别 | 平台要做的 | 用户能得到的 |
|---|---|---|
| **L1 收录** | 提 PR，新增 `providers/<id>.yaml` | 在官网和桌面端可见；注册链接可带你们自己的渠道码，用于统计来源 |
| **L2 半自动** | 再提供 Key 页深链接、Key 前缀、查剩余额度的接口或响应头 | 粘贴 Key 即自动识别；本地网关按真实剩余额度限量 |
| **L3 全自动** | 再提供 **OAuth 2.0 PKCE 公共客户端**，回调到 `http://127.0.0.1:<任意端口>`，授权后签发一把只给本应用用的 Key，最好支持 Key 级额度上限 | 桌面端“一键开通” |

详细要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。L3 的参考实现是 [OpenRouter OAuth PKCE](https://openrouter.ai/docs/use-cases/oauth-pkce)。

## 安全模型

- 用户的 Key 只保存在用户本机（系统钥匙串）。
- 羊毛switch 的线上服务不接触 Key，也不转发任何模型调用。
- 桌面端的本机入口只监听 127.0.0.1，用户的请求带着用户自己的 Key 直接发往平台；模型名填 `auto` 时，按本目录的模型排序挑选用户账号能用的免费模型，限流或出错时换下一家。

## 许可证

[MIT](LICENSE)。部分初始数据参考了 [mvalentsev/awesome-free-ai-coding](https://github.com/mvalentsev/awesome-free-ai-coding)（MIT），引用时在条目里注明来源。
