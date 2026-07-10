#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成自包含 HTML 看板 → GitHub Pages 可访问
手机/电脑浏览器直接打开，无需服务器

用法:
  python skill/report_to_html.py                    # 生成完整看板
  python skill/report_to_html.py --simple            # 仅表格（更快）
"""
import sys, os, json, math, base64
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
HTML_DIR = os.path.join(BASE_DIR, "docs")
REVIEW_DIR = os.path.join(BASE_DIR, "预测数据")


def load_json(name):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def esc(s):
    """HTML 转义"""
    if s is None: return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ============================================================
# 数据准备
# ============================================================

def prepare_data():
    db = load_json("predictions_db.json")
    pnl = load_json("pnl_records.json")
    auto = load_json("auto_results.json")

    predictions = db.get("predictions", [])
    pnl_records = pnl.get("records", [])

    # 分类
    pending = [p for p in predictions if p.get("result", {}).get("status") != "matched"]
    settled = [p for p in predictions if p.get("result", {}).get("status") == "matched"
               and p["result"].get("correct") is not None]
    correct = sum(1 for p in settled if p["result"]["correct"])
    total = len(settled)
    acc = correct / total if total > 0 else 0

    # Brier
    brier = 0
    for p in settled:
        pf = p.get("p_final", 0.5)
        outcome = 1 if p["result"]["correct"] else 0
        brier += (pf - outcome) ** 2
    brier = round(brier / total, 4) if total > 0 else 0

    # LogLoss
    logloss = 0
    for p in settled:
        pf = max(1e-10, min(1-1e-10, p.get("p_final", 0.5)))
        outcome = 1 if p["result"]["correct"] else 0
        logloss += -math.log(pf) if outcome else -math.log(1-pf)
    logloss = round(logloss / total, 4) if total > 0 else 0

    # 准确率趋势
    sorted_settled = sorted(settled, key=lambda x: x.get("date", ""))
    trend = []
    window = 5
    for i in range(len(sorted_settled)):
        batch = sorted_settled[max(0, i-window):i+1]
        if len(batch) >= 3:
            w_correct = sum(1 for p in batch if p["result"]["correct"])
            trend.append({
                "date": batch[-1].get("date", "")[-5:],
                "acc": round(w_correct / len(batch), 3),
            })

    # 校准曲线
    cal_bins = defaultdict(lambda: {"n": 0, "c": 0, "sum_p": 0})
    for p in settled:
        pf = p.get("p_final", 0.5)
        bin_idx = min(int(pf * 10), 9)
        cal_bins[bin_idx]["n"] += 1
        if p["result"]["correct"]:
            cal_bins[bin_idx]["c"] += 1
        cal_bins[bin_idx]["sum_p"] += pf

    cal_curve = []
    for bin_idx in range(10):
        d = cal_bins.get(bin_idx, {"n": 0, "c": 0, "sum_p": 0})
        if d["n"] == 0: continue
        cal_curve.append({
            "bin": f"{bin_idx/10:.1f}-{(bin_idx+1)/10:.1f}",
            "n": d["n"],
            "actual": round(d["c"] / d["n"], 3),
            "predicted": round(d["sum_p"] / d["n"], 3),
        })

    # 推荐复盘统计
    rec_total = 0
    rec_hit = 0
    rec_pending = 0
    rec_by_market = {}
    rec_pending_list = []
    for p in predictions:
        for r in p.get("recommendations", []):
            m = r.get("market", "")
            if "大小球" in m: cat = "OU"
            elif "亚盘" in m: cat = "AH"
            elif "BTTS" in m: cat = "BTTS"
            elif "1X2" in m: cat = "1X2"
            else: cat = "其他"
            if r.get("hit") is not None:
                rec_total += 1
                if r["hit"]:
                    rec_hit += 1
                if cat not in rec_by_market:
                    rec_by_market[cat] = {"total": 0, "hit": 0}
                rec_by_market[cat]["total"] += 1
                if r["hit"]:
                    rec_by_market[cat]["hit"] += 1
            else:
                rec_pending += 1
                if len(rec_pending_list) < 10:
                    rec_pending_list.append({
                        "market": m, "ev": r.get("ev", 0),
                        "odds": r.get("odds", 0), "bet_amount": r.get("bet_amount", 0),
                    })

    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "predictions": len(predictions),
        "settled": total,
        "pending": len(pending),
        "correct": correct,
        "accuracy": round(acc, 4),
        "brier": brier,
        "logloss": logloss,
        "trend": trend,
        "cal_curve": cal_curve,
        "pnl_records": pnl_records,
        "pnl_count": len(pnl_records),
        "pnl_wins": sum(1 for r in pnl_records if r.get("result") == "win"),
        "pnl_losses": sum(1 for r in pnl_records if r.get("result") == "loss"),
        "pnl_total_pnl": sum(r.get("pnl", 0) for r in pnl_records),
        "rec_total": rec_total,
        "rec_hit": rec_hit,
        "rec_by_market": rec_by_market,
        "rec_pending": rec_pending,
        "rec_pending_list": rec_pending_list,
        "rec_data": {"total": rec_total, "hit": rec_hit, "markets": rec_by_market},
        "settled_list": [{
            "date": p.get("date", ""),
            "home": p.get("home", ""),
            "away": p.get("away", ""),
            "p_final": p.get("p_final", 0.5),
            "direction": p.get("direction", ""),
            "league": p.get("league", ""),
            "confidence": p.get("confidence", ""),
            "correct": p["result"].get("correct"),
            "score": f"{p['result'].get('score_home','?')}-{p['result'].get('score_away','?')}",
        } for p in reversed(settled[-30:])],  # 最近30场
        "pending_list": [{
            "date": p.get("date", ""),
            "home": p.get("home", ""),
            "away": p.get("away", ""),
            "p_final": p.get("p_final", 0.5),
            "direction": p.get("direction", ""),
            "league": p.get("league", ""),
            "confidence": p.get("confidence", ""),
        } for p in reversed(pending[-20:])],
    }


# ============================================================
# HTML 生成
# ============================================================

def gen_html(data):
    data_json = json.dumps(data, ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚽ 足球分析看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, 'Segoe UI', sans-serif; background: #0f1923; color: #e0e0e0; padding: 16px; }}
h1 {{ font-size: 1.4rem; margin-bottom: 8px; color: #fff; }}
h2 {{ font-size: 1.1rem; margin: 20px 0 10px; color: #90caf9; }}
.card {{ background: #1a2a3a; border-radius: 10px; padding: 14px; margin-bottom: 12px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }}
.stat {{ text-align: center; padding: 10px; }}
.stat .value {{ font-size: 1.6rem; font-weight: bold; color: #fff; }}
.stat .label {{ font-size: 0.75rem; color: #8899aa; margin-top: 2px; }}
.stat .tag {{ font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-top: 4px; }}
.tag-green {{ background: #1b5e20; color: #81c784; }}
.tag-yellow {{ background: #e65100; color: #ffcc80; }}
.tag-red {{ background: #b71c1c; color: #ef9a9a; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.78rem; }}
th, td {{ padding: 6px 4px; text-align: left; border-bottom: 1px solid #2a3a4a; }}
th {{ color: #90caf9; font-weight: 500; position: sticky; top: 0; background: #1a2a3a; }}
.correct {{ color: #81c784; }}
.wrong {{ color: #ef9a9a; }}
.pending {{ color: #ffcc80; }}
.chart-container {{ height: 200px; margin: 10px 0; }}
.footer {{ text-align: center; font-size: 0.7rem; color: #667; margin-top: 20px; padding: 10px; }}
@media (prefers-color-scheme: light) {{
  body {{ background: #f5f5f5; color: #333; }}
  .card {{ background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }}
  th {{ background: #fff; color: #1565c0; }}
  th, td {{ border-color: #e0e0e0; }}
  h2 {{ color: #1565c0; }}
  .stat .value {{ color: #000; }}
  .stat .label {{ color: #666; }}
}}
</style>
</head>
<body>

<h1>⚽ 足球分析看板</h1>
<p style="font-size:0.78rem;color:#8899aa;">更新: {data['updated']} | 数据源: predictions_db.json + pnl_records.json</p>

<!-- KPI Cards -->
<div class="card">
<div class="grid">
  <div class="stat">
    <div class="value">{data['accuracy']:.0%}</div>
    <div class="label">方向准确率</div>
    <div class="tag {'tag-green' if data['accuracy']>0.65 else 'tag-yellow'}">{data['correct']}/{data['settled']}</div>
  </div>
  <div class="stat">
    <div class="value">{data['brier']:.3f}</div>
    <div class="label">Brier Score</div>
    <div class="tag {'tag-green' if data['brier']<0.2 else 'tag-yellow' if data['brier']<0.25 else 'tag-red'}">{'良好' if data['brier']<0.2 else '边缘' if data['brier']<0.25 else '需关注'}</div>
  </div>
  <div class="stat">
    <div class="value">{data['logloss']:.3f}</div>
    <div class="label">Log Loss</div>
  </div>
  <div class="stat">
    <div class="value">{data['pnl_count']}</div>
    <div class="label">PnL 记录</div>
    <div class="tag {'tag-green' if data['pnl_total_pnl']>0 else 'tag-red'}">{data['pnl_wins']}胜 {data['pnl_losses']}负</div>
  </div>
  <div class="stat">
    <div class="value">{data['pending']}</div>
    <div class="label">待结算</div>
  </div>
  <div class="stat">
    <div class="value">{data['predictions']}</div>
    <div class="label">总预测</div>
  </div>
</div>
</div>

<!-- 推荐复盘 -->
<div class="card" id="recCard">
<h2>🎯 推荐命中率</h2>
<div id="recContent">
<p style="font-size:0.85rem;color:#8899aa;">加载中...</p>
</div>
</div>

<script>
var _rd=DATA.rec_data;
var _rp=DATA.rec_pending_list;
if(_rd.total>0||_rp.length>0){{
  var _h='<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:8px;">';
  if(_rd.total>0){{
    _h+='<div class="stat"><div class="value">'+_rd.hit+'/'+_rd.total+'</div><div class="label">全部推荐</div><div class="tag '+(_rd.hit/_rd.total>0.5?'tag-green':'tag-yellow')+'">'+Math.round(_rd.hit/_rd.total*100)+'%</div></div>';
    for(var _k in _rd.markets){{
      var _d=_rd.markets[_k];
      if(_d.total>0){{
        var _p=Math.round(_d.hit/_d.total*100);
        _h+='<div class="stat"><div class="value" style="font-size:1.1rem;">'+_d.hit+'/'+_d.total+'</div><div class="label">'+_k+'</div><div class="tag '+(_d.hit/_d.total>0.5?'tag-green':'tag-yellow')+'">'+_p+'%</div></div>';
      }}
    }}
  }}
  if(_rp.length>0){{
    _h+='</div><div style="margin-top:8px;font-size:0.78rem;color:#8899aa;">待结算推荐:';
    for(var _i=0;_i<_rp.length;_i++){{
      _h+=' <span style="display:inline-block;background:#2a3a4a;padding:1px 6px;border-radius:3px;margin:2px;">'+_rp[_i].market+' +'+_rp[_i].ev+'%</span>';
    }}
    _h+='</div>';
  }}
  document.getElementById('recContent').innerHTML=_h;
}}else{{
  document.getElementById('recContent').innerHTML='<p style="font-size:0.85rem;color:#8899aa;">暂无推荐数据</p>';
}}
</script>

<!-- 校准曲线 -->
<div class="card">
<h2>📈 校准曲线</h2>
<div class="chart-container">
<canvas id="calChart"></canvas>
</div>
</div>

<!-- 准确率趋势 -->
<div class="card">
<h2>📉 准确率趋势 (滚动窗口=5)</h2>
<div class="chart-container">
<canvas id="trendChart"></canvas>
</div>
</div>

<!-- 待结算预测 -->
<div class="card">
<h2>⏳ 待结算预测 ({len(data['pending_list'])})</h2>
<div style="overflow-x:auto;">
<table>
<thead><tr><th>日期</th><th>主队</th><th>客队</th><th>方向</th><th>P_final</th><th>联赛</th></tr></thead>
<tbody>
{''.join(f'<tr><td>{esc(p["date"])}</td><td>{esc(p["home"])}</td><td>{esc(p["away"])}</td><td>{esc(p["direction"])}</td><td>{p["p_final"]:.3f}</td><td>{esc(p["league"])}</td></tr>' for p in data['pending_list'])}
</tbody>
</table>
</div>
</div>

<!-- 最近30场 -->
<div class="card">
<h2>📋 最近结算 ({len(data['settled_list'])})</h2>
<div style="overflow-x:auto;">
<table>
<thead><tr><th>日期</th><th>主队</th><th>客队</th><th>方向</th><th>P_final</th><th>比分</th><th>结果</th></tr></thead>
<tbody>
{''.join(f'<tr><td>{esc(p["date"])}</td><td>{esc(p["home"])}</td><td>{esc(p["away"])}</td><td>{esc(p["direction"])}</td><td>{p["p_final"]:.3f}</td><td>{esc(p["score"])}</td><td class="{"correct" if p["correct"] else "wrong" if p["correct"] is False else "pending"}">{"✅" if p["correct"] else "❌" if p["correct"] is False else "⏳"}</td></tr>' for p in data['settled_list'])}
</tbody>
</table>
</div>
</div>

<div class="footer">
⚡ 自动生成 by report_to_html.py | GitHub Pages 托管<br>
<a href="https://github.com/你的用户名/scorelab" style="color:#90caf9;">scorelab</a>
</div>

<script>
const DATA = {data_json};

// 校准曲线
const calCtx = document.getElementById('calChart').getContext('2d');
const calBins = DATA.cal_curve;
new Chart(calCtx, {{
  type: 'bar',
  data: {{
    labels: calBins.map(b => b.bin + ' (n=' + b.n + ')'),
    datasets: [
      {{ label: '实际胜率', data: calBins.map(b => b.actual), backgroundColor: '#42a5f5' }},
      {{ label: '预测均值', data: calBins.map(b => b.predicted), backgroundColor: '#ef5350' }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top', labels: {{ color: '#ccc' }} }} }},
    scales: {{
      y: {{ beginAtZero: true, max: 1, ticks: {{ color: '#999' }} }},
      x: {{ ticks: {{ color: '#999', maxRotation: 45 }} }}
    }}
  }}
}});

// 趋势图
const trCtx = document.getElementById('trendChart').getContext('2d');
const trData = DATA.trend;
new Chart(trCtx, {{
  type: 'line',
  data: {{
    labels: trData.map(t => t.date),
    datasets: [{{ label: '准确率', data: trData.map(t => t.acc), borderColor: '#66bb6a', backgroundColor: 'rgba(102,187,106,0.1)', fill: true, tension: 0.3 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      y: {{ min: 0, max: 1, ticks: {{ color: '#999' }} }},
      x: {{ ticks: {{ color: '#999' }} }}
    }}
  }}
}});
</script>
</body>
</html>'''

# ============================================================
# 主入口
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="生成HTML看板")
    parser.add_argument("--simple", action="store_true", help="仅表格（无图表，更快）")
    parser.add_argument("--no-sync", action="store_true", help="不触发结果回填")
    args = parser.parse_args()

    # ── 触发自动结果回填（v8.5） ──
    if not args.no_sync:
        try:
            import subprocess, sys
            _review_path = os.path.join(os.path.dirname(__file__), "auto_review.py")
            _ret = subprocess.run(
                [sys.executable, _review_path, "--sync"],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace"
            )
            if _ret.stdout:
                _line = [l for l in _ret.stdout.strip().split("\n") if "回填" in l or "同步" in l]
                if _line:
                    print(f"[自动回填] {_line[0]}")
        except Exception:
            pass

    data = prepare_data()
    html = gen_html(data)

    os.makedirs(HTML_DIR, exist_ok=True)
    path = os.path.join(HTML_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ 看板已生成: {path}")
    print(f"   大小: {len(html)/1024:.0f} KB")
    print(f"   GitHub Pages: https://你的用户名.github.io/scorelab/")


if __name__ == "__main__":
    main()
