#!/usr/bin/env python3
"""pipeline.py — 雷速独立预测系统主入口

全链路：抓取 → 预测 → 入库 → 看板 → 复盘

用法:
  python -m src.pipeline --date 2026-06-25
  python -m src.pipeline --date 2026-06-25 --skip-fetch
  python -m src.pipeline --date 2026-06-25 --review-only
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from db import init_db, upsert_prediction, get_predictions, get_db_path
from predict import predict_match


def step_fetch(date_str: str, output_dir: str) -> str:
    """Step 1: 抓取雷速数据 → JSON"""
    from leisu_scraper import run_scraper
    output_path = os.path.join(output_dir, f"leisu_{date_str.replace('-', '')}.json")
    result = run_scraper(output_path=output_path, date_str=date_str)
    print(f"  ✅ 抓取完成: {result.get('count', 0)} 场比赛")
    return output_path


def step_predict(json_path: str) -> list:
    """Step 2: 对每场比赛运行预测"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    matches = data.get('matches', [])
    predicted = []
    for m in matches:
        p = predict_match(m)
        predicted.append(p)

    n_skip = sum(1 for p in predicted if p.get('prediction') == 'SKIP')
    n_value = sum(1 for p in predicted if p.get('value_flag') == 1)
    print(f"  🧮 预测完成: {len(predicted)} 场 (跳过{n_skip}, 价值投注{n_value})")
    return predicted


def step_save(predicted: list, db_path: str, date_str: str):
    """Step 3: 写入 DB"""
    conn = sqlite3.connect(db_path)
    for p in predicted:
        if p.get('prediction') == 'SKIP':
            continue
        row = {
            'date': date_str,
            'match_id': p.get('match_id'),
            'league': p.get('league', ''),
            'home_team': p.get('home_team'),
            'away_team': p.get('away_team'),
            'home_rank': p.get('home_rank', ''),
            'away_rank': p.get('away_rank', ''),
            'avg_odds_w': p.get('avg_odds_w'),
            'avg_odds_d': p.get('avg_odds_d'),
            'avg_odds_l': p.get('avg_odds_l'),
            'avg_prob_w': p.get('avg_prob_w'),
            'avg_prob_d': p.get('avg_prob_d'),
            'avg_prob_l': p.get('avg_prob_l'),
            'avg_margin': p.get('avg_margin', 0),
            'ah_handicap': p.get('ah_handicap'),
            'ah_home_water': p.get('ah_home_water'),
            'ah_away_water': p.get('ah_away_water'),
            'ah_prob_home': p.get('ah_prob_home'),
            'ah_prob_away': p.get('ah_prob_away'),
            'ou_over': p.get('ou_over'),
            'ou_line': p.get('ou_line'),
            'ou_under': p.get('ou_under'),
            'ou_prob_over': p.get('ou_prob_over'),
            'ou_prob_under': p.get('ou_prob_under'),
            'corner_over': p.get('corner_over'),
            'corner_line': p.get('corner_line'),
            'corner_under': p.get('corner_under'),
            'win_rate_home': p.get('win_rate_home'),
            'win_rate_away': p.get('win_rate_away'),
            'recent_home': json.dumps(p.get('recent_home')) if p.get('recent_home') else None,
            'recent_away': json.dumps(p.get('recent_away')) if p.get('recent_away') else None,
            'home_lambda': p.get('home_lambda'),
            'away_lambda': p.get('away_lambda'),
            'poisson_w': p.get('poisson_w'),
            'poisson_d': p.get('poisson_d'),
            'poisson_l': p.get('poisson_l'),
            'final_w': p.get('final_w'),
            'final_d': p.get('final_d'),
            'final_l': p.get('final_l'),
            'prediction': p.get('prediction'),
            'prediction_prob': p.get('prediction_prob'),
            'ev_w': p.get('ev_w', 0),
            'ev_d': p.get('ev_d', 0),
            'ev_l': p.get('ev_l', 0),
            'best_direction': p.get('best_direction', ''),
            'kelly_stake': p.get('kelly_stake', 0),
            'value_flag': p.get('value_flag', 0),
            'risk_level': p.get('risk_level', ''),
            'confidence_index': p.get('confidence_index', 0),
        }
        upsert_prediction(conn, row)
    conn.commit()
    conn.close()
    print(f"  💾 入库完成: {len(predicted)} 场")


def step_dashboard(db_path: str, date_str: str, output_dir: str) -> str:
    """Step 4: 生成预测看板"""
    from dashboard import generate_dashboard
    conn = sqlite3.connect(db_path)
    preds = get_predictions(conn, date_str)
    conn.close()

    if not preds:
        print(f"  ⚠️ 无预测数据: {date_str}")
        return ""

    output_path = os.path.join(output_dir, f"dashboard_{date_str.replace('-', '')}.html")
    generate_dashboard(preds, date_str, output_path)
    print(f"  📊 预测看板: {output_path}")
    return output_path


def step_review(db_path: str, date_str: str, output_dir: str) -> str:
    """Step 5: 复盘（赛果回填 + 分析 + 看板）"""
    from review import run_review
    stats = run_review(date_str, db_path, output_dir)
    if stats:
        output_path = os.path.join(output_dir, f"review_{date_str.replace('-', '')}.html")
        return output_path
    return ""


def main():
    parser = argparse.ArgumentParser(description='雷速独立预测系统')
    parser.add_argument('--date', type=str, default=None, help='日期 YYYY-MM-DD (默认今天)')
    parser.add_argument('--db', type=str, default=None, help='DB 路径')
    parser.add_argument('--skip-fetch', action='store_true', help='跳过抓取，用已有JSON')
    parser.add_argument('--dashboard-only', action='store_true', help='只生成看板')
    parser.add_argument('--predict-only', action='store_true', help='只预测不入库')
    parser.add_argument('--review-only', action='store_true', help='只复盘')
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime('%Y-%m-%d')
    db_path = args.db or get_db_path()
    output_dir = os.path.join(REPO_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)

    print(f"{'='*60}")
    print(f"🏆 雷速独立预测系统 — {date_str}")
    print(f"{'='*60}")

    init_db(db_path)

    if args.review_only:
        step_review(db_path, date_str, output_dir)
        return

    if args.dashboard_only:
        step_dashboard(db_path, date_str, output_dir)
        return

    # Step 1: 抓取
    json_path = None
    if not args.skip_fetch:
        print(f"\n▶ [1/5] 抓取雷速数据")
        try:
            json_path = step_fetch(date_str, output_dir)
        except Exception as e:
            print(f"  ❌ 抓取失败: {e}")
            json_path = os.path.join(output_dir, f"leisu_{date_str.replace('-', '')}.json")

    if not json_path or not os.path.exists(json_path):
        jsons = sorted([f for f in os.listdir(output_dir) if f.startswith('leisu_') and f.endswith('.json')])
        if jsons:
            json_path = os.path.join(output_dir, jsons[-1])
            print(f"  📂 使用已有: {jsons[-1]}")
        else:
            print("  ❌ 无数据可用")
            return

    # Step 2: 预测
    print(f"\n▶ [2/5] 泊松预测")
    predicted = step_predict(json_path)

    if args.predict_only:
        for p in predicted[:5]:
            print(f"  {p['home_team']} vs {p['away_team']} → {p.get('prediction','?')} "
                  f"({p.get('prediction_prob',0):.1%}) risk={p.get('risk_level','')}")
        return

    # Step 3: 入库
    print(f"\n▶ [3/5] 写入 DB")
    step_save(predicted, db_path, date_str)

    # Step 4: 预测看板
    print(f"\n▶ [4/5] 生成预测看板")
    dashboard_path = step_dashboard(db_path, date_str, output_dir)

    # Step 5: 复盘
    print(f"\n▶ [5/5] 复盘")
    review_path = step_review(db_path, date_str, output_dir)

    print(f"\n{'='*60}")
    print(f"🎉 完成! DB={db_path}")
    if dashboard_path:
        print(f"   预测看板: {dashboard_path}")
    if review_path:
        print(f"   复盘报告: {review_path}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
