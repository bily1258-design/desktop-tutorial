#!/usr/bin/env python3
"""dashboard.py — HTML 看板生成器

风格: 深色主题、数据密度高、一目了然
"""

import html
import os


DIRECTION_CN = {'W': '主胜', 'D': '平局', 'L': '客胜'}
RISK_COLOR = {'低': '#4caf50', '中': '#ff9800', '高': '#f44336', '': '#999'}
VALUE_ICON = {0: '', 1: '🔥'}


def _bar(percent, color, width=60):
    """生成概率条 HTML"""
    w = max(2, int(percent * width))
    return f'<div style="background:{color};width:{w}px;height:14px;border-radius:2px;display:inline-block;vertical-align:middle"></div>'


def _stars(score):
    """信心指数 → 星星"""
    n = max(0, min(5, int(score)))
    return '★' * n + '☆' * (5 - n)


def _ev_color(ev):
    if ev > 0.10:
        return '#4caf50'
    elif ev > 0.05:
        return '#8bc34a'
    elif ev > 0:
        return '#ff9800'
    return '#666'


def generate_dashboard(predictions: list, date_str: str, output_path: str):
    """生成 HTML 看板"""
    # 分组: 价值投注 / 普通
    value_bets = [p for p in predictions if p.get('value_flag') == 1]
    normal = [p for p in predictions if p.get('value_flag') != 1]

    # 统计
    n_total = len(predictions)
    n_value = len(value_bets)
    n_w = sum(1 for p in predictions if p.get('prediction') == 'W')
    n_d = sum(1 for p in predictions if p.get('prediction') == 'D')
    n_l = sum(1 for p in predictions if p.get('prediction') == 'L')

    rows_html = ''

    # 价值投注优先
    for p in value_bets + normal:
        pred = p.get('prediction', '?')
        pred_cn = DIRECTION_CN.get(pred, pred)
        prob = p.get('prediction_prob', 0) or 0
        risk = p.get('risk_level', '')
        conf = p.get('confidence_index', 0) or 0
        ev_max = max(p.get('ev_w', 0) or 0, p.get('ev_d', 0) or 0, p.get('ev_l', 0) or 0)
        kelly = p.get('kelly_stake', 0) or 0
        is_value = p.get('value_flag') == 1
        odds_w = p.get('avg_odds_w', 0) or 0
        odds_d = p.get('avg_odds_d', 0) or 0
        odds_l = p.get('avg_odds_l', 0) or 0
        ah = p.get('ah_handicap')
        ou = p.get('ou_line')

        # 概率条
        fw = p.get('final_w', 0) or 0
        fd = p.get('final_d', 0) or 0
        fl = p.get('final_l', 0) or 0

        row_class = 'value-row' if is_value else ''
        value_icon = VALUE_ICON.get(1 if is_value else 0, '')

        rows_html += f"""
        <tr class="{row_class}">
            <td class="team">{html.escape(p.get('home_team',''))} <span class="vs">vs</span> {html.escape(p.get('away_team',''))}</td>
            <td class="center">{html.escape(p.get('league',''))}</td>
            <td class="odds">{odds_w:.2f} / {odds_d:.2f} / {odds_l:.2f}</td>
            <td class="center">
                {_bar(fw, '#5c6bc0')} {fw:.1%}
                <br>{_bar(fd, '#78909c')} {fd:.1%}
                <br>{_bar(fl, '#ef5350')} {fl:.1%}
            </td>
            <td class="center"><b>{pred_cn}</b> {prob:.1%}</td>
            <td class="center" style="color:{RISK_COLOR.get(risk,'#999')}">{risk}</td>
            <td class="center">{_stars(conf)}</td>
            <td class="center" style="color:{_ev_color(ev_max)}">{ev_max:+.1%}</td>
            <td class="center">{kelly:.1%}</td>
            <td class="center">{ah:+.1f} / O{ou:.2f}</td>
            <td class="center">{value_icon}</td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>雷速预测看板 — {date_str}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#1a1a2e; color:#e0e0e0; font-family:'SF Mono','Cascadia Code',monospace; padding:20px; }}
h1 {{ color:#fff; font-size:20px; margin-bottom:4px; }}
.subtitle {{ color:#888; font-size:12px; margin-bottom:16px; }}
.stats {{ display:flex; gap:20px; margin-bottom:16px; }}
.stat {{ background:#16213e; padding:8px 16px; border-radius:6px; }}
.stat-label {{ color:#888; font-size:11px; }}
.stat-value {{ color:#fff; font-size:18px; font-weight:bold; }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
th {{ background:#16213e; color:#aaa; padding:8px 6px; text-align:left; position:sticky; top:0; }}
td {{ padding:6px; border-bottom:1px solid #2a2a4a; vertical-align:top; }}
.value-row {{ background:rgba(255,152,0,0.08); }}
.value-row:hover {{ background:rgba(255,152,0,0.15); }}
tr:hover {{ background:rgba(255,255,255,0.03); }}
.team {{ white-space:nowrap; font-weight:500; }}
.vs {{ color:#666; margin:0 4px; }}
.center {{ text-align:center; }}
.odds {{ font-size:11px; color:#bbb; }}
.footer {{ margin-top:20px; color:#555; font-size:11px; text-align:center; }}
</style>
</head>
<body>
<h1>⚽ 雷速预测看板</h1>
<div class="subtitle">数据源: leisu.com 百家平均 | {date_str} | 泊松+隐含概率融合</div>

<div class="stats">
    <div class="stat"><div class="stat-label">总场次</div><div class="stat-value">{n_total}</div></div>
    <div class="stat"><div class="stat-label">价值投注</div><div class="stat-value" style="color:#ff9800">{n_value}</div></div>
    <div class="stat"><div class="stat-label">主胜/平/客</div><div class="stat-value" style="font-size:14px">{n_w}/{n_d}/{n_l}</div></div>
</div>

<table>
<tr>
    <th>比赛</th><th>联赛</th><th>欧赔(主/平/客)</th><th>融合概率</th>
    <th>方向</th><th>风险</th><th>信心</th><th>EV</th><th>Kelly</th>
    <th>亚盘/大小</th><th>V</th>
</tr>
{rows_html}
</table>

<div class="footer">
    Generated by leisu-predict | 泊松λ={2.4/2:.1f}+0.15 HOME_ADV | α=0.5/0.5 | EV阈值=5%
</div>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


if __name__ == '__main__':
    # 测试：用已有 JSON 生成
    import json
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from db import init_db, get_db_path

    json_path = sys.argv[1] if len(sys.argv) > 1 else '../output/leisu_20260625.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    from predict import predict_match
    preds = [predict_match(m) for m in data.get('matches', [])]

    output_path = json_path.replace('leisu_', 'dashboard_').replace('.json', '.html')
    generate_dashboard(preds, data.get('date', '2026-06-25'), output_path)
    print(f"Dashboard: {output_path}")
