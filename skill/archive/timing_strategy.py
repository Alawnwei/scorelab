#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投注时机策略 v1.0
解决：什么时候买？——从"预测"到"出手"的完整流程
"""
import sys, json, os
from datetime import datetime, timedelta

def p(text):
    try:
        print(text)
    except:
        print(str(text).encode('utf-8', errors='replace').decode('gbk', errors='replace'))

class TimingStrategy:
    """投注时机策略引擎"""

    # 推荐出手时机
    RECOMMEND = {
        "early": {"window": "T-48h~T-24h", "label": "早期出手", "desc": "赔率最优，但信息最少"},
        "mid": {"window": "T-24h~T-3h", "label": "中期出手", "desc": "平衡赔率和信息量"},
        "late": {"window": "T-3h~T-0.5h", "label": "临场出手", "desc": "信息最多（首发/伤病/天气）"},
        "live": {"window": "比赛中", "label": "现场出手", "desc": "观察实际表现后决策"},
    }

    @staticmethod
    def suggest(odds_first, odds_current, ev_first, ev_current, hours_to_kickoff):
        """根据赔率变化推荐出手时机
        Args:
            odds_first: 首次看到的赔率
            odds_current: 当前赔率
            ev_first: 首次计算时的+EV%
            ev_current: 当前+EV%
            hours_to_kickoff: 距离比赛还有多少小时
        Returns:
            dict: 建议
        """
        if not odds_first or not odds_current:
            return {"action": "等待", "reason": "数据不足"}

        change = (odds_current - odds_first) / odds_first * 100  # 赔率变动%
        ev_change = ev_current - ev_first  # +EV变动

        p(f"\n{'='*60}")
        p(f"投注时机分析")
        p(f"{'='*60}")
        p(f"  首次赔率: {odds_first:.2f} (+EV {ev_first:+.1f}%)")
        p(f"  当前赔率: {odds_current:.2f} (+EV {ev_current:+.1f}%)")
        p(f"  赔率变动: {change:+.1f}%")
        p(f"  +EV变动:  {ev_change:+.1f}%")
        p(f"  距离比赛: {hours_to_kickoff:.0f}小时")
        p(f"")

        # 场景判断
        if ev_current < 5:
            return {"action": "放弃", "reason": f"+EV已降到{ev_current:.1f}%，不值得出手"}

        if change < -3 and ev_change > 0:
            # 赔率下降，+EV上升 → 市场在朝你有利的方向走
            return {"action": "观望", "reason": f"赔率在降({change:.1f}%)，+EV在涨({ev_change:+.1f}%)，等接近-5%再出手"}

        if change > 3 and ev_change < -3:
            # 赔率上升，+EV下降 → 你的价值在消失
            if ev_current >= 10:
                return {"action": "立即出手", "reason": f"赔率在涨({change:+.1f}%)，价值在消失，现在出手锁定剩余+EV"}
            else:
                return {"action": "放弃", "reason": f"赔率涨了{change:.1f}%，+EV只剩{ev_current:.1f}%，不值得"}

        if abs(change) < 3 and ev_current >= 10:
            # 赔率稳定，+EV充足
            if hours_to_kickoff > 24:
                return {"action": "等首发", "reason": f"赔率稳定，+EV{ev_current:.1f}%，但还有{hours_to_kickoff:.0f}小时，等首发出来后确认"}
            elif hours_to_kickoff > 3:
                return {"action": "可以出手", "reason": f"赔率稳定({change:+.1f}%)，+EV{ev_current:.1f}%，距离开赛{hours_to_kickoff:.0f}小时，时机合适"}
            else:
                return {"action": "立即出手", "reason": f"临场赔率稳定，+EV{ev_current:.1f}%，距离开赛不到3小时，出手"}

        return {"action": "观望", "reason": "情况不明，继续观察"}

    @staticmethod
    def plan(match_name, prediction, probs, odds_h, odds_d, odds_a):
        """生成完整的2-1-2节奏方案"""
        p(f"\n{'='*60}")
        p(f"推荐出手方案 — {match_name}")
        p(f"方向: {prediction}")
        p(f"{'='*60}")

        p(f"""
┌─────────────────────────────────────────────────────────┐
│                    2-1-2 出手节奏                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  【第一阶段】T-48h 首次分析                              │
│  动作: 获取初始赔率，计算+EV                             │
│  决策: +EV > 15% → 可以早出手锁价                       │
│        +EV < 15% → 等待                                 │
│                                                         │
│  【第二阶段】T-24h 二次确认                              │
│  动作: 对比赔率变化，验证+EV是否还在                     │
│  决策: 赔率降(利你) → 继续等                            │
│        赔率涨(不利) → 考虑提前出手                       │
│                                                         │
│  【第三阶段】T-2h 临场检查                               │
│  动作: 首发公布！确认关键球员是否上场                    │
│  决策: +EV仍 > 10% → 出手                               │
│        +EV < 10% → 放弃                                 │
│                                                         │
│  【第四阶段】T+0 记录CLV                                │
│  动作: 记录开赛前最终赔率，算CLV                        │
│  决策: CLV > 0% → 你的判断比市场准                      │
│        CLV < 0% → 你的判断有问题                        │
│                                                         │
└─────────────────────────────────────────────────────────┘

当前赔率参考:
  主胜: {odds_h} | 平局: {odds_d} | 客胜: {odds_a}
  模型概率: {probs[0]}% / {probs[1]}% / {probs[2]}%

建议:
  1. 去 Bet365/1xbet 查看当前赔率
  2. 和系统2算出来的+EV对比
  3. 按上述节奏在T-2h做最终决定
""")

        return {
            "match": match_name,
            "checkpoints": ["T-48h首次分析", "T-24h二次确认", "T-2h临场检查", "T+0记录CLV"],
            "current_ev": "未知（需输入当前赔率）"
        }


# ============================================================
# 演示
# ============================================================
if __name__ == "__main__":
    p("投注时机策略引擎")
    p("=" * 60)

    # 生成方案
    TimingStrategy.plan("阿根廷 vs 佛得角", "主胜", (87, 8, 5), 1.15, 7.00, 15.00)

    # 赔率变化场景模拟
    p("\n\n赔率变化场景分析:")
    p("-" * 40)

    scenarios = [
        ("赔率稳定", 2.10, 2.08, 15.0, 14.5, 20),
        ("赔率暴跌(利你)", 2.10, 1.85, 15.0, 20.5, 20),
        ("赔率暴涨(不利)", 2.10, 2.40, 15.0, 8.0, 20),
        ("临场稳定", 2.10, 2.10, 12.0, 12.0, 2),
    ]

    for name, odds_f, odds_c, ev_f, ev_c, hours in scenarios:
        r = TimingStrategy.suggest(odds_f, odds_c, ev_f, ev_c, hours)
        p(f"  {name}: {r['action']} — {r['reason'][:50]}...")
        p("")
