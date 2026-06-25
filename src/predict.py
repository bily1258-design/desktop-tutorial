#!/usr/bin/env python3
"""predict.py — 泊松预测引擎

从雷速百家平均隐含概率出发：
  1. 隐含概率 → 反推 λ_home / λ_away
  2. 泊松独立分布 → P(主胜/平/客胜)
  3. final = α×poisson + (1-α)×implied
  4. 判定方向 + 信心指数 + 风险等级
"""

import math

# === 算法常量 ===
BASE_TOTAL_GOALS = 2.4    # 联赛平均总进球
HOME_ADV = 0.15            # 主场加成
SKILL_FACTOR = 0.6         # 实力调整系数
POISSON_WEIGHT = 0.5       # final 权重: 泊松
IMPLIED_WEIGHT = 0.5       # final 权重: 隐含概率
LAMBDA_MIN, LAMBDA_MAX = 0.3, 4.0


def poisson_pmf(lam, k):
    """泊松分布 P(X=k)"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def poisson_match_probs(lam_h, lam_a, max_goals=10):
    """泊松独立分布算 P(主胜/平/客胜)"""
    p_h = [poisson_pmf(lam_h, k) for k in range(max_goals + 1)]
    p_a = [poisson_pmf(lam_a, k) for k in range(max_goals + 1)]
    p_w = p_d = p_l = 0.0
    for k in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = p_h[k] * p_a[j]
            if k > j:
                p_w += p
            elif k == j:
                p_d += p
            else:
                p_l += p
    return p_w, p_d, p_l


def estimate_lambdas(imp_w, imp_d, imp_l):
    """从隐含概率反推 λ_home / λ_away

    imp_w/d/l 为 0~1 的概率值（非百分比）
    """
    base = BASE_TOTAL_GOALS / 2
    denom = max(imp_w + imp_l, 0.01)
    share_h = imp_w / denom
    skill_adj = SKILL_FACTOR * (share_h - 0.5)
    lam_h = base + HOME_ADV + skill_adj
    lam_a = base - HOME_ADV - skill_adj
    lam_h = max(LAMBDA_MIN, min(LAMBDA_MAX, lam_h))
    lam_a = max(LAMBDA_MIN, min(LAMBDA_MAX, lam_a))
    return round(lam_h, 3), round(lam_a, 3)


def implied_from_odds(odds_w, odds_d, odds_l):
    """从欧赔反推隐含概率（去抽水归一化），返回 (w, d, l) 0~1"""
    if not odds_w or not odds_d or not odds_l:
        return None, None, None
    if odds_w <= 0 or odds_d <= 0 or odds_l <= 0:
        return None, None, None
    raw_w = 1.0 / odds_w
    raw_d = 1.0 / odds_d
    raw_l = 1.0 / odds_l
    total = raw_w + raw_d + raw_l
    return raw_w / total, raw_d / total, raw_l / total


def calc_margin(odds_w, odds_d, odds_l):
    """计算抽水（margin/overround）"""
    if not odds_w or not odds_d or not odds_l or odds_w <= 0 or odds_d <= 0 or odds_l <= 0:
        return 0.0
    return round((1.0/odds_w + 1.0/odds_d + 1.0/odds_l - 1.0) * 100, 2)


def risk_level(prob_max, prob_second):
    """风险等级：基于最大概率与次大概率之差"""
    gap = prob_max - prob_second
    if gap > 0.25:
        return '低'
    elif gap > 0.12:
        return '中'
    else:
        return '高'


def confidence_index(final_probs, ah_handicap=None, ou_line=None):
    """信心指数 0~5★

    因子：
    - 方向集中度（最大概率权重）
    - 亚盘一致性（方向与盘口是否一致）
    - 大小球参考（高进球预期加分）
    """
    score = 0.0
    p_max = max(final_probs)
    # 基础分: 最大概率越高越好
    if p_max >= 0.55:
        score += 2.0
    elif p_max >= 0.45:
        score += 1.5
    elif p_max >= 0.38:
        score += 1.0
    else:
        score += 0.5

    # 方向集中度
    p_sorted = sorted(final_probs, reverse=True)
    gap = p_sorted[0] - p_sorted[1]
    if gap > 0.20:
        score += 1.5
    elif gap > 0.10:
        score += 1.0
    elif gap > 0.05:
        score += 0.5

    # 亚盘一致性
    if ah_handicap is not None:
        # 主胜方向 & 亚盘主让 → 一致
        if final_probs[0] > final_probs[2] and ah_handicap < 0:  # 主让
            score += 0.5
        elif final_probs[2] > final_probs[0] and ah_handicap > 0:  # 客让
            score += 0.5

    # 大小球参考
    if ou_line and ou_line >= 2.5:
        score += 0.5  # 高进球联赛

    return min(round(score, 1), 5.0)


def predict_match(match: dict) -> dict:
    """对单场比赛生成完整预测

    输入: leisu_swot.py 解析后的 match dict（含 avg_prob_w/d/l, avg_odds_w/d/l 等）
    输出: 补全了泊松/预测/EV/Kelly 等字段的 dict
    """
    r = dict(match)  # 不修改原数据

    # 1. 获取隐含概率（优先用百家平均概率，否则从赔率反推）
    imp_w = r.get('avg_prob_w')
    imp_d = r.get('avg_prob_d')
    imp_l = r.get('avg_prob_l')

    # 百家概率是百分比形式(0~100)，转为 0~1
    if imp_w and imp_w > 1:
        imp_w, imp_d, imp_l = imp_w / 100.0, imp_d / 100.0, imp_l / 100.0

    # 兜底：从赔率反推
    if imp_w is None or imp_w <= 0:
        imp_w, imp_d, imp_l = implied_from_odds(
            r.get('avg_odds_w'), r.get('avg_odds_d'), r.get('avg_odds_l'))

    if imp_w is None:
        # 没有任何概率数据，跳过
        r['prediction'] = 'SKIP'
        r['prediction_prob'] = 0
        r['risk_level'] = '无数据'
        r['confidence_index'] = 0
        return r

    # 2. 泊松预测
    lam_h, lam_a = estimate_lambdas(imp_w, imp_d, imp_l)
    poi_w, poi_d, poi_l = poisson_match_probs(lam_h, lam_a)

    # 3. 融合
    final_w = POISSON_WEIGHT * poi_w + IMPLIED_WEIGHT * imp_w
    final_d = POISSON_WEIGHT * poi_d + IMPLIED_WEIGHT * imp_d
    final_l = POISSON_WEIGHT * poi_l + IMPLIED_WEIGHT * imp_l

    # 4. 判定方向
    probs = {'W': final_w, 'D': final_d, 'L': final_l}
    direction = max(probs, key=probs.get)
    prob_max = probs[direction]

    # 5. 风险 & 信心
    sorted_probs = sorted(probs.values(), reverse=True)
    risk = risk_level(sorted_probs[0], sorted_probs[1])
    conf = confidence_index(
        [final_w, final_d, final_l],
        ah_handicap=r.get('ah_handicap'),
        ou_line=r.get('ou_line'))

    # 6. EV (期望值)
    odds_map = {'W': r.get('avg_odds_w', 0), 'D': r.get('avg_odds_d', 0), 'L': r.get('avg_odds_l', 0)}
    ev_w = final_w * (odds_map['W'] - 1) - (1 - final_w) if odds_map['W'] > 1 else 0
    ev_d = final_d * (odds_map['D'] - 1) - (1 - final_d) if odds_map['D'] > 1 else 0
    ev_l = final_l * (odds_map['L'] - 1) - (1 - final_l) if odds_map['L'] > 1 else 0

    # 7. Kelly
    bankroll = 1.0  # 单位化
    kelly_w = ((odds_map['W'] - 1) * final_w - (1 - final_w)) / (odds_map['W'] - 1) if odds_map['W'] > 1 else 0
    kelly_d = ((odds_map['D'] - 1) * final_d - (1 - final_d)) / (odds_map['D'] - 1) if odds_map['D'] > 1 else 0
    kelly_l = ((odds_map['L'] - 1) * final_l - (1 - final_l)) / (odds_map['L'] - 1) if odds_map['L'] > 1 else 0
    kelly_max = max(kelly_w, kelly_d, kelly_l, 0)

    # 8. 价值投注标记
    ev_max = max(ev_w, ev_d, ev_l)
    value_flag = 1 if ev_max > 0.05 else 0

    # 写入结果
    r.update({
        'home_lambda': lam_h,
        'away_lambda': lam_a,
        'poisson_w': round(poi_w, 4),
        'poisson_d': round(poi_d, 4),
        'poisson_l': round(poi_l, 4),
        'final_w': round(final_w, 4),
        'final_d': round(final_d, 4),
        'final_l': round(final_l, 4),
        'prediction': direction,
        'prediction_prob': round(prob_max, 4),
        'ev_w': round(ev_w, 4),
        'ev_d': round(ev_d, 4),
        'ev_l': round(ev_l, 4),
        'best_direction': direction,
        'kelly_stake': round(kelly_max, 4),
        'value_flag': value_flag,
        'risk_level': risk,
        'confidence_index': conf,
        'avg_margin': calc_margin(r.get('avg_odds_w'), r.get('avg_odds_d'), r.get('avg_odds_l')),
    })

    return r
