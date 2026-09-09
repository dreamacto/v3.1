# Package unpacking, decompilation, and source reconstruction (APK/IPA/XAPK)

## Purpose

Use this branch whenever the operator supplies an APK, IPA, XAPK/APKS bundle, unpacked tree, package
archive, device cache, or backup material. The goal is not merely to list strings. Produce a traceable,
readable source tree and an explicit account of what could and could not be recovered.

Before deciding that a package is unavailable, attempt local decoding/unpacking on a copy. For common
Android/iOS formats this is usually productive, so use the managed tools below and record partial
recovery rather than stopping at raw metadata.

## 1. Preserve and inventory

1. Hash (sha256) and preserve every original file before transformation; originals stay in
   `materials/original/`, analysis happens on copies in `materials/working/`.
2. Identify platform, container type, package name/identifier, version, base package, splits,
   compression/encryption state (packer signature, FairPlay cryptid), size, provenance, and acquisition
   time.
3. Compare package names and hashes to avoid analyzing duplicates or mixing unrelated applications.
4. Keep extraction, decompilation, and indexing local/offline. Do not contact target services during
   decoding.

Record every package (including failures and unsupported formats) in `artifacts/app/package-inventory.csv`
and every material in `materials.csv`.

## 2. Standard tool chain (managed, registry active — 禁止临时手写解包脚本)

工具路径与版本见 `tools/tool_registry.json` 与 `AGENT_MANIFEST.md`；两者均为 B0 预置并实测（apktool
3.0.3 / jadx 1.5.6，天狐 Java 11）。调用前确认工具在 registry 中为 `active`。

| Step | Command | Purpose |
|---|---|---|
| 1. manifest/资源解码 | `java -jar tools/managed/app/apktool/3.0.3/apktool_3.0.3.jar d -f -o <ws>/artifacts/app/apktool/<pkg> <material.apk>` | AndroidManifest + 资源 + smali（实测参数：`d -f -o`） |
| 2. dex→java 反编译 | `tools/managed/app/jadx/1.5.6/bin/jadx.bat -d <ws>/artifacts/app/unpacked/<pkg> --deobf-min 3 --deobf-max 9 <material.apk>` | 可读 java 源码树（实测参数：`--deobf-min 3 --deobf-max 9`） |
| 3. 白盒 sink 扫描 | `.venv/Scripts/python.exe whitebox_triage.py --source-dir <ws>/artifacts/app/unpacked/<pkg> --out-dir <ws>/artifacts/whitebox --scan` | 复用现有 62 条 sink 库，不重写扫描器 |

**子进程纪律（每条命令都适用）：**

- 超时：默认 600s/包，超时即终止并记 failed（原因 `timeout`）。
- 输出上限：限制输出行数/体积，防止上下文与大文件失控；原始输出落盘不进对话。
- stderr 落 `<ws>/logs/`（工具名 + 时间戳命名）。
- 失败写 `artifacts/decoding-ledger.csv`：一行一次尝试（material_id、tool、version、command、exit
  code、error 摘要、attempted alternatives），不静默。
- 同引擎重跑与备用路径重试都留在 ledger；所有产物经 `artifacts/source-map.csv` 溯源——无溯源的提取
  不是证据。
- 解包器退出码 0 不是成功证明：必须核验预期入口文件（AndroidManifest.xml、classes*.dex 还原产物）、
  非空源码树与文件数量。

## 3. Split / XAPK / APKS 处理

- **XAPK**：本质是 zip 容器，内含 `manifest.json`（或同类清单）+ `base.apk` + 若干
  `config.<abi|locale|density>.apk` split。先解包容器到工作目录，逐 split 登记 inventory，再以 base.apk
  为主、split 为补做 apktool/jadx 分析。
- **APKS**（bundletool 产物）：同样按 zip 解包，`master.apk`/`base.apk` + `split_*.apk` 逐个登记；
  不做动态合成（split 合并安装属设备动作，未批准不做）。
- **Android App Bundle 直接分发渠道差异**：登记分发渠道与 split 组成，缺失 split 时 manifest/组件结论
  标注 partial。
- 每个 split 都是 `materials.csv`/`package-inventory.csv` 的一行（material_id 唯一），sha256 分别登记。

## 4. Android 加固壳特征识别表（package_inventory / package_unpack_decompile 用）

识别方式：解包后遍历 `lib/<abi>/`（armeabi-v7a、arm64-v8a 等）与 assets，按**文件名前缀**匹配（带版本号的
如 `libshella-2.10.3.1.so` 必须用 contains/前缀，不能全名等值）。命中只记 `signal`（加固厂商候选），新版壳
可能改名或 VMP 化导致 so 特征失效，需以 DEX 结构特征复核；任何脱壳动作见 §7 审批门。

| 厂商 | 特征文件（lib/ 与 assets） |
|---|---|
| 360 加固 | `libjiagu.so` / `libjiagu_art.so` / `libjiagu_x86.so` / `libjiagu_64.so` |
| 梆梆加固 | `libDexHelper.so` / `libDexHelper-x86.so` / `libsecexe.so` / `libsecmain.so`；assets 可见 `secData0.jar`、`mock.dex` |
| 爱加密 | `libexecmain.so` / `libexec.so` / `ijiami.dat` / `ijiami.ajm` |
| 腾讯乐固 | `libshella-*.so`（前缀）/ `libtup.so` / `liblegudb.so` / `libtosprotection.so` / `libmix.so` / `mix.dex` |
| 娜迦加固 | `libchaosvmp.so` / `libddog.so` / `libfdog.so`；企业版 `libedog.so` |
| 百度加固 | `libbaiduprotect.so` |
| 网秦 | `libnqshield.so` |
| 启明星辰 | `libvenustech.so` |

来源：看雪论坛《Android 加固厂商特征》帖（bbs.kanxue.com/thread-223248）、CSDN「Android加固特征」
（blog.csdn.net/u010671061/article/details/132634085）、掘金同文（juejin.cn/post/7273685263842820152）、
安全客《App加固的种类甄别与侦查》（anquanke.com/post/id/272843）、AndroidSecNotes 常见加固厂商脱壳方法
（github.com/JnuSimba/AndroidSecNotes）。

## 5. iOS：FairPlay 加密检查与受限边界

- 检查 Mach-O `LC_ENCRYPTION_INFO` 的 cryptid 标志：cryptid=1 即 FairPlay 加密。
- Windows 侧可用 python-lief 读 cryptid，或直接采用操作者提供的已解密 ipa。
- **cryptid=1 → 该材料记 `blocked(ios_fairplay_encrypted)`**：Windows 无解密能力，不得静默写成
  `not_applicable`；后备输入是 iTunes 备份/操作者提供材料。
- 未加密 ipa：Info.plist 解析（bundle id、版本、权限声明、URL scheme）+ 字符串提取（strings）+
  class-dump 形态的符号/字符串观察（工具可用时），产物同样过 source-map 溯源。

## 6. 解包失败 → blocked 记录格式

失败不等于跳过。固定格式落盘：

1. `artifacts/decoding-ledger.csv` 追加行：`material_id, tool, tool_version, command, exit_code,
   error_summary, attempted_alternatives, timestamp`。
2. `phase_status.app.json` 该阶段记 `blocked`，reason 必须含：包名/哈希、失败工具与版本、错误摘要、
   已尝试的替代路径、解锁所需最小输入（如"需操作者提供已脱壳材料"）。
3. `package_inventory` 中该包 `analysis_status=failed/blocked`，不删行。

`blocked` 与 `not_applicable` 的边界：材料存在但当前工具/授权无法还原 = `blocked`；平台/形态根本不适用
（如 Android 流程遇到 iOS-only 分支）= `not_applicable`（带理由）。**解包困难永远不是 not_applicable 的
理由。**

## 7. 红线：壳包不自动脱壳（审批门 app_hardened_unpack）

- **壳包解包默认 blocked；本项目对加固壳包不自动脱壳。**
- 唯一前进路径：操作者提供已脱壳材料（登记 provenance 与哈希入 `materials.csv`），或显式批准后在指定
  测试设备执行（审批门 `app_hardened_unpack`，双钥匙：脚本审批门 + 会话内人工显式确认）。
- FRIDA-DEXDump / BlackDex 等脱壳工具在 `tools/tool_registry.json` 保持 `unavailable`，操作者放置并
  报备前不接入、不调用。
- 加固/壳特征命中只是 signal（见 §4），不构成漏洞结论；"绕过加固"是测试技术，不是漏洞。

## 8. Make recovered code analyzable

Beautify/deobfuscate within tool bounds (jadx `--deobf-min/max` 已配置)；记录每次变换与工具版本。不宣称
完整源码恢复：名称或控制流仍含糊时如实记录"未还原区域"。用动态观察解析含糊的运行期值，不凭空发明。

## 9. Build security-oriented indexes

From the recovered tree, index:

- 组件与入口：activities/services/receivers/providers、exported 状态、intent-filter、scheme/universal
  link、iOS extension 声明。
- manifest 深解析产物：权限、allowBackup、debuggable、networkSecurityConfig、cleartext。
- full URLs、hosts、相对 API 路径、方法（可推断时）、参数名、对象标识符、版本。
- 登录交换、token/session 生命周期、签名/nonce/timestamp/重放检查代码路径。
- 本地存储（shared_prefs/db/keychain/plist）、日志、剪贴板、快照、临时文件访问代码。
- 上传/下载/导入导出/支付/订单/分享/云操作。
- WebView、JS 桥、deeplink、第三方 SDK 与云能力。
- 环境切换、debug/test host、硬编码 secret 模式、信任决策。

每条提取项保留源位置（`path:line`）、证据路径、哈希与置信度；实际凭证、token、PII 与业务值脱敏。

## 10. Completion criteria

The package branch is complete only when:

- all supplied and discovered packages/splits have a recorded result
- expected entry files and declared components are reconciled
- a recovered-source map exists, even if some entries are failures
- transformations and tool versions are recorded
- unreadable, unsupported, encrypted, missing, and dynamic regions are explicit
- security indexes have source references
- static results have been queued for dynamic or backend confirmation where needed

If recovery fails, keep the phase `blocked` with the exact package, tool, error, attempted alternatives,
and minimum missing input (§6). Do not mark it `not_applicable` merely because extraction was difficult.
