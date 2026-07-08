#!/usr/bin/env python3
"""测试磁盘缓存：先清缓存跑一次（冷启动），再新进程跑一次（读磁盘缓存）"""
import sys, os, json, time

BASE = r"C:\Users\Huawei\Downloads\电商\足球分析"
CACHE_DIR = os.path.join(BASE, "数据缓存")
SKILL_DIR = os.path.join(BASE, "skill")
cache_file = os.path.join(CACHE_DIR, "recent_matches_cache.json")
log_file = os.path.join(CACHE_DIR, "disk_cache_test.txt")

sys.path.insert(0, SKILL_DIR)

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# 清理旧缓存
if os.path.exists(cache_file):
    os.remove(cache_file)
    log("Cleared old disk cache")

import datafc_provider as dp
dp._RECENT_MATCHES_CACHE = {}

# 第1次：冷启动（走 Sofascore API）
log("=== Run 1: Cold start (Sofascore API) ===")
for team in ["索尔纳", "哥德堡"]:
    t0 = time.time()
    xg = dp.estimate_team_strength(team, "allsvenskan", max_games=5)
    t = time.time() - t0
    log(f"  {team}: {t:.0f}s -> xG_for={xg['xG_for_90']}, source={xg['source']}")

ck_size = os.path.getsize(cache_file) if os.path.exists(cache_file) else 0
log(f"\n  Disk cache file: {ck_size} bytes\n")
log("=== Run 2: New process (disk cache) ===")

# 第2次：新进程验证磁盘缓存
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
r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
if r.returncode != 0:
    log(f"  Subprocess error: {r.stderr[:200]}")

log("DONE")
