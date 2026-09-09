# Mobile app test matrix (MASVS/MASTG anchors)

Use this as a coverage index. Apply only to authorized accounts, designated devices, versions, and owned
backends. Test IDs reference OWASP MASTG v2 atomic tests (mas.owasp.org/MASTG/tests/); the per-test path
form is `<android|ios>/MASVS-<domain>/MASTG-TEST-XXXX/`. 锚点取自施工方案附录 G（2026-09 目录快照），
施工时按当日目录复核。

## MASVS 八域覆盖矩阵（Android / iOS）

| MASVS 域 | 覆盖问题 | Android 锚点 | iOS 锚点 |
|---|---|---|---|
| STORAGE | 本地存储敏感数据、外部存储写入、备份提取面是否复核？ | MASTG-TEST-0001（本地存储敏感数据）、MASTG-TEST-0200（外部存储写入） | MASTG-TEST-0052（本地数据存储）、MASTG-TEST-0058（备份敏感数据） |
| CRYPTO | 硬编码密钥、算法配置、随机数、密钥长度是否复核？ | MASTG-TEST-0013（对称加密）、MASTG-TEST-0208（密钥长度不足） | MASTG-TEST-0061（算法配置）、MASTG-TEST-0063（随机数） |
| AUTH | 凭证确认、生物识别、平台登录交换是否复核？ | MASTG-TEST-0017（Confirm Credentials）、MASTG-TEST-0018（生物识别） | MASTG-TEST-0064（生物识别） |
| NETWORK | 传输加密、NSC/pinning 配置、cleartext 是否复核？ | MASTG-TEST-0019（网络数据加密）、MASTG-TEST-0242（NSC 缺少证书绑定） | MASTG-TEST-0065（网络加密）、MASTG-TEST-0068（自定义证书与 pinning） |
| PLATFORM | 深链、WebView JS 执行、URL Scheme、IPC 组件边界是否复核？ | MASTG-TEST-0028（Deep Links）、MASTG-TEST-0031（WebView JS 执行） | MASTG-TEST-0075（自定义 URL Scheme）、MASTG-TEST-0076（iOS WebViews） |
| CODE | 注入缺陷、三方库弱点、对象持久化、内存破坏是否复核？ | MASTG-TEST-0025（注入缺陷）、MASTG-TEST-0042（三方库弱点） | MASTG-TEST-0079（对象持久化）、MASTG-TEST-0086（内存破坏） |
| RESILIENCE | root/越狱检测、混淆、加固、更新信任是否只观察记录？ | MASTG-TEST-0045（root 检测）、MASTG-TEST-0051（混淆） | MASTG-TEST-0088（越狱检测）、MASTG-TEST-0093（混淆） |
| PRIVACY | 流量中未声明 PII、危险权限、跟踪域名是否复核？ | MASTG-TEST-0206（流量中未声明 PII）、MASTG-TEST-0254（危险权限） | MASTG-TEST-0281（未声明跟踪域名） |

域 → APP 阶段映射：STORAGE→local_data_exposure；CRYPTO→crypto_and_secret_handling；AUTH→
platform_login_exchange / session_token_lifecycle / signature_replay；NETWORK→backend_web_api_testing
与 dynamic_mapping（传输观察）；PLATFORM→ipc_component_boundary / webview_bridge_links；CODE→
static_analysis / source_reconstruction；RESILIENCE→package_integrity_hardening_review；PRIVACY→
third_party_sdk_platform_boundary。

## Area coverage questions

| Area | Coverage questions |
|---|---|
| Identity and provenance | Are platform, package name, name, operator, version, signing, distribution source, hash, and material-deployment match established? |
| Package inventory | Are the base package, all splits (xapk/apks), dex counts, native libs, assets, packer signatures, and failures recorded? |
| Unpack and decompile | Are supported packages actually unpacked/decompiled, expected entry files recovered, and declared components reconciled? |
| Source reconstruction | Are sources indexed, transformations recorded, manifest deep-parsed (permissions/exported/intent-filter/allowBackup/debuggable/networkSecurityConfig), and unreadable regions identified? |
| Hardening and integrity | Are signing integrity, packer/obfuscation markers, debug switches, update endpoints, and update trust reviewed as observation only? |
| Components and routes | Are activities, services, receivers, providers, exported state, schemes, universal links, and iOS extensions inventoried? |
| Embedded configuration | Are hosts, API bases, keys, identifiers, environment switches, SDK configuration, and secret patterns classified by actual privilege? |
| Local data | Are shared_prefs, databases, keychain, plist, caches, logs, clipboard, screenshots, backup extraction, and logout cleanup reviewed? |
| Cryptography | Are key origin/storage, algorithms, randomness, nonces, timestamps, signatures, replay, and canonicalization reviewed? |
| Transport | Are TLS validation, pinning, proxy behavior, cleartext, networkSecurityConfig, certificate errors, and sensitive caching reviewed? |
| Platform login | Are OAuth codes one-time/short-lived, one-click-login device binding, token custody, and UID authorization basis reviewed? |
| Session and identity | Are tokens, device IDs, tenant binding, fixation, expiry, refresh, concurrent sessions, and stale sessions reviewed? |
| Endpoint inventory | Are methods, paths, parameters, object IDs, auth, roles, state changes, versions, and cloud calls mapped? |
| Object authorization | Are cross-account, cross-tenant, owner, shared-object, export, file, and order boundaries tested with designated accounts? |
| Function authorization | Are user/admin/operator functions, hidden routes, alternate methods, role transitions, and field-level permissions tested? |
| Input and parsing | Are server-side validation, injection classes, canonicalization, parsers, and serialization surfaces reviewed? |
| Upload and download | Are extension/type/content, filename/path, overwrite, storage, retrieval authorization, and cleanup tested? |
| Server-side requests | Are URL fetches, callbacks, images, imports, redirects, and cloud metadata controls reviewed? |
| Business workflow | Are state order, replay, duplicate requests, concurrency, limits, prices, quantities, inventory, points, and entitlements tested? |
| Payment and refund | Are sandbox mode, amount source, order binding, callback verification, idempotency, and refund authorization reviewed? |
| Webview and bridge | Are allowed origins, postMessage origin control, JS bridge exposure and capability, custom schemes, deep-link parameters, external jumps, and cookie/token sharing boundaries inventoried per branch? |
| IPC components | Are exported activities/services/receivers/providers, permission-protected components, custom schemes, universal links, and iOS extension boundaries inventoried and reviewed? |
| SDKs and third parties | Are SDK permissions, data sharing, vendor endpoints, analytics, maps, push, payment, and platform plugins classified and scoped? |
| Cloud capabilities | Are cloud functions, databases, storage rules, signed URLs, environment IDs, and IAM reviewed? |
| Privacy | Are consent, unnecessary fields, identifiers, tracking domains, analytics, logs, exports, and retention reviewed without retaining data? |
| Resilience | Are rate limits, quotas, retries, offline synchronization, and duplicate handling assessed within non-disruptive bounds? |
| Detection and cleanup | Are security events logged without secrets, and are test users, objects, files, orders, tokens, and device changes removed? |

## Required dimensions

Repeat applicable rows across anonymous, new user, established user, privileged role, disabled account,
expired session, different tenant, different device, old client version, and interrupted workflow. A
rooted/jailbroken designated device is a separate dimension that exists only after the
`device_instrumentation` approval gate. Use only authorized combinations and record unavailable
dimensions as blocked or not applicable.

Test static, dynamic, backend, and business dimensions separately. Static evidence can establish
presence and reachability clues; it usually cannot establish server-side authorization or impact.

## Authentication phase substatus branches (contract: app_auth_schema)

`platform_login_exchange` / `session_token_lifecycle` / `signature_replay` each record one coverage
substatus (tested/not_applicable/blocked/approval_required/needs_manual_validation/inconclusive) per
branch in `phase_status.app.json` and write its review artifact under `artifacts/app/auth/`. A phase is
only complete with proven tested/not_applicable statuses per branch. Analyze operator-supplied material
and local traffic only; carrier one-click-login tokens and device IDs follow credential discipline.

| Phase | Substatus branches | MASTG anchors |
|---|---|---|
| platform_login_exchange | oauth_code_one_time, oauth_code_expiry, one_click_login_device_binding, access_token_custody, uid_authorization_basis | MASTG-TEST-0017 / MASTG-TEST-0018（Android）；MASTG-TEST-0064（iOS） |
| session_token_lifecycle | token_rotation, token_revocation_logout, multi_device_login, stale_token_new_api, device_user_tenant_binding | 同上（AUTH 域） |
| signature_replay | nonce_timestamp, signature_canonicalization, replay_window, binding_scope | 同上（AUTH 域；随机数侧见 CRYPTO） |

## package_integrity_hardening_review（RESILIENCE 域，contract: app_storage_package_schema）

七分支只观察记录，输出 `artifacts/app/package/hardening-review.json`。任何绕过（脱壳、反调试 patch、
pinning bypass、重打包）都是审批门 `device_instrumentation` / `app_hardened_unpack`，且绕过本身是测试
技术不是漏洞结论；`APP_NO_REPACKING_RULE` 永不重打包/篡改/重签名。

| Phase | Substatus branches | MASTG anchors |
|---|---|---|
| package_integrity_hardening_review | package_version_inventory, signing_integrity, hardening_obfuscation_markers, debug_switches, debug_info_exposure, update_endpoint_environment, trusted_update_config | MASTG-TEST-0045 / MASTG-TEST-0051（Android）；MASTG-TEST-0088 / MASTG-TEST-0093（iOS） |

## Storage and crypto phase substatus branches (contract: app_storage_package_schema)

`local_data_exposure` / `crypto_and_secret_handling` each record one coverage substatus per branch and
write its review artifact; rows carry a `platform` column distinguishing android
(shared_prefs/db/backup) from ios (keychain/plist/snapshots). A secret string without proven validity is
only a `secret_candidate` clue, never a key-leak finding.

| Phase | Substatus branches | MASTG anchors |
|---|---|---|
| local_data_exposure | token_persistence, logout_cleanup, local_cache_database, logs_clipboard_screenshots, temp_files | MASTG-TEST-0001 / MASTG-TEST-0200（Android）；MASTG-TEST-0052 / MASTG-TEST-0058（iOS） |
| crypto_and_secret_handling | hardcoded_secrets, custom_crypto, weak_random_key_derivation, debug_config_env_keys | MASTG-TEST-0013 / MASTG-TEST-0208（Android）；MASTG-TEST-0061 / MASTG-TEST-0063（iOS） |

## ipc_component_boundary（PLATFORM 域，contract: app_ipc_schema）

App 特有阶段：exported 组件与入口面边界的静态清单复核，输出
`artifacts/app/ipc/component-inventory.csv` 与 `artifacts/app/ipc/deeplink-review-queue.csv`。静态清单
离线完成；实际触发任何写组件的 intent/deeplink = 审批门。exported 组件存在本身只是 signal。

| Phase | Substatus branches | MASTG anchors |
|---|---|---|
| ipc_component_boundary | exported_activity, exported_service, exported_receiver, exported_provider, custom_scheme_deeplink, universal_link, ios_extension_boundary | MASTG-TEST-0028（Android）；MASTG-TEST-0075（iOS） |

## Webview bridge substatus branches (contract: app_webview_schema)

七分支一行一分支，三 CSV 清单（webview-origin / bridge-method / deep-link review queue）落在
`artifacts/app/webview/`；不注入/不重放 cookie/token，不从 deeplink 启动外部应用。

| Phase | Substatus branches | MASTG anchors |
|---|---|---|
| webview_bridge_links | webview_allowed_domains, postmessage_origin, cookie_token_sharing_boundary, bridge_method_exposure, custom_scheme, deep_link_sensitive_params, external_app_browser_jump | MASTG-TEST-0028 / MASTG-TEST-0031（Android）；MASTG-TEST-0075 / MASTG-TEST-0076（iOS） |

## Reconciliation and cloud phase substatus branches (contracts: app_reconciliation_schema + app_cloud_schema)

`static_dynamic_reconciliation` 的 CSV 行携带十个行级 endpoint 状态（static_only/dynamic_only/
both_seen/feature_gated/stale/version_specific/third_party/platform_shared/unreachable/
needs_manual_validation）——区别于六值 coverage substatus；对账纯离线，不发"验证"请求。云面复核只做
材料/配置/授权流量分析 + 最小读验证；写、批量读、真实支付全部审批门。

| Phase | Substatus branches |
|---|---|
| static_dynamic_reconciliation | static_endpoint_base, dynamic_endpoint_base, match_status_classification, hidden_flow_identification, stale_entry_disposition |
| cloud_function_testing | anonymous_invocation, function_parameter_role_validation, cloud_env_id_mixing |
| cloud_storage_acl_testing | cloud_database_rules, object_storage_acl, signed_url_binding |
| third_party_sdk_platform_boundary | third_party_service_boundary, platform_shared_asset_attribution |
