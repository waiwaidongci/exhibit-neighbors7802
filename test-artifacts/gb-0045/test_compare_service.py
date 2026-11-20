"""对照服务单元测试：配对留出、分组差值、手算上下界、结论判定、冲突报告、版本锁定。

运行：python3 test_compare_service.py
"""
import sys

sys.path.insert(0, '/workspace/backend')
from src.services.compare import pair_holdout, aggregate_cells, compute, create_comparison  # noqa: E402
from src.services.audience import validate_payload  # noqa: E402
from src.schemas.audience import AudienceInput  # noqa: E402

PASS = []


def check(name, cond, extra=''):
    assert cond, f'FAIL {name} {extra}'
    PASS.append(name)


def ev(visitor, exhibit, rating, prediction):
    return {'visitor': visitor, 'exhibit': exhibit, 'rating': rating,
            'prediction': prediction, 'method': '相似邻居', 'neighbor_count': 2}


def payload(ages, methods, forbidden=None, cells=None):
    return {'age_groups': [{'key': k, 'label': k, 'share': s} for k, s in ages],
            'visit_methods': [{'key': k, 'label': k, 'share': s} for k, s in methods],
            'forbidden': [{'age': a, 'method': m} for a, m in (forbidden or [])],
            'visitor_cells': cells or {}}


# ---------- 配对 ----------
a = [ev('V1', 'E01', 4.0, 3.5), ev('V1', 'E02', 2.0, 2.5), ev('V2', 'E01', 5.0, 4.0)]
b = [ev('V1', 'E01', 4.0, 3.0), ev('V2', 'E01', 5.0, 5.0), ev('V9', 'E09', 1.0, 2.0)]
pairs, only_a, only_b = pair_holdout(a, b)
check('配对按键匹配', len(pairs) == 2)
check('仅A记录计数', only_a == 1)
check('仅B记录计数', only_b == 1)
p1 = next(p for p in pairs if p['visitor'] == 'V1')
check('配对平方误差', abs(p1['sq_a'] - 0.25) < 1e-12 and abs(p1['sq_b'] - 1.0) < 1e-12)
check('配对键含实际星级', all(set(p) >= {'visitor', 'exhibit', 'rating'} for p in pairs))
# 同访客同展品但实际星级不同不配对
pairs2, oa2, ob2 = pair_holdout([ev('V1', 'E01', 4.0, 3.0)], [ev('V1', 'E01', 5.0, 3.0)])
check('实际星级不同不配对', len(pairs2) == 0 and oa2 == 1 and ob2 == 1)

# ---------- 分组聚合 ----------
cells_map = {'V1': {'age': 'young', 'method': 'solo'}, 'V2': {'age': 'old', 'method': 'solo'}}
stats, unmapped = aggregate_cells(pairs, cells_map)
check('分组差值', abs(stats[('young', 'solo')]['diff'] - (0.25 - 1.0)) < 1e-12)
check('未分组配对计数', unmapped == 0)
stats2, unmapped2 = aggregate_cells(pairs, {})
check('无映射全部未分组', unmapped2 == 2 and not stats2)

# ---------- 手算上下界（2x2 全配对） ----------
pl = payload([('a1', 0.5), ('a2', 0.5)], [('m1', 0.5), ('m2', 0.5)],
             cells={'V1': {'age': 'a1', 'method': 'm1'}, 'V2': {'age': 'a1', 'method': 'm2'},
                    'V3': {'age': 'a2', 'method': 'm1'}, 'V4': {'age': 'a2', 'method': 'm2'}})
# 单元差值：d11=1, d12=4, d21=2, d22=3 → 下界 0.5*1+0.5*3=2.0，上界 0.5*4+0.5*2=3.0
eval_a = [ev('V1', 'E1', 3.0, 4.0), ev('V2', 'E2', 3.0, 5.0), ev('V3', 'E3', 3.0, 4.4142135623730951), ev('V4', 'E4', 3.0, 4.7320508075688772)]
eval_b = [ev('V1', 'E1', 3.0, 3.0), ev('V2', 'E2', 3.0, 3.0), ev('V3', 'E3', 3.0, 3.0), ev('V4', 'E4', 3.0, 3.0)]
# sq_a: 1,4,2,3 ; sq_b: 0,0,0,0 → diff 同上
r = compute(pl, {'evaluation': eval_a}, {'evaluation': eval_b})
check('手算下界', abs(r['bounds']['lower'] - 2.0) < 1e-5, r['bounds'])
check('手算上界', abs(r['bounds']['upper'] - 3.0) < 1e-5, r['bounds'])
check('全正判定B更准', r['verdict'] == 'b_better')
lo_cells = {(c['age'], c['method']): c['share'] for c in r['achieving']['lower']}
check('下界构成', abs(lo_cells[('a1', 'm1')] - 0.5) < 1e-6 and abs(lo_cells[('a2', 'm2')] - 0.5) < 1e-6)
hi_cells = {(c['age'], c['method']): c['share'] for c in r['achieving']['upper']}
check('上界构成', abs(hi_cells[('a1', 'm2')] - 0.5) < 1e-6 and abs(hi_cells[('a2', 'm1')] - 0.5) < 1e-6)
check('配对数', r['pairs'] == 4)

# ---------- 无配对组按 ±16 计入 ----------
pl2 = payload([('a1', 0.5), ('a2', 0.5)], [('m1', 0.5), ('m2', 0.5)],
              cells={'V1': {'age': 'a1', 'method': 'm1'}})
# 仅 (a1,m1) 有配对且 diff=0；其余三组无配对 → 全部质量可压到无配对组：下界 -16，上界 +16
r2 = compute(pl2, {'evaluation': [ev('V1', 'E1', 3.0, 3.0)]}, {'evaluation': [ev('V1', 'E1', 3.0, 3.0)]})
check('无配对组下界-16', abs(r2['bounds']['lower'] + 16.0) < 1e-6, r2['bounds'])
check('无配对组上界+16', abs(r2['bounds']['upper'] - 16.0) < 1e-6, r2['bounds'])
check('区间含零不判胜负', r2['verdict'] == 'inconclusive')
unobs = [c for c in r2['cells'] if not c['observed'] and not c['forbidden']]
check('无配对组标注范围', all(c['diff_range'] == [-16.0, 16.0] for c in unobs))

# ---------- 全负判定A更准 ----------
eval_a2 = [ev(v, 'E', 3.0, 3.0) for v in ('V1', 'V2', 'V3', 'V4')]
eval_b2 = [ev('V1', 'E', 3.0, 4.0), ev('V2', 'E', 3.0, 5.0), ev('V3', 'E', 3.0, 4.0), ev('V4', 'E', 3.0, 5.0)]
r3 = compute(pl, {'evaluation': eval_a2}, {'evaluation': eval_b2})
check('全负判定A更准', r3['verdict'] == 'a_better' and r3['bounds']['upper'] < 0, r3['bounds'])

# ---------- 冲突：合计不为1 / 两侧不等 ----------
r4 = compute(payload([('a1', 0.4), ('a2', 0.4)], [('m1', 1.0)]), {'evaluation': []}, {'evaluation': []})
check('两侧不等报冲突', r4['verdict'] == 'infeasible' and any(c['type'] == 'sum_mismatch' for c in r4['conflicts']))
r5 = compute(payload([('a1', 0.4), ('a2', 0.4)], [('m1', 0.8)]), {'evaluation': []}, {'evaluation': []})
check('合计不为1报冲突', r5['verdict'] == 'infeasible' and any(c['type'] == 'not_normalized' for c in r5['conflicts']))

# ---------- 冲突：整行禁用 ----------
r6 = compute(payload([('a1', 0.5), ('a2', 0.5)], [('m1', 0.5), ('m2', 0.5)],
                     forbidden=[['a1', 'm1'], ['a1', 'm2']]), {'evaluation': []}, {'evaluation': []})
check('整行禁用报冲突', r6['verdict'] == 'infeasible' and any(c['type'] == 'isolated_age' for c in r6['conflicts']))

# ---------- 冲突：Hall 缺口 ----------
r7 = compute(payload([('a1', 0.7), ('a2', 0.3)], [('m1', 0.5), ('m2', 0.5)],
                     forbidden=[['a1', 'm1']]), {'evaluation': []}, {'evaluation': []})
hall = next((c for c in r7['conflicts'] if c['type'] == 'hall'), None)
check('Hall冲突定位', r7['verdict'] == 'infeasible' and hall and hall['ages'] == ['a1'] and hall['methods'] == ['m2'] and abs(hall['deficit'] - 0.2) < 1e-6, r7['conflicts'])

# ---------- 禁用组合不进入构成 ----------
pl8 = payload([('a1', 0.5), ('a2', 0.5)], [('m1', 0.5), ('m2', 0.5)], forbidden=[['a1', 'm1']],
              cells={'V2': {'age': 'a1', 'method': 'm2'}, 'V3': {'age': 'a2', 'method': 'm1'}, 'V4': {'age': 'a2', 'method': 'm2'}})
eval8 = [ev('V2', 'E', 3.0, 4.0), ev('V3', 'E', 3.0, 4.0), ev('V4', 'E', 3.0, 4.0)]
r8 = compute(pl8, {'evaluation': eval8}, {'evaluation': [ev('V2', 'E', 3.0, 3.0), ev('V3', 'E', 3.0, 3.0), ev('V4', 'E', 3.0, 3.0)]})
for side in ('lower', 'upper'):
    check('禁用组合份额为零', all(not (c['age'] == 'a1' and c['method'] == 'm1') for c in r8['achieving'][side]))
    total = sum(c['share'] for c in r8['achieving'][side])
    check('构成合计为1', abs(total - 1) < 1e-6, total)

# ---------- 版本输入校验 ----------
def input_of(**kw):
    base = {'name': '测试版本', 'age_groups': [{'key': 'a1', 'label': 'A1', 'share': 0.6}, {'key': 'a2', 'label': 'A2', 'share': 0.4}],
            'visit_methods': [{'key': 'm1', 'label': 'M1', 'share': 1.0}], 'forbidden': [], 'visitor_cells': {}}
    base.update(kw)
    return AudienceInput(**base)

ok = validate_payload(input_of())
check('版本校验通过', ok['age_groups'][0]['share'] == 0.6)
for name, mut in (
    ('负占比拒绝', {'age_groups': [{'key': 'a1', 'label': 'A1', 'share': -0.1}, {'key': 'a2', 'label': 'A2', 'share': 1.1}]}),
    ('重复key拒绝', {'age_groups': [{'key': 'a1', 'label': 'A1', 'share': 0.5}, {'key': 'a1', 'label': 'A1b', 'share': 0.5}]}),
    ('未知组合拒绝', {'forbidden': [{'age': 'zz', 'method': 'm1'}]}),
    ('未知访客分组拒绝', {'visitor_cells': {'V1': {'age': 'a1', 'method': 'zz'}}}),
    ('零合计拒绝', {'visit_methods': [{'key': 'm1', 'label': 'M1', 'share': 0.0}]}),
):
    try:
        validate_payload(input_of(**mut))
        check(name, False)
    except ValueError:
        check(name, True)

# ---------- 受理时锁定同版数据（SQLite 内存库） ----------
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.config.database import Base
from src.models import user as user_model, source as source_model, record as record_model, run as run_model, note as note_model, audit as audit_model, audience as audience_model, comparison as comparison_model  # noqa: F401
from src.models.run import Run
from src.models.audience import AudienceProfile
from src.schemas.compare import ComparisonInput
from src.utils.serialization import now

engine = create_engine('sqlite://')
Base.metadata.create_all(engine)
Sess = sessionmaker(bind=engine, expire_on_commit=False)
db = Sess()
db.add(Run(id=1, source_id=1, name='研究甲', state='completed', parameters={}, snapshot={'records': []},
           result={'evaluation': eval_a}, created_at=now()))
db.add(Run(id=2, source_id=1, name='研究乙', state='completed', parameters={}, snapshot={'records': []},
           result={'evaluation': eval_b}, created_at=now()))
db.add(AudienceProfile(id=1, name='v1基线', payload=pl, created_by='seed', created_at=now()))
db.commit()


class U:
    email = 'analyst@demo'


inp = ComparisonInput(run_a_id=1, run_b_id=2, name='对照一')
c1 = create_comparison(db, U(), inp)
check('锁定当前版本v1', c1['profile_version'] == 1 and c1['verdict'] == 'b_better')
# 并发更新：插入 v2（占比变化），已受理对照保持 v1 口径
pl_v2 = payload([('a1', 0.9), ('a2', 0.1)], [('m1', 0.5), ('m2', 0.5)],
                cells=pl['visitor_cells'])
db.add(AudienceProfile(id=2, name='v2修正', payload=pl_v2, created_by='admin', created_at=now()))
db.commit()
c2 = create_comparison(db, U(), ComparisonInput(run_a_id=1, run_b_id=2, name='对照二'))
check('新对照采用v2', c2['profile_version'] == 2)
check('旧对照保持v1快照', c1['profile_snapshot'] == pl and c1['profile_version'] == 1)
check('不同版本结论各自独立', c1['result']['bounds'] != c2['result']['bounds'] or c1['profile_snapshot'] != c2['profile_snapshot'])
from src.services.compare import get_comparison
again = get_comparison(db, c1['id'])
check('历史对照回读同版快照', again['profile_version'] == 1 and again['profile_snapshot'] == pl)
# 同一份研究对照拒绝
try:
    create_comparison(db, U(), ComparisonInput(run_a_id=1, run_b_id=1, name='自身对照'))
    check('同研究拒绝', False)
except Exception:
    check('同研究拒绝', True)
# 未完成研究拒绝
db.add(Run(id=3, source_id=1, name='研究丙', state='queued', parameters={}, snapshot={'records': []}, created_at=now()))
db.commit()
try:
    create_comparison(db, U(), ComparisonInput(run_a_id=1, run_b_id=3, name='未完成对照'))
    check('未完成拒绝', False)
except Exception:
    check('未完成拒绝', True)

print(f'全部通过：{len(PASS)} 项')
for name in PASS:
    print('  ✓', name)
