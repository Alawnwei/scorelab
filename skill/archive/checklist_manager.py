#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自查清单管理器 — 确保已知偏差模式在每次预测中被检查

用法:
  from checklist_manager import load_checklist, filter_checklist, print_checklist

流程:
  ① 每次 predict() 调用时加载 checklist.json
  ② 根据当前比赛的 factors + league 筛选相关检查项
  ③ 打印检查清单（quick模式只警告，非quick模式强制确认）
  ④ 预测完成后，若发现新偏差，可通过 add_finding() 追加到清单
"""
import json, os, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKLIST_FILE = os.path.join(BASE_DIR, "数据缓存", "checklist.json")


def load_checklist() -> dict:
    """加载 checklist.json，若文件不存在则返回空清单"""
    if not os.path.exists(CHECKLIST_FILE):
        return {"version": "0.0", "items": []}
    try:
        with open(CHECKLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"version": "0.0", "items": []}


def _factor_matches(item: dict, factors: dict) -> bool:
    """检查一个检查项是否适用于当前比赛的 factors 配置"""
    # 检查 applicable_if_factor
    factor_key = item.get("applicable_if_factor")
    if not factor_key:
        return True  # 无 factor 条件，默认适用

    actual_value = factors.get(factor_key)

    # 精确值匹配
    expected_value = item.get("applicable_if_value")
    if expected_value is not None:
        if actual_value == expected_value:
            return True
        # bool 与字符串兼容
        if isinstance(expected_value, bool) and actual_value is True:
            return True

    # 值在列表中
    value_in = item.get("applicable_if_value_in")
    if value_in and actual_value in value_in:
        return True

    # 最小值匹配（数字类型）
    min_val = item.get("applicable_if_value_min")
    if min_val is not None and isinstance(actual_value, (int, float)):
        if actual_value >= min_val:
            return True

    return False


def _league_matches(item: dict, league: str) -> bool:
    """检查联赛适用性"""
    league_in = item.get("applicable_if_league_in")
    if not league_in:
        return True  # 不限制联赛

    # 联赛简码映射
    league_groups = {
        "world_cup": {"wm26", "WC"},
        "cup": {"wm26", "WC", "ucl", "europa"},
        "knockout": {"wm26", "WC", "ucl", "europa"},
    }

    for allowed in league_in:
        group = league_groups.get(allowed, {allowed})
        if league in group:
            return True

    return False


def _special_condition_matches(item: dict, result: dict, factors: dict) -> bool:
    """检查特殊条件"""
    condition = item.get("applicable_if")
    if condition == "always":
        return True
    if condition == "live_odds_available":
        # 只要赛前有赔率就假设有临场数据
        return bool(result.get("odds_home"))
    if condition == "title_or_relegation_battle":
        # 需要用户标记
        return factors.get("is_title_battle", False) or factors.get("is_relegation_battle", False)
    return True


def filter_checklist(result: dict, factors: dict, league: str = "wm26") -> list:
    """根据当前比赛筛选适用的检查项

    Args:
        result: predict() 的 result 字典（用于检查 quality_score/xg_source 等）
        factors: M系数因子字典
        league: 联赛代码

    Returns:
        适用的检查项列表（按严重度排序）
    """
    checklist = load_checklist()
    applicable = []

    for item in checklist.get("items", []):
        # 三个条件同时满足才适用
        factor_ok = _factor_matches(item, factors)
        league_ok = _league_matches(item, league)
        special_ok = _special_condition_matches(item, result, factors)

        if factor_ok and league_ok and special_ok:
            applicable.append(item)

    # 按严重度排序: high > medium > low
    severity_order = {"high": 0, "medium": 1, "low": 2}
    applicable.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 3))

    return applicable


def print_checklist(checklist_items: list, quick_mode: bool = False) -> list:
    """打印检查清单并收集确认结果

    Args:
        checklist_items: filter_checklist 的输出
        quick_mode: True=只打印警告不拦停；False=要求逐项确认

    Returns:
        确认结果列表 [{"id": str, "checked": bool, "note": str}, ...]
    """
    if not checklist_items:
        print("  [清单] 本次无适用的检查项")
        return []

    results = []
    print(f"\n  {'='*55}")
    print(f"  📋 赛前强制自查清单 ({len(checklist_items)}项适用)")
    print(f"  {'='*55}")

    for i, item in enumerate(checklist_items, 1):
        sev = item.get("severity", "low")
        sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
        sev_label = {"high": "必查", "medium": "建议", "low": "参考"}.get(sev, "")

        print(f"\n  {sev_icon} [{i}/{len(checklist_items)}] {sev_label} {item.get('title', '?')}")
        print(f"    v{item.get('source_version', '?')}")
        print(f"    检查: {item.get('question', '?')}")

        if quick_mode:
            # quick模式：只警告，自动标记为"未确认"
            print(f"    ⚠️  (quick模式—请赛后复盘时确认此检查项)")
            results.append({"id": item.get("id", f"item_{i}"), "checked": False, "note": "quick模式跳过"})
        else:
            # 交互模式：要求确认
            try:
                answer = input(f"    ✅ 已确认无误？(y=确认, n=需修改, Enter=跳过): ").strip().lower()
                if answer == "y":
                    results.append({"id": item.get("id", f"item_{i}"), "checked": True, "note": "已确认"})
                    print(f"    ✅ 已确认")
                elif answer == "n":
                    note = input(f"    请说明需要如何修改: ").strip()
                    results.append({"id": item.get("id", f"item_{i}"), "checked": False, "note": note or "需修改但未说明"})
                    print(f"    ⚠️ 已记录: {note or '需修改'}")
                else:
                    results.append({"id": item.get("id", f"item_{i}"), "checked": False, "note": "跳过未确认"})
                    print(f"    ⏭️ 跳过")
            except (EOFError, KeyboardInterrupt):
                results.append({"id": item.get("id", f"item_{i}"), "checked": False, "note": "中断"})
                print(f"    ⏭️ 中断跳过")

    # 汇总
    checked_count = sum(1 for r in results if r["checked"])
    unchecked = [r for r in results if not r["checked"]]

    print(f"\n  {'='*55}")
    print(f"  清单完成: {checked_count}/{len(results)} 已确认")
    if unchecked:
        print(f"  ⚠️  {len(unchecked)}项未确认:")
        for u in unchecked:
            print(f"    - {u['id']}: {u['note']}")
        if quick_mode:
            print(f"  (quick模式，继续执行)")
        else:
            print(f"  (继续执行，但建议复盘时回顾未确认项)")
    print(f"  {'='*55}\n")

    return results


def add_observation(title: str, question: str, match: str = "",
                    severity: str = "medium", factor_key: str = None,
                    factor_value=None, league_in: list = None,
                    confidence: str = "待验证"):
    """赛后偏差分析——将新发现记入「待观察清单」，不立即加为规则

    用法（替代旧的 add_finding）:
      # 旧方式: 立即加入规则列表
      # 新方式: 记入待观察，积累50场后批量验证

    Args:
        title: 偏差模式名称
        question: 需要验证的问题
        match: 发现此偏差的比赛名称
        severity: high/medium/low
        factor_key: 触发因子（如果适用）
        factor_value: 触发值
        league_in: 适用联赛
        confidence: "待验证" / "高疑似" / "存疑"
    """
    checklist = load_checklist()
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d")

    new_obs = {
        "id": f"obs_{len(checklist.get('observations', [])) + 1}",
        "title": title,
        "question": question,
        "match": match,
        "severity": severity,
        "confidence": confidence,
        "added_date": now,
        "validated": False,
        "validation_result": None,
        "source_version": "待观察",
    }
    if factor_key:
        new_obs["applicable_if_factor"] = factor_key
        if factor_value is not None:
            new_obs["applicable_if_value"] = factor_value
    if league_in:
        new_obs["applicable_if_league_in"] = league_in

    # 去重
    for existing in checklist.get("observations", []):
        if existing.get("title") == title:
            print(f"  [观察] 已存在相同观察项: {title}")
            return

    checklist.setdefault("observations", []).append(new_obs)
    checklist["last_updated"] = now

    # 更新批次计数
    meta = checklist.get("observation_meta", {})
    meta["current_batch_count"] = len(checklist["observations"])
    checklist["observation_meta"] = meta

    try:
        with open(CHECKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(checklist, f, ensure_ascii=False, indent=2)
        batch = meta.get("batch_size_target", 50)
        count = meta["current_batch_count"]
        print(f"  [观察] 已记录: [{title}]")
        print(f"  [观察] 待验证总数: {count}/{batch} （积累到{batch}场后批量验证）")
    except IOError as e:
        print(f"  [观察] 写入失败: {e}")


def list_observations(only_pending: bool = True) -> list:
    """列出所有待观察项"""
    checklist = load_checklist()
    obs = checklist.get("observations", [])
    if only_pending:
        obs = [o for o in obs if not o.get("validated")]
    return obs


def print_observations():
    """打印待观察清单"""
    obs = list_observations(only_pending=True)
    if not obs:
        print("  [观察] 当前无待验证的观察项")
        return

    meta = load_checklist().get("observation_meta", {})
    batch = meta.get("batch_size_target", 50)
    count = meta.get("current_batch_count", 0)

    print(f"\n  {'='*55}")
    print(f"  📋 偏差待观察清单 ({count}项，目标{batch}场后验证)")
    print(f"  {'='*55}")
    for i, o in enumerate(obs, 1):
        sev = o.get("severity", "medium")
        sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
        confidence = o.get("confidence", "待验证")
        print(f"\n  {sev_icon} [{i}] {o.get('title', '?')}")
        print(f"      比赛: {o.get('match', '未记录')} | 置信: {confidence} | 日期: {o.get('added_date', '?')}")
        print(f"      待验证: {o.get('question', '?')}")
    print(f"\n  当前 {count} 项，达到 {batch} 项或积累50场比赛后运行 validate_observations()")
    print(f"  {'='*55}\n")


def validate_observations(predictions_db_path: str = None) -> list:
    """批量验证待观察项（需要在积累足够比赛后调用）

    这是框架函数，仅在积累50+场比赛且有predictions_db.json后才有统计意义。

    Returns:
        验证结果列表: [{"id": str, "title": str, "verified": bool, "note": str}]
    """
    obs = list_observations(only_pending=True)
    if not obs:
        print("  [验证] 无待验证项")
        return []

    results = []
    print(f"\n  [验证] 正在验证 {len(obs)} 项待观察...")
    print(f"  [验证] 当前为框架函数，待积累{load_checklist().get('observation_meta', {}).get('batch_size_target', 50)}场比赛后接入校准数据运行")
    print(f"  [验证] 下方为逐项标记接口（需要人工判断或接入predictions_db）:")

    for o in obs:
        print(f"\n    [{o.get('id', '?')}] {o.get('title', '?')}")
        print(f"      问题: {o.get('question', '?')}")
        try:
            answer = input(f"      验证通过? (y=是/确认规律存在, n=否/随机波动, Enter=暂不判定): ").strip().lower()
            if answer == "y":
                verified = True
                note = "人工判定为有效规律"
            elif answer == "n":
                verified = False
                note = "人工判定为随机波动/无效"
            else:
                verified = None
                note = "暂不判定，保留观察"
        except (EOFError, KeyboardInterrupt):
            verified = None
            note = "中断"

        results.append({
            "id": o.get("id"),
            "title": o.get("title"),
            "verified": verified,
            "note": note,
        })

    # 更新checklist.json
    checklist = load_checklist()
    for r in results:
        for o in checklist.get("observations", []):
            if o["id"] == r["id"]:
                o["validated"] = True
                o["validation_result"] = r["verified"]
                o["validation_note"] = r["note"]
                o["validated_date"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d")

                # 如果验证通过，升级为规则
                if r["verified"]:
                    new_rule = {
                        "id": f"from_obs_{o['id']}",
                        "title": o["title"],
                        "question": o["question"],
                        "severity": o.get("severity", "medium"),
                        "source_version": "验证升级",
                    }
                    if o.get("applicable_if_factor"):
                        new_rule["applicable_if_factor"] = o["applicable_if_factor"]
                    if o.get("applicable_if_value"):
                        new_rule["applicable_if_value"] = o["applicable_if_value"]
                    if o.get("applicable_if_league_in"):
                        new_rule["applicable_if_league_in"] = o["applicable_if_league_in"]
                    checklist.setdefault("items", []).append(new_rule)
                    print(f"      → 验证通过，已升级为规则 [{r['title']}]")
                break

    checklist["last_updated"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    try:
        with open(CHECKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(checklist, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"  [验证] 写入失败: {e}")

    return results


# ============================================================
# 独立测试
# ============================================================
if __name__ == "__main__":
    # 示例：模拟一场世界杯淘汰赛
    test_factors = {
        "hold_lead": True,
        "must_win": "high",
        "rotation": 0,
        "big_loss": 0,
        "do_or_die": True,
    }
    test_result = {"odds_home": 1.5, "xg_source": "datafc"}

    items = filter_checklist(test_result, test_factors, league="wm26")
    print(f"\n适用检查项: {len(items)} 条\n")
    for item in items:
        print(f"  [{item['severity']}] {item['title']}")

    print("\n--- 交互确认 ---")
    print_checklist(items, quick_mode=True)
