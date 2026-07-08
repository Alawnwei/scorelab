#!/usr/bin/env python3
"""测试 estimate_team_strength 磁盘缓存"""
import sys, os, time

BASE = r"C:\Users\Huawei\Downloads\电商\足球分析"
SKILL_DIR = os.path.join(BASE, "skill")
CACHE_DIR = os.path.join(BASE, "数据缓存")
log_file = os.path.join(CACHE_DIR, "full_cache_test.txt")

sys.path.insert(0, SKILL_DIR)

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# 清缓存
for fname in ["team_strength_cache.json", "recent_matches_cache.json"]:
    fp = os.path.join(CACHE_DIR, fname)
    if os.path.exists(fp):
        os.remove(fp)
        log(f"Cleared {fname}")

import datafc_provider as dp
dp._RECENT_MATCHES_CACHE = {}

# Run 1: 冷启动
log("=== Run 1: Cold start ===")
for team in ["索尔纳", "哥德堡"]:
    t0 = time.time()
    xg = dp.estimate_team_strength(team, "allsvenskan", max_games=5)
    t = time.time() - t0
    log(f"  {team}: {t:.0f}s -> xG_for={xg['xG_for_90']}, source={xg['source']}")

# 查看缓存文件大小
for fname in ["team_strength_cache.json", "recent_matches_cache.json"]:
    fp = os.path.join(CACHE_DIR, fname)
    sz = os.path.getsize(fp) if os.path.exists(fp) else 0
    log(f"  Cache {fname}: {sz} bytes")

log("\n=== Run 2: New process (full cache) ===")

import subprocess
script = f"""
import sys, os, time
sys.path.insert(0, {repr(SKILL_DIR)})
import datafc_provider as dp
dp._RECENT_MATCHES_CACHE = {{}}
log_file = {repr(log_file)}
for team in ["索尔纳", "哥德堡"]:
    t0 = time.time()
    xg = dp.estimate_team_strength(team, "allsvenskan", max_games=5)
    t = time.time() - t0
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"  {{team}}: {{t:.0f}}s -> xG_for={{xg['xG_for_90']}}, source={{xg['source']}}\\n")
"""
r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
if r.returncode != 0:
    log(f"  Subprocess error: {r.stderr[:200]}")
log("DONE")
