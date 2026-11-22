# 条目字段（v1）

机器校验以 [provider.schema.json](provider.schema.json) 为准，本页是说明。本地校验：`pip install pyyaml jsonschema && python scripts/build.py`。示例见 [providers/openrouter.yaml](../providers/openrouter.yaml)。

```yaml
id: openrouter                 # 唯一 ID
name: OpenRouter
homepage: https://openrouter.ai
region: global                 # global / cn / 具体国家或地区代码
api_usable: true               # false 表示只能在对方产品内使用
status: verified               # verified / unconfirmed / delisted
last_verified: 2026-11-19

api:
  protocol: [openai]           # openai / anthropic / gemini / other
  base_url: https://openrouter.ai/api/v1

signup:
  url: https://openrouter.ai   # 可带平台自己的渠道码
  requires: [email]            # email / phone / phone_cn / card / real_name / company
  regions_blocked: []          # 不可用地区
  min_age: 18

quotas:                        # 每项额度一条
  - unit: requests             # requests / tokens / input_tokens / output_tokens / credits / usd / cny / points / neurons
    amount: 50
    period: day                # minute / hour / day / week / month / one-time
    reset: "00:00 UTC"         # 重置时间和时区；滚动窗口写 rolling
    scope: account             # account / key / project / org / model
    models: ":free 模型"
    condition: "累计充值不足 10 美元"
    new_users: false           # 只给新用户的活动（如注册后 N 天内）设 true，页面标“新用户活动”
    evidence: https://openrouter.ai/docs/api-reference/limits
    quote: "..."               # 证据页面上逐字复制的一句原文，用于自动比对是否变化
overage: blocked               # blocked（超额即停）/ auto_paid（自动转付费）/ manual（需用户手动开通付费）
expires: null                  # 赠金的有效期
ends: null                     # 官方公布的活动或服务截止日期；过了这天自动显示为已下线
ended: null                    # 免费活动已下线的日期：条目保留并标注“已下线”，不删除、不下架

onboarding:
  level: L3                    # L1 / L2 / L3
  key_page: https://openrouter.ai/keys
  key_pattern: "^sk-or-v1-"
  quota_api: GET https://openrouter.ai/api/v1/key
  oauth:
    authorize_url: https://openrouter.ai/auth
    token_url: https://openrouter.ai/api/v1/auth/keys
    pkce: S256
    loopback: true             # 允许回调到 127.0.0.1 任意端口
    docs: https://openrouter.ai/docs/use-cases/oauth-pkce

terms:                         # 条款要点，每条附链接
  - point: "禁止同一人开多个账号"
    url: https://openrouter.ai/terms
partner:
  contact: null                # 合作联系方式
sources: []                    # 引用的其他清单
```
