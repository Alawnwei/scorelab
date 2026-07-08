#!/bin/bash
# ============================================================
# 一键部署：预测 → 看板 → 推送 GitHub
# 用法: bash deploy.sh <主队> <客队> [联赛]
# 示例: bash deploy.sh "葡萄牙" "西班牙" wm26
# ============================================================

if [ $# -lt 2 ]; then
    echo ""
    echo "❌ 用法: bash deploy.sh <主队> <客队> [联赛]"
    echo "   示例: bash deploy.sh \"葡萄牙\" \"西班牙\" wm26"
    echo ""
    exit 1
fi

HOME="$1"
AWAY="$2"
LEAGUE="${3:-wm26}"
DATE=$(date +%Y-%m-%d)
START=$(date +%s)

echo ""
echo "═══════════════════════════════════════════"
echo "  ⚽ 一键部署 — $HOME vs $AWAY"
echo "  📅 $DATE | 🏆 $LEAGUE"
echo "═══════════════════════════════════════════"
echo ""

# 步骤 1：预测
echo "🔮 [1/4] 运行预测引擎..."
python skill/predict.py --home "$HOME" --away "$AWAY" --league "$LEAGUE"
if [ $? -ne 0 ]; then
    echo "❌ 预测失败"
    exit 1
fi

# 步骤 2：检查是否有待结算
echo ""
echo "📊 [2/4] 检查待结算..."
python -c "
import json
with open('数据缓存/predictions_db.json', 'r') as f:
    db = json.load(f)
pending = [p for p in db['predictions'] if p.get('result',{}).get('status') != 'matched']
print(f'  待结算: {len(pending)} 场')
if pending:
    for p in pending:
        print(f'    {p[\"home\"]} vs {p[\"away\"]} ({p.get(\"date\",\"?\")})')
"

# 步骤 3：生成 HTML 看板
echo ""
echo "📊 [3/4] 生成看板..."
python skill/report_to_html.py

# 步骤 4：推送到 GitHub
echo ""
echo "🚀 [4/4] 推送到 GitHub..."
git add -A
git commit -m "📊 $DATE $HOME vs $AWAY"

# 检查是否有内容可推送
if git push 2>&1 | grep -q "Everything up-to-date"; then
    echo "  ℹ️ 没有新变更"
else
    echo "  ✅ 推送成功"
fi

# 完成
END=$(date +%s)
COST=$((END - START))

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ 部署完成 (耗时 ${COST}s)"
echo "═══════════════════════════════════════════"
echo ""
echo "  📱 手机查看:"
echo "  https://你的用户名.github.io/scorelab/"
echo ""
