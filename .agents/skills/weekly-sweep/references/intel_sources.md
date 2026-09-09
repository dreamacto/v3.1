# 情报源监控清单（weekly-sweep 巡检用，WZ/XCX 能力升级 P2 ⑨，方案 §7.2）

> weekly-sweep 按下表巡检；命中的单条情报走 `tools/poc_intake/` 流水线
> （SOURCE.md 登记 → TRIAGE.md 三分类 → 操作者审批 → detect-only 转模板 →
> 白名单提案 → labs/ 本地复现先行）。巡检本身零执行零目标接触。

监控源（权威度从高到低）：

| 源 | 用途 | 频率 |
|---|---|---|
| CISA KEV 目录 | 已被在野利用的 CVE 优先级清单（NDAY/1DAY 排序金标准） | 每周 |
| nuclei-templates release notes | 每版约 100 个新 CVE 模板，直接转白名单提案 | 每两周 |
| OSCS（oscs1024.com） | 国内 0day/1day 早期预警，免费订阅 | 每日 |
| GitHub Advisory + GitHub Topic（cve-xxxx） | 补充 PoC 线索 | 每周 |
| 先知社区 / Seebug / 奇安信 CERT 公告 | 国内情报补充 | 每周 |
| afrog pocs 更新日志 | 国内产品 POC 增量 | 每两周 |
| Vulhub | 本地复现环境（labs/ 配套），不是目标情报 | 按需 |

巡检纪律：

- 排序以 CISA KEV 为金标准（在野利用优先），国内源（OSCS/先知/Seebug）补
  国内产品面（用友/泛微/致远/通达/蓝凌/万户/金和/大汉等）；
- afrog 产品关键词启用前先 `-s <关键词> -pl` 确认 PoC 非零（大汉 hanweb 实测
  为 0，"以为有覆盖其实为 0"是已知陷阱，见方案附录 C）；
- 任何 POC/情报复现先走 labs/ 本地靶场（Vulhub/自建），零目标接触；
- exploit-only 情报只登记留档，永不转模板、永不进白名单。
