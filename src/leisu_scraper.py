#!/usr/bin/env python3
"""雷速体育数据抓取主入口

数据流:
1. 获取比赛列表 (www.leisu.com首页 + api-football)
2. 批量获取SWOT数据 (百家平均赔率+亚盘+大小球)
3. 输出JSON文件

用法:
  python -m src.leisu_scraper --date 2026-06-25
  python -m src.leisu_scraper --match-ids 4460943,4460940
  python -m src.leisu_scraper --scan-range 4460940 4460970
  python -m src.leisu_scraper --test
"""
import argparse
import json
import time
import os
import re
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.leisu_client import LeisuClient
from src.leisu_swot import parse_swot
from src.config import OUTPUT_DIR


def get_matches_from_homepage(client: LeisuClient) -> list:
    """从www.leisu.com首页提取比赛列表
    
    Returns:
        [{match_id, home_team, away_team, league_id}, ...]
    """
    print("📋 从首页获取比赛列表...")
    html = client.fetch_page('https://www.leisu.com/')
    if not html:
        return []
    
    # 提取所有detail链接中的match_id
    all_mids = re.findall(r'detail-(\d+)', html)
    unique_mids = list(set(int(x) for x in all_mids))
    
    # 提取队名
    # 使用更可靠的解析方式: 先找到所有team链接
    team_data = re.findall(
        r'/data/zuqiu/team-(\d+)"[^>]*>[^<]*<[^>]*>[^<]*<[^>]*class="name"[^>]*>([^<]+)<',
        html
    )
    
    # 构建team_id → name映射
    team_map = {}
    for tid, name in team_data:
        team_map[int(tid)] = name.strip()
    
    # 为每个match_id找附近的队名
    matches = []
    for mid in unique_mids:
        idx = html.find(f'detail-{mid}')
        if idx < 0:
            continue
        
        # 向前搜索最近的team ID
        context_before = html[max(0, idx-3000):idx]
        home_teams = re.findall(r'team-(\d+)"[^>]*>.*?class="name"[^>]*>([^<]+)<', context_before)
        home_team = home_teams[-1][1].strip() if home_teams else ''
        home_team_id = int(home_teams[-1][0]) if home_teams else 0
        
        # 向后搜索最近的team ID
        context_after = html[idx:idx+2000]
        away_teams = re.findall(r'team-(\d+)"[^>]*>.*?class="name"[^>]*>([^<]+)<', context_after)
        away_team = away_teams[0][1].strip() if away_teams else ''
        away_team_id = int(away_teams[0][0]) if away_teams else 0
        
        # 找联赛
        comp_ids = re.findall(r'comp-(\d+)"', context_before)
        league_id = comp_ids[-1] if comp_ids else ''
        
        # 判断是否是足球 (通过data/zuqiu路径)
        is_football = 'zuqiu' in context_before.lower()
        
        if is_football or (home_team and away_team):
            matches.append({
                'match_id': mid,
                'home_team': home_team,
                'away_team': away_team,
                'home_team_id': home_team_id,
                'away_team_id': away_team_id,
                'league_id': league_id,
            })
    
    print(f"  找到 {len(matches)} 场比赛 (含 {sum(1 for m in matches if m['home_team'])} 场有队名)")
    return matches


def scan_match_range(client: LeisuClient, start_id: int, end_id: int) -> list:
    """扫描match_id范围, 获取有效比赛的SWOT数据
    
    Args:
        client: LeisuClient
        start_id: 起始match_id
        end_id: 结束match_id
    
    Returns:
        LeisuOdds列表
    """
    print(f"🔍 扫描 match_id {start_id}~{end_id} ({end_id-start_id+1}个)...")
    results = []
    success = 0
    
    for mid in range(start_id, end_id + 1):
        swot = client.get_swot(mid)
        if swot:
            odds = parse_swot(mid, swot)
            results.append(odds.to_dict())
            success += 1
            print(f"  ✅ {mid}: {odds.home_team} vs {odds.away_team}", end="")
            if odds.avg_odds_w:
                print(f" | 欧{odds.avg_odds_w:.2f}/{odds.avg_odds_d:.2f}/{odds.avg_odds_l:.2f}", end="")
            print()
        # 扫描模式不需要打印失败
    
    print(f"\n📊 扫描完成: 有效{success}/{end_id-start_id+1}")
    return results


def fetch_swot_batch(client: LeisuClient, match_list: list) -> list:
    """批量获取SWOT数据
    
    Args:
        client: LeisuClient
        match_list: [{match_id, home_team, away_team, league}, ...]
    
    Returns:
        LeisuOdds dict列表
    """
    results = []
    total = len(match_list)
    success = 0
    fail = 0
    
    for i, m in enumerate(match_list):
        match_id = m['match_id']
        league = m.get('league', '')
        home = m.get('home_team', '')
        away = m.get('away_team', '')
        
        print(f"  [{i+1}/{total}] SWOT {match_id}...", end=" ", flush=True)
        swot = client.get_swot(match_id)
        
        if swot:
            odds = parse_swot(match_id, swot, league, home, away)
            results.append(odds.to_dict())
            success += 1
            w, d, l = odds.avg_odds_w or 0, odds.avg_odds_d or 0, odds.avg_odds_l or 0
            ah = odds.ah_handicap or 0
            print(f"✅ {odds.home_team} vs {odds.away_team} | 欧{w:.2f}/{d:.2f}/{l:.2f} 亚{ah}")
        else:
            fail += 1
            print("❌")
    
    print(f"\n📊 结果: 成功{success}, 失败{fail}, 合计{total}")
    return results


def save_output(data: list, date_str: str, source: str = "leisu_swot"):
    """保存输出JSON"""
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    output_path = Path(OUTPUT_DIR) / f"leisu_{date_str.replace('-', '')}.json"
    
    output = {
        "date": date_str,
        "fetch_time": datetime.now().isoformat(),
        "source": source,
        "count": len(data),
        "matches": data,
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"💾 保存到: {output_path}")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="雷速体育数据抓取")
    parser.add_argument("--date", default=None, help="日期 YYYY-MM-DD (默认今天)")
    parser.add_argument("--match-ids", default=None, help="指定match_id, 逗号分隔")
    parser.add_argument("--scan-range", nargs=2, type=int, metavar=('START', 'END'),
                       help="扫描match_id范围")
    parser.add_argument("--test", action="store_true", help="测试模式(少量数据)")
    parser.add_argument("--homepage", action="store_true", help="从首页获取比赛列表")
    args = parser.parse_args()
    
    date_str = args.date or datetime.now().strftime('%Y-%m-%d')
    client = LeisuClient()
    
    # 测试连通性
    server_time = client.get_server_time()
    if server_time:
        print(f"✅ 服务器连通")
    else:
        print("❌ 服务器不可达")
        return
    
    # 模式1: 扫描match_id范围
    if args.scan_range:
        results = scan_match_range(client, args.scan_range[0], args.scan_range[1])
        if results:
            save_output(results, date_str, "scan")
        return
    
    # 模式2: 指定match_ids
    if args.match_ids:
        match_ids = [int(x.strip()) for x in args.match_ids.split(',')]
        match_list = [{'match_id': mid} for mid in match_ids]
        if args.test:
            match_list = match_list[:5]
        results = fetch_swot_batch(client, match_list)
        if results:
            save_output(results, date_str, "manual")
        return
    
    # 模式3: 从首页获取比赛列表
    match_list = get_matches_from_homepage(client)
    if not match_list:
        print("❌ 未获取到比赛列表")
        return
    
    # 测试模式: 只取前5场
    if args.test:
        match_list = match_list[:5]
        print(f"🧪 测试模式: 只处理前{len(match_list)}场")
    
    # 批量获取SWOT
    results = fetch_swot_batch(client, match_list)
    if results:
        save_output(results, date_str, "homepage")


if __name__ == "__main__":
    main()
