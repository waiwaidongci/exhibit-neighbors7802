"""对照模块求解器 oracle 测试：最小费用流 vs scipy.optimize.linprog。

口径：可行构成 = 运输多面体（行和=年龄占比、列和=方式占比、禁用组合为 0、x>=0），
目标 = Σ x·d；无配对组按评分允许差值 ±16 计入。上下界即两个 LP 的最优值。
本测试用 scipy 独立求解同一 LP 作为 oracle，验证自研最小费用流的最值与达到构成。
运行：python3 oracle_bounds.py（在仓库根或任意目录均可，不依赖被测目录的模块路径）
"""
import itertools
import random
import sys

sys.path.insert(0, '/workspace/backend')
from src.services.flow import min_cost_flow, feasibility_cut  # noqa: E402

import numpy as np  # noqa: E402
from scipy.optimize import linprog  # noqa: E402

TOL = 1e-6


def lp_oracle(p, q, allowed, costs, maximize=False):
    cells = sorted(allowed)
    idx = {c: k for k, c in enumerate(cells)}
    n_r, n_m = len(p), len(q)
    A_eq, b_eq = [], []
    for i in range(n_r):
        row = [0.0] * len(cells)
        for j in range(n_m):
            if (i, j) in idx:
                row[idx[(i, j)]] = 1.0
        A_eq.append(row)
        b_eq.append(p[i])
    for j in range(n_m):
        row = [0.0] * len(cells)
        for i in range(n_r):
            if (i, j) in idx:
                row[idx[(i, j)]] = 1.0
        A_eq.append(row)
        b_eq.append(q[j])
    c = [costs[cell] * (-1 if maximize else 1) for cell in cells]
    res = linprog(c, A_eq=np.array(A_eq), b_eq=np.array(b_eq),
                  bounds=[(0, None)] * len(cells), method='highs')
    assert res.status == 0, f'oracle LP failed: {res.message}'
    return -res.fun if maximize else res.fun


def random_instance(rng):
    n_r, n_m = rng.randint(2, 5), rng.randint(2, 4)
    p = [rng.random() + 0.05 for _ in range(n_r)]
    q = [rng.random() + 0.05 for _ in range(n_m)]
    sp, sq = sum(p), sum(q)
    p = [x / sp for x in p]
    q = [x / sq for x in q]
    all_cells = [(i, j) for i in range(n_r) for j in range(n_m)]
    forbidden = set(rng.sample(all_cells, rng.randint(0, len(all_cells) // 2)))
    allowed = set(all_cells) - forbidden
    costs = {}
    for cell in all_cells:
        if cell in allowed:
            costs[cell] = rng.choice([rng.uniform(-3, 3), -16.0, 16.0])  # 含无配对组的 ±16
    return p, q, forbidden, allowed, costs


def check_plan(p, q, forbidden, costs, plan, bound, sign):
    rows = [0.0] * len(p)
    cols = [0.0] * len(q)
    obj = 0.0
    for (i, j), x in plan.items():
        assert (i, j) not in forbidden, '达到构成使用了禁用组合'
        assert x > 0, '达到构成含非正份额'
        rows[i] += x
        cols[j] += x
        obj += x * costs[(i, j)]
    for a, b in itertools.chain(zip(rows, p), zip(cols, q)):
        assert abs(a - b) < 1e-6, f'达到构成不满足边际占比: {a} != {b}'
    assert abs(obj - bound) < 1e-5, f'达到构成目标值 {obj} 与界 {bound} 不符'


def main():
    rng = random.Random(20261120)
    checked = skipped = 0
    for t in range(400):
        p, q, forbidden, allowed, costs = random_instance(rng)
        feasible, rr, rc = feasibility_cut(p, q, allowed)
        if not feasible:
            # Hall 冲突证据：可达行集合的占比合计必须大于其可行列集合
            assert all((i, j) not in allowed for i in rr for j in range(len(q)) if j not in rc)
            assert sum(p[i] for i in rr) > sum(q[j] for j in rc) + 1e-9
            skipped += 1
            continue
        flow_lo, lo, plan_lo = min_cost_flow(p, q, costs)
        flow_hi, hi_neg, plan_hi = min_cost_flow(p, q, {k: -v for k, v in costs.items()})
        hi = -hi_neg
        assert abs(flow_lo - 1) < 1e-6 and abs(flow_hi - 1) < 1e-6
        oracle_lo = lp_oracle(p, q, allowed, costs, maximize=False)
        oracle_hi = lp_oracle(p, q, allowed, costs, maximize=True)
        assert abs(lo - oracle_lo) < TOL, f'#{t} 下界 {lo} != oracle {oracle_lo}'
        assert abs(hi - oracle_hi) < TOL, f'#{t} 上界 {hi} != oracle {oracle_hi}'
        assert lo <= hi + 1e-9
        check_plan(p, q, forbidden, costs, plan_lo, lo, -1)
        check_plan(p, q, forbidden, costs, plan_hi, hi, +1)
        checked += 1
    print(f'oracle ok: {checked} 个可行实例上下界与达到构成全部吻合, {skipped} 个不可行实例 Hall 证据成立')


if __name__ == '__main__':
    main()
