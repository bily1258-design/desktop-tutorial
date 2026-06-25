#!/usr/bin/env python3
"""雷速体育数据抓取主入口

数据流:
1. 从 www.leisu.com 首页提取足球比赛列表 (match_id)
2. 批量获取 SWOT 数据 (百家平均赔率+亚盘+大小球+角球)
3. 输出 JSON 文件

用法:
  python -m src.leisu_scraper                  # 首页模式(默认)
  python -m src.leisu_scraper --test           # 首页模式, 只取5场
  python -m src.leisu_scraper --date 2026-06-25
  python -m src.leisu_scraper --match-ids 4460943,4460940
  python -m src.leisu_scraper --scan-range 4460940 4460970
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.leisu_client import LeisuClient
from src.leisu_swot import parse_swot
from src.leisu_matches import get_matches_from_homepage
from src.config import OUTPUT_DIR


def scan_match_range(client: LeisuClient, start_id: int, end_id: int) -> list:
    """扫描match_id范围, 获取有效比赛的SWOT数据"""
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
    from pathlib import Path
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
    parser.add_argument("--test", action="store_true", help="测试模式(只取5场)")
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
        results = fetch_swot_batch(client, match_list)
        if results:
            save_output(results, date_str, "manual")
        return

    # 模式3: 首页模式(默认)
    match_list = get_matches_from_homepage(client, date_str)
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
