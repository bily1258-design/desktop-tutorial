# leisu-scraper

雷速体育(leisu.com)足球赔率数据抓取工具，为预测系统提供百家平均赔率补充数据源。

## 核心能力

- **百家平均欧赔**: SWOT接口提供100+家博彩公司的平均赔率
- **亚盘数据**: 让球盘口 + 水位（百家平均）
- **大小球**: 盘口 + 水位（百家平均）
- **角球盘**: 雷速独有数据
- **SWOT胜率**: 基于历史数据的胜率分析

## 数据获取方式

| 方式 | 说明 | 覆盖范围 |
|------|------|---------|
| `--homepage` | 从首页提取比赛 | 当日热门约10场 |
| `--scan-range START END` | 扫描match_id范围 | 自定义范围 |
| `--match-ids ID1,ID2` | 指定match_id | 精确控制 |

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 测试模式 (只取5场)
python -m src.leisu_scraper --test

# 扫描指定ID范围
python -m src.leisu_scraper --scan-range 4460940 4460970

# 指定match_id
python -m src.leisu_scraper --match-ids 4460943,4460950

# 指定日期 (影响输出文件名)
python -m src.leisu_scraper --date 2026-06-25 --scan-range 4460940 4461000
```

## 输出格式

```json
{
  "date": "2026-06-25",
  "fetch_time": "2026-06-25T10:00:00",
  "source": "scan",
  "count": 16,
  "matches": [
    {
      "match_id": 4460943,
      "home_team": "波黑",
      "away_team": "卡塔尔",
      "avg_odds_w": 1.38,
      "avg_odds_d": 4.45,
      "avg_odds_l": 5.55,
      "ah_handicap": 1.0,
      "ah_home_water": 0.98,
      "ah_away_water": 0.88,
      "ou_line": 2.25,
      "ou_over": 0.8,
      "ou_under": 1.05
    }
  ]
}
```

## 解密原理

雷速web-gateway返回加密数据，解密链路：

```
roott(data, code-100) → base64 decode → gzip decompress → URL decode → JSON
```

关键点：
- `roott`是Caesar位移，**解密方向为减shift**
- 压缩格式为gzip (wbits=31)
- shift值 = code - 100，动态变化(100-126)

## 与现有预测系统集成

输出的`avg_odds_w/d/l`对应DB字段`avg_odds_close_w/d/l`，
`ah_handicap/home_water/away_water`对应DB的亚盘字段。

匹配方式：通过队名相似度匹配到DB中的`poisson_predictions`记录，
然后UPDATE对应字段。

## 项目结构

```
src/
├── config.py          # 配置（端点、常量、路径）
├── leisu_decrypt.py   # 解密模块（roott+base64+gzip）
├── leisu_client.py    # HTTP客户端（Cookie管理、请求控制）
├── leisu_swot.py      # SWOT数据解析（映射到DB字段）
├── leisu_matches.py   # 比赛列表获取（HTML解析）
├── leisu_matcher.py   # 队名匹配（雷速→DB映射）
└── leisu_scraper.py   # 主入口
output/                # 输出目录
```

## 注意事项

- Cookie有效期有限，需定期刷新（访问www.leisu.com自动获取）
- 请求间隔1.5秒，避免触发WAF
- SWOT接口无WAF，可从curl直接访问
- match_id为递增序列，扫描模式可发现所有比赛
