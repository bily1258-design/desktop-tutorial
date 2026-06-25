"""雷速体育比赛列表获取

从 www.leisu.com 首页HTML提取当日足球比赛列表。
两种HTML结构:
1. match-lier: 已开赛/完场, 含detail链接+onhome/onaway队名
2. match: 即将开赛, 含detail链接+team-name队名

足球通过 data/zuqiu/ 路径区分, 篮球用 data/lanqiu/。
SWOT接口返回完整队名+赔率, 首页提取主要负责 match_id 列表。
"""
import re
from datetime import datetime
from .leisu_client import LeisuClient


def get_matches_from_homepage(client: LeisuClient, date_str: str = None) -> list:
    """从 www.leisu.com 首页提取足球比赛列表

    Returns:
        [{match_id, home_team, away_team, league, league_id,
          kickoff_time, home_team_id, away_team_id}, ...]
    """
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    print(f"📋 从首页获取 {date_str} 足球比赛列表...")
    html = client.fetch_page('https://www.leisu.com/')
    if not html:
        print("  ❌ 首页获取失败")
        return []

    matches = {}

    # === 结构1: match-lier 块 (已开赛/完场) ===
    for block in re.split(r'<div class="match-lier"', html)[1:]:
        if 'data/zuqiu/' not in block:
            continue
        m = _parse_match_lier(block)
        if m and m['match_id'] not in matches:
            matches[m['match_id']] = m

    # === 结构2: match 块 (即将开赛/推荐) ===
    for block in re.split(r'<div class="match">', html)[1:]:
        if 'data/zuqiu/' not in block and 'football/' not in block:
            # 如果没有明确标记, 但有足球detail链接也试试
            if not re.search(r'live\.leisu\.com/detail-\d+', block):
                continue
            if 'lanqiu' in block:
                continue
        m = _parse_match_block(block)
        if m and m['match_id'] not in matches:
            matches[m['match_id']] = m

    # === 兜底: 从所有足球detail链接提取 (确保不遗漏) ===
    # 足球detail = live.leisu.com/detail-{id} (不含 /lanqiu/)
    all_detail_ids = set(re.findall(r'live\.leisu\.com/detail-(\d+)', html))
    lanqiu_ids = set(re.findall(r'live\.leisu\.com/lanqiu/detail-(\d+)', html))
    football_ids = all_detail_ids - lanqiu_ids

    for mid_str in football_ids:
        mid = int(mid_str)
        if mid not in matches:
            matches[mid] = {'match_id': mid, 'home_team': '', 'away_team': '',
                            'home_team_id': 0, 'away_team_id': 0,
                            'league': '', 'league_id': '', 'kickoff_time': ''}

    result = sorted(matches.values(), key=lambda x: x.get('kickoff_time', ''))
    print(f"  ✅ 提取到 {len(result)} 场足球比赛")
    for m in result:
        teams = f"{m['home_team']} vs {m['away_team']}" if m['home_team'] else f"match_id={m['match_id']}"
        print(f"     {m['league']:8s} {m['kickoff_time']:12s} {teams}")

    return result


def _parse_match_lier(block: str) -> dict:
    """解析 match-lier 块 (已开赛/完场)"""
    detail_m = re.search(r'live\.leisu\.com/detail-(\d+)', block)
    if not detail_m:
        return None

    # 联赛
    comp_m = re.search(r'data/zuqiu/comp-(\d+)"[^>]*>([^<]+)<', block)
    league = comp_m.group(2).strip() if comp_m else ''
    league_id = comp_m.group(1) if comp_m else ''

    # 主队
    home_m = re.search(
        r'onhome[^>]*href="[^"]*data/zuqiu/team-(\d+)"[^>]*>.*?class="name"[^>]*>([^<]+)<',
        block, re.DOTALL)
    home_team = home_m.group(2).strip() if home_m else ''
    home_team_id = int(home_m.group(1)) if home_m else 0

    # 客队
    away_m = re.search(
        r'onaway[^>]*href="[^"]*data/zuqiu/team-(\d+)"[^>]*>.*?class="name"[^>]*>([^<]+)<',
        block, re.DOTALL)
    away_team = away_m.group(2).strip() if away_m else ''
    away_team_id = int(away_m.group(1)) if away_m else 0

    # 时间
    time_m = re.search(r'class="timecolor"[^>]*>(\d+:\d+)<', block)
    date_m = re.search(r'</span>\s*<span>(\d+-\d+)</span>', block)
    kickoff = ''
    if time_m:
        kickoff = time_m.group(1)
        if date_m:
            kickoff = f"{date_m.group(1)} {kickoff}"

    return {
        'match_id': int(detail_m.group(1)),
        'home_team': home_team, 'away_team': away_team,
        'home_team_id': home_team_id, 'away_team_id': away_team_id,
        'league': league, 'league_id': league_id,
        'kickoff_time': kickoff,
    }


def _parse_match_block(block: str) -> dict:
    """解析 match 块 (即将开赛/推荐)"""
    detail_m = re.search(r'live\.leisu\.com/detail-(\d+)', block)
    if not detail_m:
        return None

    # 队名 (team-name 格式)
    team_names = re.findall(r'class="team-name[^"]*"[^>]*>([^<]+)<', block)
    home_team = team_names[0].strip() if len(team_names) >= 1 else ''
    away_team = team_names[1].strip() if len(team_names) >= 2 else ''

    # 时间
    title_m = re.search(r'class="title"[^>]*>([^<]+)<', block)
    kickoff = title_m.group(1).strip() if title_m else ''

    # 联赛 (match块通常没有联赛信息, SWOT会补充)
    comp_m = re.search(r'data/zuqiu/comp-(\d+)"[^>]*>([^<]+)<', block)
    league = comp_m.group(2).strip() if comp_m else ''
    league_id = comp_m.group(1) if comp_m else ''

    return {
        'match_id': int(detail_m.group(1)),
        'home_team': home_team, 'away_team': away_team,
        'home_team_id': 0, 'away_team_id': 0,
        'league': league, 'league_id': league_id,
        'kickoff_time': kickoff,
    }
