"""雷速体育比赛列表获取

从live.leisu.com页面提取比赛列表:
1. 获取页面HTML
2. 找到Canvas加密文本
3. 解密得到比赛数据(含match_id)
4. 解析为统一格式

也可从WAP版API获取赛程列表
"""
import re
import json
from datetime import datetime, timedelta
from .leisu_decrypt import decrypt_canvas
from .leisu_client import LeisuClient


def extract_canvas_text(html: str) -> str:
    """从HTML中提取Canvas加密文本
    
    雷速在页面中用Canvas绘制文字来防止爬虫,
    文字内容经过 rott+base64+zlib 加密后嵌入JS
    """
    # 匹配模式: document.getElementById('canvas元素').textContent 或类似
    # 也可能在 <script> 中以字符串形式出现
    patterns = [
        r'var\s+\w+\s*=\s*["\']([A-Za-z0-9+/=]{100,})["\']',
        r'\.textContent\s*=\s*["\']([A-Za-z0-9+/=]{100,})["\']',
        r'canvasData\s*=\s*["\']([A-Za-z0-9+/=]{100,})["\']',
        r'fontText\s*=\s*["\']([A-Za-z0-9+/=]{100,})["\']',
        # 完场页特殊格式: 在script标签中赋值给全局变量
        r'(?:var|let|const)\s+\w*data\w*\s*=\s*["\']([A-Za-z0-9+/=]{50,})["\']',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html)
        if matches:
            # 返回最长的匹配(最可能是完整的加密数据)
            return max(matches, key=len)
    
    return ""


def parse_match_from_canvas(canvas_data: dict) -> dict:
    """从Canvas解密数据中解析单场比赛
    
    Canvas数据格式(完场页示例):
    每场比赛包含: match_id, 联赛, 主客队, 比分, 时间等
    """
    # Canvas数据格式可能因页面而异, 这里处理常见的列表格式
    if isinstance(canvas_data, list):
        matches = []
        for item in canvas_data:
            match = _parse_single_match(item)
            if match:
                matches.append(match)
        return matches
    elif isinstance(canvas_data, dict):
        # 可能是嵌套结构
        for key in ['data', 'list', 'matches', 'result']:
            if key in canvas_data:
                return parse_match_from_canvas(canvas_data[key])
        # 可能本身就是单场比赛
        match = _parse_single_match(canvas_data)
        return [match] if match else []
    return []


def _parse_single_match(item) -> dict:
    """解析单场比赛数据"""
    if not isinstance(item, (dict, list)):
        return None
    
    if isinstance(item, list):
        # 数组格式: 可能是 [id, league, home, away, score, time, ...]
        if len(item) >= 6:
            return {
                'match_id': item[0],
                'league': item[1],
                'home_team': item[2],
                'away_team': item[3],
                'score': item[4],
                'kickoff_time': item[5],
            }
        return None
    
    # dict格式
    match_id = item.get('id') or item.get('match_id') or item.get('mid')
    if not match_id:
        return None
    
    home = item.get('home', {})
    away = item.get('away', {})
    
    return {
        'match_id': match_id,
        'league': item.get('league', {}).get('name', '') if isinstance(item.get('league'), dict) else item.get('league', ''),
        'home_team': home.get('name', '') if isinstance(home, dict) else item.get('home_team', str(home)),
        'away_team': away.get('name', '') if isinstance(away, dict) else item.get('away_team', str(away)),
        'home_rank': home.get('rank', '') if isinstance(home, dict) else '',
        'away_rank': away.get('rank', '') if isinstance(away, dict) else '',
        'kickoff_time': item.get('kickoff_time', '') or item.get('start_time', '') or item.get('time', ''),
        'score': item.get('score', ''),
    }


def get_match_list_from_page(client: LeisuClient, date_str: str = None) -> list:
    """从雷速live页面获取比赛列表
    
    Args:
        client: LeisuClient实例
        date_str: 日期字符串 YYYY-MM-DD, 默认今天
    
    Returns:
        比赛列表, 每项含match_id, league, home/away_team等
    """
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 尝试WAP版API (可能有赛程列表)
    # live.leisu.com的主页有当日赛程
    url = f"https://live.leisu.com/"
    if date_str != datetime.now().strftime('%Y-%m-%d'):
        url = f"https://live.leisu.com/?date={date_str}"
    
    print(f"📋 获取比赛列表: {date_str}")
    html = client.fetch_page(url)
    if not html:
        print("  ❌ 页面获取失败")
        return []
    
    # 提取Canvas加密文本
    canvas_text = extract_canvas_text(html)
    if not canvas_text:
        print("  ⚠ 未找到Canvas加密文本, 尝试从页面JS中提取match_id...")
        # 备用方案: 从页面中提取所有match_id
        return _extract_match_ids_from_html(html, date_str)
    
    # 解密Canvas数据
    try:
        canvas_data = decrypt_canvas(canvas_text)
        matches = parse_match_from_canvas(canvas_data)
        print(f"  ✅ Canvas解密成功: {len(matches)}场比赛")
        return matches
    except Exception as e:
        print(f"  ⚠ Canvas解密失败: {e}")
        return _extract_match_ids_from_html(html, date_str)


def _extract_match_ids_from_html(html: str, date_str: str) -> list:
    """从HTML中直接提取match_id(备用方案)
    
    页面中的比赛链接格式: /detail-{match_id}
    """
    pattern = r'/detail-(\d+)'
    match_ids = re.findall(pattern, html)
    match_ids = list(set(match_ids))  # 去重
    
    if match_ids:
        print(f"  ✅ 从页面链接提取到 {len(match_ids)} 个match_id")
        return [{'match_id': int(mid), 'date': date_str} for mid in match_ids]
    
    print("  ❌ 未找到任何比赛ID")
    return []


def get_match_list_from_wap(client: LeisuClient, date_str: str = None) -> list:
    """从WAP版API获取比赛列表(备选方案)
    
    WAP版: wap.leisu.com 可能有不同的赛程API
    """
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 尝试直接从完场页获取
    url = f"https://live.leisu.com/finished"
    html = client.fetch_page(url)
    if not html:
        return []
    
    return _extract_match_ids_from_html(html, date_str)
