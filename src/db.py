#!/usr/bin/env python3
"""db.py — SQLite 数据库管理

精简 schema，专为 leisu 数据源设计，不含 football-dashboard 的 174 列历史包袱。
"""

import sqlite3
import os
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    match_id INTEGER,
    league TEXT DEFAULT '',
    home_team TEXT,
    away_team TEXT,
    home_rank TEXT DEFAULT '',
    away_rank TEXT DEFAULT '',

    -- 百家平均欧赔
    avg_odds_w REAL, avg_odds_d REAL, avg_odds_l REAL,
    -- 百家平均隐含概率(%)
    avg_prob_w REAL, avg_prob_d REAL, avg_prob_l REAL,
    -- 抽水
    avg_margin REAL DEFAULT 0,

    -- 亚盘(百家平均)
    ah_handicap REAL, ah_home_water REAL, ah_away_water REAL,
    ah_prob_home REAL, ah_prob_away REAL,

    -- 大小球(百家平均)
    ou_over REAL, ou_line REAL, ou_under REAL,
    ou_prob_over REAL, ou_prob_under REAL,

    -- 角球盘
    corner_over REAL, corner_line REAL, corner_under REAL,

    -- SWOT 胜率
    win_rate_home REAL, win_rate_away REAL,

    -- 近期战绩 JSON [胜,平,负]
    recent_home TEXT, recent_away TEXT,

    -- 泊松预测
    home_lambda REAL, away_lambda REAL,
    poisson_w REAL, poisson_d REAL, poisson_l REAL,
    final_w REAL, final_d REAL, final_l REAL,
    prediction TEXT,
    prediction_prob REAL,

    -- EV & Kelly
    ev_w REAL DEFAULT 0, ev_d REAL DEFAULT 0, ev_l REAL DEFAULT 0,
    best_direction TEXT DEFAULT '',
    kelly_stake REAL DEFAULT 0,
    value_flag INTEGER DEFAULT 0,

    -- 风险 & 信心
    risk_level TEXT DEFAULT '',
    confidence_index REAL DEFAULT 0,

    -- 赛果复盘
    actual_outcome TEXT DEFAULT '',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(date, home_team, away_team)
);

CREATE INDEX IF NOT EXISTS idx_pred_date ON predictions(date);
CREATE INDEX IF NOT EXISTS idx_pred_match ON predictions(match_id);
CREATE INDEX IF NOT EXISTS idx_pred_value ON predictions(value_flag);
"""


def get_db_path():
    """默认 DB 路径: 项目根/data/leisu.db"""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo, 'data', 'leisu.db')


def init_db(db_path=None):
    """初始化数据库（建表+索引）"""
    if db_path is None:
        db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.close()
    return db_path


def upsert_prediction(conn, row: dict):
    """UPSERT 单条预测（按 date+home+away 唯一约束）"""
    keys = [k for k in row.keys() if k not in ('id', 'created_at')]
    placeholders = ', '.join(keys)
    values = [row.get(k) for k in keys]

    update_sets = ', '.join(f"{k}=excluded.{k}" for k in keys if k not in ('date', 'home_team', 'away_team'))
    sql = f"""
        INSERT INTO predictions ({placeholders})
        VALUES ({', '.join('?' * len(keys))})
        ON CONFLICT(date, home_team, away_team)
        DO UPDATE SET {update_sets}
    """
    conn.execute(sql, values)


def get_predictions(conn, date_str: str):
    """获取指定日期的预测"""
    cur = conn.execute(
        "SELECT * FROM predictions WHERE date = ? ORDER BY prediction_prob DESC",
        (date_str,)
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_value_bets(conn, date_str: str, min_ev: float = 0.05):
    """获取价值投注 (value_flag=1)"""
    cur = conn.execute("""
        SELECT * FROM predictions
        WHERE date = ? AND value_flag = 1
        ORDER BY kelly_stake DESC
    """, (date_str,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def update_result(conn, date_str: str, home_team: str, away_team: str, outcome: str):
    """更新赛果"""
    conn.execute(
        "UPDATE predictions SET actual_outcome = ? WHERE date = ? AND home_team = ? AND away_team = ?",
        (outcome, date_str, home_team, away_team)
    )
