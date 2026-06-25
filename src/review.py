#!/usr/bin/env python3
"""review.py — 赛果回填 + 复盘分析

数据源: 500.com 完场比分 (live.500.com/wanchang.php)
功能: 
  1. 抓取赛果 → 回填 DB actual_outcome
  2. 对比预测 vs 实际 → 命中率 / ROI / 偏差分析
  3. 生成复盘 HTML 看板
"""

import json
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml',
}


# ========== 队名别名表 ==========
_ALIAS = {
    '巴萨': '巴塞罗那', '皇马': '皇家马德里', '贝蒂斯': '皇家贝蒂斯',
    '国米': '国际米兰', '米兰': 'AC米兰',
    '曼城': '曼彻斯特城', '热刺': '托特纳姆热刺', '纽卡': '纽卡斯尔联',
    '拜仁': '拜仁慕尼黑', '马竞': '马德里竞技',
}


def name_sim(a: str, b: str) -> float:
    """字符集相似度"""
    if not a or not b:
        return 0.0
    a2, b2 = _ALIAS.get(a, a), _ALIAS.get(b, b)
    s1 = len(set(a2) & set(b2)) / max(len(a2), len(b2), 1)
    # 也试原始
    s2 = len(set(a) & set(b)) / max(len(a), len(b), 1)
    return max(s1, s2)


def fetch_500com_results(date_str: str = None) -> List[Dict]:
    """从500.com抓完场比分

    返回: [{league, kickoff, home, away, score, home_goals, away_goals, outcome}]
    outcome: 'W' / 'D' / 'L' (主视角)
    """
    try:
        r = requests.get("https://live.500.com/wanchang.php", headers=HEADERS, timeout=20)
    except Exception as e:
        print(f"  ❌ 500.com 请求失败: {e}")
        return []

    if r.status_code != 200:
        print(f"  ❌ 500.com HTTP {r.status_code}")
        return []

    try:
        text = r.content.decode('gbk', errors='replace')
    except:
        text = r.content.decode('utf-8', errors='replace')

    results = []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.S)

    for row in rows:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
        if len(tds) < 8:
            continue

        clean = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]

        # TD[0]=联赛, TD[1]=轮次, TD[2]=时间, TD[3]=状态(完), 
        # TD[4]=主队+排名, TD[5]=亚盘, TD[6]=客队+排名, TD[7]=比分
        league = clean[0]
        kickoff = clean[2]
        status = clean[3]
        home_raw = clean[4]
        away_raw = clean[6]
        score_raw = clean[7]

        # 只要完场
        if status != '完':
            continue

        # 解析比分 "2 - 1" or "1:0"
        score_m = re.match(r'(\d+)\s*[-:]\s*(\d+)', score_raw)
        if not score_m:
            continue

        hg = int(score_m.group(1))
        ag = int(score_m.group(2))

        # 解析队名（去掉排名数字）
        home = re.sub(r'^\[\d+\]', '', home_raw).strip()
        home = re.sub(r'^\d+', '', home).strip()
        away = re.sub(r'\[\d+\]$', '', away_raw).strip()
        away = re.sub(r'\d+$', '', away).strip()

        outcome = 'W' if hg > ag else ('D' if hg == ag else 'L')

        results.append({
            'league': league,
            'kickoff': kickoff,
            'home': home,
            'away': away,
            'score': f"{hg}-{ag}",
            'home_goals': hg,
            'away_goals': ag,
            'outcome': outcome,
        })

    print(f"  📥 500.com: {len(results)} 场完场")
    return results


def match_result(db_home, db_away, results: List[Dict]) -> Optional[Dict]:
    """在500.com结果中匹配比赛"""
    best = None
    best_sim = 0
    for r in results:
        sim_fwd = (name_sim(db_home, r['home']) + name_sim(db_away, r['away'])) / 2
        sim_rev = (name_sim(db_home, r['away']) + name_sim(db_away, r['home'])) / 2
        sim = max(sim_fwd, sim_rev)
        if sim > best_sim:
            best_sim = sim
            best = r
    if best and best_sim >= 0.4:
        return best
    return None


def backfill_results(conn, results: List[Dict], date_str: str) -> Tuple[int, int]:
    """回填赛果到 DB"""
    from db import get_predictions

    preds = get_predictions(conn, date_str)
    filled = 0
    no_match = 0

    for p in preds:
        if p.get('actual_outcome'):
            continue  # 已有赛果
        r = match_result(p['home_team'], p['away_team'], results)
        if r:
            conn.execute(
                "UPDATE predictions SET actual_outcome = ? WHERE date = ? AND home_team = ? AND away_team = ?",
                (r['outcome'], date_str, p['home_team'], p['away_team'])
            )
            filled += 1
        else:
            no_match += 1

    conn.commit()
    return filled, no_match


def analyze_performance(conn, date_str: str) -> Dict:
    """分析预测表现"""
    from db import get_predictions

    preds = get_predictions(conn, date_str)

    stats = {
        'date': date_str,
        'total': 0,
        'resolved': 0,
        'hit': 0,
        'miss': 0,
        'hit_by_direction': {'W': {'hit': 0, 'total': 0}, 'D': {'hit': 0, 'total': 0}, 'L': {'hit': 0, 'total': 0}},
        'hit_by_risk': {'低': {'hit': 0, 'total': 0}, '中': {'hit': 0, 'total': 0}, '高': {'hit': 0, 'total': 0}},
        'value_bets': {'hit': 0, 'total': 0, 'roi': 0.0},
        'ev_accuracy': [],
        'matches': [],
    }

    for p in preds:
        stats['total'] += 1
        outcome = p.get('actual_outcome', '')
        if not outcome:
            continue

        stats['resolved'] += 1
        pred = p.get('prediction', '')
        hit = (pred == outcome)
        if hit:
            stats['hit'] += 1
        else:
            stats['miss'] += 1

        # 方向命中
        if pred in stats['hit_by_direction']:
            stats['hit_by_direction'][pred]['total'] += 1
            if hit:
                stats['hit_by_direction'][pred]['hit'] += 1

        # 风险命中
        risk = p.get('risk_level', '')
        if risk in stats['hit_by_risk']:
            stats['hit_by_risk'][risk]['total'] += 1
            if hit:
                stats['hit_by_risk'][risk]['hit'] += 1

        # 价值投注
        if p.get('value_flag') == 1:
            stats['value_bets']['total'] += 1
            if hit:
                stats['value_bets']['hit'] += 1
                # ROI: 假设投注1单位，赢了得到 odds-1
                odds_map = {'W': p.get('avg_odds_w', 0), 'D': p.get('avg_odds_d', 0), 'L': p.get('avg_odds_l', 0)}
                odds = odds_map.get(pred, 0) or 0
                stats['value_bets']['roi'] += (odds - 1) if odds > 1 else 0
            else:
                stats['value_bets']['roi'] -= 1  # 亏1单位

        # EV 偏差
        ev_key = f'ev_{pred.lower()}'
        ev_pred = p.get(ev_key, 0) or 0
        actual_return = 1.0 if hit else 0.0  # 简化
        stats['ev_accuracy'].append({
            'home': p.get('home_team', ''),
            'away': p.get('away_team', ''),
            'pred': pred,
            'outcome': outcome,
            'hit': hit,
            'ev': ev_pred,
            'risk': p.get('risk_level', ''),
        })

        stats['matches'].append({
            'home': p.get('home_team', ''),
            'away': p.get('away_team', ''),
            'league': p.get('league', ''),
            'pred': pred,
            'outcome': outcome,
            'score': '',  # 从 match_result 获取
            'hit': hit,
            'risk': p.get('risk_level', ''),
            'confidence': p.get('confidence_index', 0),
            'ev': max(p.get('ev_w', 0) or 0, p.get('ev_d', 0) or 0, p.get('ev_l', 0) or 0),
        })

    # 计算 ROI
    if stats['value_bets']['total'] > 0:
        stats['value_bets']['roi_pct'] = round(
            stats['value_bets']['roi'] / stats['value_bets']['total'] * 100, 1)
    else:
        stats['value_bets']['roi_pct'] = 0

    # 命中率
    stats['hit_rate'] = round(stats['hit'] / max(stats['resolved'], 1) * 100, 1)

    return stats


def generate_review_dashboard(stats: Dict, output_path: str):
    """生成复盘 HTML 看板"""
    import html as html_mod

    DIRECTION_CN = {'W': '主胜', 'D': '平局', 'L': '客胜'}
    HIT_ICON = {True: '✅', False: '❌'}

    # 方向命中表
    dir_rows = ''
    for d, v in stats['hit_by_direction'].items():
        if v['total'] > 0:
            rate = v['hit'] / v['total'] * 100
            dir_rows += f"""
            <tr>
                <td class="center">{DIRECTION_CN.get(d, d)}</td>
                <td class="center">{v['total']}</td>
                <td class="center">{v['hit']}</td>
                <td class="center">{rate:.0f}%</td>
            </tr>"""

    # 风险命中表
    risk_rows = ''
    for r, v in stats['hit_by_risk'].items():
        if v['total'] > 0:
            rate = v['hit'] / v['total'] * 100
            color = '#4caf50' if r == '低' else '#ff9800' if r == '中' else '#f44336'
            risk_rows += f"""
            <tr>
                <td class="center" style="color:{color}">{r}</td>
                <td class="center">{v['total']}</td>
                <td class="center">{v['hit']}</td>
                <td class="center">{rate:.0f}%</td>
            </tr>"""

    # 逐场结果
    match_rows = ''
    for m in stats['matches']:
        hit_icon = HIT_ICON.get(m['hit'], '⏳')
        pred_cn = DIRECTION_CN.get(m['pred'], m['pred'])
        outcome_cn = DIRECTION_CN.get(m['outcome'], m['outcome'])
        row_class = 'hit' if m['hit'] else 'miss'

        match_rows += f"""
        <tr class="{row_class}">
            <td>{html_mod.escape(m['home'])} vs {html_mod.escape(m['away'])}</td>
            <td class="center">{html_mod.escape(m['league'])}</td>
            <td class="center"><b>{pred_cn}</b></td>
            <td class="center">{outcome_cn}</td>
            <td class="center">{hit_icon}</td>
            <td class="center">{m['risk']}</td>
            <td class="center">{m['ev']:+.1%}</td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>复盘报告 — {stats['date']}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#1a1a2e; color:#e0e0e0; font-family:'SF Mono','Cascadia Code',monospace; padding:20px; }}
h1 {{ color:#fff; font-size:20px; margin-bottom:4px; }}
.subtitle {{ color:#888; font-size:12px; margin-bottom:16px; }}
.stats {{ display:flex; gap:16px; margin-bottom:20px; flex-wrap:wrap; }}
.stat {{ background:#16213e; padding:10px 16px; border-radius:6px; min-width:120px; }}
.stat-label {{ color:#888; font-size:11px; }}
.stat-value {{ color:#fff; font-size:20px; font-weight:bold; }}
.stat-value.green {{ color:#4caf50; }}
.stat-value.red {{ color:#f44336; }}
.stat-value.orange {{ color:#ff9800; }}
.section {{ margin-bottom:24px; }}
.section h2 {{ color:#ccc; font-size:14px; margin-bottom:8px; border-bottom:1px solid #2a2a4a; padding-bottom:4px; }}
table {{ width:100%; border-collapse:collapse; font-size:12px; margin-bottom:16px; }}
th {{ background:#16213e; color:#aaa; padding:6px; text-align:left; }}
td {{ padding:6px; border-bottom:1px solid #2a2a4a; }}
.center {{ text-align:center; }}
.hit {{ background:rgba(76,175,80,0.05); }}
.miss {{ background:rgba(244,67,54,0.05); }}
.hit:hover {{ background:rgba(76,175,80,0.12); }}
.miss:hover {{ background:rgba(244,67,54,0.12); }}
.footer {{ margin-top:20px; color:#555; font-size:11px; text-align:center; }}
</style>
</head>
<body>
<h1>📊 复盘报告</h1>
<div class="subtitle">{stats['date']} | 雷速独立预测系统</div>

<div class="stats">
    <div class="stat">
        <div class="stat-label">总场次</div>
        <div class="stat-value">{stats['total']}</div>
    </div>
    <div class="stat">
        <div class="stat-label">已出结果</div>
        <div class="stat-value">{stats['resolved']}</div>
    </div>
    <div class="stat">
        <div class="stat-label">命中率</div>
        <div class="stat-value {'green' if stats['hit_rate']>=50 else 'red'}">{stats['hit_rate']}%</div>
    </div>
    <div class="stat">
        <div class="stat-label">价值投注</div>
        <div class="stat-value orange">{stats['value_bets']['hit']}/{stats['value_bets']['total']}</div>
    </div>
    <div class="stat">
        <div class="stat-label">价值ROI</div>
        <div class="stat-value {'green' if stats['value_bets']['roi_pct']>=0 else 'red'}">{stats['value_bets']['roi_pct']}%</div>
    </div>
</div>

<div class="section">
<h2>方向命中</h2>
<table>
<tr><th>方向</th><th>总数</th><th>命中</th><th>命中率</th></tr>
{dir_rows}
</table>
</div>

<div class="section">
<h2>风险等级命中</h2>
<table>
<tr><th>风险</th><th>总数</th><th>命中</th><th>命中率</th></tr>
{risk_rows}
</table>
</div>

<div class="section">
<h2>逐场复盘</h2>
<table>
<tr><th>比赛</th><th>联赛</th><th>预测</th><th>实际</th><th>结果</th><th>风险</th><th>EV</th></tr>
{match_rows}
</table>
</div>

<div class="footer">
    雷速复盘 | 数据源: 500.com 赛果 + leisu.com 赔率 | {datetime.now().strftime('%Y-%m-%d %H:%M')}
</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


def run_review(date_str: str = None, db_path: str = None, output_dir: str = None):
    """执行复盘全流程"""
    from db import init_db, get_db_path

    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    if not db_path:
        db_path = get_db_path()
    if not output_dir:
        output_dir = os.path.join(REPO_DIR, 'output')

    print(f"📊 复盘 — {date_str}")

    # Step 1: 抓赛果
    print("  [1/3] 抓取500.com赛果")
    results = fetch_500com_results(date_str)
    if not results:
        print("  ⚠️ 无赛果数据")
        return

    # Step 2: 回填
    conn = sqlite3.connect(db_path)
    filled, no_match = backfill_results(conn, results, date_str)
    print(f"  [2/3] 回填: {filled} 场匹配, {no_match} 场未匹配")

    # Step 3: 分析 + 看板
    stats = analyze_performance(conn, date_str)
    conn.close()

    print(f"  [3/3] 分析: {stats['resolved']} 场已出结果, 命中率 {stats['hit_rate']}%")
    if stats['value_bets']['total'] > 0:
        print(f"         价值投注: {stats['value_bets']['hit']}/{stats['value_bets']['total']} ROI={stats['value_bets']['roi_pct']}%")

    output_path = os.path.join(output_dir, f"review_{date_str.replace('-', '')}.html")
    generate_review_dashboard(stats, output_path)
    print(f"  📊 复盘看板: {output_path}")
    return stats


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='雷速复盘')
    parser.add_argument('--date', type=str, default=None)
    args = parser.parse_args()
    run_review(args.date)
