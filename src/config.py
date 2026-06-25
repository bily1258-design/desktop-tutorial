"""雷速体育数据抓取配置"""
import os

# === 雷速账号 ===
LEISU_USERNAME = os.getenv("LEISU_USERNAME", "Cruiser.ydlkr@gradesec.com")
LEISU_PASSWORD = os.getenv("LEISU_PASSWORD", "Digit123456")

# === API端点 ===
WEB_GATEWAY = "https://web-gateway.leisu.com"
API_GATEWAY = "https://api-gateway.leisu.com"
LIVE_HOST = "https://live.leisu.com"

# SWOT端点 (已验证: curl可获取加密数据→Python解密)
SWOT_PATH = "/v1/web/match/football/swot"

# 公共时间端点
TIME_PATH = "/v1/web/public/time"

# === 解密常量 ===
# web-gateway加密: shift = code - 100, roott减shift → base64 → gzip → URL decode → JSON
# Canvas加密: roott(str, 13) → base64 → zlib(wbits=15) → URL decode → JSON
CANVAS_SHIFT = 13

# === 签名相关 (api-gateway用, web-gateway不需要) ===
AMOUT_SPRING = "NcFebvke4S9vZJ8sR4QvrVKGAxkmqIo4"
UEMBER = "77&44H3"
DIFFTIME = -1

# === HTTP配置 ===
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://live.leisu.com/",
    "X-Requested-With": "XMLHttpRequest",
}

# === 路径 ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")

# === 请求间隔 ===
REQUEST_INTERVAL = 1.5  # 秒, 避免触发WAF
