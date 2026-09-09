# 浏览器与 Burp MCP 显式调用手册

本手册供 WZ/XCX 单目标流程和单阶段推进统一使用。它解决两个常见错误：已有抓包时先索要 HAR，以及需要页面时猜测不存在的“Firefox MCP”。`browser-firefox`/`browser-edge` 是浏览器角色标签，不是项目内可猜测的 MCP 工具名。

## 1. 先做工具决策，不要先问用户要包

出现任一条件时，先按本手册执行，不得先要求用户重新提供 HAR/XML/TXT/cURL：

- 操作者明确说已经登录、点击页面/小程序并在 Burp 抓包；
- 当前 phase 需要认证态、动态页面、XHR/API、路由或业务状态；
- 需要验证当前授权页面是否可达。

固定顺序：

```text
读取当前 scope/target-model/phase
  ↓
Burp MCP list
  ↓
list 成功：查询只读 HTTP history
  ↓
按精确 scheme/host/port 过滤并脱敏摘要
  ↓
命中：继续当前 phase；不命中：记录状态并保留人工队列
```

HAR/XML/TXT/cURL 只能在以下情况请求或使用：

1. `list` 明确失败，确认 Burp/扩展/9876 后最多重试一次仍失败；或
2. 操作者明确说明本机没有可用 Burp history。

`not_found` 或 `host_mismatch` 不是“缺包”，不得直接要求重新导出包；应记录该状态并继续可做的离线/人工队列工作。

## 2. Burp MCP：固定命令

Burp 必须打开，且启用 PortSwigger MCP Server 扩展，监听 `127.0.0.1:9876`。先执行：

```bash
npx -y mcporter@0.9.0 list http://127.0.0.1:9876 --allow-http
```

`list` 成功后，只选择列表中实际存在的只读历史工具。通常是：

```bash
npx -y mcporter@0.9.0 call get_proxy_http_history \
  --http-url http://127.0.0.1:9876 --allow-http \
  "count=60" "offset=0" --output json
```

按脱敏路径筛选时：

```bash
npx -y mcporter@0.9.0 call get_proxy_http_history_regex \
  --http-url http://127.0.0.1:9876 --allow-http \
  "count=60" "offset=0" "regex=<脱敏路径或操作名>" --output json
```

硬性要求：

- `call` 必须使用 `--http-url`，不能把 URL 当位置参数；
- 参数必须是 `key=value`；
- 保留 `--allow-http` 和 `--output json`；
- 不猜工具名，先 `list`；
- 只读取 URL/path/method/状态码/字段名结构；Cookie、Authorization、JWT、请求体和响应值不进入对话或普通产物。

Windows PowerShell 重定向可能产生 UTF-16。解析落盘输出时先按 `utf-8-sig`、再按 `utf-16-le` 自适应解码；mcporter 常见返回外层 JSON 的 `content` 字符串，需先解析外层，再解析 `content`，不要把原始 history 打印到对话。

## 3. Burp 结果状态与回退

只记录以下非敏感状态：

| 状态 | 含义 | 下一步 |
|---|---|---|
| `found` | 精确 host 有相关只读 history | 继续当前 phase，使用脱敏结构 |
| `not_found` | MCP 可用但没有匹配请求 | 保留人工队列；不先索要 HAR |
| `host_mismatch` | history 存在但不属于当前精确 host/端口 | 保留 scope/归属确认队列；不扩大范围 |
| `mcp_unavailable` | list 失败或 9876 拒绝连接 | 检查 Burp/扩展/端口，最多重试一次；仍失败才请求离线材料 |
| `pending` | 信息不足或 scope 尚未确认 | 停在待确认状态，不发请求 |

写入 `auth_preflight.json` 时只写状态、时间、匹配数量（必要时）和脱敏 host；不要写原始请求、凭证或请求体。

## 4. 浏览器工具：不要编造 Firefox MCP

项目中的 `browser-firefox` / `browser-edge` 是“操作者使用的浏览器”角色标签，不是可猜测的 MCP 工具名。需要 AI 自己打开、导航、检查或操作网页时，使用项目提供的 Browser Use 入口：

```text
mcp__node_repl__js
```

不要用 shell 浏览器、curl 或虚构的 `browser-firefox.*` 工具替代；浏览器任务也不得委托给子代理。

### 4.1 每次调用都先 bootstrap

每个新的 `mcp__node_repl__js` 调用都是新 JavaScript 内核，必须重新执行以下 bootstrap；插件根目录只能从环境变量取得：

```js
const browserPluginRoot =
  process.env.ZCODE_PLUGIN_ROOT ?? process.env.CLAUDE_PLUGIN_ROOT;
if (!browserPluginRoot) {
  throw new Error("Browser plugin root is unavailable in the node_repl host");
}
const { join } = await import("node:path");
const { pathToFileURL } = await import("node:url");
const browserClientUrl = pathToFileURL(
  join(browserPluginRoot, "scripts", "browser-client.mjs"),
).href;
const { setupBrowserRuntime } = await import(browserClientUrl);
await setupBrowserRuntime({ globals: globalThis });
```

### 4.2 选择浏览器和页面

先检查可用后端和全部 tab，不要凭记忆选第一个 tab：

```js
const available = await agent.browsers.list();
nodeRepl.write(available);
```

有目标 URL 且未指定后端时：

```js
const browser = await agent.browsers.getForUrl("https://<当前已授权目标>/");
nodeRepl.write(await browser.documentation());
```

每个逻辑操作批次先单独列出 tabs：

```js
const tabs = await browser.tabs.list();
nodeRepl.write(tabs);
```

下一次调用中，按已验证的 `id`、URL 或标题选择 tab；不要使用 `[0]`、`at(-1)` 或记忆中的 tab id。如果没有匹配的受控 tab，再检查 `browser.user.openTabs()`，最后才新建 tab。

### 4.3 打开和检查页面

用户明确给出或当前 scope/target-model 已验证的 URL 才能导航：

```js
const tab = await agent.browsers.open("https://<已验证目标 URL>/");
await tab.playwright.waitForLoadState({ state: "domcontentloaded" });
nodeRepl.write(await tab.playwright.domSnapshot());
```

只需读页面时优先 `domSnapshot()`；只有布局、Canvas 或用户要求视觉证据时才截图。点击/填写前必须从最新 snapshot 获取事实，操作后重新读取最小必要状态；不要猜 selector、路径、ID 或查询参数。

若需要人工已登录页面，先从 `browser.tabs.list()` / `browser.user.openTabs()` 找到并验证目标 tab，再 `tabs.get(id)`，不要新建页面破坏已有登录态。

## 5. 何时调用浏览器、何时停止

应调用浏览器：

- 当前 phase 需要页面当前 DOM、登录后路由或可见业务状态；
- 用户要求打开/检查明确的授权 URL；
- Burp history 无匹配，但需要确认授权页面入口是否可达，且 URL 已由用户或 scope 提供。

不应调用浏览器：

- 只需读取已有离线材料或已脱敏 Burp 元数据；
- URL/host 尚未完成 scope/归属确认；
- 动作涉及登录凭证输入、写入、上传、导出、支付、删除、命令执行或利用，且没有对应审批；
- 页面打开失败后想通过猜测多个路径、ID 或参数继续探测。

## 6. 失败记录模板

将故障写入当前 engagement 的 `notes/operator_tasks.md`，不把它笼统写成“请提供某某包”：

```text
- task_id: MCP-<phase>-<timestamp>
  source_phase: <当前 phase>
  status: pending | blocked | completed
  component: burp_mcp | browser_use
  result: mcp_unavailable | not_found | host_mismatch | browser_unavailable | page_open_failed
  verified_target: <脱敏 scheme/host/port 或 URL>
  action_taken: <list/history/bootstrap/navigation/snapshot>
  retry: 0 | 1
  unlocks: <完成后解锁的 phase 或复核动作>
  sensitive_values: omitted
```

只有 Burp `mcp_unavailable` 重试一次仍失败，或操作者明确没有 history，才把 HAR/XML/TXT/cURL 作为 operator task 的下一步输入。
