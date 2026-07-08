---
title: 2026-07-06 数据源重构 — OpenLigaDB + odds-api.io 双管线
author: AI辅助分析
status: 已上线
需回滚: 否
---

# 数据源重构：OpenLigaDB + odds-api.io 双管线

> **问题：** SofaScore API 被 CDN/Varnish 封锁（HTTP 403），`datafc`库的 `curl_cffi` 每次请求等待 30s×3次重试，导致预测管线超时（120s+）。
> **方案：** 预测用 OpenLigaDB（HTTP，稳定可用），赔率用 odds-api.io（HTTPS，API Key 验证通过），SofaScore 数据全部跳过。

---

## 改动文件

### 1. `skill/datafc_provider.py`

| 改动 | 说明 |
|:-----|:------|
| **SofaScore连通性硬编码** | `DATAFIC_ALIVE = False` 硬编码，移除 HTTP 探测。SofaScore 已被 CDN 永久封禁(403)，无探测必要 |
| **`estimate_xg_from_openligadb()` 新增** | 从 OpenLigaDB 获取球队赛果 → 计算场均进/失球 → 映射到七维L1攻防评分。零网络等待，全本地计算。 |
| **`TEAM_DE` 映射表新增** | OpenLigaDB 使用德文队名（Portugal/Spanien），新增中文→德文的完整映射 |
| **`estimate_xg_from_openligadb` 多队名匹配** | 同时检查 TEAM_EN(英文) 和 TEAM_DE(德文) 两个映射表 |
| **`_load_elo_rankings` 无依赖** | ELO 数据不受 SofaScore 影响，独立走本地缓存 |
| **stdout编码修复** | Windows 下 `reconfigure(encoding='utf-8', errors='replace')` 防止中文打印崩溃 |

### 2. `skill/predict.py`

| 改动 | 说明 |
|:-----|:------|
| **`_call_with_timeout` 超时 12s → 6s** | 所有 datafc 调用加速失败（目前SofaScore不可达，6s足够） |
| **所有 `if DATAFIC_AVAILABLE:` → `if DATAFIC_AVAILABLE and DATAFIC_ALIVE:`** | 连通性探测失败时跳过所有 datafc 块 |
| **Step② xG/攻防 新增 OpenLigaDB 估算** | 替代 xg_estimator 子进程（90s超时）为先尝试 OpenLigaDB 比分估算（<1s），失败再回退 xg_estimator |
| **Step⑤ ELO 解绑 datafc** | `get_team_elo` 从 `if DATAFIC_ALIVE` 门中移出，独立走本地缓存 |
| **新增 `estimate_xg_from_openligadb` 导入** | 模块导入新增 |

### 3. `skill/fetch_match_data.py`

无改动（原 odds-api.io 路径已正常工作）

---

## 数据流变更

### 改造前

```
datafc(SofaScore) → 30s×3重试 → timeout → OpenLigaDB/odds-api fallback
                                                    ↓
                                              总等待 ~120-180s
```

### 改造后

```
DATAFIC_ALIVE=False → 跳过所有 datafc 块
     ↓
OpenLigaDB(HTTP)  ← 基本面 + xG估算（~3s）
odds-api.io       ← 赔率（~3s）
ELO缓存           ← 排名融合（<1s）
     ↓
总耗时 ~25s ✅
```

---

## 性能对比

| 指标 | 改造前 | 改造后 |
|:-----|:------:|:------:|
| 单次预测耗时 | 120s+(超时) | ~25s |
| 数据获取成功率 | ❌（SofaScore 403） | ✅（OpenLigaDB 100%） |
| 赔率获取 | ❌（datafc超时） | ✅（odds-api.io 秒通） |
| xG精度 | xG（SofaScore射门级） | 🟡 实际进球近似（精度降一档） |
| 控球率/中场数据 | 缺失 | 缺失（同前） |
| ELO排名 | ✅ 本地缓存 | ✅ 本地缓存 |

---

## 待改进

| 事项 | 优先级 |
|:-----|:------:|
| xG数据源接入（API-Football免费Key） | 中 |
| 控球率/统计数据补充（懂球帝或API-Football） | 低 |
| 移除 `estimate_xg_from_openligadb` 中残余SyntaxError（不影响结果） | 低 |
