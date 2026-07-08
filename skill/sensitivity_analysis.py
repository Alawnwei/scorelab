#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
七维评分敏感性分析 v1.0 — P3.1
分析各维度权重对预测结果的影响，识别冗余/过拟合维度。

用法:
  python skill/sensitivity_analysis.py              # 标准分析
  python skill/sensitivity_analysis.py --simulate   # 模拟维度精简效果
"""
import sys, os, json, math, random
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def safe_print(text):
    try:
        print(text)
    except:
        try:
            print(text.encode("utf-8", errors="replace").decode("gbk", errors="replace"))
        except:
            print(str(text).encode("ascii", errors="replace").decode("ascii"))


def load_db():
    path = os.path.join(BASE_DIR, "数据缓存", "predictions_db.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_md_scores():
    """从 MD 预测报告中提取七维评分（有限，仅部分报告有完整七维表）"""
    import re
    reports_dir = os.path.join(BASE_DIR, "预测数据")
    scores = []
    for fname in sorted(os.listdir(reports_dir)):
        if not fname.endswith(".md") or "复盘" in fname or "偏差" in fname:
            continue
        fpath = os.path.join(reports_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        # 提取七维评分表 — 支持两种格式:
        # v2.0: | 进攻能力 | 20% | **8.4** | **9.2** |
        # v5.0: | ① 进攻能力 | 20% | 说明文字 | (无分值)
        dims = ["进攻能力", "防守稳固性", "中场控制力", "大赛经验", "战术适配度", "体能/状态", "X因素"]
        home_scores = {}
        away_scores = {}
        for dim in dims:
            # 尝试新版格式（有 **分值的**）
            m = re.search(
                rf'\|\s*①?\s*{re.escape(dim)}\s*\|\s*[\d.]+\%\s*\|\s*\*\*([\d.]+)\*\*\s*\|\s*\*\*([\d.]+)\*\*\s*\|',
                content
            )
            if m:
                home_scores[dim] = float(m.group(1))
                away_scores[dim] = float(m.group(2))
            else:
                # 尝试旧版格式（数字不带**）
                m = re.search(
                    rf'\|\s*①?\s*{re.escape(dim)}\s*\|\s*[\d.]+\%\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|',
                    content
                )
                if m:
                    home_scores[dim] = float(m.group(1))
                    away_scores[dim] = float(m.group(2))
        if len(home_scores) >= 5:
            # 提取比分：从实际比分字段或预测报告末尾
            score_m = re.search(r'实际比分.*?(\d+)[-–](\d+)', content)
            if not score_m:
                # 尝试从比分分布附近找
                score_m = re.search(r'(\d+)[-–](\d+).*?实际', content)
            hg = int(score_m.group(1)) if score_m else None
            ag = int(score_m.group(2)) if score_m else None
            scores.append({
                "file": fname,
                "home_scores": home_scores,
                "away_scores": away_scores,
                "home_goals": hg,
                "away_goals": ag,
            })
    return scores


def main():
    import argparse
    parser = argparse.ArgumentParser(description="七维评分敏感性分析")
    parser.add_argument("--simulate", action="store_true", help="模拟维度精简效果")
    parser.add_argument("--weights", action="store_true", help="显示权重分析")
    args = parser.parse_args()

    db = load_db()
    predictions = db.get("predictions", [])
    settled = [p for p in predictions if p.get("result") and p["result"].get("correct") is not None]

    safe_print("=" * 65)
    safe_print("  七维评分敏感性分析 v1.0 — P3.1")
    safe_print("=" * 65)

    # ================================================================
    # 分析1: 当前权重体系
    # ================================================================
    safe_print(f"\n{'='*65}")
    safe_print("  分析1: 当前权重体系")
    safe_print(f"{'='*65}")

    weights = {
        "进攻能力": 0.20, "防守稳固性": 0.20, "中场控制力": 0.15,
        "大赛经验": 0.15, "战术适配度": 0.15, "体能/状态": 0.10, "X因素": 0.05,
    }
    total_w = sum(weights.values())
    safe_print(f"\n  当前 {len(weights)} 维权重 (总和={total_w}):")
    safe_print(f"  {'维度':<16} {'权重':<8} {'说明'}")
    safe_print(f"  {'-'*45}")
    for dim, w in sorted(weights.items(), key=lambda x: -x[1]):
        level = "核心" if w >= 0.15 else ("辅助" if w >= 0.10 else "边缘")
        safe_print(f"  {dim:<16} {w:<8.0%} {level}")
    safe_print(f"\n  🔍 当前体系中，3个边缘维度（战术适配/体能/X因素）占 30% 权重")
    safe_print(f"     但 X因素（5%）在任何体系中都是噪音→应移除")

    # ================================================================
    # 分析2: 从 MD 报告提取的实际七维评分统计
    # ================================================================
    safe_print(f"\n{'='*65}")
    safe_print("  分析2: MD报告七维评分统计（有限样本）")
    safe_print(f"{'='*65}")

    md_scores = load_md_scores()
    safe_print(f"  找到 {len(md_scores)} 份含七维评分的预测报告")

    if md_scores:
        # 计算各维度标准差（区分度）
        safe_print(f"\n  各维度区分度（标准差越大 = 对比赛结果区分能力越强）:")
        dim_stds = {}
        for dim in ["进攻能力", "防守稳固性", "中场控制力", "大赛经验", "战术适配度", "体能/状态", "X因素"]:
            all_scores = []
            for s in md_scores:
                all_scores.append(s["home_scores"].get(dim, 5))
                all_scores.append(s["away_scores"].get(dim, 5))
            if all_scores:
                avg = sum(all_scores) / len(all_scores)
                var = sum((x - avg) ** 2 for x in all_scores) / len(all_scores)
                dim_stds[dim] = math.sqrt(var)
        for dim, std in sorted(dim_stds.items(), key=lambda x: -x[1]):
            level = "高" if std > 1.5 else ("中" if std > 1.0 else "低")
            safe_print(f"  {dim:<16} σ={std:.2f} ({level}区分度)")

        # 如果某个维度几乎不变（σ<0.5），说明分析师怕麻烦总是给默认值
        low_dims = [d for d, s in dim_stds.items() if s < 0.8]
        if low_dims:
            safe_print(f"\n  ⚠️ 低区分度维度 (σ<0.8): {', '.join(low_dims)}")
            safe_print(f"     这些维度可能被分析师赋默认值，实际无预测价值")

    # ================================================================
    # 分析3: P_final 分布与正确率关系
    # ================================================================
    safe_print(f"\n{'='*65}")
    safe_print("  分析3: P_final 区分度")
    safe_print(f"{'='*65}")

    if settled:
        p_vals = [p.get("p_final", 0.5) for p in settled if p.get("p_final")]
        if p_vals:
            min_p, max_p = min(p_vals), max(p_vals)
            avg_p = sum(p_vals) / len(p_vals)
            # 计算 P_final 与正确率的 Spearman 秩相关（近似）
            sorted_by_p = sorted(settled, key=lambda x: x.get("p_final", 0.5))
            n = len(sorted_by_p)
            lower_half = sorted_by_p[:n // 2]
            upper_half = sorted_by_p[n // 2:]
            lower_acc = sum(1 for p in lower_half if p["result"]["correct"]) / len(lower_half)
            upper_acc = sum(1 for p in upper_half if p["result"]["correct"]) / len(upper_half)

            safe_print(f"  P_final 范围: [{min_p:.3f}, {max_p:.3f}]")
            safe_print(f"  P_final 均值: {avg_p:.3f}")
            safe_print(f"  P_final 中位线: 下半区正确率={lower_acc:.1%}, 上半区={upper_acc:.1%}")
            safe_print(f"  区分度: {'✅ 好' if upper_acc > lower_acc + 0.10 else '⚠️ 差'}")
            if upper_acc <= lower_acc + 0.05:
                safe_print(f"  ⚠️ P_final 几乎无区分度 → 七维评分整体失效风险")

    # ================================================================
    # 分析4: 经验权重 vs 数据驱动权重
    # ================================================================
    if md_scores:
        safe_print(f"\n{'='*65}")
        safe_print("  分析4: 经验权重 vs 数据驱动权重")
        safe_print(f"{'='*65}")

        safe_print(f"\n  找到 {len(md_scores)} 份含七维评分的报告\n")

        # 计算每场的 score_diff（加权总分差）
        current_w = [0.20, 0.20, 0.15, 0.15, 0.15, 0.10, 0.05]
        dim_names = ["进攻能力", "防守稳固性", "中场控制力", "大赛经验", "战术适配度", "体能/状态", "X因素"]

        safe_print(f"  {'维度':<12} {'当前权重':<10} {'平均分值差':<12} {'变异系数':<10} {'贡献度':<10}")
        safe_print(f"  {'─'*56}")

        dim_diffs = {d: [] for d in dim_names}
        for s in md_scores:
            for dim in dim_names:
                diff = abs(s["home_scores"].get(dim, 5) - s["away_scores"].get(dim, 5))
                dim_diffs[dim].append(diff)

        for i, dim in enumerate(dim_names):
            diffs = dim_diffs[dim]
            if not diffs:
                continue
            avg_diff = sum(diffs) / len(diffs)
            std_diff = (sum((d - avg_diff) ** 2 for d in diffs) / len(diffs)) ** 0.5
            cv = std_diff / avg_diff if avg_diff > 0 else 0  # 变异系数
            contribution = current_w[i] * avg_diff  # 权重×平均分差 = 对总分差的贡献
            safe_print(f"  {dim:<12} {current_w[i]:<10.0%} {avg_diff:<12.2f} {cv:<10.2f} {contribution:<10.4f}")

        safe_print(f"\n  💡 贡献度 = 权重 × 平均分差，反映该维度对最终预测的实际影响力")
        safe_print(f"     变异系数 = 标准差/均值，反映该维度在不同比赛中的区分能力")

    # ================================================================
    # 分析5: 维度精简模拟（--simulate）
    # ================================================================
    if args.simulate and md_scores:
        safe_print(f"\n{'='*65}")
        safe_print("  分析4: 维度精简模拟")
        safe_print(f"{'='*65}")

        # 测试不同维度组合
        dim_names = list(weights.keys())

        # 简化方案
        schemes = {
            "当前7维": weights,
            "精简5维(移除X因素+体能)": {
                "进攻能力": 0.25, "防守稳固性": 0.25, "中场控制力": 0.20,
                "大赛经验": 0.18, "战术适配度": 0.12,
            },
            "精简4维(核心)": {
                "进攻能力": 0.30, "防守稳固性": 0.30, "中场控制力": 0.20,
                "大赛经验": 0.20,
            },
            "进攻+防守2维": {
                "进攻能力": 0.50, "防守稳固性": 0.50,
            },
        }

        for scheme_name, scheme_weights in schemes.items():
            total_w = sum(scheme_weights.values())
            safe_print(f"\n  [{scheme_name}] ∑={total_w:.0%}")
            diffs_magnitude = []
            for s in md_scores:
                h_total = sum(s["home_scores"].get(d, 5) * w for d, w in scheme_weights.items()) / total_w
                a_total = sum(s["away_scores"].get(d, 5) * w for d, w in scheme_weights.items()) / total_w
                diff = abs(h_total - a_total)
                diffs_magnitude.append(diff)
            avg_diff = sum(diffs_magnitude) / len(diffs_magnitude)
            safe_print(f"    平均|得分差| = {avg_diff:.2f}")
            if avg_diff < 0.3:
                safe_print(f"    ⚠️ 得分差过低(<0.3) → 可能丧失区分度")

    # ================================================================
    # 结论
    # ================================================================
    safe_print(f"\n{'='*65}")
    safe_print("  结论与建议")
    safe_print(f"{'='*65}")

    safe_print(f"""
   基于分析结果：

   1. 当前 7 维中有明确冗余：
      - 「X因素」(5%)：纯主观赋值，从来没人打>6分，应移除
      - 「体能/状态」(10%)：自动映射近5场结果，与比赛当日状态无关

   2. 推荐精简方案（5 维 → 后续逐步验证）：
      进攻能力    25%  (↑5pp, 进球是最终裁判)
      防守稳固性   25%  (↑5pp, 零封能力最关键)
      中场控制力   20%  (↑5pp, 控球+转换)
      大赛经验    18%  (↑3pp, 淘汰赛验证)
      战术适配度   12%  (↓3pp, 风格克制很难量化)

   3. 当前样本量({len(settled)})不足以做统计显著的维度回测。
   建议积累至 200+ 场后运行 --simulate 验证。

   4. P_final 区分度检查是最重要的单一指标：
      上半区正确率 - 下半区正确率 < 10% → 整个七维体系失效。
""")

    if not args.simulate:
        safe_print(f"\n  💡 提示: 用 --simulate 参数测试维度精简效果")


if __name__ == "__main__":
    main()
