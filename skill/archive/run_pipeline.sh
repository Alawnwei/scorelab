#!/bin/bash
# 一键流水线：预测→缓存→赛后回填→校准→PnL (v2.0)
# 用法: bash run_pipeline.sh "主队" "客队" [联赛]
# 示例: bash run_pipeline.sh "阿根廷" "佛得角" wm26

HOME_TEAM=$1
AWAY_TEAM=$2
LEAGUE=${3:-wm26}
BASE_DIR="C:/Users/Huawei/Downloads/电商/足球分析"

echo "=========================================="
echo "一键流水线 v2.0: $HOME_TEAM vs $AWAY_TEAM ($LEAGUE)"
echo "=========================================="

# 第1步：系统1预测（自动缓存赔率+λ到本地）
echo ""
echo "[1/3] 系统1预测..."
python "$BASE_DIR/skill/predict.py" --home "$HOME_TEAM" --away "$AWAY_TEAM" --league "$LEAGUE"
echo "  OK"

# 第2步：赛后结果自动回填（匹配已完场的结果）
echo ""
echo "[2/3] 赛后结果自动回填..."
python "$BASE_DIR/skill/sync_results.py"
echo "  OK"

# 第3步：校准+PnL分析（只有已结算的比赛才纳入统计）
echo ""
echo "[3/3] 校准+PnL分析..."
python "$BASE_DIR/skill/calibration_analysis.py"
python "$BASE_DIR/skill/pnl_analysis.py"
echo "  OK"

echo ""
echo "=========================================="
echo "流水线完成"
echo "预测文件: 预测数据/足球预测-$(date +%F)-$HOME_TEAM""vs""$AWAY_TEAM.md"
echo "=========================================="
