# leisu-scraper ⚽

雷速体育(leisu.com)独立预测系统 — 数据抓取 + 泊松预测 + EV/Kelly + HTML看板

## 架构

```
leisu-scraper/
├── src/
│   ├── leisu_scraper.py    # 主抓取入口
│   ├── leisu_matches.py    # 首页比赛列表提取（双结构解析）
│   ├── leisu_swot.py       # SWOT 数据解析（百家平均赔率/概率）
│   ├── leisu_client.py     # HTTP 客户端（Cookie + 解密）
│   ├── leisu_decrypt.py    # web-gateway 响应解密
│   ├── leisu_matcher.py    # 队名匹配
│   ├── config.py           # 配置
│   ├── predict.py          # 泊松预测引擎（λ反推 + 融合 + EV + Kelly）
│   ├── db.py               # SQLite 管理（精简 schema）
│   ├── pipeline.py         # 全链路：抓取→预测→入库→看板
│   └── dashboard.py        # HTML 看板生成
├── data/
│   └── leisu.db            # SQLite 数据库
├── output/
│   ├── leisu_*.json        # 原始抓取数据
│   └── dashboard_*.html    # 看板页面
└── requirements.txt
```

## 使用

```bash
# 完整流程（抓取+预测+入库+看板）
python -m src.pipeline --date 2026-06-25

# 跳过抓取，用已有 JSON
python -m src.pipeline --date 2026-06-25 --skip-fetch

# 只生成看板
python -m src.pipeline --date 2026-06-25 --dashboard-only
```

## 预测模型

1. **隐含概率**：雷速百家平均直接提供（去抽水后的市场概率）
2. **泊松预测**：隐含概率 → 反推 λ_home/λ_away → 泊松独立分布
3. **融合**：`final = 0.5×泊松 + 0.5×隐含概率`
4. **EV**：`EV = final_prob × (odds-1) - (1-final_prob)`
5. **Kelly**：`f* = (b×p - q) / b`，b=赔率-1，p=final_prob，q=1-p
6. **价值标记**：EV > 5% → 🔥

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| BASE_TOTAL_GOALS | 2.4 | 联赛平均总进球 |
| HOME_ADV | 0.15 | 主场加成 |
| SKILL_FACTOR | 0.6 | 实力调整系数 |
| POISSON_WEIGHT | 0.5 | 泊松权重 |
| EV阈值 | 5% | 价值投注标记线 |

## 数据来源

- 比赛列表：`https://www.leisu.com/` 首页 HTML
- SWOT数据：`https://web-gateway.leisu.com/v1/web/match/football/swot?match_id={id}`
- 不限竞彩，所有足球比赛均可入场
