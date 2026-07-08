#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盈亏追踪中枢 (PnL Tracker) — 自动记录预测→结果→盈亏

用途:
  每次预测后记录：比赛ID、P_final、赔率、+EV、注额、实际结果
  月底自动生成：命中率、收益率、Sharpe Ratio、归因分析

用法:
  python skill/pnl_tracker.py --record       # 记录一场预测结果
  python skill/pnl_tracker.py --report       # 生成月度报表
  python skill/pnl_tracker.py --list         # 列出所有记录
  python skill/pnl_tracker.py --export       # 导出为CSV
"""

import json, sys, os, csv
from datetime import datetime, timedelta
from typing import Optional, Dict, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "数据缓存")
RECORDS_FILE = os.path.join(OUTPUT_DIR, "pnl_records.json")

# 默认记录模板
RECORD_TEMPLATE = {
    "records": [],
    "last_updated": None,
    "bankroll": {
        "initial": 10000,       # 初始本金（可配置）
        "current": 10000,       # 当前余额
        "peak": 10000,          # 历史峰值
        "lowest": 10000,        # 历史最低（用于回撤计算）
        "peak_to_trough": 0,    # 当前回撤 %
        "max_drawdown": 0,      # 最大回撤 %
        "updated_at": None,
    },
}

# 资金曲线 C-1: 本金+盈亏累计
def _compute_bankroll_curve(records):
    """按结算顺序计算资金曲线 — 返回 [(日期, 余额), ...]"""
    bankroll = RECORD_TEMPLATE["bankroll"]["initial"]
    peak = bankroll
    max_dd = 0
    curve = [("开始", bankroll)]
    for r in sorted(records, key=lambda x: x["date"]):
        if r["result"] == "pending" or r["stake"] <= 0:
            continue
        # PnL = 盈亏（单位：按等价金额换算）
        # 将 stake 视为注码单位，pnl 为已计算好的盈亏
        stake = r.get("stake", 1)
        pnl = r.get("pnl", 0)
        # 只有当 pnl 不为 0（或赔率有效）时才更新
        if r["odds"] > 0:
            bankroll += pnl
        if bankroll > peak:
            peak = bankroll
        dd = (peak - bankroll) / peak * 100
        if dd > max_dd:
            max_dd = dd
        curve.append((r["date"], round(bankroll, 2)))
    return curve, round(bankroll, 2), round(max_dd, 2), round(peak, 2)


# ============================================================
# 数据管理
# ============================================================

def _load_records() -> dict:
    """加载所有预测记录"""
    if os.path.exists(RECORDS_FILE):
        with open(RECORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(RECORD_TEMPLATE)


def _save_records(data: dict):
    """保存预测记录"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] 已保存 {RECORDS_FILE}")


def add_record(home: str, away: str, p_final: float, odds: float,
               stake: float = 1.0, result: str = "pending",
               direction: str = "", league: str = "", notes: str = "",
               ev: float = 0, confidence: str = ""):
    """添加一条预测记录（自动去重：相同 home/away/date/direction 合并）"""
    data = _load_records()
    today = datetime.now().strftime("%Y-%m-%d")
    record = {
        "id": f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{home}_vs_{away}",
        "date": today,
        "home": home,
        "away": away,
        "league": league,
        "direction": direction,        # 推荐方向（主胜/大球/让球等）
        "P_final": round(p_final, 3),
        "odds": round(odds, 3),
        "+EV": round(ev, 3),
        "stake": stake,                # 注码（单位）
        "confidence": confidence,       # ⭐评级
        "result": result,               # win / loss / push / pending
        "pnl": 0,                       # 盈亏（返回时更新）
        "notes": notes,
    }
    # 如果不是pending，计算盈亏（odds=0时跳过，待回填）
    if odds > 0:
        if result in ("win", "loss"):
            if result == "win":
                record["pnl"] = round(stake * (odds - 1), 2)
            else:
                record["pnl"] = round(-stake, 2)
        elif result == "push":
            record["pnl"] = 0
    else:
        record["notes"] = (record.get("notes", "") + " | 无赔率，待回填").strip()
        record["pnl"] = 0

    # ── 去重：相同 home/away/date/direction 的已有记录覆盖更新 ──
    norm_h = home.strip().lower()
    norm_a = away.strip().lower()
    norm_dir = direction.strip().lower()
    records = data.setdefault("records", [])
    for i, r in enumerate(records):
        if (r.get("home", "").strip().lower() == norm_h
                and r.get("away", "").strip().lower() == norm_a
                and r.get("date", "") == today
                and r.get("direction", "").strip().lower() == norm_dir):
            # 合并：保留原有 result/pnl（已有结算结果的不覆盖），更新 P_final/odds/+EV
            old_result = r.get("result", "pending")
            if old_result == "pending":
                r.update(record)
                r["result"] = "pending"  # 保持待结算状态
                r["id"] = record["id"]   # 更新时间戳
                _save_records(data)
                print(f"  ⚠️ 合并重复记录: {home} vs {away} ({direction}) | P_final={record['P_final']} | 赔率={record['odds']}")
                return r["id"]
            # 已有结算结果 → 忽略新记录
            print(f"  ⚠️ 跳过重复记录(已有结果): {home} vs {away} ({direction}) → {old_result}")
            return r["id"]

    # 无重复 → 追加
    records.append(record)
    _save_records(data)
    print(f"  已记录: {home} vs {away} | P_final={record['P_final']} | 赔率={record['odds']} | {result}")
    return record["id"]


def update_result(record_id: str, result: str, odds: float = None):
    """更新一条记录的实际结果（odds=0时需提供实际赔率才能算PnL）"""
    data = _load_records()
    for r in data.get("records", []):
        if r["id"] == record_id:
            r["result"] = result
            if odds is not None and odds > 0:
                r["odds"] = odds
            # 仅当有有效赔率时计算盈亏
            if r["odds"] > 0:
                if result == "win":
                    r["pnl"] = round(r["stake"] * (r["odds"] - 1), 2)
                elif result == "loss":
                    r["pnl"] = round(-r["stake"], 2)
                elif result == "push":
                    r["pnl"] = 0
            else:
                r["pnl"] = 0
                r["notes"] = (r.get("notes", "") + " | 赔率缺失，PnL未计算").strip()
            _save_records(data)
            pnl_str = f"{r['pnl']:+}" if r["odds"] > 0 else "N/A(无赔率)"
            print(f"  已更新: {r['home']} vs {r['away']} → {result} (盈亏: {pnl_str})")
            return True
    print(f"  未找到记录: {record_id}")
    return False


def delete_record(record_id: str):
    """删除一条记录"""
    data = _load_records()
    before = len(data.get("records", []))
    data["records"] = [r for r in data.get("records", []) if r["id"] != record_id]
    if len(data["records"]) < before:
        _save_records(data)
        print(f"  已删除: {record_id}")
    else:
        print(f"  未找到: {record_id}")


# ============================================================
# 报表生成
# ============================================================

def generate_report(months: int = 1) -> str:
    """生成盈亏报表"""
    data = _load_records()
    all_records = data.get("records", [])

    if not all_records:
        return "暂无预测记录"

    # 按月份筛选
    cutoff = datetime.now() - timedelta(days=30 * months)
    recent = [r for r in all_records
              if datetime.strptime(r["date"], "%Y-%m-%d") >= cutoff
              and r["result"] != "pending"]

    total_records = len(recent)
    if total_records == 0:
        return "所选时间段内无已结算记录"

    # 统计：分离有赔率和无赔率记录
    with_odds = [r for r in recent if r["odds"] > 0]
    no_odds = [r for r in recent if r["odds"] <= 0]

    wins = sum(1 for r in recent if r["result"] == "win")
    losses = sum(1 for r in recent if r["result"] == "loss")
    pushes = sum(1 for r in recent if r["result"] == "push")
    total_pnl = sum(r["pnl"] for r in recent)
    total_stake = sum(r["stake"] for r in recent if r["result"] != "push")
    win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0

    # 平均赔率（仅统计有赔率的记录）
    settled_with_odds = [r for r in with_odds if r["result"] != "push"]
    avg_odds = sum(r["odds"] for r in settled_with_odds) / len(settled_with_odds) if settled_with_odds else 0

    # ROI
    roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0

    # Sharpe Ratio
    returns = [r["pnl"] / r["stake"] for r in recent if r["stake"] > 0]
    avg_return = sum(returns) / len(returns) if returns else 0
    std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if len(returns) > 1 else 0
    risk_free = 0.02  # 年化2%无风险利率，约月化0.00167
    sharpe = (avg_return - risk_free / 12) / std_return if std_return > 0 else 0

    # 资金曲线
    curve, final_br, max_dd, peak_br = _compute_bankroll_curve(all_records)
    init_br = RECORD_TEMPLATE["bankroll"]["initial"]

    # 按联赛分组
    leagues = {}
    for r in recent:
        l = r.get("league", "未知")
        leagues.setdefault(l, []).append(r)

    # 按confidence分组
    confs = {}
    for r in recent:
        c = r.get("confidence", "未知")
        confs.setdefault(c, []).append(r)

    # 构建报表
    lines = []
    lines.append("=" * 60)
    lines.append(f"  盈亏报表 (近{months}个月)")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  累计记录: {total_records} 场 ({wins}胜 {losses}负 {pushes}走)")
    if no_odds:
        lines.append(f"  ⚠️ 其中 {len(no_odds)} 场无市场赔率（PnL未计入）")
    lines.append("=" * 60)

    # 核心指标
    sharp_str = f"{sharpe:.2f}"
    sharp_tag = "🏆" if sharpe > 1.0 else ("✅" if sharpe > 0.5 else ("⚠️" if sharpe > 0 else "🔴"))
    pnl_str = f"{total_pnl:+.2f}单位"
    pnl_tag = "🟢" if total_pnl > 0 else "🔴"

    lines.append(f"\n  核心指标:")
    lines.append(f"    命中率:    {win_rate:.1f}% ({wins}/{wins+losses})")
    lines.append(f"    平均赔率:  {avg_odds:.3f}")
    lines.append(f"    总盈亏:    {pnl_tag} {pnl_str}")
    lines.append(f"    收益率:    {roi:+.1f}%")
    lines.append(f"    Sharpe:    {sharp_tag} {sharp_str}")
    if sharpe > 1.0:
        lines.append(f"    评级:      🏆 优秀（盈利稳定）")
    elif sharpe > 0.5:
        lines.append(f"    评级:      ✅ 良好（风险可控）")
    elif sharpe > 0:
        lines.append(f"    评级:      ⚠️ 边缘（需检查+EV计算）")
    else:
        lines.append(f"    评级:      🔴 亏损（建议停止投注）")

    # 资金曲线
    br_change = final_br - init_br
    br_sign = "+" if br_change >= 0 else ""
    lines.append(f"\n  ── 资金曲线（本金{init_br:.0f}元）──")
    lines.append(f"    当前余额: {final_br:.0f}元 ({br_sign}{br_change:.0f}元)")
    lines.append(f"    历史峰值: {peak_br:.0f}元")
    lines.append(f"    最大回撤: {max_dd:.2f}%")
    if max_dd < 10:
        lines.append(f"    风控评级: 🏆 回撤极小")
    elif max_dd < 20:
        lines.append(f"    风控评级: ✅ 回撤可控")
    elif max_dd < 35:
        lines.append(f"    风控评级: ⚠️ 回撤较大")
    else:
        lines.append(f"    风控评级: 🔴 回撤严重（>35%）")
    # 资金曲线简图
    if len(curve) > 2:
        # 缩放到 20 格
        vals = [p[1] for p in curve]
        mn, mx = min(vals), max(vals)
        span = max(mx - mn, 1)
        bar_len = 20
        lines.append(f"    资金曲线:")
        for i in range(0, len(curve), max(1, len(curve)//8)):
            d, v = curve[i]
            bar = "█" * int((v - mn) / span * bar_len) + "░" * (bar_len - int((v - mn) / span * bar_len))
            lines.append(f"      {d[:5]:5s} | {bar} | {v:.0f}")

    # 按联赛
    if len(leagues) > 1:
        lines.append(f"\n  按联赛:")
        for league_name, league_records in sorted(leagues.items()):
            lw = sum(1 for r in league_records if r["result"] == "win")
            ll = sum(1 for r in league_records if r["result"] == "loss")
            lp = sum(r["pnl"] for r in league_records)
            lr = lp / sum(r["stake"] for r in league_records if r["result"] != "push") * 100 if sum(r["stake"] for r in league_records if r["result"] != "push") > 0 else 0
            lines.append(f"    {league_name:12s}: {lw}胜{ll}负 | 盈亏{lp:+.1f} | ROI{lr:+.1f}%")

    # 按confidence
    lines.append(f"\n  按评级:")
    for conf_name, conf_records in sorted(confs.items()):
        cw = sum(1 for r in conf_records if r["result"] == "win")
        cl = sum(1 for r in conf_records if r["result"] == "loss")
        cp = sum(r["pnl"] for r in conf_records)
        lines.append(f"    {conf_name:8s}: {cw}胜{cl}负 | 盈亏{cp:+.1f}")

    # 最近5场
    lines.append(f"\n  最近5场:")
    for r in recent[-5:]:
        pnl_mark = "✅" if r["pnl"] > 0 else ("❌" if r["pnl"] < 0 else "➖")
        lines.append(f"    {r['date']} {r['home'][:8]} vs {r['away'][:8]} | {r['direction'][:6]} | P_final={r['P_final']} | 赔率={r['odds']} | {pnl_mark} {r['pnl']:+.1f}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def list_records(limit: int = 20):
    """列出最近N条记录"""
    data = _load_records()
    records = data.get("records", [])
    if not records:
        print("暂无记录")
        return

    print(f"\n最近 {min(limit, len(records))} 条记录:")
    print(f"{'ID':22s} {'日期':10s} {'主队':10s} {'客队':10s} {'P_final':8s} {'赔率':6s} {'结果':8s} {'盈亏':8s}")
    print("-" * 85)
    for r in records[-limit:]:
        pid = r["id"][-20:]
        odds_str = f"{r['odds']:.3f}" if r["odds"] > 0 else "无赔率"
        print(f"{pid:22s} {r['date']:10s} {r['home'][:10]:10s} {r['away'][:10]:10s} {r['P_final']:.3f} {odds_str:>6s} {r['result'][:8]:8s} {r['pnl']:+.1f}")


def export_csv():
    """导出为CSV"""
    data = _load_records()
    records = data.get("records", [])
    if not records:
        print("暂无记录")
        return

    path = os.path.join(OUTPUT_DIR, "pnl_export.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["日期", "主队", "客队", "联赛", "方向", "P_final", "赔率", "+EV", "注码", "置信度", "结果", "盈亏", "备注"])
        for r in records:
            writer.writerow([
                r["date"], r["home"], r["away"], r.get("league", ""),
                r.get("direction", ""), r["P_final"], r["odds"],
                r.get("+EV", ""), r["stake"], r.get("confidence", ""),
                r["result"], r["pnl"], r.get("notes", ""),
            ])
    print(f"\n[OK] 已导出: {path}")


# ============================================================
# 命令行
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="盈亏追踪中枢")
    parser.add_argument("--record", action="store_true", help="记录一场预测")
    parser.add_argument("--update", help="更新结果: 记录ID")
    parser.add_argument("--result", choices=["win", "loss", "push"], help="实际结果")
    parser.add_argument("--report", action="store_true", help="生成报表")
    parser.add_argument("--list", action="store_true", help="列出记录")
    parser.add_argument("--export", action="store_true", help="导出CSV")
    # 录制参数
    parser.add_argument("--home", help="主队")
    parser.add_argument("--away", help="客队")
    parser.add_argument("--p", type=float, help="P_final")
    parser.add_argument("--odds", type=float, help="赔率")
    parser.add_argument("--stake", type=float, default=1, help="注码")
    parser.add_argument("--result-v", choices=["win", "loss", "push", "pending"], default="pending", help="结果")
    parser.add_argument("--direction", default="", help="推荐方向")
    parser.add_argument("--league", default="", help="联赛")
    parser.add_argument("--ev", type=float, default=0, help="+EV")
    parser.add_argument("--confidence", default="", help="评级")
    parser.add_argument("--months", type=int, default=1, help="报表月份数")
    parser.add_argument("--delete", help="删除记录ID")
    parser.add_argument("--bankroll", type=float, default=None, help="设置初始本金（元）")
    parser.add_argument("--capital", action="store_true", help="显示资金曲线")
    args = parser.parse_args()

    if args.record:
        if not args.home or not args.away or args.p is None or args.odds is None:
            print("请指定 --home, --away, --p, --odds")
            return
        add_record(args.home, args.away, args.p, args.odds,
                   stake=args.stake, result=args.result_v,
                   direction=args.direction, league=args.league,
                   ev=args.ev, confidence=args.confidence)
        return

    if args.bankroll is not None:
        data = _load_records()
        if "bankroll" not in data:
            data["bankroll"] = dict(RECORD_TEMPLATE["bankroll"])
        data["bankroll"]["initial"] = args.bankroll
        data["bankroll"]["current"] = args.bankroll
        data["bankroll"]["peak"] = args.bankroll
        data["bankroll"]["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _save_records(data)
        print(f"  [OK] 初始本金已设为 {args.bankroll:.0f} 元")
        return

    if args.capital:
        data = _load_records()
        records = data.get("records", [])
        curve, final_br, max_dd, peak_br = _compute_bankroll_curve(records)
        init_br = data.get("bankroll", {}).get("initial", 10000)
        print(f"\n  资金曲线 ({len(curve)} 个节点)")
        print(f"  本金: {init_br:.0f} → 当前: {final_br:.0f}")
        print(f"  峰值: {peak_br:.0f} | 最大回撤: {max_dd:.2f}%")
        print()
        # ASCII 图
        vals = [p[1] for p in curve]
        mn, mx = min(vals), max(vals)
        span = max(mx - mn, 1)
        bw = 25
        print(f"  {'日期':<6} | {'资金曲线':<27} | {'余额'}")
        print(f"  {'-'*45}")
        for d, v in curve:
            bar = "█" * int((v - mn) / span * bw) + "░" * (bw - int((v - mn) / span * bw))
            print(f"  {d[:5]:<6} | {bar} | {v:.0f}")
        return

    if args.update and args.result:
        update_result(args.update, args.result)
        return

    if args.delete:
        delete_record(args.delete)
        return

    if args.report:
        print(generate_report(months=args.months))
        return

    if args.list:
        list_records()
        return

    if args.export:
        export_csv()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
