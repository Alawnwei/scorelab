#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix ELO print statement to avoid Chinese character encoding issues"""
with open('skill/predict.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''            print(f\"  [ELO] {home} elo={str(elo_home.get(chr(39)+chr(101)+chr(108)+chr(111)+chr(39)))} rank={str(elo_home.get(chr(39)+chr(114)+chr(97)+chr(110)+chr(107)+chr(39)))} | \"\n                  f\"{away} elo={str(elo_away.get(chr(39)+chr(101)+chr(108)+chr(111)+chr(39)))} rank={str(elo_away.get(chr(39)+chr(114)+chr(97)+chr(110)+chr(107)+chr(39)))}")'''

new = '''            print(f\"  [ELO] home_elo={str(elo_home.get(chr(39)+chr(101)+chr(108)+chr(111)+chr(39)))} home_rank={str(elo_home.get(chr(39)+chr(114)+chr(97)+chr(110)+chr(107)+chr(39)))} | away_elo={str(elo_away.get(chr(39)+chr(101)+chr(108)+chr(111)+chr(39)))} away_rank={str(elo_away.get(chr(39)+chr(114)+chr(97)+chr(110)+chr(107)+chr(39)))}\")'''

if old in content:
    content = content.replace(old, new)
    with open('skill/predict.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed ELO print!')
else:
    print('Could not find old print')
    idx = content.find('chr(39)+chr(101)+chr(108)+chr(111)')
    if idx >= 0:
        # Show context
        start = content.rfind('print', 0, idx)
        end = content.find(')', idx) + 30
        print(repr(content[start:end]))
