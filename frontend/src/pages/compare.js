import {research} from '../stores/research.js';
import {session} from '../stores/session.js';
import {audienceApi,compareApi} from '../api/research.js';
import {runOptions} from '../components/common/business.js';
import {table} from '../components/common/table.js';
import {esc,fmt,formObject,localTime} from '../utils/format.js';
import {action,toast} from '../hooks/actions.js';
import {verdicts} from '../constants/enums.js';

function runName(id){const r=research.runs.find(x=>x.id===id);return r?r.name+' · #'+id:'研究 #'+id}
function versionName(audience,id){const v=(audience.versions||[]).find(x=>x.id===id);return v?v.name:'版本 v'+id}

function matrix(snapshot,shares){
  const map={};for(const s of shares||[])map[s.age+'|'+s.method]=s.share;
  const forbidden=new Set((snapshot.forbidden||[]).map(f=>f.age+'|'+f.method));
  return '<div class="table-wrap"><table class="matrix"><thead><tr><th>年龄段 ＼ 来访方式</th>'+snapshot.visit_methods.map(m=>'<th>'+esc(m.label)+'</th>').join('')+'</tr></thead><tbody>'+snapshot.age_groups.map(a=>'<tr><th>'+esc(a.label)+'</th>'+snapshot.visit_methods.map(m=>{const k=a.key+'|'+m.key;if(forbidden.has(k))return '<td class="forbidden">禁用</td>';const v=map[k];return '<td>'+(v===undefined?'0':fmt(v))+'</td>'}).join('')+'</tr>').join('')+'</tbody></table></div>';
}

function banner(d){
  const r=d.result;
  if(d.verdict==='infeasible')return '<div class="verdict infeasible"><h2>无可行构成 · 约束冲突</h2><p>当前客群版本的分组、占比与组合限制相互冲突，不存在任何可行构成，无法给出对照结论。请修正后保存新版本再发起对照。</p></div>';
  const interval='差值区间 ['+fmt(r.bounds.lower)+' , '+fmt(r.bounds.upper)+']（差值=研究A均方误差−研究B均方误差）';
  if(d.verdict==='inconclusive')return '<div class="verdict inconclusive"><h2>区间含零 · 不判胜负</h2><p>'+interval+'。所有可行构成下差值可正可负，两份研究的准确度无法区分。</p></div>';
  const winner=d.verdict==='a_better'?runName(d.run_a_id):runName(d.run_b_id);
  return '<div class="verdict decided"><h2>'+esc(winner)+' 更准</h2><p>'+interval+'。区间整体'+(d.verdict==='a_better'?'小于':'大于')+'零，结论在所有可行客群构成下一致成立。</p></div>';
}

function detailView(d,audience){
  const r=d.result;
  const conflicts=r.conflicts&&r.conflicts.length?'<h2>冲突明细</h2><ul class="conflicts">'+r.conflicts.map(c=>'<li><b>'+esc(c.type)+'</b>：'+esc(c.message)+'</li>').join('')+'</ul>':'';
  const bounds=r.bounds?'<dl class="metrics"><div><dt>差值下界</dt><dd>'+fmt(r.bounds.lower)+'</dd></div><div><dt>差值上界</dt><dd>'+fmt(r.bounds.upper)+'</dd></div><div><dt>配对留出记录</dt><dd>'+r.pairs+'</dd></div><div><dt>无配对组计入口径</dt><dd>±'+fmt(r.rating_span_sq)+'</dd></div></dl>':'';
  const achieving=r.achieving?'<div class="compare-grid"><section><h2>达到下界的构成</h2>'+matrix(d.profile_snapshot,r.achieving.lower)+'</section><section><h2>达到上界的构成</h2>'+matrix(d.profile_snapshot,r.achieving.upper)+'</section></div>':'';
  const cells=r.cells.map(c=>({...c,state:c.forbidden?'禁用组合':(c.observed?'有配对':'无配对'),pairs:c.pairs??'—',mse_a:c.observed?c.mse_a:'—',mse_b:c.observed?c.mse_b:'—',diff:c.observed?c.diff:('['+c.diff_range[0]+', '+c.diff_range[1]+']')}));
  return '<div class="run-title"><h2>'+esc(d.name)+'</h2><span class="status '+esc(d.verdict)+'">'+esc(verdicts[d.verdict]||d.verdict)+'</span><small>#'+d.id+' · '+esc(d.created_by)+' · '+esc(localTime(d.created_at))+'</small></div>'
    +'<p class="fine">研究A：'+esc(runName(d.run_a_id))+' · 研究B：'+esc(runName(d.run_b_id))+'<br>采用数据版本：客群构成 v'+d.profile_version+'「'+esc(versionName(audience,d.profile_version))+'」（受理时锁定，后续更新不影响本结论）</p>'
    +banner(d)+conflicts+bounds
    +'<p class="fine">配对 '+r.pairs+' 条 · 仅研究A '+r.unpaired_a+' 条 · 仅研究B '+r.unpaired_b+' 条 · 未归入任何组的配对 '+r.unmapped_pairs+' 条（不计入）。'+esc(r.explanation)+'</p>'
    +achieving
    +'<h2>各组差值明细 <small>按 年龄段×来访方式</small></h2>'
    +table(cells,[{key:'age',label:'年龄段'},{key:'method',label:'来访方式'},{key:'state',label:'状态'},{key:'pairs',label:'配对数'},{key:'mse_a',label:'研究A 均方误差'},{key:'mse_b',label:'研究B 均方误差'},{key:'diff',label:'差值 / 允许范围'}],{limit:60});
}

function audiencePanel(audience){
  const c=audience.current;
  if(!c)return '<div class="empty"><strong>还没有客群构成版本。</strong><p>先在下方维护分组、占比与组合限制，再发起对照。</p></div>';
  const p=c.payload;
  return '<h2>当前客群构成 <small>v'+c.id+' · '+esc(c.name)+'</small></h2>'
    +'<p class="fine">'+esc(c.created_by)+' · '+esc(localTime(c.created_at))+' · 年龄段 '+p.age_groups.length+' 组 · 来访方式 '+p.visit_methods.length+' 类 · 不可能组合 '+p.forbidden.length+' 种 · 访客分组 '+Object.keys(p.visitor_cells).length+' 人</p>'
    +'<p class="fine">占比：'+p.age_groups.map(g=>esc(g.label)+' '+fmt(g.share)).join('，')+'<br>'+p.visit_methods.map(g=>esc(g.label)+' '+fmt(g.share)).join('，')+(p.forbidden.length?'<br>不可能组合：'+p.forbidden.map(f=>esc(f.age)+' × '+esc(f.method)).join('，'):'')+'</p>';
}

export async function comparePage(){
  const [audience,comparisons]=await Promise.all([audienceApi.overview(),compareApi.list()]);
  if(!research.comparisonId&&comparisons.length)research.comparisonId=comparisons[0].id;
  let detail=null;
  if(research.comparisonId){try{detail=await compareApi.get(research.comparisonId)}catch(e){research.comparisonId=null}}
  const completed=research.runs.filter(r=>r.state==='completed');
  const launch=session.writable?(completed.length>=2&&audience.current
    ?'<h2>发起对照</h2><form id="compare-form"><label>研究A<select name="run_a_id">'+runOptions(research.runs,completed[0].id,true)+'</select></label><label>研究B<select name="run_b_id">'+runOptions(research.runs,completed[1].id,true)+'</select></label><label>对照名称<input name="name" required value="冬季试展准确度对照"></label><p class="fine">受理时锁定当前客群版本 v'+audience.current.id+'；客群数据并发更新不影响本次口径。</p><button type="submit">锁定版本并对照 →</button></form>'
    :'<h2>发起对照</h2><p>'+(audience.current?'至少需要两份已完成研究。':'请先维护客群构成版本。')+'</p>')
    :'<h2>发起对照</h2><p>阅读者可以查看对照结论；发起对照由分析师或负责人执行。</p>';
  const history=comparisons.length?'<h2>对照历史 <small>点击查看结论与采用版本</small></h2><div class="ledger">'+comparisons.map(c=>'<a href="#compare" data-comparison="'+c.id+'"><small>#'+c.id+'</small><strong>'+esc(c.name)+'</strong><span class="status '+esc(c.verdict)+'">'+esc(verdicts[c.verdict]||c.verdict)+'</span><time>客群 v'+c.profile_version+' · '+esc(localTime(c.created_at))+'</time></a>').join('')+'</div>':'';
  const versions=audience.versions.length?'<h2>客群版本账册</h2><div class="ledger">'+audience.versions.map(v=>'<a href="#compare"><small>v'+v.id+'</small><strong>'+esc(v.name)+(audience.current&&v.id===audience.current.id?'（当前）':'')+'</strong><span></span><time>'+esc(v.created_by)+' · '+esc(localTime(v.created_at))+'</time></a>').join('')+'</div>':'';
  const editor=session.writable?'<details><summary>维护客群构成（保存为新版本，不影响已受理对照）</summary><form id="audience-form"><label>版本名称<input name="name" required value="2026 冬季试展客群修正"></label><label>构成定义 JSON（分组 / 占比 / 不可能组合 / 访客分组映射）<textarea name="payload" rows="16" spellcheck="false">'+esc(audience.current?JSON.stringify(audience.current.payload,null,2):'{"age_groups":[],"visit_methods":[],"forbidden":[],"visitor_cells":{}}')+'</textarea></label><p class="fine">保存即生成新版本；占比合计不为 1、两侧合计不等或组合限制冲突时，对照结论会报告具体冲突。</p><button type="submit">保存为新版本 →</button></form></details>':'';
  return '<section class="page-heading"><p class="eyebrow">05 / STUDY COMPARISON</p><h1>两份研究，谁更经得起下一场客群。</h1><p>按访客、展品和实际星级配对两份已完成研究的留出记录，求所有可行客群构成下均方误差之差的最紧上下界；区间含零不判胜负。</p></section>'
    +'<div class="split"><section>'+(detail?detailView(detail,audience):'<div class="empty"><strong>还没有对照结论。</strong><p>选择两份已完成研究发起对照，结论会显示采用的客群数据版本。</p></div>')+'</section>'
    +'<aside class="entry-sheet">'+launch+'<hr>'+audiencePanel(audience)+'</aside></div>'
    +history+versions+editor;
}

export function bindCompare(refresh){
  action('#compare-form',async form=>{const data=formObject(form);if(data.run_a_id===data.run_b_id){toast('对照需要两份不同的研究',true);return}const c=await compareApi.create({run_a_id:Number(data.run_a_id),run_b_id:Number(data.run_b_id),name:data.name});research.comparisonId=c.id;await refresh();toast('对照完成：'+(verdicts[c.verdict]||c.verdict))});
  action('#audience-form',async form=>{const data=formObject(form);let payload;try{payload=JSON.parse(data.payload)}catch(e){toast('构成定义不是合法 JSON',true);return}try{const v=await audienceApi.create({name:data.name,...payload});await refresh();toast('已保存为客群版本 v'+v.id)}catch(e){toast(e.message,true)}});
  for(const a of document.querySelectorAll('[data-comparison]'))a.addEventListener('click',async()=>{research.comparisonId=Number(a.dataset.comparison);await refresh()});
}
