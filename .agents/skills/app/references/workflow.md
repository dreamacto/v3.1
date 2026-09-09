# Mobile app assessment workflow

## Contents

1. Intake routing
2. Initial decoding and package analysis
3. Static analysis
4. Dynamic analysis
5. Backend and business testing
6. Validation and closure
7. Resume logic

每个阶段按「目的 / 输入 / 步骤 / 分支 / 工件 / 红线 / MASTG 锚点」展开；阶段名与 `phase_status.app.json`
种子（施工方案附录 B，33 阶段）逐一对应。MASTG 锚点引用 OWASP MASTG v2 原子测试
（mas.owasp.org/MASTG/tests/，路径形态 `<android|ios>/MASVS-<域>/MASTG-TEST-XXXX/`）。

## 1. Intake routing

| Input | First action | Limitation until more evidence exists |
|---|---|---|
| APK file | Hash and preserve the original, analyze a copy; decode manifest/resources (apktool) and dex (jadx) | Static evidence does not prove runtime behavior |
| XAPK / APKS / split bundle | Unpack the container locally, inventory every split APK, analyze base + config splits as one logical app | Missing splits make manifest/component conclusions partial |
| IPA file | Hash, check FairPlay cryptid before promising source recovery | Encrypted material is `blocked(ios_fairplay_encrypted)`, never silently `not_applicable` |
| Package name | Record identity; require operator-supplied material or distribution source before package claims | A name alone proves no package/traffic coverage |
| Market link / distribution page | Record channel, version, and developer clues locally | A link does not prove material authenticity |
| Unpacked directory | Record provenance and hash manifest, index into source map | Cannot assume it matches the deployed version |
| Traffic export (HAR/XML/TXT/cURL) | Redact at ingestion, decode hosts/paths/sessions/timing | Traffic covers only journeys executed on the capture device |
| Device cache / backup directory | Inventory and hash files, map to identity | Separate unrelated apps and stale versions |

Use the user-supplied app input as the initial authorization basis. Record that basis and the identity
state, but do not pause to ask for separate proof of the original target. Continue useful offline
analysis while waiting for a designated device, accounts, backend confirmation, or narrow approval.

### authorization

- 目的：把"用户提供的初始目标"固化为授权依据，无需用户二次证明。
- 输入：操作员提供的任一入口材料（APK/IPA/XAPK/包名/市场链接/解包目录/流量）与可选授权引用。
- 步骤：init 种子即 complete；记录 basis（默认 `user_supplied_initial_target`）、测试窗口、指定设备、
  允许/禁止动作到 `engagement.json`。
- 分支：无。
- 工件：`engagement.json`。
- 红线：授权引用只登记不外传；范围外材料立即上报并停止接触。
- MASTG：无（流程阶段）。

### identity

- 目的：建立应用身份与分发事实。
- 输入：包材料 manifest、市场页线索、操作者提供的名称/版本/运营者。
- 步骤：提取应用名、包名（`com.*` 形态）、versionName/versionCode、签名/证书指纹（SHA-256）、分发渠道、
  开发者/备案线索； ambiguity 显式标注 `identity_status`。
- 分支：无。
- 工件：`app.json`。
- 红线：身份不明保持 pending，不阻塞离线分析；不因包内字符串自动扩大 scope。
- MASTG：无（工程阶段）。

### platform_identification

- 目的：确定 android / ios / dual / other，避免把 Android 假设强加 iOS。
- 输入：材料后缀与内容（apk/ipa/xapk/apks）、manifest 形态（AndroidManifest.xml vs Info.plist）。
- 步骤：按输入自动分类；dual 平台两侧材料分别登记。
- 分支：无。
- 工件：`app.json`（platform 字段）。
- 红线：平台不确定时按材料事实记录 `other`，不猜测。
- MASTG：无（工程阶段）。

### material_acquisition

- 目的：登记全部素材及来源，保证可追溯。
- 输入：任何包文件、解包目录、流量文件、设备缓存/备份。
- 步骤：每个素材算 sha256；原始包只留 `materials/original/` 受限目录，分析用副本入 `materials/working/`；
  每行记 material_id/platform/type/path/sha256/provenance/analysis_status。
- 分支：无。
- 工件：`materials.csv`。
- 红线：不下载范围外样本；操作者提供材料登记 provenance；不把素材内容粘贴进对话。
- MASTG：无（工程阶段）。

## 2. Initial decoding and package analysis

**标准工具链（registry active 受管工具，禁止临时手写解包脚本；详见
[package-analysis.md](package-analysis.md)）：**

| Step | Command | Purpose |
|---|---|---|
| 1. manifest/资源解码 | `java -jar tools/managed/app/apktool/3.0.3/apktool_3.0.3.jar d -f -o <ws>/artifacts/app/apktool/<pkg> <material.apk>` | AndroidManifest + 资源 + smali |
| 2. dex→java 反编译 | `tools/managed/app/jadx/1.5.6/bin/jadx.bat -d <ws>/artifacts/app/unpacked/<pkg> --deobf-min 3 --deobf-max 9 <material.apk>` | 可读 java 源码树 |
| 3. 白盒 sink 扫描 | `.venv/Scripts/python.exe whitebox_triage.py --source-dir <ws>/artifacts/app/unpacked/<pkg> --out-dir <ws>/artifacts/whitebox --scan` | 62 条 sink 模式扫描 |

子进程纪律：超时默认 600s/包、输出行数上限、stderr 落 `logs/`、失败写
`artifacts/decoding-ledger.csv`（failed + 原因），不静默。同引擎重跑与备用路径重试都记 ledger；
解包产物一律过 `artifacts/source-map.csv` 溯源（无溯源的提取不是证据）。

### initial_decoding

- 目的：对每个输入自动分类并留下解码台账。
- 输入：`materials.csv` 全部素材。
- 步骤：按后缀/内容识别 8 类输入（apk/ipa/xapk/apks/链接/目录/流量导出/缓存目录）；每类走对应本地
  解码路径；成功/部分恢复/失败全部落 ledger。
- 分支：无。
- 工件：`artifacts/decoding-ledger.csv`。
- 红线：全离线；解码不接触任何目标服务。
- MASTG：无（工程阶段）。

### preflight

- 目的：工具与设备可用性预登记，明确能力边界。
- 输入：受管工具目录、系统 java、操作者声明的设备。
- 步骤：检查 jadx/apktool/java 可用性与版本（`--version` 实测）；设备可用性只登记不连接；
  缺失能力记 `unavailable`。
- 分支：无。
- 工件：`notes/runtime-inventory.md`。
- 红线：缺工具不临时下载替代；frida/objection 等保持 unavailable 直到操作者放置并报备。
- MASTG：无（工程阶段）。

### package_inventory

- 目的：为每个包建立结构清单与加固识别。
- 输入：包文件与解包产物。
- 步骤：统计 dex 数量、`lib/<abi>/` so 列表、assets、split/xapk 组成；按加固特征表
  （[package-analysis.md](package-analysis.md)）匹配 `libjiagu`/`libDexHelper`/`libexecmain`/`libshella`
  等特征 so；iOS 检查 FairPlay encrypted 标志。
- 分支：无。
- 工件：`artifacts/app/package-inventory.csv`。
- 红线：加固识别=signal，不构成结论；特征 so 匹配用 contains/前缀（带版本号文件名不全名等值）。
- MASTG：无（清单阶段；壳识别属 RESILIENCE 观察，见 package_integrity_hardening_review）。

### package_unpack_decompile

- 目的：apktool（资源+manifest）+ jadx（dex→java）产出可分析源码树。
- 输入：`package-inventory.csv` 中的包材料副本。
- 步骤：按标准工具链逐包执行；iOS 未加密 ipa 提取 Info.plist/class-dump 字符串；解包失败先同引擎重试
  再走备用，仍失败记 blocked；每个产物行入 `source-map.csv`。
- 分支：无。
- 工件：`artifacts/app/apktool/<pkg>/`、`artifacts/app/unpacked/<pkg>/`。
- 红线：**壳包 → blocked + 操作者决策，不自动脱壳**（审批门 `app_hardened_unpack`）；FairPlay 加密 ipa →
  `blocked(ios_fairplay_encrypted)`；解包失败不能写成 not_applicable。
- MASTG：无（工程阶段；解包是后续所有 MASTG 静态测试的前置）。

### source_reconstruction

- 目的：建立源码索引并深解析 manifest。
- 输入：解包产物。
- 步骤：`source-map.csv` 逐文件映射来源；AndroidManifest 深解析（权限、exported 组件、intent-filter、
  allowBackup、debuggable、networkSecurityConfig、cleartext）；记录未还原/加密/动态加载区域（负空间）。
- 分支：无。
- 工件：`artifacts/source-map.csv`。
- 红线：不得在 strings/URL 提取后就宣布静态分析完成；未还原区域必须显式记录。
- MASTG：CODE 域前置（MASTG-TEST-0025 注入缺陷、MASTG-TEST-0042 三方库弱点 / MASTG-TEST-0079 对象持久化、
  MASTG-TEST-0086 内存破坏）。

### package_integrity_hardening_review

- 目的：MASVS-RESILIENCE 域观察：包完整性、加固/混淆、调试暴露、更新信任——只观察不绕过。
- 输入：解包产物、签名信息、清单证据。
- 步骤：按分支逐项记录观察，输出 review JSON（契约 `app_storage_package_schema`）。
- 分支：`package_version_inventory` / `signing_integrity` / `hardening_obfuscation_markers` /
  `debug_switches` / `debug_info_exposure` / `update_endpoint_environment`（热更新/dex.zip 下载源）/
  `trusted_update_config`。
- 工件：`artifacts/app/package/hardening-review.json`。
- 红线：**只观察记录，任何绕过=审批门**（`device_instrumentation`）；永不重打包/篡改/重签名
  （`APP_NO_REPACKING_RULE`）。
- MASTG：RESILIENCE——MASTG-TEST-0045 root 检测、MASTG-TEST-0051 混淆（Android）；
  MASTG-TEST-0088 越狱检测、MASTG-TEST-0093 混淆（iOS）。

## 3. Static analysis

### static_analysis

- 目的：从恢复源码提取 secrets、第三方 SDK 与 API 面，并把 sink 交给白盒库。
- 输入：`artifacts/app/unpacked/<pkg>/`、manifest 深解析结果。
- 步骤：secrets 模式扫描（复用现有 secret 逻辑 + app 特征：云 AK/SK、jpush/umeng/maps key）；第三方 SDK
  清单及域名提取；API 路径提取；白盒 sink 复用 `whitebox_triage.py --scan`（62 条库）。
- 分支：无（secrets/crypto 归属 crypto_and_secret_handling，避免双计）。
- 工件：`artifacts/whitebox/`、secrets/SDK 清单（notes 或 artifacts 内结构化文件）。
- 红线：**secret_candidate 红线**——未证实有效性的密钥串只是 signal，不做 key 有效性探测、不发请求。
- MASTG：CODE——MASTG-TEST-0025、MASTG-TEST-0042 / MASTG-TEST-0079、MASTG-TEST-0086。

### endpoint_inventory

- 目的：建立 client 端静态端点基线。
- 输入：static_analysis 产物、流量导入。
- 步骤：URL/域名/相对路径/方法（可推断时）/参数名/对象 ID 字段/认证标记逐条入 CSV。
- 分支：无。
- 工件：`endpoints.csv`。
- 红线：静态发现只登记不验证；归属未确认 host 不发请求。
- MASTG：无（清单阶段，NETWORK 域观察在 dynamic_mapping）。

### host_classification

- 目的：host 归属与 scope 对账（对齐 wz/xcx 状态机，不新造一套）。
- 输入：`endpoints.csv` 全部 host、SDK 域名、操作者 scope 声明。
- 步骤：提取 host → `hosts.csv`；分类 own backend / third_party / CDN / platform / vendor；域级授权根域
  自动继承（`--scope-root`），精确子域/兄弟域/第三方/平台共享保持 pending。
- 分支：无。
- 工件：`hosts.csv`。
- 红线：归属未确认 = confirmation_required，禁主动请求；SDK/推送/统计端点不得误报为自有后端。
- MASTG：无（工程阶段；PRIVACY 流量归属见 third_party_sdk_platform_boundary）。

## 4. Dynamic analysis

动态阶段前提：指定测试设备已登记（dynamic_setup 完成）；无设备时动态分支保持 pending，不阻塞静态流。

### dynamic_setup（重量级）

- 目的：登记设备、代理拓扑与 CA 信任观察，建立动态分析前提。
- 输入：操作者提供的指定测试设备、Burp 代理信息。
- 步骤：登记设备型号/系统版本/是否已 root 或越狱（只观察）；代理拓扑（设备 → 本机 Burp）；用户 CA 信任
  观察与 Android 7+ networkSecurityConfig 影响记录；录屏/截图约束登记。
- 分支：无。
- 工件：`notes/safety-controls.md`（设备段）+ phase note。
- 红线：**设备改动（root/越狱、装用户 CA、装 frida-server、装测试版 APK、改系统设置）= 审批门
  （`device_instrumentation`，双钥匙）**；仅观察"设备是否已 root/pinning 是否存在"免批。
- MASTG：无（环境阶段；控制观察锚点在 dynamic_mapping）。

### dynamic_mapping（重量级）

- 目的：用户旅程 → 流量基线（结构化、无敏感值）。
- 输入：指定设备上的 App 操作 + 本机 Burp history。
- 步骤：按旅程（启动/登录/核心业务/支付沙箱/分享/更新）记录 endpoint/method/参数名/状态/结构；
  pinning/反调试/root 检测的存在性只作控制观察记录；429/5xx 退避 10s、连续 5 错停 host。
- 分支：无。
- 工件：`endpoints.csv`（动态行）+ phase note。
- 红线：**SSL pinning bypass、frida 注入 = 审批门**；绕过是测试技术不是漏洞结论；敏感值不落任何产物。
- MASTG：NETWORK——MASTG-TEST-0019 网络数据加密、MASTG-TEST-0242 NSC 缺少证书绑定（Android）；
  MASTG-TEST-0065 网络加密、MASTG-TEST-0068 自定义证书与 pinning（iOS）。

### static_dynamic_reconciliation

- 目的：静态端点基线与动态端点基线的纯离线对账。
- 输入：`endpoints.csv` 静态/动态行、流量导入。
- 步骤：五分支产出；每行 endpoint 落一个行级十态枚举（`static_only` / `dynamic_only` / `both_seen` /
  `feature_gated` / `stale` / `version_specific` / `third_party` / `platform_shared` / `unreachable` /
  `needs_manual_validation`）——行级枚举区别于六值 coverage substatus。
- 分支：`static_endpoint_base` / `dynamic_endpoint_base` / `match_status_classification` /
  `hidden_flow_identification` / `stale_entry_disposition`。
- 工件：`artifacts/app/reconciliation/static-dynamic-endpoints.csv`（契约 `app_reconciliation_schema`）。
- 红线：纯离线对账，永不发"验证"请求（尤其 unreachable/stale 行）；stale/unreachable 不上报为活问题；
  `dynamic_only`/`feature_gated` 行记为隐藏流假设。
- MASTG：无（工程对账阶段）。

## 5. Backend and business testing

### platform_login_exchange

- 目的：App 语境平台登录交换复核（OAuth code、一键登录、token 保管、UID 授权依据）。
- 输入：操作者提供的认证材料、本地流量、恢复源码中的登录代码路径。
- 步骤：五分支逐项记录观察，输出 review JSON（契约 `app_auth_schema`）。
- 分支：`oauth_code_one_time` / `oauth_code_expiry` / `one_click_login_device_binding` /
  `access_token_custody` / `uid_authorization_basis`。
- 工件：`artifacts/app/auth/platform-login-review.json`。
- 红线：只分析操作者提供材料/本地流量；运营商一键登录 token、device-id 属凭证纪律；公开标识符不是授权。
- MASTG：AUTH——MASTG-TEST-0017 Confirm Credentials、MASTG-TEST-0018 生物识别（Android）；
  MASTG-TEST-0064 生物识别（iOS）。

### session_token_lifecycle

- 目的：服务端 session/token 生命周期复核。
- 输入：同上。
- 步骤：五分支逐项记录观察，输出 review JSON。
- 分支：`token_rotation` / `token_revocation_logout` / `multi_device_login` / `stale_token_new_api` /
  `device_user_tenant_binding`。
- 工件：`artifacts/app/auth/session-lifecycle-review.json`。
- 红线：不自动登录/签发/吊销；写动作走审批门。
- MASTG：AUTH——同 platform_login_exchange 锚点。

### signature_replay

- 目的：请求签名与重放假设的离线复核。
- 输入：同上。
- 步骤：四分支逐项记录观察，输出 review JSON。
- 分支：`nonce_timestamp` / `signature_canonicalization` / `replay_window` / `binding_scope`。
- 工件：`artifacts/app/auth/signature-replay-review.json`。
- 红线：**永不自动重放任何请求（含读）**；写与并发验证=审批门。
- MASTG：AUTH——同上；CRYPTO 侧随机数锚点见 crypto_and_secret_handling。

### backend_web_api_testing

- 目的：对确认归属且 in_scope 的自有后端做与 WZ 同构的 API 测试。
- 输入：`hosts.csv`（own backend + in_scope）、`endpoints.csv`。
- 步骤：endpoint-role-object 矩阵；低速只读请求（同 host 串行、间隔≥2s、退避规则同 ROE）。
- 分支：无。
- 工件：phase note + `review_ledger.csv` 候选行。
- 红线：写/导出/下载/支付=审批门；未确认归属 host 不发请求。
- MASTG：NETWORK——MASTG-TEST-0019 / MASTG-TEST-0065（传输观察）。

### access_control_testing

- 目的：只读 IDOR 差分。
- 输入：≥2 套授权会话（同 host）。
- 步骤：语义复用 `idor_triage.py`（同 host ≥2 凭证、GET/HEAD、delay≥3s、每 host≤5 端点、A 凭证
  401/302 即停）；一次只改一个标识符或角色维度；用合成记录。
- 分支：无。
- 工件：`review_ledger.csv` 候选行。
- 红线：授权会话不足记 blocked；不访问/留存真实他人数据。
- MASTG：PLATFORM/AUTH 边界观察（对象授权语义），锚点同 AUTH。

### input_file_testing

- 目的：注入/上传面候选筛查（only 筛查，不自动探测写型参数）。
- 输入：白盒 sink 候选、端点参数。
- 步骤：复用 wz `input_testing` 编排语义做候选筛查；按 data-to-test-playbook 选 payload 族。
- 分支：无。
- 工件：`review_ledger.csv` 候选行。
- 红线：不自动探测写型参数；marker/盲注类探测按 ROE 3.1 免批清单约束。
- MASTG：CODE——MASTG-TEST-0025（注入缺陷）。

### business_logic_testing

- 目的：业务状态机建模与逻辑假设产出。
- 输入：流量序列、端点语义。
- 步骤：复用 logic-workshop 状态机产物语义；只重建模型不发并发请求。
- 分支：无。
- 工件：phase note + 假设清单。
- 红线：真实支付/影响他人=禁止；并发验证走竞态审批门。
- MASTG：无（业务逻辑域，MASTG 不直接覆盖）。

### local_data_exposure

- 目的：本地存储暴露面复核（token 持久化、登出清理、缓存/数据库、日志/剪贴板/截屏、临时文件）。
- 输入：操作者授权材料（设备缓存/备份/拉取文件）、恢复源码存储代码路径。
- 步骤：五分支逐项记录观察，输出 review JSON（契约 `app_storage_package_schema`）；行内 `platform` 列
  区分 android（shared_prefs/db/allowBackup 提取面）/ ios（keychain/plist/快照）。
- 分支：`token_persistence` / `logout_cleanup` / `local_cache_database` / `logs_clipboard_screenshots` /
  `temp_files`。
- 工件：`artifacts/app/storage/local-data-review.json`。
- 红线：只用操作者授权材料与指定测试设备；敏感值不进任何产物。
- MASTG：STORAGE——MASTG-TEST-0001 本地存储敏感数据、MASTG-TEST-0200 外部存储写入（Android）；
  MASTG-TEST-0052 本地数据存储、MASTG-TEST-0058 备份敏感数据（iOS）。

### crypto_and_secret_handling

- 目的：密码学与密钥处理复核。
- 输入：恢复源码 crypto 代码路径、secrets 模式命中。
- 步骤：四分支逐项记录观察，输出 review JSON（契约 `app_storage_package_schema`）。
- 分支：`hardcoded_secrets` / `custom_crypto` / `weak_random_key_derivation` / `debug_config_env_keys`。
- 工件：`artifacts/app/crypto/secret-review.json`。
- 红线：**secret_candidate 红线**：未证实有效性只是线索；不做 key 有效性探测、不发请求。
- MASTG：CRYPTO——MASTG-TEST-0013 对称加密、MASTG-TEST-0208 密钥长度不足（Android）；
  MASTG-TEST-0061 算法配置、MASTG-TEST-0063 随机数（iOS）。

### webview_bridge_links

- 目的：WebView/JS 桥/深链边界复核。
- 输入：恢复源码 WebView 代码路径、manifest intent-filter、流量。
- 步骤：七分支一行一分支；三 CSV 清单落盘（契约 `app_webview_schema`）。
- 分支：`webview_allowed_domains` / `postmessage_origin` / `cookie_token_sharing_boundary` /
  `bridge_method_exposure` / `custom_scheme` / `deep_link_sensitive_params` / `external_app_browser_jump`。
- 工件：`artifacts/app/webview/webview-origin-inventory.csv`、
  `artifacts/app/webview/bridge-method-inventory.csv`、`artifacts/app/webview/deep-link-review-queue.csv`。
- 红线：不注入/不重放 cookie/token，不从 deeplink 启动外部应用；cookie/token 共享按 origin 记录状态。
- MASTG：PLATFORM——MASTG-TEST-0028 Deep Links、MASTG-TEST-0031 WebView JS 执行（Android）；
  MASTG-TEST-0075 自定义 URL Scheme、MASTG-TEST-0076 iOS WebViews（iOS）。

### ipc_component_boundary

- 目的：App 特有 IPC/exported 组件边界复核（静态清单离线完成）。
- 输入：AndroidManifest 组件声明（exported/activity/service/receiver/provider）、intent-filter scheme、
  iOS extension 声明。
- 步骤：七分支逐项记录；组件清单与深链复核队列两 CSV 落盘（契约 `app_ipc_schema`）。
- 分支：`exported_activity` / `exported_service` / `exported_receiver` / `exported_provider` /
  `custom_scheme_deeplink` / `universal_link` / `ios_extension_boundary`。
- 工件：`artifacts/app/ipc/component-inventory.csv`、`artifacts/app/ipc/deeplink-review-queue.csv`。
- 红线：**实际触发写组件的 intent/deeplink = 审批门**；静态清单不等于可利用证明（exported 存在只是
  signal）。
- MASTG：PLATFORM——MASTG-TEST-0028 / MASTG-TEST-0075（深链与 scheme）。

### cloud_function_testing

- 目的：云函数调用边界复核（多数 App = not_applicable，必须带理由）。
- 输入：SDK 配置、流量中的云调用。
- 步骤：三分支逐项记录观察，输出 review JSON（契约 `app_cloud_schema`）。
- 分支：`anonymous_invocation` / `function_parameter_role_validation` / `cloud_env_id_mixing`。
- 工件：`artifacts/app/cloud/cloud-function-review.json`。
- 红线：只做最小只读验证，不触发写型函数。
- MASTG：无独立锚点（云面按 AUTH/NETWORK 语义观察）。

### cloud_storage_acl_testing

- 目的：对象存储与云数据库访问控制复核。
- 输入：signed URL 样本（脱敏结构）、SDK 配置。
- 步骤：三分支逐项记录观察，输出 review JSON。
- 分支：`cloud_database_rules` / `object_storage_acl` / `signed_url_binding`。
- 工件：`artifacts/app/cloud/object-storage-review.json`。
- 红线：不批量读对象、不下载对象内容。
- MASTG：无独立锚点（存储 ACL 按边界语义观察）。

### third_party_sdk_platform_boundary

- 目的：第三方 SDK 数据流与平台共享资产归属复核。
- 输入：SDK 清单及域名、流量、`hosts.csv` 分类。
- 步骤：两分支逐项记录；边界 CSV 行归属对齐 hosts.csv 分类状态。
- 分支：`third_party_service_boundary` / `platform_shared_asset_attribution`。
- 工件：`artifacts/app/cloud/third-party-boundary.csv`。
- 红线：不触发真实支付；平台共享资产不得误报为自有资产。
- MASTG：PRIVACY——MASTG-TEST-0206 流量中未声明 PII、MASTG-TEST-0254 危险权限（Android）；
  MASTG-TEST-0281 未声明跟踪域名（iOS）。

## 6. Validation and closure

### candidate_validation

- 目的：把候选变成可辩护结论（或被否决）。
- 输入：`review_ledger.csv` 全部 active 候选。
- 步骤：每个候选先记录假设/预期行为/最小证明/负控/停止条件/审批需求/cleanup，全部就绪才允许验证；
  结论按 SKILL 顶部 AI 结论模板 + 四问否决组织。
- 分支：无。
- 工件：phase note + ledger disposition 更新。
- 红线：confirmed 仍写 `needs_manual_validation`，人工终审门不可越；细微发现处置清单见 SKILL 顶部。
- MASTG：无（流程阶段）。

### reporting

- 目的：产出最终报告（无可报告成果时 = not_applicable）。
- 输入：confirmed/accepted findings、证据索引。
- 步骤：按 [artifact-contract.md](artifact-contract.md) 报告契约与 [evidence-reporting.md](evidence-reporting.md)
  规范生成 DOCX 与 final-report.md 工作稿。
- 分支：无。
- 工件：`reports/攻防成果报告_<engagement>_<日期>.docx`、`reports/final-report.md`。
- 红线：人工终审门不可越；截图由人工插入，生成器禁写清单见契约。
- MASTG：无（流程阶段）。

### cleanup

- 目的：清理测试残留。
- 输入：测试账号/对象/文件/会话/设备改动登记。
- 步骤：逐项清理并记录；设备改动（证书/应用/设置）恢复确认。
- 分支：无。
- 工件：cleanup 记录（phase note / operator_tasks 闭环）。
- 红线：未清理不得闭合；无法清理项显式登记交操作者。
- MASTG：无（流程阶段）。

## 7. Resume logic

1. Read `engagement.json`, `app.json`, `materials.csv`, `hosts.csv`, `endpoints.csv`,
   `phase_status.app.json`, and `review_ledger.csv`.
2. Verify that the identity, platform, and material hashes still match; do not reopen authorization for
   the original user-supplied target.
3. Resume the first incomplete applicable phase without overwriting originals or human dispositions.
4. Revalidate in-scope hosts, test-account validity, and designated-device status before dynamic or
   backend requests.
5. Record version drift. Analyze a new package/version as a new material, not as a silent replacement.
