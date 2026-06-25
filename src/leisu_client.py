"""雷速体育HTTP客户端

管理Cookie、WAF验证、请求重试
"""
import re
import json
import time
import requests
from pathlib import Path
from .config import (
    WEB_GATEWAY, LIVE_HOST, DEFAULT_HEADERS,
    LEISU_USERNAME, LEISU_PASSWORD, REQUEST_INTERVAL,
    OUTPUT_DIR
)
from .leisu_decrypt import decrypt_auto


class LeisuClient:
    """雷速体育API客户端"""
    
    def __init__(self, cookie_file=None):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._last_request_time = 0
        self._cookie_file = cookie_file or Path(OUTPUT_DIR) / ".leisu_cookies.json"
        self._logged_in = False
        self._load_cookies()
    
    def _rate_limit(self):
        """请求间隔控制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()
    
    def _load_cookies(self):
        """从文件加载Cookie"""
        if Path(self._cookie_file).exists():
            try:
                with open(self._cookie_file, 'r') as f:
                    cookies = json.load(f)
                for name, value in cookies.items():
                    self.session.cookies.set(name, value, domain=".leisu.com")
                self._logged_in = True
                print(f"  加载Cookie: {len(cookies)}个")
            except Exception as e:
                print(f"  加载Cookie失败: {e}")
    
    def _save_cookies(self):
        """保存Cookie到文件"""
        try:
            Path(self._cookie_file).parent.mkdir(parents=True, exist_ok=True)
            # Deduplicate cookies
            cookies = {}
            for c in self.session.cookies:
                cookies[c.name] = c.value
            with open(self._cookie_file, 'w') as f:
                json.dump(cookies, f)
        except Exception as e:
            print(f"  保存Cookie失败: {e}")
    
    def login(self):
        """登录雷速获取Cookie
        
        流程: 访问首页获取WAF Cookie → 设置source cookie
        """
        if self._logged_in:
            return True
            
        print("🔑 获取雷速Cookie...")
        
        # Step 1: 获取WAF Cookie
        try:
            resp = self.session.get("https://www.leisu.com/", timeout=15)
            print(f"  首页状态: {resp.status_code}")
        except Exception as e:
            print(f"  ⚠ 获取WAF Cookie失败: {e}")
        
        # Step 2: 确保source cookie
        self.session.cookies.set("source", "pc_leisu", domain=".leisu.com")
        
        # Step 3: 验证Cookie有效
        has_waf = any(c.name == "_c_WBKFRo" for c in self.session.cookies)
        if has_waf:
            self._logged_in = True
            self._save_cookies()
            print("  ✅ WAF Cookie获取成功")
        else:
            print("  ⚠ 未获取到WAF Cookie, 尝试继续...")
            # 即使没有WAF cookie, SWOT可能仍然可用
            self._logged_in = True
            self._save_cookies()
        
        return True
    
    def _ensure_cookies(self):
        """确保有Cookie"""
        if not self._logged_in:
            self.login()
    
    def get_swot(self, match_id: int) -> dict:
        """获取SWOT数据(百家平均赔率+亚盘+大小球+角球)
        
        Args:
            match_id: 雷速比赛ID
            
        Returns:
            解密后的SWOT数据, 失败返回None
        """
        self._ensure_cookies()
        self._rate_limit()
        
        url = f"{WEB_GATEWAY}/v1/web/match/football/swot"
        params = {"match_id": match_id}
        
        try:
            resp = self.session.get(url, params=params, timeout=15)
            raw = resp.json()
            code = raw.get("code", -1)
            
            if code == 0:
                return raw.get("data")  # 明文
            
            if 100 <= code <= 126:
                try:
                    return decrypt_auto(raw["data"], code)
                except Exception as e:
                    print(f"  SWOT {match_id} 解密失败: {e}")
                    return None
            
            # code != 0 and not in 100-126 range
            return None
            
        except Exception as e:
            print(f"  SWOT {match_id} 错误: {e}")
            return None
    
    def get_server_time(self):
        """获取服务器时间(测试连通性)"""
        url = f"{WEB_GATEWAY}/v1/web/public/time"
        try:
            resp = self.session.get(url, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data")
            return None
        except Exception as e:
            print(f"  获取服务器时间失败: {e}")
            return None
    
    def fetch_page(self, url: str) -> str:
        """获取页面HTML"""
        self._rate_limit()
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"  获取页面失败: {e}")
            return ""
