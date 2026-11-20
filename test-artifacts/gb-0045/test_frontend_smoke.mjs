// 前端对照页面渲染冒烟：node 环境下以 shim 的 fetch/location/localStorage 渲染 comparePage，
// 校验页面包含发起入口、采用数据版本、结论横幅、达到两端的构成、冲突明细等关键标记。
// 运行：node test_frontend_smoke.mjs
const store = {};
globalThis.location = { port: '18249', hash: '' };
globalThis.localStorage = { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v }, removeItem: k => { delete store[k] } };

const payload = {
  age_groups: [{ key: '18-25', label: '18–25 岁', share: 0.3 }, { key: '26+', label: '26 岁及以上', share: 0.7 }],
  visit_methods: [{ key: 'solo', label: '个人参观', share: 0.6 }, { key: 'group', label: '团体预约', share: 0.4 }],
  forbidden: [{ age: '18-25', method: 'group' }],
  visitor_cells: { V001: { age: '18-25', method: 'solo' } }
};
const audience = { current: { id: 3, name: 'v3 基线', payload, created_by: 'admin@demo', created_at: '2026-11-20T01:00:00+00:00' },
  versions: [{ id: 3, name: 'v3 基线', created_by: 'admin@demo', created_at: '2026-11-20T01:00:00+00:00' }, { id: 2, name: 'v2', created_by: 'seed', created_at: '2026-11-19T01:00:00+00:00' }] };
const baseResult = { pairs: 40, unpaired_a: 1, unpaired_b: 2, unmapped_pairs: 0, rating_span_sq: 16,
  cells: [{ age: '18-25', method: 'solo', forbidden: false, observed: true, pairs: 4, mse_a: 0.5, mse_b: 0.4, diff: 0.1 },
          { age: '18-25', method: 'group', forbidden: true, observed: false, diff_range: [-16, 16] }],
  conflicts: [], explanation: '差值=研究A均方误差−研究B均方误差……' };
const inconclusive = { id: 7, name: '对照一', run_a_id: 1, run_b_id: 2, profile_version: 3, profile_snapshot: payload,
  verdict: 'inconclusive', created_by: 'admin@demo', created_at: '2026-11-20T02:00:00+00:00',
  result: { ...baseResult, verdict: 'inconclusive', bounds: { lower: -1.2, upper: 0.8 },
            achieving: { lower: [{ age: '18-25', method: 'solo', share: 0.3 }], upper: [{ age: '26+', method: 'group', share: 0.4 }] } } };
const infeasible = { ...inconclusive, id: 8, verdict: 'infeasible',
  result: { ...baseResult, verdict: 'infeasible', bounds: null, achieving: null,
            conflicts: [{ type: 'sum_mismatch', message: '年龄段占比合计 1 与来访方式占比合计 0.9 不相等，无可行构成' }] } };
const comparisons = [{ id: 7, name: '对照一', run_a_id: 1, run_b_id: 2, profile_version: 3, verdict: 'inconclusive',
  created_by: 'admin@demo', created_at: '2026-11-20T02:00:00+00:00', bounds: { lower: -1.2, upper: 0.8 } }];

let detail = inconclusive;
globalThis.fetch = async url => {
  const u = String(url);
  const data = u.endsWith('/audience') ? audience : u.endsWith('/comparisons') ? comparisons : /\/comparisons\/\d+/.test(u) ? detail : {};
  return { ok: true, status: 200, json: async () => data };
};

const { research } = await import('/workspace/frontend/src/stores/research.js');
research.runs = [{ id: 1, name: '研究甲', state: 'completed' }, { id: 2, name: '研究乙', state: 'completed' }];
const { session } = await import('/workspace/frontend/src/stores/session.js');
session.user = { role: 'admin', email: 'admin@demo' };
session.token = 't';
const { comparePage } = await import('/workspace/frontend/src/pages/compare.js');

const html = await comparePage();
for (const marker of ['发起对照', '采用数据版本', '客群构成 v3', '区间含零 · 不判胜负', '达到下界的构成', '达到上界的构成',
  '禁用', '对照历史', '客群版本账册', '维护客群构成', '各组差值明细', '研究甲', '研究乙']) {
  if (marker && !html.includes(marker)) throw new Error('页面缺少标记: ' + marker);
}
detail = infeasible;
research.comparisonId = 8;
const html2 = await comparePage();
for (const marker of ['无可行构成 · 约束冲突', '冲突明细', 'sum_mismatch']) {
  if (!html2.includes(marker)) throw new Error('冲突页缺少标记: ' + marker);
}
console.log('frontend smoke ok: 正常结论页与冲突页关键标记齐全');
