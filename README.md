# leisu-scraper

雷速体育(leisu.com)足球赔率数据抓取工具 — 百家平均欧赔+亚盘+大小球+角球

## 数据源

- **首页**: `www.leisu.com` → 提取当日足球比赛列表 (match_id)
- **SWOT接口**: `web-gateway.leisu.com/v1/web/match/football/swot` → 百家平均赔率数据

## 数据字段

| 雷速字段 | 映射到 DB | 说明 |
|---------|----------|------|
| `europe[0][0/1/2]` | `avg_odds_close_w/d/l` | 百家平均欧赔 |
| `europe[1][0/1/2]` | `avg_prob_w/d/l` | 隐含概率% |
| `asia[0][0/1/2]` | `ah_home_water/handicap/away_water` | 亚盘 |
| `bs[0][0/1/2]` | `ou_over/line/under` | 大小球 |
| `corner[0][0/1/2]` | `corner_over/line/under` | 角球盘 |
| `win_rate[0/1]` | `win_rate_home/away` | SWOT胜率 |

## 用法

```bash
# 安装依赖
pip install requests

# 默认: 从首页获取当日足球比赛, 批量抓取SWOT
python -m src.leisu_scraper

# 测试模式: 只取前5场
python -m src.leisu_scraper --test

# 指定日期
python -m src.leisu_scraper --date 2026-06-25

# 指定match_id
python -m src.leisu_scraper --match-ids 4460943,4460940

# 扫描match_id范围
python -m src.leisu_scraper --scan-range 4460940 4460970
```

## 项目结构

```
src/
├── config.py          # 端点、常量、路径配置
├── leisu_decrypt.py   # 解密模块 (roott+base64+gzip)
├── leisu_client.py    # HTTP客户端 (Cookie/限流)
├── leisu_matches.py   # 首页比赛列表提取
├── leisu_swot.py      # SWOT数据解析 (DB字段映射)
├── leisu_matcher.py   # 队名匹配 (雷速→DB)
└── leisu_scraper.py   # 主入口
```

## 解密链路

雷速 web-gateway 响应加密: `code` 字段 100-126 动态变化

```
encrypted_data → roott(data, code-100) → base64.decode → gzip.decompress(wbits=31) → URL.decode → JSON
```

## 集成到 football-dashboard

输出 JSON 可直接导入 football-dashboard 的 pipeline:

```python
# pipeline中添加步骤: fetch_leisu_swot
# 将雷速百家平均赔率写入 poisson_predictions 表
```
