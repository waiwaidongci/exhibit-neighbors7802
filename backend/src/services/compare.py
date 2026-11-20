from fastapi import HTTPException
from sqlalchemy import select
from ..models.comparison import Comparison
from ..models.audience import AudienceProfile
from ..utils.serialization import row, now
from .runs import get_run
from .audit import log
from .flow import min_cost_flow, feasibility_cut, EPS

# 显式评分 1–5，预测被截断到同一区间，单条平方误差 ∈ [0, 16]
RATING_MIN, RATING_MAX = 1.0, 5.0
SPAN_SQ = (RATING_MAX - RATING_MIN) ** 2
TOL = 1e-9


def _key(e):
    return (e['visitor'], e['exhibit'], round(float(e['rating']), 6))


def pair_holdout(eval_a, eval_b):
    """按访客、展品和实际星级配对两份研究的留出记录。

    仅两侧都出现的键计入配对；单侧多余记录只统计不进入差值。
    """
    index_b = {}
    for e in eval_b:
        index_b.setdefault(_key(e), e)
    pairs, matched, only_a = [], set(), 0
    for e in eval_a:
        k = _key(e)
        other = index_b.get(k)
        if other is None:
            only_a += 1
            continue
        matched.add(k)
        actual = k[2]
        pairs.append({'visitor': e['visitor'], 'exhibit': e['exhibit'], 'rating': actual,
                      'sq_a': (float(e['prediction']) - actual) ** 2,
                      'sq_b': (float(other['prediction']) - actual) ** 2})
    return pairs, only_a, len(eval_b) - len(matched)


def aggregate_cells(pairs, visitor_cells):
    """按（年龄段, 来访方式）单元汇总配对记录的均方误差之差（A−B）。"""
    buckets = {}
    unmapped = 0
    for p in pairs:
        cell = visitor_cells.get(p['visitor'])
        if not cell:
            unmapped += 1
            continue
        buckets.setdefault((cell['age'], cell['method']), []).append(p)
    stats = {}
    for (age, method), ps in buckets.items():
        n = len(ps)
        mse_a = sum(x['sq_a'] for x in ps) / n
        mse_b = sum(x['sq_b'] for x in ps) / n
        stats[(age, method)] = {'pairs': n, 'mse_a': mse_a, 'mse_b': mse_b,
                                'diff': mse_a - mse_b}
    return stats, unmapped


def _conflicts_and_plans(ages, methods, forbidden, stats):
    """求所有可行构成下差值 D=Σ x·d 的最紧上下界与达到两端的构成。

    可行构成：x≥0，行和=年龄占比，列和=方式占比，禁用组合 x=0。
    无配对单元的单元 d 未知，按评分允许的差值范围 ±SPAN_SQ 计入：
    下界取 −SPAN_SQ、上界取 +SPAN_SQ，仍为线性规划，由最小费用流精确求解。
    """
    p = [g['share'] for g in ages]
    q = [g['share'] for g in methods]
    forbidden_keys = {(f['age'], f['method']) for f in forbidden}
    conflicts = []
    sum_p, sum_q = sum(p), sum(q)
    if abs(sum_p - 1) > 1e-6 or abs(sum_q - 1) > 1e-6:
        conflicts.append({'type': 'not_normalized',
                          'message': '年龄段占比合计 %.6g、来访方式占比合计 %.6g，可行构成要求两者都等于 1' % (sum_p, sum_q)})
    if abs(sum_p - sum_q) > 1e-6:
        conflicts.append({'type': 'sum_mismatch',
                          'message': '年龄段占比合计 %.6g 与来访方式占比合计 %.6g 不相等，无可行构成' % (sum_p, sum_q)})
    forbidden_idx = {(ai, mi) for ai, a in enumerate(ages) for mi, m in enumerate(methods)
                     if (a['key'], m['key']) in forbidden_keys}
    allowed = {(i, j) for i in range(len(ages)) for j in range(len(methods))} - forbidden_idx
    for i, a in enumerate(ages):
        if p[i] > EPS and not any((i, j) in allowed for j in range(len(methods))):
            conflicts.append({'type': 'isolated_age', 'age': a['key'],
                              'message': '年龄段「%s」占比 %.6g，但其全部组合都被列为不可能' % (a['label'], p[i])})
    for j, m in enumerate(methods):
        if q[j] > EPS and not any((i, j) in allowed for i in range(len(ages))):
            conflicts.append({'type': 'isolated_method', 'method': m['key'],
                              'message': '来访方式「%s」占比 %.6g，但其全部组合都被列为不可能' % (m['label'], q[j])})
    if conflicts:
        return None, None, conflicts
    feasible, reach_rows, reach_cols = feasibility_cut(p, q, allowed)
    if not feasible:
        need = sum(p[i] for i in reach_rows)
        have = sum(q[j] for j in reach_cols)
        conflicts.append({'type': 'hall',
                          'ages': [ages[i]['key'] for i in sorted(reach_rows)],
                          'methods': [methods[j]['key'] for j in sorted(reach_cols)],
                          'deficit': need - have,
                          'message': '年龄段 %s 合计占比 %.6g，其可行来访方式只有 %s（合计 %.6g），缺口 %.6g' % (
                              '、'.join(ages[i]['label'] for i in sorted(reach_rows)), need,
                              '、'.join(methods[j]['label'] for j in sorted(reach_cols)), have, need - have)})
        return None, None, conflicts

    def costs(sign_unobserved):
        out = {}
        for (i, j) in allowed:
            s = stats.get((ages[i]['key'], methods[j]['key']))
            out[(i, j)] = s['diff'] if s else sign_unobserved * SPAN_SQ
        return out

    _, lo, plan_lo = min_cost_flow(p, q, costs(-1.0))
    _, hi_neg, plan_hi = min_cost_flow(p, q, {k: -v for k, v in costs(1.0).items()})

    def shares(plan):
        return [{'age': ages[i]['key'], 'method': methods[j]['key'], 'share': round(x, 6)}
                for (i, j), x in sorted(plan.items())]
    return (round(lo, 6), shares(plan_lo)), (round(-hi_neg, 6), shares(plan_hi)), []


def compute(payload, result_a, result_b):
    """完整对照口径：配对 -> 分组差值 -> 可行构成上的最紧上下界 -> 结论。"""
    ages, methods = payload['age_groups'], payload['visit_methods']
    pairs, only_a, only_b = pair_holdout(result_a.get('evaluation') or [],
                                         result_b.get('evaluation') or [])
    stats, unmapped = aggregate_cells(pairs, payload['visitor_cells'])
    (lo_plan, hi_plan, conflicts) = _conflicts_and_plans(ages, methods, payload['forbidden'], stats)
    cells = []
    forbidden = {(f['age'], f['method']) for f in payload['forbidden']}
    for a in ages:
        for m in methods:
            key = (a['key'], m['key'])
            s = stats.get(key)
            cell = {'age': a['key'], 'method': m['key'], 'forbidden': key in forbidden,
                    'observed': bool(s)}
            if s:
                cell.update({'pairs': s['pairs'], 'mse_a': round(s['mse_a'], 6),
                             'mse_b': round(s['mse_b'], 6), 'diff': round(s['diff'], 6)})
            else:
                cell['diff_range'] = [-SPAN_SQ, SPAN_SQ]
            cells.append(cell)
    result = {'pairs': len(pairs), 'unpaired_a': only_a, 'unpaired_b': only_b,
              'unmapped_pairs': unmapped, 'rating_span_sq': SPAN_SQ,
              'cells': cells, 'conflicts': conflicts,
              'bounds': None, 'achieving': None,
              'explanation': ('差值=研究A均方误差−研究B均方误差；按访客、展品和实际星级配对两份研究的留出记录，'
                              '按（年龄段×来访方式）汇总各组差值；可行构成满足两侧边际占比与不可能组合限制，'
                              '上下界为该运输多面体上最小费用流的精确最优值；无配对组按评分允许差值 ±%g 计入；'
                              '区间含零不判胜负。') % SPAN_SQ}
    if conflicts:
        result['verdict'] = 'infeasible'
        return result
    (lo, plan_lo), (hi, plan_hi) = lo_plan, hi_plan
    result['bounds'] = {'lower': lo, 'upper': hi}
    result['achieving'] = {'lower': plan_lo, 'upper': plan_hi}
    if lo > TOL:
        result['verdict'] = 'b_better'
    elif hi < -TOL:
        result['verdict'] = 'a_better'
    else:
        result['verdict'] = 'inconclusive'
    return result


def create_comparison(db, user, data):
    run_a, run_b = get_run(db, data.run_a_id), get_run(db, data.run_b_id)
    if run_a.id == run_b.id:
        raise HTTPException(422, '对照需要两份不同的研究')
    for r in (run_a, run_b):
        if r.state != 'completed':
            raise HTTPException(409, '研究 #%s 尚未完成，不能纳入对照' % r.id)
    # 受理时锁定：本事务内读取当前客群版本，随后并发更新产生新版本也不影响本次口径
    profile = db.scalar(select(AudienceProfile).order_by(AudienceProfile.id.desc()).limit(1))
    if not profile:
        raise HTTPException(422, '请先维护客群构成版本，再发起对照')
    payload = profile.payload
    result = compute(payload, run_a.result, run_b.result)
    c = Comparison(name=data.name, run_a_id=run_a.id, run_b_id=run_b.id,
                   profile_version=profile.id, profile_snapshot=payload,
                   result=result, verdict=result['verdict'],
                   created_by=user.email, created_at=now())
    db.add(c)
    db.flush()
    log(db, user, 'comparison.created', c.id,
        data.name + ' · 客群版本v' + str(profile.id) + ' · ' + result['verdict'])
    db.commit()
    return row(c)


def list_comparisons(db):
    out = []
    for c in db.scalars(select(Comparison).order_by(Comparison.id.desc())):
        d = {k: v for k, v in row(c).items() if k not in ('profile_snapshot', 'result')}
        d['bounds'] = (c.result or {}).get('bounds')
        out.append(d)
    return out


def get_comparison(db, id):
    c = db.get(Comparison, id)
    if not c:
        raise HTTPException(404, '未找到对照结论')
    return row(c)
