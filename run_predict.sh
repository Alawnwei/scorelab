#!/usr/bin/env bash
# ============================================================
# 统一预测启动器 — 单入口：预测 → 记录 → 监控 → 校准
# ============================================================
# 用法:
#   bash run_predict.sh --home "西班牙" --away "佛得角" --league wm26
#                                                          预测(完整系统1引擎)
#   bash run_predict.sh --all "西班牙" "佛得角" wm26       预测 + 进入全能监控
#   bash run_predict.sh --watch                            全能监控(60s循环)
#   bash run_predict.sh --status                           仪表盘(待赛+结果+校准)
#   bash run_predict.sh --refresh-odds                     刷新一次待赛赔率
#   bash run_predict.sh --clv                              CLV追踪
#   bash run_predict.sh --calibration                      校准报告
#   bash run_predict.sh --dashboard                        可视化看板(HTML)
#   bash run_predict.sh --list                             列出所有预测
# ============================================================
set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/c/Users/Huawei/AppData/Local/Programs/Python/Python313/python.exe"
DB_PY="$BASE_DIR/skill/prediction_db.py"

# 检测可用的 python
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

show_help() {
    sed -n 's/^# //p; s/^#$//p' "$0"
    exit 0
}

# ============================================================
# 子命令: 赛后自动回填 (watch mode)
# ============================================================
watch_mode() {
    echo "=== 赛后结果自动回填 (每60秒检查) ==="
    echo "按 Ctrl+C 停止"
    echo ""
    while true; do
        # 从 auto_results 同步
        "$PYTHON" "$DB_PY" --sync-results 2>&1 | tail -3
        # 从 datafc 同步（如果可用）
        "$PYTHON" "$DB_PY" --sync-datafc wm26 2>&1 | tail -3
        sleep 60
    done
}

# ============================================================
# 子命令: 运行预测并记录
# ============================================================
run_prediction() {
    local home="$1"
    local away="$2"
    local league="$3"
    local date_str="$4"

    echo "=========================================="
    echo "  系统1预测引擎 (v2.0)"
    echo "  $home vs $away ($league)"
    echo "=========================================="

    # 调用统一的 predict.py（完整七维评分 + NB + WVR + 三级漏斗）
    "$PYTHON" "$BASE_DIR/skill/predict.py" \
        --home "$home" --away "$away" --league "$league" --force 2>&1

    echo ""
    echo "=========================================="
    echo "  预测完成"
    echo "  详情: $BASE_DIR/预测数据/足球预测-$date_str-${home}vs${away}.md"
    echo "=========================================="
}

# ============================================================
# 主入口
# ============================================================
if [ $# -eq 0 ]; then
    show_help
fi

case "$1" in
    --home)
        home="$2"
        away="$4"
        league="${6:-wm26}"
        date_str="${8:-$(date +%Y-%m-%d)}"
        run_prediction "$home" "$away" "$league" "$date_str"
        ;;
    --all)
        # 用法: --all "主队" "客队" [联赛]
        home="$2"
        away="$3"
        league="${4:-wm26}"
        date_str="$(date +%Y-%m-%d)"
        run_prediction "$home" "$away" "$league" "$date_str"
        echo ""
        echo "进入全能监控模式 (Ctrl+C停止)..."
        sleep 3
        "$PYTHON" "$DB_PY" --watch
        ;;
    --status)
        echo "=== 预测仪表盘 ==="
        echo ""
        echo "--- 待赛预测 ---"
        "$PYTHON" "$DB_PY" --report 2>&1 | grep -E "pending|待赛|方向|P_final" | head -10
        echo ""
        echo "--- 最新校准 ---"
        "$PYTHON" "$DB_PY" --calibration 2>&1 | tail -5
        echo ""
        echo "--- CLV ---"
        "$PYTHON" "$DB_PY" --track-clv 2>&1 | tail -3
        ;;
    --watch)
        "$PYTHON" "$DB_PY" --watch
        ;;
    --calibration)
        "$PYTHON" "$DB_PY" --calibration
        ;;
    --dashboard)
        "$PYTHON" "$DB_PY" --dashboard
        ;;
    --list|--report)
        "$PYTHON" "$DB_PY" --report
        ;;
    --check)
        "$PYTHON" "$DB_PY" --check
        ;;
    --backfill)
        "$PYTHON" "$DB_PY" --backfill
        ;;
    --sync)
        "$PYTHON" "$DB_PY" --sync-results
        ;;
    --refresh-odds)
        "$PYTHON" "$DB_PY" --refresh-odds
        ;;
    --clv|--track-clv)
        "$PYTHON" "$DB_PY" --track-clv
        ;;
    *)
        show_help
        ;;
esac
