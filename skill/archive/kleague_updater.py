#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K1联赛积分榜自动更新工具

用法:
  方式1: 手动更新（找到最新数据后运行）
    python skill/kleague_updater.py --update

  方式2: 查看当前内置数据
    python skill/kleague_updater.py --show

  方式3: 通过WebSearch获取最新数据后更新
    python skill/kleague_updater.py --import-json '{"全北现代":{"gf":21,"ga":12,"played":15,"pts":26,"rank":2},...}'

数据流向: KLEAGUE1_TABLE (xg_estimator.py) ← 此脚本更新
"""

import sys, os, json, re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XG_ESTIMATOR = os.path.join(BASE_DIR, "skill", "xg_estimator.py")

def show_current():
    """显示当前内置的K联赛数据"""
    with open(XG_ESTIMATOR, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 KLEAGUE1_TABLE 区域
    match = re.search(r'KLEAGUE1_TABLE\s*=\s*\{([^}]+)\}', content, re.DOTALL)
    if match:
        print("当前K1联赛内置数据:")
        print(match.group(0)[:2000])
    else:
        print("未找到KLEAGUE1_TABLE")

def update_from_json(json_str: str):
    """从JSON字符串更新KLEAGUE1_TABLE"""
    try:
        new_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        return False

    with open(XG_ESTIMATOR, "r", encoding="utf-8") as f:
        content = f.read()

    # 验证数据格式
    for name, stats in new_data.items():
        if not isinstance(stats, dict):
            print(f"无效格式: {name}")
            return False
        for key in ["gf", "ga", "played", "pts", "rank"]:
            if key not in stats:
                print(f"{name} 缺少字段: {key}")
                return False

    # 构建新的table条目
    entries = []
    for name_en, stats in new_data.items():
        entry = f'    "{name_en}": {{"played":{stats["played"]},"gf":{stats["gf"]},"ga":{stats["ga"]},"pts":{stats["pts"]},"rank":{stats["rank"]}}},'
        entries.append(entry)

    # 替换旧的KLEAGUE1_TABLE区域
    new_table = "KLEAGUE1_TABLE = {\n" + "\n".join(entries) + "\n}"

    # 找到并替换
    pattern = r'KLEAGUE1_TABLE\s*=\s*\{.*?\n\}'
    if re.search(pattern, content, re.DOTALL):
        new_content = re.sub(pattern, new_table, content, flags=re.DOTALL)
        with open(XG_ESTIMATOR, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"✅ 已更新 {len(new_data)} 支球队数据")
        print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        return True
    else:
        print("❌ 未找到 KLEAGUE1_TABLE")
        return False

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "--show":
        show_current()
    elif cmd == "--update":
        print("请用以下方式之一提供数据:")
        print("  1. WebSearch找到K联赛积分榜后, 运行:")
        print('     python skill/kleague_updater.py --import-json \'{"队名":{"gf":x,"ga":x,...}}\'')
        print()
        print("  2. 或告诉我比赛编号, 我用WebSearch帮你查最新数据")
    elif cmd == "--import-json" and len(sys.argv) > 2:
        update_from_json(sys.argv[2])
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
