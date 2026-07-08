#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统2：投注决策引擎 v2.0 — 多市场版
支持: 1X2 / 亚洲让球盘 / 大小球 / 双方进球
职业赌徒模式: 1/4凯利 + +EV阈值10% + CLV追踪 + 出赛率控制
"""
import sys, math, os, subprocess, json
from datetime import datetime

def p(text):
    try:
        print(text)
    except:
        print(str(text).encode('utf-8', errors='replace').decode('gbk', errors='replace'))

class BettingEngine:
    """系统2投注引擎 v2.0"""

    def __init__(self, bankroll=10000, mode="pro", match_name="", league="", temperature=1.60):
        """
        mode: "pro" = 职业模式(1/4凯利, +EV阈值10%)
              "normal" = 普通模式(半凯利, +EV阈值5%)
        match_name: 比赛名称 "主队 vs 客队"（用于持久化记录）
        league: 联赛名称
        temperature: 温度缩放(1.0=不缩放, 1.60=当前最优)
        """
        self.bankroll = bankroll
        self.mode = mode
        self.temperature = temperature
        self.match_name = match_name
        self.league = league
        self.daily_bet = 0
        self.daily_pnl = 0
        self.consecutive_losses = 0
        self.bet_history = []
        self.total_recommended = 0  # 总出赛场次

        # 路径（用于持久化记录）
        self._base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._skill_dir = os.path.join(self._base_dir, "skill")

        # 风控参数
        self.max_bet_pct = 0.10
        self.max_daily_pct = 0.30
        self.max_daily_loss_pct = 0.10
        self.max_consecutive_losses = 3

        # 职业模式 vs 普通模式
        if mode == "pro":
            self.min_ev = 10        # +EV阈值10%
            self.kelly_frac = 0.25  # 1/4凯利
        else:
            self.min_ev = 5         # +EV阈值5%
            self.kelly_frac = 0.50  # 半凯利

    # ============================================================
    # 概率工具
    # ============================================================
    # ============================================================
    # λ管理：支持外部传入真实λ
    # ============================================================
    def set_lambda(self, lam_h, lam_a):
        """设置外部λ值（来自系统1的xg_estimator）
        调用此方法后，后续所有亚盘/大小球计算使用此λ而非内部估算
        """
        self._lam_h = lam_h
        self._lam_a = lam_a
        return self

    def _get_lam(self, lam_h=None, lam_a=None):
        """获取λ：优先使用参数或set_lambda设置的，最后fallback到内部估算"""
        if lam_h is not None and lam_a is not None:
            return lam_h, lam_a
        if hasattr(self, '_lam_h') and hasattr(self, '_lam_a'):
            return self._lam_h, self._lam_a
        return None, None

    # ============================================================
    # 概率工具（负二项分布替代泊松）
    # ============================================================
    @staticmethod
    def nbinom_prob(k, lam, theta=8):
        """负二项分布概率: 替代泊松，更适合足球数据（方差>均值）
        θ=8为默认值（杯赛典型值），θ越大越接近泊松
        """
        if theta > 100:  # 近似泊松
            return math.exp(-lam) * (lam ** k) / math.factorial(k)
        # 负二项PMF: Γ(k+θ)/(k!×Γ(θ)) × (θ/(θ+λ))^θ × (λ/(θ+λ))^k
        log_p = math.lgamma(k + theta) - math.lgamma(k + 1) - math.lgamma(theta)
        log_p += theta * math.log(theta / (theta + lam))
        log_p += k * math.log(lam / (theta + lam))
        return math.exp(log_p)

    @staticmethod
    def _temperature_scale(probs, T):
        """温度缩放: 对 (p_h, p_d, p_a) 应用 softmax(logits/T)

        T=1.0 → 不变
        T>1.0 → 压平(降低自信), T<1.0 → 锐化(提高自信)
        """
        if T == 1.0 or not probs:
            return probs
        import math as _m
        logits = [_m.log(max(p / 100.0 if p > 1 else p, 0.0001)) for p in probs]
        scaled = [l / T for l in logits]
        max_s = max(scaled)
        exps = [_m.exp(s - max_s) for s in scaled]
        s = sum(exps)
        return tuple(e / s for e in exps)

    @staticmethod
    def poisson_prob(k, lam):
        """泊松分布概率（保留作为备选）"""
        return math.exp(-lam) * (lam ** k) / math.factorial(k)

    def estimate_lambda(self, prob_h, prob_d, prob_a, total_goals):
        """从1X2概率+总进球估算两队λ（进球率）
        当没有系统1的真实λ时使用此方法
        """
        # 主队预期进球占比 ≈ 主胜概率
        home_ratio = prob_h / (prob_h + prob_a) if (prob_h + prob_a) > 0 else 0.5
        lam_h = total_goals * home_ratio
        lam_a = total_goals * (1 - home_ratio)
        adjust = total_goals / (lam_h + lam_a) if (lam_h + lam_a) > 0 else 1
        return lam_h * adjust, lam_a * adjust

    def score_distribution(self, lam_h=None, lam_a=None, max_goals=8):
        """计算比分分布（优先使用set_lambda传入的值）"""
        lam_h, lam_a = self._get_lam(lam_h, lam_a)
        if lam_h is None:
            return {}
        dist = {}
        total = 0
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                p_val = self.nbinom_prob(i, lam_h) * self.nbinom_prob(j, lam_a)
                dist[(i, j)] = p_val
                total += p_val
        for k in dist:
            dist[k] /= total
        return dist

    def prob_over(self, lam_h=None, lam_a=None, line=2.5):
        """P(总进球 > line)"""
        lam_h, lam_a = self._get_lam(lam_h, lam_a)
        if lam_h is None:
            return 0
        dist = self.score_distribution(lam_h, lam_a)
        return sum(p for (i,j), p in dist.items() if i + j > line)

    def prob_cover_handicap(self, lam_h=None, lam_a=None, hdp=-0.5):
        """P(主队覆盖让球盘) = P(主队净胜 > hdp)"""
        lam_h, lam_a = self._get_lam(lam_h, lam_a)
        if lam_h is None:
            return 0
        dist = self.score_distribution(lam_h, lam_a)
        return sum(p for (i,j), p in dist.items() if i - j > hdp)

    # ============================================================
    # 推水
    # ============================================================
    def vig_free_1x2(self, odds_h, odds_d, odds_a):
        """1X2推水"""
        raw = [1/o for o in [odds_h, odds_d, odds_a] if o and o > 0]
        total = sum(raw)
        return [p/total for p in raw]

    def vig_free_2way(self, odds_home, odds_away):
        """双选项推水（亚盘/大小球）"""
        raw = [1/o for o in [odds_home, odds_away] if o and o > 0]
        total = sum(raw)
        return [p/total for p in raw]

    # ============================================================
    # +EV计算
    # ============================================================
    def calc_ev(self, model_prob, market_odds, all_odds=None, market_type="1x2"):
        """计算+EV%（自动推水）

        Args:
            model_prob: 模型概率（%）
            market_odds: 要评估的选项赔率
            all_odds: 该市场所有选项赔率列表（用于精确推水）
                      e.g. [主胜, 平局, 客胜] 或 [大, 小]
                      不传则用市场默认推水率
            market_type: 市场类型 → 默认推水率
                        "1x2"=1.06, "asian"=1.04, "ou"=1.03,
                        "btts"=1.05, "jc"=1.12
        """
        # 市场默认推水率（当 all_odds 未提供时使用）
        DEFAULT_VIG = {
            "1x2": 1.06, "asian": 1.04, "ou": 1.03,
            "btts": 1.05, "jc": 1.12,
        }
        if all_odds and len(all_odds) >= 2:
            total_implied = sum(1/o for o in all_odds if o and o > 0)
            mip = (1 / market_odds) / total_implied * 100
        else:
            vig = DEFAULT_VIG.get(market_type, 1.05)
            mip = 1 / market_odds / vig * 100
        return (model_prob / mip - 1) * 100, mip

    def kelly(self, odds, prob):
        """凯利公式（按设定分数）"""
        prob_dec = prob / 100
        f = (odds * prob_dec - 1) / (odds - 1)
        if f < 0:
            return 0
        return f * self.kelly_frac

    # ============================================================
    # 各市场分析
    # ============================================================
    def analyze_1x2(self, match_name, prediction, odds_data, probs, total_goals=2.5):
        """1X2市场分析"""
        odds_h, odds_d, odds_a = odds_data
        prob_h, prob_d, prob_a = probs
        fair = self.vig_free_1x2(odds_h, odds_d, odds_a)

        # 温度缩放（T=1.60 校准概率）
        if self.temperature != 1.0:
            scaled = self._temperature_scale((prob_h, prob_d, prob_a), self.temperature)
            prob_h, prob_d, prob_a = [s * 100 if p > 1 else s for s, p in zip(scaled, (prob_h, prob_d, prob_a))]

        # 平局预测降级：平局是最难猜的结果，优先转为"不败"或跳过
        if prediction == "draw":
            if prob_h > 30:
                # 主胜概率尚可 → "主队不败(防平)"，覆盖主胜+平局
                model_prob = (prob_h + prob_d) * 100
                market_odds = odds_h  # 保守用主胜赔率
                ev_pct, mip = self.calc_ev(model_prob, market_odds, market_type="1x2")
                self.total_recommended += 1
                return self._build_result(match_name, "1X2-主队不败(防平)", market_odds,
                                          model_prob, mip, ev_pct, total_goals=total_goals)
            elif prob_a > 30:
                # 客胜概率尚可 → "客队不败(防平)"，覆盖客胜+平局
                model_prob = (prob_a + prob_d) * 100
                market_odds = odds_a  # 保守用客胜赔率
                ev_pct, mip = self.calc_ev(model_prob, market_odds, market_type="1x2")
                self.total_recommended += 1
                return self._build_result(match_name, "1X2-客队不败(防平)", market_odds,
                                          model_prob, mip, ev_pct, total_goals=total_goals)
            else:
                # 双方赢球概率都低 → 平局不值得猜，跳过
                return {"recommend":False,"reason":"平局预测: 双方赢面都低，跳过不猜",
                        "model_prob":prob_d*100,"mip":1/odds_d/1.03*100,"ev":0,"odds":odds_d,
                        "direction":"skip","kelly_pct":0,"bet_pct":0,"bet_amount":0,
                        "value_divergence":0}

        dir_map = {"home":"主胜","away":"客胜"}
        dir_idx = {"home":0,"away":2}
        idx = dir_idx[prediction]
        model_prob = [prob_h, prob_d, prob_a][idx] * 100
        market_odds = [odds_h, odds_d, odds_a][idx]
        ev_pct, mip = self.calc_ev(model_prob, market_odds, market_type="1x2")

        self.total_recommended += 1
        return self._build_result(match_name, f"1X2-{dir_map[prediction]}", market_odds,
                                  model_prob, mip, ev_pct, total_goals=total_goals)

    def analyze_asian(self, match_name, side, hdp, odds_home, odds_away, lam_h=None, lam_a=None):
        """亚洲让球盘分析（优先使用set_lambda传入的值）"""
        lam_h, lam_a = self._get_lam(lam_h, lam_a)
        if lam_h is None:
            return {"recommend":False,"reason":"λ未设置"}
        model_prob = self.prob_cover_handicap(lam_h, lam_a, hdp) * 100
        market_odds = odds_home if side == "home" else odds_away
        ev_pct, mip = self.calc_ev(model_prob, market_odds, market_type="asian")

        # 友好显示
        label = f"亚盘{'主' if side=='home' else '客'}{hdp:+.1f}"
        self.total_recommended += 1
        return self._build_result(f"{match_name} {label}", label, market_odds,
                                  model_prob, mip, ev_pct, lam_h=lam_h, lam_a=lam_a)

    def analyze_ou(self, match_name, line, odds_over, odds_under, lam_h=None, lam_a=None):
        """大小球分析（优先使用set_lambda传入的值）"""
        lam_h, lam_a = self._get_lam(lam_h, lam_a)
        if lam_h is None:
            return {"recommend":False,"reason":"λ未设置"}
        model_prob_over = self.prob_over(lam_h, lam_a, line) * 100
        ev_over, mip_over = self.calc_ev(model_prob_over, odds_over, market_type="ou")
        ev_under, mip_under = self.calc_ev(100 - model_prob_over, odds_under, market_type="ou")

        results = []
        self.total_recommended += 1

        # 大球
        if ev_over >= self.min_ev:
            r = self._build_result(f"{match_name} 大{line}", f"大{line}", odds_over,
                                   model_prob_over, mip_over, ev_over,
                                   lam_h=lam_h, lam_a=lam_a)
            results.append(r)

        # 小球
        if ev_under >= self.min_ev:
            r = self._build_result(f"{match_name} 小{line}", f"小{line}", odds_under,
                                   100-model_prob_over, mip_under, ev_under,
                                   lam_h=lam_h, lam_a=lam_a)
            results.append(r)

        if not results:
            return {"recommend":False,"reason":f"大小球{line}无+EV", "market":"over_under"}
        return results[0] if len(results) == 1 else results

    # ============================================================
    # 竞彩分析
    # ============================================================
    def analyze_jingcai(self, match_name, odds_hda, odds_rq, probs, lam_h, lam_a):
        """竞彩分析（固定让1球 + 高抽水）
        Args:
            odds_hda: (主胜赔率, 平局赔率, 客胜赔率)
            odds_rq: (让胜赔率, 让平赔率, 让负赔率)
            probs: 系统1概率 (主%, 平%, 客%)
            lam_h, lam_a: 预期进球率
        """
        vig = 1.12
        results = []
        self.total_recommended += 1
        odds_h, odds_d, odds_a = odds_hda
        prob_h, prob_d, prob_a = probs

        # 胜平负（跳过平局——猜平局不如猜不败，且竞彩抽水极高）
        for pred, idx, label in [("home",0,"主胜"),("away",2,"客胜")]:
            mp = [prob_h, prob_d, prob_a][idx]
            mo = [odds_h, odds_d, odds_a][idx]
            mip = 1 / mo / vig * 100
            ev = (mp / mip - 1) * 100
            if ev >= self.min_ev:
                results.append(self._build_result(f"{match_name} 竞彩-{label}", f"竞彩{label}", mo, mp, mip, ev))

        # 让球胜平负(固定让1球)
        dist = self.score_distribution(lam_h, lam_a)
        p_rq_h = sum(p for (i,j), p in dist.items() if i - j >= 2)
        p_rq_d = sum(p for (i,j), p in dist.items() if i - j == 1)
        p_rq_a = 1 - p_rq_h - p_rq_d
        rq_h, rq_d, rq_a = odds_rq

        for mp, odds, label in [(p_rq_h, rq_h, "让胜"), (p_rq_d, rq_d, "让平"), (p_rq_a, rq_a, "让负")]:
            prob = mp * 100
            mip = 1 / odds / vig * 100 if odds and odds > 0 else 0
            if mip == 0:
                continue
            ev = (prob / mip - 1) * 100
            if ev >= self.min_ev:
                results.append(self._build_result(f"{match_name} 竞彩-{label}", f"竞彩{label}", odds, prob, mip, ev))

        if not results:
            return {"recommend":False,"reason":"竞彩无+EV"}
        return results if len(results) > 1 else results[0]

    # 串关相关性折扣因子
    # 同联赛/同日的比赛存在正相关性（天气、裁判风格、轮换周期等）
    # 导致独立概率相乘高估串关真实概率
    CORRELATION_DISCOUNT = {
        "same_league_same_day": 0.85,   # 同联赛同天：高相关性
        "same_league_diff_day": 0.90,   # 同联赛不同天：中相关性
        "diff_league_same_day": 0.92,   # 不同联赛同天：中低相关性
        "diff_league_diff_day": 0.95,   # 不同联赛不同天：低相关性
    }

    @staticmethod
    def _parlay_correlation_factor(combo):
        """计算一组串关选场的相关性折扣系数

        实际串关概率 < 独立概率乘积，因为同联赛/同日的比赛存在
        正相关性（天气、裁判风格、赛程密度等）。
        返回折扣因子 (0,1] 乘以独立概率。

        默认保守估计：同联赛不同天，相关性折扣 0.90^(n-1)
        """
        n = len(combo)
        if n <= 1:
            return 1.0
        return BettingEngine.CORRELATION_DISCOUNT["same_league_diff_day"] ** (n - 1)

    def optimize_parlay(self, picks, max_legs=3, total_bankroll=10000):
        """串关优化器 v2.0 — 加入相关性折扣

        v2.0 修复：
        - 串关概率不再简单相乘，加入相关性折扣因子
        - 串关抽水随注数增加（书商对多串抽水更高）
        """
        from itertools import combinations
        valid = [p for p in picks if isinstance(p, dict) and p.get("recommend") and p.get("odds",0) > 0]
        if len(valid) < 2:
            return {"recommend":False,"reason":"至少需要2场推荐"}

        best, best_odds = None, 0
        best_ev = -999

        for n in range(2, min(max_legs + 1, len(valid) + 1)):
            # 串关额外抽水：书商对多串抽水高于单关累计
            # 2串=1.12, 3串=1.15, 4串=1.18, 5+=1.20
            parlay_vig = {2: 1.12, 3: 1.15, 4: 1.18}.get(n, 1.20)

            for combo in combinations(valid, n):
                parlay_odds = 1
                for p in combo:
                    parlay_odds *= p["odds"]

                # 独立概率相乘
                indep_prob = 1
                for p in combo:
                    indep_prob *= (p.get("model_prob", 50) / 100)

                # 相关性折扣
                corr_factor = self._parlay_correlation_factor(combo)
                adj_prob = indep_prob * corr_factor

                # 串关 EV（含相关性折扣 + 串关抽水）
                parlay_ev = (adj_prob * parlay_odds / parlay_vig - 1) * 100

                if parlay_ev > best_ev:
                    best, best_odds, best_ev = combo, parlay_odds, parlay_ev
                    best_indep = indep_prob
                    best_corr = corr_factor
                    best_adj = adj_prob

        if not best or best_ev < 5:
            return {"recommend":False,"reason":f"无正EV串关 (最优={best_ev:.1f}%)"}
        stake = total_bankroll * 0.03  # 串关仓位保守至3%
        detail = "; ".join([f"{p.get('direction','?')}@{p.get('odds','?')}" for p in best])
        print(f"\n串关推荐: {detail} | {len(best)}串1 @{best_odds:.2f} | +EV{best_ev:.1f}% | {stake:.0f}元")
        print(f"  独立概率: {best_indep:.4f} → 相关性折扣×{best_corr:.3f} → 调整概率: {best_adj:.4f}")

        # 持久化串关推荐（每个单关分别记录）
        for p in best:
            self._save_recommendation(p.get("direction","串关"), p.get("direction",""),
                                     p.get("odds",0), p.get("ev",0))
        return {"recommend":True,"type":f"{len(best)}串1","odds":best_odds,"ev":round(best_ev,1),"stake":stake}

    # ============================================================
    # 风控
    # ============================================================
    def risk_check(self, bet_amount):
        checks = []
        checks.append(("单笔下注", bet_amount <= self.bankroll*self.max_bet_pct, f"{bet_amount:.0f}<={self.bankroll*self.max_bet_pct:.0f}"))
        checks.append(("日累计", self.daily_bet+bet_amount <= self.bankroll*self.max_daily_pct, f"{self.daily_bet+bet_amount:.0f}<={self.bankroll*self.max_daily_pct:.0f}"))
        checks.append(("当日亏损", self.daily_pnl >= -self.bankroll*self.max_daily_loss_pct, f"{self.daily_pnl:.0f}>={-self.bankroll*self.max_daily_loss_pct:.0f}"))
        checks.append(("连错", self.consecutive_losses < self.max_consecutive_losses, f"{self.consecutive_losses}<{self.max_consecutive_losses}"))
        return all(c[1] for c in checks), checks

    # ============================================================
    # 统一输出
    # ============================================================
    def _build_result(self, label, direction, odds, model_prob, mip, ev_pct,
                      total_goals=None, lam_h=None, lam_a=None):
        """构建统一结果"""
        kelly = self.kelly(odds, model_prob)
        bet_pct = min(kelly, self.max_bet_pct)
        bet_amount = self.bankroll * bet_pct

        # 价值分歧检测
        # P_final < 50% 但 +EV > 20% → 高+EV来自市场分歧而非模型确信
        value_divergence = (model_prob < 50 and ev_pct > 20)
        div_level = 0
        if value_divergence:
            if model_prob < 30 and ev_pct > 30:
                div_level = 2  # ⚠️⚠️ 高风险
            else:
                div_level = 1  # ⚠️ 注意

        div_tag = {0: "", 1: " [价值分歧⚠️]", 2: " [价值分歧⚠️⚠️]"}[div_level]
        div_warn = {0: "", 1: "\n  ⚠️ 模型概率<50%，高+EV来自市场分歧，非模型高确信",
                     2: "\n  ⚠️⚠️ 模型概率<30%，+EV虚高，注码请严格控制"}[div_level]

        p(f"\n{'='*60}")
        p(f"系统2 — {label}")
        p(f"{'='*60}")
        p(f"  模型概率: {model_prob:.1f}% | 市场MIP: {mip:.1f}%")
        p(f"  +EV: {ev_pct:+.1f}% ({'通过' if ev_pct>=self.min_ev else '不通过'}){div_tag}")
        if total_goals:
            p(f"  预期总进球: {total_goals:.1f}")
        if lam_h and lam_a:
            p(f"  预期进球分布: 主{lam_h:.2f} 客{lam_a:.2f}")

        if ev_pct < self.min_ev:
            p(f"  +EV {ev_pct:.1f}% < 阈值{self.min_ev}% -> 不推荐")
            return {"recommend":False,"reason":f"+EV{ev_pct:.1f}%低于阈值", "market":"unknown",
                    "model_prob":model_prob,"mip":mip,"ev":ev_pct,"odds":odds,
                    "direction":direction,"kelly_pct":0,"bet_pct":0,"bet_amount":0,
                    "value_divergence":div_level}

        p(f"\n  凯利({self.kelly_frac*100:.0f}分之1): {kelly*100:.1f}%")
        p(f"  仓位(上限{self.max_bet_pct*100:.0f}%): {bet_pct*100:.1f}%")
        p(f"  金额: {bet_amount:.0f}元")

        # 风控
        ok, checks = self.risk_check(bet_amount)
        for name, passed, detail in checks:
            p(f"  {'OK' if passed else 'FAIL'} {name}: {detail}")

        if not ok:
            p(f"\n  风控未通过 -> 不下注")
            return {"recommend":False,"reason":"风控未通过"}

        p(f"\n  >>> {direction} @{odds} | {bet_amount:.0f}元 | +EV{ev_pct:+.1f}%{div_tag}")
        if div_warn:
            p(f"  {div_warn.strip()}")

        # 持久化推荐记录到 pnl_records.json（透传真实 P_final）
        self._save_recommendation(label, direction, odds, ev_pct, p_final=model_prob / 100)

        return {
            "recommend":True, "direction":direction, "odds":odds,
            "model_prob":model_prob, "mip":mip, "ev":ev_pct,
            "kelly_pct":kelly*100, "bet_pct":bet_pct*100,
            "bet_amount":bet_amount,
            "value_divergence":div_level,
        }

    # ============================================================
    # CLV + 记录 + 报告 + 持久化
    # ============================================================

    def _parse_match_name(self):
        """从 match_name 解析主客队名（格式: "主队 vs 客队" 或 "主队 vs 客队 附加信息"）"""
        if not self.match_name:
            return "", ""
        # 去掉附加信息（亚盘/大小球等）
        base = self.match_name.split(" 亚盘")[0].split(" 大")[0].split(" 小")[0].split(" 竞彩")[0]
        if " vs " in base:
            parts = base.split(" vs ", 1)
            return parts[0].strip(), parts[1].strip()
        return "", ""

    def _save_recommendation(self, label, direction, odds, ev_pct, p_final=None):
        """将系统2推荐持久化到 pnl_records.json"""
        home, away = self._parse_match_name()
        if not home or not away:
            return
        # 使用透传的真实 P_final，无可用的才回退到硬编码
        if p_final is None:
            if "主胜" in direction or "主" in direction:
                p_final = 0.65
            elif "客胜" in direction or "客" in direction:
                p_final = 0.35
            elif "平" in direction:
                p_final = 0.50
            elif "大" in direction:
                p_final = 0.55
            elif "小" in direction:
                p_final = 0.45
            else:
                p_final = 0.50

        try:
            pnl_tracker = os.path.join(self._skill_dir, "pnl_tracker.py")
            cmd = (
                f"python \"{pnl_tracker}\" --record "
                f"--home \"{home}\" --away \"{away}\" "
                f"--p {p_final:.3f} --odds {odds} "
                f"--direction \"系统2-{direction}\" --league \"{self.league}\" "
                f"--ev {ev_pct} --confidence \"系统2\" "
                f"--result-v pending"
            )
            subprocess.run(cmd, shell=True, timeout=15,
                          capture_output=True, text=True)
        except Exception:
            pass  # 持久化失败不影响主流程
    def record_result(self, bet_result, won, final_odds=None):
        """记录结果（含CLV）"""
        if won:
            profit = bet_result["bet_amount"] * (bet_result["odds"] - 1)
            self.daily_pnl += profit
            self.consecutive_losses = 0
        else:
            profit = -bet_result["bet_amount"]
            self.daily_pnl += profit
            self.consecutive_losses += 1

        clv = None
        if final_odds and bet_result["odds"]:
            clv = (bet_result["odds"] - final_odds) / final_odds * 100

        bet_result["won"] = won
        bet_result["pnl"] = profit
        bet_result["clv"] = clv
        bet_result["timestamp"] = datetime.now()
        self.bet_history.append(bet_result)
        return bet_result

    def report(self):
        """投注报告"""
        if not self.bet_history:
            return "暂无记录"

        total_bet = sum(r["bet_amount"] for r in self.bet_history)
        total_pnl = sum(r["pnl"] for r in self.bet_history)
        wins = sum(1 for r in self.bet_history if r.get("won"))
        total = len(self.bet_history)

        p(f"\n{'='*60}")
        p(f"投注报告 (模式: {self.mode})")
        p(f"{'='*60}")
        p(f"  总下注: {total}笔 | 总投入: {total_bet:.0f}元")
        p(f"  总盈亏: {total_pnl:+.0f}元 | ROI: {total_pnl/total_bet*100:+.1f}%")
        p(f"  命中率: {wins}/{total} = {wins/total*100:.1f}%")
        p(f"  出赛率: {total}/{self.total_recommended} = {total/max(self.total_recommended,1)*100:.1f}%")
        p(f"  当前资金: {self.bankroll + total_pnl:.0f}元")
        p(f"  模式: {'职业(+EV>=10%, 1/4凯利)' if self.mode=='pro' else '普通(+EV>=5%, 半凯利)'}")

        # CLV
        clv_records = [r for r in self.bet_history if r.get("clv") is not None]
        if clv_records:
            avg_clv = sum(r["clv"] for r in clv_records) / len(clv_records)
            p(f"  平均CLV: {avg_clv:+.1f}%")
            if avg_clv > 0:
                p(f"  -> CLV为正，长期盈利概率高")
            else:
                p(f"  -> CLV为负，需要检查下注时机")

        return {"total":total,"won":wins,"pnl":total_pnl,"roi":total_pnl/total_bet*100}


    def auto_jingcai(self, keyword, probs, total_goals=2.5):
        """自动从竞彩官方API获取赔率并分析"""
        import subprocess, json
        try:
            script = os.path.join(os.path.dirname(__file__), "竞彩查询.py")
            r = subprocess.run(["python", script, keyword, "--json"],
                capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace")
            matches = json.loads(r.stdout)
            if not matches:
                return {"error": f"竞彩未找到: {keyword}"}
            m = matches[0]
            name = f"{m['home']} vs {m['away']}"
            odds_hda = (m['odds_h'], m['odds_d'], m['odds_a'])
            odds_rq = (m['rq_h'], m['rq_d'], m['rq_a'])
            lam_h, lam_a = self.estimate_lambda(probs[0], probs[1], probs[2], total_goals)
            self.set_lambda(lam_h, lam_a)
            print(f"\n  [竞彩官方] {name}")
            print(f"  胜平负: {odds_hda[0]}/{odds_hda[1]}/{odds_hda[2]}")
            print(f"  让球:   {odds_rq[0]}/{odds_rq[1]}/{odds_rq[2]}")
            return self.analyze_jingcai(name, odds_hda, odds_rq, probs, lam_h, lam_a)
        except Exception as e:
            return {"error": f"竞彩失败: {e}"}


# ============================================================
# 演示：三市场对比
# ============================================================
if __name__ == "__main__":
    engine = BettingEngine(bankroll=10000, mode="pro")

    p(f"{'='*70}")
    p(f"系统2 v2.0 — 多市场投注决策 (职业模式)")
    p(f"模式: +EV阈值>=10%, 1/4凯利, CLV追踪")
    p(f"{'='*70}")

    # 模拟一场比赛: 阿根廷 vs 佛得角
    p(f"\n{'='*70}")
    p(f"示例: 阿根廷 vs 佛得角")
    p(f"{'='*70}")

    # 系统1输出
    prob_h, prob_d, prob_a = 87, 8, 5   # 1X2概率(%)
    total_goals = 2.5                     # 预期总进球
    lam_h, lam_a = engine.estimate_lambda(prob_h, prob_d, prob_a, total_goals)

    # 1X2市场
    p(f"\n--- 1X2市场 ---")
    r1 = engine.analyze_1x2("阿根廷vs佛得角", "home",
                            (1.15, 7.00, 15.00), (87, 8, 5), total_goals)

    # 亚盘市场（实际赔率: 阿根廷-1.25 @1.80）
    p(f"\n--- 亚洲让球盘 ---")
    r2 = engine.analyze_asian("阿根廷vs佛得角", "home", -1.25, 1.80, 2.05, lam_h, lam_a)

    # 大小球市场（实际赔率: 大2.5 @2.00）
    p(f"\n--- 大小球 ---")
    r3 = engine.analyze_ou("阿根廷vs佛得角", 2.5, 2.00, 1.85, lam_h, lam_a)

    # 统计
    p(f"\n{'='*70}")
    p(f"三市场对比")
    p(f"{'='*70}")
    for name, r in [("1X2主胜", r1), ("亚盘-1.25", r2), ("大小球", r3)]:
        if isinstance(r, list):
            for sub in r:
                ev = sub.get("ev", 0)
                p(f"  {name}: {'推荐' if sub.get('recommend') else '不推荐'} (+EV{ev:+.1f}%)")
        else:
            ev = r.get("ev", 0) if r else 0
            rec = r.get("recommend", False) if r else False
            p(f"  {name}: {'推荐' if rec else '不推荐'} (+EV{ev:+.1f}%)")
