# 子域自动纳入范围改造说明

已对 WZ/XCX 的域名范围继承进行改造：默认情况下，用户提供单位下任意一个合法主机（例如 `www.example.com`）即作为该单位授权入口，系统自动推导可注册根域 `example.com`，并允许根域及其合法子域（如 `123.example.com`、`api.example.com`）。只有用户明确说明“只测该 host/指定子域”等范围限制时，才使用 exact 模式收窄。

## 安全边界

- 默认模式下，初始目标的任意合法单位 host 都会派生其注册父域并建立 `default_domain` scope profile；额外显式 `--allowed-host` 仍按 exact 记录，除非另有域级标记。
- 自动继承只发生在根域 profile 已建立且 scope 行为 `in_scope` 时。
- 自动继承只解决 scope，不会自动打开 `active_testing_authorized`，也不批准弱口令、写入、导出、利用、认证态重量级复核等动作。
- 严格使用点号边界：不匹配 `evilabc.com` 或 `abc.com.evil.com`。
- 默认不再把初始 `www.example.com` 当成只允许该 host；它会按 `default_domain` 继承 `example.com` 及合法子域。只有显式 `--scope-mode exact`（WZ）或等价的 exact scope profile 才关闭该继承。
- 第三方、平台共享、CDN、支付、身份服务和供应商 host 仍保持待确认/排除。
- WZ 写入 `scope.csv`，XCX 写入 `hosts.csv`；XCX 仍只使用 `phase_status.miniapp.json`。

## 代码改动

- `src/authorized_assessment/scope.py`：统一 host 归一化、严格后缀匹配、公共后缀保守拒绝和审计结果。
- `policy_engine.py`：域级 anchor 的子域授权及 `matched_scope_anchor`、`scope_match_kind`、`domain_authorized` 审计字段。
- `.agents/skills/wz/scripts/init_engagement.py`：WZ scope 字段、域级根域初始化和 `append_domain_authorized_subdomain()`。
- `.agents/skills/xcx/scripts/init_miniapp_engagement.py`：XCX host 字段、`--scope-root` 显式域级根域入口和 `append_domain_authorized_host()`。
- `src/authorized_assessment/miniapp/endpoint_offline.py`、`manual_search_helper.py`：移除基于最后两段标签的危险 `same_site()` 授权误判。
- `contracts/policy_decision_schema.json`：增加范围匹配审计字段。

## XCX 使用方式

初始化小程序工作区时，如果操作者已有明确域级授权，可显式指定：

```powershell
python .agents/skills/xcx/scripts/init_miniapp_engagement.py <小程序材料或入口> `
  --output <工作区> --scope-root abc.com
```

该参数只会登记 `abc.com` 为已确认的域级 backend anchor；整体 active-testing 授权仍独立受 `engagement.json`、`ROE.md` 和审批门控制。随后发现 `123.abc.com` 时，可调用 host 追加逻辑写入 `hosts.csv`。

## WZ 使用方式

WZ 裸根域输入会在 `scope.csv` 中记录域级 anchor；根域正式确认后，发现子域可以调用：

```python
append_domain_authorized_subdomain(workspace / "scope.csv", "123.abc.com")
```

函数幂等，重复调用不会重复写行；根域未确认或候选不属于根域时返回 `False`。

## 验证

已通过 35 项定向测试，覆盖统一 classifier、PolicyEngine、WZ/XCX scope 扩展、恶意相似域名、公共后缀、第三方/平台优先、CSV 兼容升级、WZ/FH 与 WZ/XCX 游标隔离。项目全量 pytest 尚未执行；当前系统 Python 没有 pytest，定向测试使用 `.venv\Scripts\python.exe`。
