# 全链路深度修复：Sofascore xG 通路 / NaN 熔断 / 温度缩放

> 日期: 2026-07-08 (持续至 07-09)
> 涉及文件: `skill/datafc_provider.py`, `skill/predict.py`

---

## 问题背景

系统 v8.4 部署后存在六大问题，导致预测输出不可信：

1. **Sofascore xG 从未真正生效** → λ 值基于实际进球而不是真实 xG
2. **NaN 静默传播** → Sofascore 射门数据中 `null` xG 值未被过滤，NaN 经计算链传播到七维评分 → 出现摩洛哥防守 10/10 的荒谬值
3. **λ 校准因子 1.305 对真实 xG 反作用** → 用旧数据算的放大因子在 Sofascore xG 上继续推高 λ
4. **淘汰赛误判轮换 L4** → `get_team_starting_xi` 在杯赛返回了错误数据，触发极端的 ×0.55 惩罚因子
5. **温度缩放 T=4.08** → 旧 λ 时代校准出的极端值，把有区分度的概率全压到 ~0.52
6. **杯赛轮次逻辑缺失** → 世界杯无轮次上限，`season_rounds_data` 失败后默认 38 轮空请求

---

## 修复清单

### P0 — 数据可信度

#### 1. Sofascore xG 通路打通（datafc_provider.py:1276）

- **问题**: `get_team_recent_matches` 中 `type == "world_cup"` 直接 `return pd.DataFrame()`，Sofascore 从未被尝试
- **修复**: 移除 world_cup 的提前返回（仅保留 `knockout`/`uefa`）
- **效果**: 世界杯 xG 数据源从 `openligadb`（实际进球）变为 `datafc_xg`（真实 xG）
- λ 从 3.45→1.69（法国）、2.37→1.53（摩洛哥）

#### 2. xG 值 NaN 防护（datafc_provider.py:1433）

- **问题**: `row.get("xg", 0) or 0` 不防 NaN，因 Python 的 `bool(float('nan'))` 为 `True`
- **NaN → 10 的传播链**:
  ```
  Sofascore xG=null → float('nan')
  → (nan or 0) = nan → total_xg_against += nan
  → 存入缓存 xG_against_90 = nan
  → _score_from_ratio(nan, avg):
      min(10, nan) = 10  # Python 中 NaN 比较总返回 False
      max(1, 10) = 10
  ```
- **修复**: `isnan(xg_val)` 检查回退到 `0.0`
- **效果**: 摩洛哥防守分从 10→5.6（合理）

#### 3. 七维评分 NaN 保护（datafc_provider.py:2185-2201）

- **问题**: `compute_7dim_scores` 中进攻/防守评分直接使用 xG 值，未做 NaN 防御
- **修复**: 在 `_score_from_ratio` 调用前对 `lam_h/lam_a/raw_def_h/raw_def_a` 做 `isnan` 检查
- **效果**: 即使缓存中残留 NaN，评分函数也不会再输出 10 分

#### 4. λ 校准因子跳过真实 xG（predict.py:326-329）

- **问题**: λ校准因子 1.305（基于 OpenLigaDB 时代的实际进球偏差数据）对 Sofascore 真实 xG 反作用
- **修复**: 当 `xg_h/xg_a` 的 source 均为 `datafc_xg` 时跳过校准
- **效果**: λ 从 2.20→1.69（法国，-23%），1.99→1.53（摩洛哥，-23%）

### P1 — 模型逻辑

#### 5. 淘汰赛轮换误触发修复（datafc_provider.py:2804-2810）

- **问题**: `infer_rotation_level` 在杯赛环境下返回 L4（7 人以上轮换），为半决赛完全不可能
- **修复**: `infer_m_factors` 中对 `is_knockout_league` 的联赛直接设 `rotation=0` 跳过检测
- **效果**: M 系数从 0.746（淘汰赛×0.963×轮换L4×0.775）恢复为 0.963

#### 6. 温度缩放 T=4.08→1.50（predict.py:369-375）

- **问题**: T=4.08 在旧 λ 极端值基础上校准，λ 修复后反而压平了合理概率
- **旧 T=4.08 效果**: 法国打佛得角（七维分差 3.38）→ P_final=0.527
- **新 T=1.50 效果**: 同一场比赛 → P_final=0.577
- **修复**: 改为 T=1.50（轻度正则化，保留区分度）

#### 7. cup/shots 日志与防御（datafc_provider.py）

- `get_xg_data` 异常捕获增加日志输出（不再静默）
- `is_home` 默认值从 `True` 改为 `None`，缺失时尝试从 `home_team_id/team_id` 推断
- 杯赛 `season_rounds_data` 失败后 max_week 限制为 10 轮

---

## 效果验证

### 法国 vs 摩洛哥（世界杯半决赛）

| 指标 | 修前 | 修后 |
|:-----|:----:|:----:|
| 数据源 | OpenLigaDB(实际进球) | **Sofascore xG(真实)** |
| 法国 λ | 3.45 | **1.69** |
| 摩洛哥 λ | 2.37 | **1.53** |
| 预期总进球 | 5.82 | **3.22** |
| 摩洛哥防守分 | 10/10(NaN bug) | **5.6** |
| M 系数 | 0.746(被轮换L4压低) | **0.963** |
| 温度缩放 | T=4.08 | **T=1.50** |
| P_final | 0.478 | **0.513** |
| 方向 | 不推荐/均衡 | **主不败(双选)** |
| 校准声明 | λ高估已修正(误导) | **Sofascore真实xG(已校准)** |

### 法国 vs 佛得角（碾压局 — 区分度测试）

| 指标 | T=4.08(旧) | T=1.50(新) |
|:-----|:----------:|:----------:|
| P_final | 0.527 🔴(无区分度) | **0.577** 🟢 |

---

## 技术债务与剩余问题

- α (Logistic 斜率 0.15) 仍基于旧数据校准，score_diff=3.38 仅映射到 P_base=0.624
- 缓存文件 `team_strength_cache.json` 含 NaN 遗留，已备份后清空
- `_estimate_from_scores` 和其他 4 处 `row.get("score") or 0` 模式有 NaN 风险但有 `try/except` 兜底
- 七维评分中 X 因素（5%）恒为 5.0，纯噪音

---

## 文件哈希

- `skill/datafc_provider.py` — 7 处改动
- `skill/predict.py` — 3 处改动（λ校准跳过 + 温度缩放 + 校准声明）
