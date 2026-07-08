#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型冻结监控器 v1.0 — P3.3

监控预测准确率，当连续 N 场低于基线时触发冻结。
冻结后自动建议：停止预测 → 运行校准 → 复盘归因。

用法:
  python skill/freeze_monitor.py              # 检查当前健康状态
  python skill/freeze_monitor.py --freeze     # 手动触发冻结
  python skill/freeze_monitor.py --unfreeze   # 解冻
  python skill/freeze_monitor.py --status     # 查看冻结状态
"""
import sys, os, json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
FREEZE_FILE = os.path.join(CACHE_DIR, "model_freeze.json")

# ============================================================
# 配置
# ============================================================
DEFAULT_CONFIG = {
    "frozen": False,                # 是否冻结
    "freeze_reason": "",            # 冻结原因
    "freeze_time": None,            # 冻结时间
    "unfreeze_time": None,          # 解冻时间
    # 触发条件
    "accuracy_baseline": 0.65,      # 基线命中率（低于此值触发警告）
    "consecutive_below_baseline": 3, # 连续低于基线 N 场触发冻结
    "min_samples": 10,              # 最少样本数才触发检查
    # 运行统计
    "consecutive_wrong": 0,         # 当前连续错误
    "last_n_correct": [],           # 最近 N 场正确/错误 [1,0,1,...]
    "accuracy_last_10": 1.0,        # 最近10场命中率
    "accuracy_all": 1.0,            # 全部命中率
    "last_checked": None,
}


def safe_print(text):
    try:
        print(text)
    except:
        try:
            print(text.encode("utf-8", errors="replace").decode("gbk", errors="replace"))
        except:
            pass


def load_state():
    if os.path.exists(FREEZE_FILE):
        with open(FREEZE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(DEFAULT_CONFIG)


def save_state(state):
    state["last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(FREEZE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_predictions():
    path = os.path.join(CACHE_DIR, "predictions_db.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        db = json.load(f)
    return db.get("predictions", [])


def compute_accuracy(predictions, n_last=None):
    """计算命中率（全部 或 最近N场）"""
    settled = [p for p in predictions
               if p.get("result") and p["result"].get("correct") is True
               or p.get("result") and p["result"].get("correct") is False]
    if n_last:
        settled = settled[-n_last:]
    if not settled:
        return 1.0, 0
    correct = sum(1 for p in settled if p["result"].get("correct") is True)
    return correct / len(settled), len(settled)


def update_monitor(state, predictions):
    """更新监控状态"""
    settled = [p for p in predictions
               if p.get("result") and p["result"].get("correct") is not None]

    # 最近 N 场
    last_10 = settled[-10:] if len(settled) >= 10 else settled
    correct_flags = [1 if p["result"]["correct"] else 0 for p in last_10]

    # 计算连续错误
    consec_wrong = 0
    for flag in reversed(correct_flags):
        if flag == 0:
            consec_wrong += 1
        else:
            break

    acc_all, n_all = compute_accuracy(settled)
    acc_l10, n_l10 = compute_accuracy(settled, 10)

    state["consecutive_wrong"] = consec_wrong
    state["last_n_correct"] = correct_flags[-10:] if len(correct_flags) > 10 else correct_flags
    state["accuracy_last_10"] = round(acc_l10, 4)
    state["accuracy_all"] = round(acc_all, 4)

    # 触发检查
    if n_l10 >= state["min_samples"] and not state["frozen"]:
        if acc_l10 < state["accuracy_baseline"] and consec_wrong >= state["consecutive_below_baseline"]:
            state["frozen"] = True
            state["freeze_reason"] = (
                f"最近{len(last_10)}场命中率{acc_l10:.0%}低于基线{state['accuracy_baseline']:.0%},"
                f"连续{consec_wrong}场错误"
            )
            state["freeze_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            safe_print(f"\n  🚨 模型已自动冻结！")
            safe_print(f"  原因: {state['freeze_reason']}")
            safe_print(f"  建议: 运行校准后复盘，确认问题后再解冻")

    save_state(state)
    return state


def main():
    import argparse
    parser = argparse.ArgumentParser(description="模型冻结监控器")
    parser.add_argument("--freeze", action="store_true", help="手动冻结")
    parser.add_argument("--unfreeze", action="store_true", help="解冻")
    parser.add_argument("--status", action="store_true", help="查看当前状态")
    parser.add_argument("--baseline", type=float, default=None, help="设置基线命中率")
    args = parser.parse_args()

    state = load_state()

    if args.freeze:
        state["frozen"] = True
        state["freeze_reason"] = "手动触发冻结"
        state["freeze_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_state(state)
        safe_print("  🚨 模型已手动冻结")
        return

    if args.unfreeze:
        state["frozen"] = False
        state["freeze_reason"] = ""
        state["unfreeze_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        state["consecutive_wrong"] = 0
        save_state(state)
        safe_print("  ✅ 模型已解冻")
        return

    if args.baseline is not None:
        state["accuracy_baseline"] = args.baseline
        save_state(state)
        safe_print(f"  基线命中率已设为 {args.baseline:.0%}")
        return

    # 默认：更新并显示状态
    predictions = load_predictions()
    state = update_monitor(state, predictions)

    safe_print("=" * 60)
    safe_print("  模型冻结监控器 v1.0 — P3.3")
    safe_print("=" * 60)

    status_icon = "🧊 已冻结" if state["frozen"] else "✅ 正常"
    safe_print(f"\n  状态: {status_icon}")
    if state["frozen"]:
        safe_print(f"  原因: {state['freeze_reason']}")
        safe_print(f"  冻结时间: {state['freeze_time']}")
    else:
        safe_print(f"  全部命中率: {state['accuracy_all']:.1%}")
        safe_print(f"  最近10场:   {state['accuracy_last_10']:.1%}")
        safe_print(f"  连续错误:   {state['consecutive_wrong']} 场")
        safe_print(f"  基线:       {state['accuracy_baseline']:.0%}")

        # 健康指示
        l10 = state["accuracy_last_10"]
        if l10 >= 0.70:
            safe_print(f"  健康状态: ✅ 良好")
        elif l10 >= 0.60:
            safe_print(f"  健康状态: ⚠️ 边缘 ({l10:.0%} < 70%)")
        else:
            wrong_needed = state["consecutive_below_baseline"] - state["consecutive_wrong"]
            safe_print(f"  健康状态: 🔴 需要注意 (再错{wrong_needed}场将触发冻结)")

        # 最近正确/错误序列
        flags = state["last_n_correct"]
        seq = "".join(["🟢" if f else "🔴" for f in flags])
        safe_print(f"  最近序列: {seq}")
        safe_print(f"\n  建议: 将 freeze_monitor.py 加入预测管线")
        safe_print(f"        每次预测后调用: python freeze_monitor.py")

    safe_print(f"\n  上次检查: {state.get('last_checked', 'N/A')}")


if __name__ == "__main__":
    main()
