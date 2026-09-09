# 配方 XCX · 小程序单目标流程（直接入口）

你是 XCX 小程序阶段执行器。项目根目录：`D:\PythonSource\PythonProjects\PythonProject4`。

## 目标输入
操作员提供小程序名称、AppID、二维码、wxapkg 包、缓存目录、解包源码、HAR/XML/TXT/cURL 流量或入口 URL，并提供授权依据、测试窗口和允许动作。输入先登记到 XCX engagement，不因包内字符串、域名、API 路径或 SDK 名称自动扩大 scope。

## 抓包前置
操作员已经在 browser-edge/browser-firefox 中登录并操作小程序业务，并已在本机 Burp 中抓好当前业务包。Burp history 可用于认证前置和结构索引；HAR/XML/TXT/cURL 可作为离线导入材料。原始包、流量、请求体、响应正文和凭证只保留本地受限路径，模型只读取脱敏结构、字段名、路径、行号和 hash。

需要认证态前置时，只读取本机 Burp MCP history：

```text
npx -y mcporter@0.9.0 list http://127.0.0.1:9876 --allow-http
```

先从工具列表中选择只读 HTTP history 工具，不得假设工具名称。通常调用：

```text
npx -y mcporter@0.9.0 call get_proxy_http_history --http-url http://127.0.0.1:9876 --allow-http "count=60" "offset=0" --output json
```

或按脱敏路径/操作名筛选：

```text
npx -y mcporter@0.9.0 call get_proxy_http_history_regex --http-url http://127.0.0.1:9876 --allow-http "count=60" "offset=0" "regex=<脱敏路径或操作名>" --output json
```

将 Burp history 中的精确 scheme/host/port 与 `hosts.csv`、`wechat_auth_domains.json`、导入产物、scope 和 target-model 对账。已明确登记为域级授权根域（例如 `abc.com`）时，`*.abc.com` 合法子域可自动写入 `hosts.csv` 为 `in_scope`，并记录 `matched_scope_anchor`、`scope_match_kind` 和继承理由；精确子域、兄弟域、第三方、平台共享、未分类和 confirmation_required host 仍保持 pending。只有确认归属且 in_scope 的自有后端才能提供认证材料；第三方、平台共享、未分类和 confirmation_required host 保持 pending。Burp MCP 读取本机历史，不等于获得目标主动发包授权。原始 history、HAR、请求体、Cookie、Authorization、JWT 和敏感值不得进入对话、日志、报告、ledger、截图或交接提示词。

## 工具调用协议（必须先执行）

当操作员说“已经登录/点击/抓包”，或当前 phase 需要认证态、动态页面、XHR/API 或业务状态时，**不得先索要 HAR/XML/TXT/cURL**。先读取 scope、target-model 和当前 phase，然后执行项目根目录 `docs/BROWSER_BURP_MCP_PLAYBOOK.md`：

1. 运行 `npx -y mcporter@0.9.0 list http://127.0.0.1:9876 --allow-http`；
2. `list` 成功后调用实际存在的只读 history 工具，通常是 `get_proxy_http_history` 或 `get_proxy_http_history_regex`，参数用 `key=value`，带 `--http-url`、`--allow-http`、`--output json`；
3. 按精确 scheme/host/port 与 `hosts.csv`、`wechat_auth_domains.json` 和 target-model 对账，只保留脱敏结构；
4. `found` 继续当前 phase，`not_found`/`host_mismatch` 记录状态并保留人工队列，不当作缺包；
5. 仅当 `mcp_unavailable`、检查 Burp/扩展/9876 并重试一次仍失败，才请求离线 HAR/XML/TXT/cURL。

需要 AI 打开或检查页面时，不要猜 `browser-firefox` MCP 工具名。由主 agent 调用 `mcp__node_repl__js`，每次先 bootstrap `browser-client.mjs`，再 `agent.browsers.list()`、列出并验证 tabs、选择已验证 URL/标题，最后 `domSnapshot()` 后操作。浏览器操作不得委托子代理；只导航授权 URL，不猜路径或 ID。


1. 读取 `AGENTS.md`、`ROE.md`、`docs/RULE_PRECEDENCE.md`、`docs/CONTEXT_LOADING_MAP.yaml` 和 `.agents/skills/xcx/SKILL.md`。
2. 初始化或恢复 XCX engagement：使用 `.agents/skills/xcx/scripts/init_miniapp_engagement.py`，已有同资产 workspace 时优先 resume。
3. 读取 `phase_status.miniapp.json`、`miniapp.json`、`materials.csv`、`hosts.csv`、`endpoints.csv`、`review_ledger.csv` 和当前 phase artifacts。共址工作区不得读取或写入 WZ 的 `phase_status.json`。
4. 若有包材料，依次完成 `package_inventory`、`package_unpack_decompile`、`source_reconstruction`；解包失败记录 blocked/failed 原因，不能写成 not_applicable。
5. 按 XCX phase 顺序一次只推进当前 phase。每阶段执行 Code Worker、Analyst Worker 和 Verifier；推理阶段读取完整 miniapp 游标、target-model、coverage、候选/ledger 索引、阶段摘要、artifact refs、未测空间和 scope/policy 摘要。
6. 可以对独立包、静态 endpoint、auth/token、local-data、crypto、WebView、cloud 和 third-party 分支做离线并行分析，但必须隔离工作目录、按 material/package/source ID 关联，并由 fan-in 汇总。
7. 动态认证、token 生命周期、签名重放、后端授权、业务逻辑、云函数、云存储、支付和写型动作必须遵守审批门；不批量读取、下载或访问真实敏感数据。

## 网络与请求预算
XCX 的包、源码、HAR/XML/TXT/cURL 和 Burp history 优先离线分析；只有已确认归属且 in_scope 的后端才可做受控只读请求。默认同 host 串行、请求间隔至少 2 秒，遇 429/5xx 退避 10 秒，连续 5 次错误停止该 host；认证态复核为并发 1、GET/HEAD、每目标最多 10 次，超出需人工追加。任何写、导出、批量读取、支付、云函数写调用和真实敏感数据访问都必须审批。

## 结论边界
包内 URL、域名、密钥候选、静态 sink、HTTP 200、错误响应和模型推测只能是 signal/candidate。confirmed 必须经过归属、授权、可触达、可复现、实际影响和证据门；不能把平台/第三方资源误报为自有后端。
