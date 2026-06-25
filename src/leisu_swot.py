"""雷速体育SWOT数据解析

SWOT接口返回的结构:
{
  "match_id": 4460943,
  "home": {"rank": "65", "id": 10478, "name": "波黑"},
  "away": {"rank": "56", "id": 11289, "name": "卡塔尔"},
  "recent_battles": {"home": [5,7,3], "away": [2,5,8]},
  "win_rate": [0.8405, 0.1595],
  "average_odds": {
    "europe": [[1.38,4.45,5.55], [64.2,19.9,16.0]],  # [[胜,平,负], [概率%]]
    "asia": [[0.98,1.0,0.88], [52.7,47.3]],           # [[主水,盘口,客水], [概率%]]
    "bs": [[0.8,2.25,1.05], [43.2,56.8]],             # [[大水,盘口,小水], [概率%]]
    "corner": [[0.72,9.5,1.0], [41.9,58.1]]           # [[大水,盘口,小水], [概率%]]
  }
}

映射到现有预测系统DB字段:
- avg_odds_close_w/d/l  ← average_odds.europe[0][0/1/2]
- ah_handicap           ← average_odds.asia[0][1]
- ah_home_water         ← average_odds.asia[0][0]
- ah_away_water         ← average_odds.asia[0][2]
- ou_over               ← average_odds.bs[0][0]
- ou_line               ← average_odds.bs[0][1]
- ou_under              ← average_odds.bs[0][2]
"""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class LeisuOdds:
    """雷速赔率数据(映射到现有DB字段)"""
    match_id: int
    league: str = ""
    home_team: str = ""
    away_team: str = ""
    home_rank: str = ""
    away_rank: str = ""
    
    # 百家平均欧赔
    avg_odds_w: Optional[float] = None
    avg_odds_d: Optional[float] = None
    avg_odds_l: Optional[float] = None
    
    # 百家平均隐含概率(%)
    avg_prob_w: Optional[float] = None
    avg_prob_d: Optional[float] = None
    avg_prob_l: Optional[float] = None
    
    # 亚盘(百家平均)
    ah_handicap: Optional[float] = None
    ah_home_water: Optional[float] = None
    ah_away_water: Optional[float] = None
    ah_prob_home: Optional[float] = None
    ah_prob_away: Optional[float] = None
    
    # 大小球(百家平均)
    ou_over: Optional[float] = None
    ou_line: Optional[float] = None
    ou_under: Optional[float] = None
    ou_prob_over: Optional[float] = None
    ou_prob_under: Optional[float] = None
    
    # 角球盘(雷速独有)
    corner_over: Optional[float] = None
    corner_line: Optional[float] = None
    corner_under: Optional[float] = None
    
    # 胜率(SWOT独有)
    win_rate_home: Optional[float] = None
    win_rate_away: Optional[float] = None
    
    # 近期战绩 [胜,平,负]
    recent_home: Optional[list] = None
    recent_away: Optional[list] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


def _safe_list_get(lst, idx, default=None):
    """安全获取列表元素"""
    if lst is None:
        return default
    try:
        return lst[idx] if idx < len(lst) else default
    except (TypeError, IndexError):
        return default


def parse_swot(match_id: int, swot_data: dict, league: str = "",
               home_team: str = "", away_team: str = "") -> LeisuOdds:
    """解析SWOT响应为LeisuOdds对象"""
    odds = LeisuOdds(match_id=match_id)
    
    # 基本信息
    home = swot_data.get("home") or {}
    away = swot_data.get("away") or {}
    odds.league = league
    odds.home_team = home_team or home.get("name", "")
    odds.away_team = away_team or away.get("name", "")
    odds.home_rank = str(home.get("rank", "")) if home.get("rank") else ""
    odds.away_rank = str(away.get("rank", "")) if away.get("rank") else ""
    
    # 胜率
    win_rate = swot_data.get("win_rate") or []
    if len(win_rate) >= 2:
        odds.win_rate_home = win_rate[0]
        odds.win_rate_away = win_rate[1]
    
    # 近期战绩
    recent = swot_data.get("recent_battles") or {}
    odds.recent_home = recent.get("home")
    odds.recent_away = recent.get("away")
    
    # 赔率数据
    avg_odds = swot_data.get("average_odds") or {}
    
    # 欧赔
    europe = avg_odds.get("europe")
    if europe and len(europe) >= 1:
        e0 = europe[0]
        if e0 and len(e0) >= 3:
            odds.avg_odds_w = e0[0]
            odds.avg_odds_d = e0[1]
            odds.avg_odds_l = e0[2]
        if len(europe) >= 2:
            e1 = europe[1]
            if e1 and len(e1) >= 3:
                odds.avg_prob_w = e1[0]
                odds.avg_prob_d = e1[1]
                odds.avg_prob_l = e1[2]
    
    # 亚盘
    asia = avg_odds.get("asia")
    if asia and len(asia) >= 1:
        a0 = asia[0]
        if a0 and len(a0) >= 3:
            odds.ah_home_water = a0[0]
            odds.ah_handicap = a0[1]
            odds.ah_away_water = a0[2]
        if len(asia) >= 2:
            a1 = asia[1]
            if a1 and len(a1) >= 2:
                odds.ah_prob_home = a1[0]
                odds.ah_prob_away = a1[1]
    
    # 大小球
    bs = avg_odds.get("bs")
    if bs and len(bs) >= 1:
        b0 = bs[0]
        if b0 and len(b0) >= 3:
            odds.ou_over = b0[0]
            odds.ou_line = b0[1]
            odds.ou_under = b0[2]
        if len(bs) >= 2:
            b1 = bs[1]
            if b1 and len(b1) >= 2:
                odds.ou_prob_over = b1[0]
                odds.ou_prob_under = b1[1]
    
    # 角球
    corner = avg_odds.get("corner")
    if corner and len(corner) >= 1:
        c0 = corner[0]
        if c0 and len(c0) >= 3:
            odds.corner_over = c0[0]
            odds.corner_line = c0[1]
            odds.corner_under = c0[2]
    
    return odds
