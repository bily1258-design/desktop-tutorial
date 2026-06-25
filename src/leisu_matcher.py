"""比赛匹配: 将雷速match数据映射到现有DB记录

匹配策略:
1. 精确匹配: 主客队名完全一致
2. 模糊匹配: 字符集相似度 > 0.6
3. 日期+联赛匹配: 同日同联赛的主客队
"""
import re
from typing import Optional


def normalize_team_name(name: str) -> str:
    """标准化队名用于匹配"""
    if not name:
        return ""
    # 去除空格、标点
    name = re.sub(r'[\s\-_.]', '', name)
    # 转小写
    name = name.lower()
    # 去除常见后缀
    for suffix in ['fc', 'cf', 'sc', 'ac', 'bc', 'fc.', 'afc', 'bfc']:
        if name.endswith(suffix) and len(name) > len(suffix) + 2:
            name = name[:-len(suffix)]
    return name


def name_similarity(a: str, b: str) -> float:
    """字符集相似度 (与现有team_match逻辑对齐)"""
    a = normalize_team_name(a)
    b = normalize_team_name(b)
    if not a or not b:
        return 0.0
    return len(set(a) & set(b)) / max(len(a), len(b), 1)


def match_leisu_to_db(leisu_match: dict, db_matches: list,
                       threshold: float = 0.5) -> Optional[dict]:
    """将雷速比赛匹配到DB记录
    
    Args:
        leisu_match: 雷速比赛数据 (含home_team, away_team)
        db_matches: DB记录列表 (含home_team, away_team, date, league)
        threshold: 最低相似度阈值
    
    Returns:
        最佳匹配的DB记录, 无匹配返回None
    """
    best_match = None
    best_score = 0
    
    leisu_home = leisu_match.get('home_team', '')
    leisu_away = leisu_match.get('away_team', '')
    
    for db in db_matches:
        db_home = db.get('home_team', '')
        db_away = db.get('away_team', '')
        
        # 主队和客队都要匹配
        home_sim = name_similarity(leisu_home, db_home)
        away_sim = name_similarity(leisu_away, db_away)
        
        # 综合得分: 两个方向都要匹配
        score = min(home_sim, away_sim)
        
        # 主客反转检查 (雷速主客可能与DB不同)
        home_sim_rev = name_similarity(leisu_home, db_away)
        away_sim_rev = name_similarity(leisu_away, db_home)
        score_rev = min(home_sim_rev, away_sim_rev)
        
        score = max(score, score_rev)
        
        if score > best_score:
            best_score = score
            best_match = db
    
    if best_score >= threshold:
        return best_match
    return None


def build_leisu_to_db_map(leisu_matches: list, db_matches: list) -> dict:
    """批量构建雷速match_id → DB记录的映射
    
    Returns:
        {leisu_match_id: db_record}
    """
    mapping = {}
    for lm in leisu_matches:
        db_match = match_leisu_to_db(lm, db_matches)
        if db_match:
            mapping[lm['match_id']] = db_match
    return mapping
