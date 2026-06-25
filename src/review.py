#!/usr/bin/env python3
"""review.py — 赛果回填 + 复盘分析

数据源: 雷速 match_stats API (web-gateway.leisu.com)
功能: 
  1. 通过 match_id 获取赛果 → 回填 DB actual_outcome + actual_score
  2. 对比预测 vs 实际 → 命中率 / ROI / 偏差分析
  3. 生成复盘 HTML 看板

优势: 队名同源（100%匹配），比分来自雷速官方（无翻译误差）
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


def fetch_leisu_results(match_ids: List[int], client=None) -> Dict[int, Dict]:
    """通过雷速 match_stats API 获取赛果

    Args:
        match_ids: 雷速比赛ID列表
        client: LeisuClient实例（可选，不传则自建）

    Returns:
        {match_id: {score: '2-1', home_goals: 2, away_goals: 1, outcome: 'W', status: 'finished'}}
    """
    if client is None:
        from src.leisu_client import LeisuClient
        client = LeisuClient()
        client.login()

    from src.leisu_decrypt import decrypt_auto

    results = {}
    for mid in match_ids:
        try:
            resp = client.session.get(
                f'https://web-gateway.leisu.com/v1/web/match/football/match_stats?match_id={mid}',
                timeout=10, verify=False
            )
            raw = resp.json()
            code = raw.get('code', -1)

            if 100 <= code <= 126:
                data = decrypt_auto(raw['data'], code)
                incidents = data.get('incidents', [])

                # 找最后一个有home_score/away_score的进球事件 → 最终比分
                last_score = None
                for inc in incidents:
                    if 'home_score' in inc and 'away_score' in inc:
                        last_score = (inc['home_score'], inc['away_score'])

                if last_score:
                    hg, ag = last_score
                    outcome = 'W' if hg > ag else ('D' if hg == ag else 'L')
                    results[mid] = {
                        'score': f'{hg}-{ag}',
                        'home_goals': hg,
                        'away_goals': ag,
                        'outcome': outcome,
                        'status': 'finished',
                    }
                else:
                    # 无进球事件 = 未完场或0-0
                    if incidents:
                        results[mid] = {
                            'score': '0-0',
                            'home_goals': 0,
                            'away_goals': 0,
                            'outcome': 'D',
                            'status': 'finished',
                        }
                    else:
                        results[mid] = {
                            'score': None,
                            'home_goals': None,
                            'away_goals': None,
                            'outcome': None,
                            'status': 'not_started',
                        }
            elif code == 110:
                results[mid] = {'status': 'auth_required', 'outcome': None}
            else:
                results[mid] = {'status': f'error_code_{code}', 'outcome': None}

        except Exception as e:
            results[mid] = {'status': f'error: {e}', 'outcome': None}

    return results


def backfill_leisu_results(conn, results: Dict[int, Dict], date_str: str) -> Tuple[int, int]:
    """回填雷速赛果到 DB（直接用match_id，100%匹配）"""
    from src.db import get_predictions

    preds = get_predictions(conn, date_str)
    filled = 0
    no_match = 0

    for p in preds:
        if p.get('actual_outcome'):
            continue  # 已有赛果

        mid = p.get('match_id')
        if not mid or mid not in results:
            no_match += 1
            continue

        r = results[mid]
        if r.get('outcome'):
            conn.execute(
                "UPDATE predictions SET actual_outcome = ?, actual_score = ? WHERE date = ? AND match_id = ?",
                (r['outcome'], r.get('score'), date_str, mid)
            )
            filled += 1
        else:
            no_match += 1

    conn.commit()
    return filled, no_match


def analyze_performance(conn, date_str: str) -> Dict:
    """分析预测表现"""
    from src.db import get_predictions

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
                odds_map = {'W': p.get('avg_odds_w', 0), 'D': p.get('avg_odds_d', 0), 'L': p.get('avg_odds_l', 0)}
                odds = odds_map.get(pred, 0) or 0
                stats['value_bets']['roi'] += (odds - 1) if odds > 1 else 0
            else:
                stats['value_bets']['roi'] -= 1

        stats['matches'].append({
            'home': p.get('home_team', ''),
            'away': p.get('away_team', ''),
            'league': p.get('league', ''),
            'pred': pred,
            'outcome': outcome,
            'score': p.get('actual_score', ''),
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
        score_display = m.get('score', '') or '-'

        match_rows += f"""
        <tr class="{row_class}">
            <td>{html_mod.escape(m['home'])} vs {html_mod.escape(m['away'])}</td>
            <td class="center">{html_mod.escape(m['league'])}</td>
            <td class="center"><b>{pred_cn}</b></td>
            <td class="center">{outcome_cn}</td>
            <td class="center">{score_display}</td>
            <td class="center">{hit_icon}</td>
            <td class="center">{m['risk']}</td>
            <td class="center">{m['confidence']}★</td>
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
<div class="subtitle">{stats['date']} | 雷速独立预测系统 | 数据源: leisu match_stats</div>

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
<tr><th>比赛</th><th>联赛</th><th>预测</th><th>实际</th><th>比分</th><th>结果</th><th>风险</th><th>信心</th><th>EV</th></tr>
{match_rows}
</table>
</div>

<div class="footer">
    雷速复盘 | 数据源: leisu.com match_stats API | {datetime.now().strftime('%Y-%m-%d %H:%M')}
</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


def run_review(date_str: str = None, db_path: str = None, output_dir: str = None):
    """执行复盘全流程"""
    from src.db import init_db, get_db_path, get_predictions

    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    if not db_path:
        db_path = get_db_path()
    if not output_dir:
        output_dir = os.path.join(REPO_DIR, 'output')

    print(f"📊 复盘 — {date_str}")

    # Step 1: 从DB获取当天所有match_id
    conn = sqlite3.connect(db_path)
    preds = get_predictions(conn, date_str)
    match_ids = [p['match_id'] for p in preds if p.get('match_id')]
    print(f"  [1/3] 获取 {len(match_ids)} 个match_id")

    if not match_ids:
        print("  ⚠️ 无比赛数据")
        conn.close()
        return

    # Step 2: 雷速API获取赛果 + 回填
    print("  [2/3] 雷速 match_stats 获取赛果...")
    results = fetch_leisu_results(match_ids)
    finished = sum(1 for r in results.values() if r.get('status') == 'finished')
    print(f"         {finished}/{len(match_ids)} 场已完场")

    # 清空旧的错误赛果
    conn.execute("UPDATE predictions SET actual_outcome = NULL, actual_score = NULL WHERE date = ?", (date_str,))

    filled, no_match = backfill_leisu_results(conn, results, date_str)
    print(f"         回填: {filled} 场匹配, {no_match} 场未完场")

    # Step 3: 分析 + 看板
    stats = analyze_performance(conn, date_str)
    conn.close()

    print(f"  [3/3] 分析: {stats['resolved']} 场已出结果, 命中率 {stats['hit_rate']}%")
    if stats['value_bets']['total'] > 0:
        print(f"         价值投注: {stats['value_bets']['hit']}/{stats['value_bets']['total']} ROI={stats['value_bets']['roi_pct']}%")

    # 逐场打印
    DIRECTION_CN = {'W': '主胜', 'D': '平局', 'L': '客胜'}
    for m in stats['matches']:
        icon = '✅' if m['hit'] else '❌'
        print(f"         {icon} {m['home']} vs {m['away']}: 预测={DIRECTION_CN.get(m['pred'],'')} 实际={DIRECTION_CN.get(m['outcome'],'')} ({m.get('score','')}) risk={m['risk']} conf={m['confidence']}★")

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
