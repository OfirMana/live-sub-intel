"use strict";
function visibleTimeline(timeline,elapsed){return timeline.filter((t,i)=>i===0||t.elapsed<elapsed).at(-1);}
function scoreAt(fixture,elapsed){const s={[fixture.home.id]:0,[fixture.away.id]:0};for(const e of fixture.events)if(e.elapsed<elapsed&&['goal','own_goal'].includes(e.kind))s[e.team_id]++;return s;}
function matchStatsAt(fixture,elapsed){
 const teams=Object.fromEntries([fixture.home.id,fixture.away.id].map(id=>[id,{shots:0,onTarget:0,xg:0,passes:0,completed:0,accuracy:null,possessionProxy:null}])),players={},passes=new Map(),seen=new Set();
 const player=id=>players[id]||(players[id]={goals:0,assists:0,yellows:0,red:false});
 for(const e of fixture.stat_events||[]){
  if(e.elapsed>=elapsed||seen.has(e.id))continue;seen.add(e.id);
  const team=teams[e.team_id];if(!team)continue;
  if(e.kind==='pass'){team.passes++;if(e.success===true)team.completed++;passes.set(e.id,e);}
  if(['shot','goal'].includes(e.kind)){team.shots++;team.xg+=Number(e.xg)||0;if(e.on_target===true||e.kind==='goal')team.onTarget++;}
  if(e.kind==='goal'&&e.player_id){
   player(e.player_id).goals++;
   const pass=passes.get(e.key_pass_id);
   if(pass&&pass.success===true&&pass.team_id===e.team_id&&pass.player_id&&pass.player_id!==e.player_id&&pass.recipient_id===e.player_id)player(pass.player_id).assists++;
  }
  if(e.kind==='card'&&e.player_id){const p=player(e.player_id);if(e.card==='yellow'||e.card==='second_yellow')p.yellows++;if(e.card==='red'||e.card==='second_yellow')p.red=true;}
 }
 const total=Object.values(teams).reduce((sum,t)=>sum+t.passes,0);
 for(const t of Object.values(teams)){t.accuracy=t.passes?100*t.completed/t.passes:null;t.possessionProxy=total?100*t.passes/total:null;}
 return {teams,players};
}
function contextKey(view,minute,config){return JSON.stringify([view.match_id,view.team_id,minute,config]);}
function explanationKey(context,planId,audience,lang){return JSON.stringify([context,planId,audience,lang]);}
if(typeof module!=='undefined')module.exports={visibleTimeline,scoreAt,matchStatsAt,contextKey,explanationKey};
if(typeof document!=='undefined')initialize();

function initialize(){
 const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fmt=(v,n=3)=>v==null?'—':Number(v).toFixed(n);
 const q=new URLSearchParams(location.search);let lang=q.get('lang')==='he'?'he':'en';
 const t=(key,params)=>translate(lang,key,params),pos=p=>lang==='he'?(positionsHe[p]||p):p;
 let data,view,fixture,record,index=0,elapsed=0,stages=[],requestToken=0,animation=0,playing=false,pending=false,opened=false,chosen=null,explainToken=0,explainAbort=null;
 const config=()=>({stance:$('stance').value,objective:$('objective').value,formation:'auto',freshness_cap:Number($('freshness').value)});
 const minutes=()=>stages[index]?.minute;
 const planId=()=>chosen?.plan_id||record?.selected_plan_id||'wait';
 const currentContext=()=>view?contextKey(view,minutes(),config()):'';
 const currentExplanation=()=>explanationKey(currentContext(),planId(),$('audience').value,lang);
 const planName=p=>p?.out_player?t('planName',{off:p.out_player.name,on:p.in_player.name}):p?t('tacticalName',{shape:p.formation}):t('wait');
 function resetExplain(){explainToken++;explainAbort?.abort();explainAbort=null;$('explainText').textContent='';$('explainSource').textContent='';$('explainBtn').disabled=!record;$('explainPlan').textContent=t('inspected',{plan:planName(chosen)});}
 function applyLanguage(){
  document.documentElement.lang=lang;document.documentElement.dir=lang==='he'?'rtl':'ltr';document.title=lang==='he'?'Live Sub Intel — חדר המאמן':'Live Sub Intel — Coach Room';$('language').value=lang;
  document.querySelectorAll('[data-i18n]').forEach(e=>e.textContent=t(data?.data_mode==='synthetic'&&['research','caveat'].includes(e.dataset.i18n)?'synthetic_'+e.dataset.i18n:e.dataset.i18n));
  $('language').setAttribute('aria-label',t('language'));$('team').setAttribute('aria-label',t('perspective'));document.querySelector('.explain').setAttribute('aria-label',t('explanation'));
 }
 function badges(id,stats){
  const p=stats.players[id];if(!p)return '';
  const badge=(kind,label,text)=>`<span class="player-badge ${kind}" title="${esc(label)}" aria-label="${esc(label)}">${text}</span>`;
  return `<span class="player-badges">${p.yellows?badge('yellow-card',t('yellowCards',{n:p.yellows}),p.yellows>1?p.yellows:''):''}${p.red?badge('red-card',t('sentOff'),''):''}${p.goals?badge('goal-badge',t('goalCount',{n:p.goals}),'⚽'+(p.goals>1?p.goals:'')):''}${p.assists?badge('assist-badge',t('assistCount',{n:p.assists}),'A'+(p.assists>1?p.assists:'')):''}</span>`;
 }
 function renderStats(stats){
  const ids=[fixture.home.id,fixture.away.id];
  const rows=[['xgTotal','xg',2],['totalShots','shots',0],['shotsOnTarget','onTarget',0],['passAttempts','passes',0],['passAccuracy','accuracy',1],['possessionProxy','possessionProxy',1]];
  $('matchStats').innerHTML='<table><tr><th>'+esc(fixture.home.name)+'</th><th>'+t('statistic')+'</th><th>'+esc(fixture.away.name)+'</th></tr>'+rows.map(([label,key,n])=>'<tr>'+`<td class="num">${stats.teams[ids[0]][key]==null?'—':fmt(stats.teams[ids[0]][key],n)+(n===1?'%':'')}</td><th>${t(label)}</th><td class="num">${stats.teams[ids[1]][key]==null?'—':fmt(stats.teams[ids[1]][key],n)+(n===1?'%':'')}</td></tr>`).join('')+'</table>';
  const dismissed=Object.entries(stats.players).filter(([id,p])=>p.red&&data.profiles[id]?.team===view.team);
  $('dismissedPlayers').innerHTML=dismissed.length?`<strong>${t('sentOff')}</strong> `+dismissed.map(([id])=>`<span class="dismissed-player"><span class="dismissed-shirt" aria-hidden="true">👕</span>${esc(data.profiles[id]?.name||id)} ${badges(id,stats)}</span>`).join(' '):'';
 }
 function renderPitch(id,lineup,incoming=null,moved=[],outgoing=null){
  const stats=matchStatsAt(fixture,elapsed);
  $(id).innerHTML='<div class="field-lines"><span class="center-circle"></span><span class="box-top"></span><span class="box-bottom"></span></div>'+(lineup||[]).filter(p=>!stats.players[p.player_id]?.red).map(p=>`<div class="footballer ${p.role==='GK'?'gk':''} ${p.player_id===incoming?'incoming':''} ${moved.includes(p.player_id)?'moved':''}" style="left:${p.x}%;top:${p.y}%" title="${esc(p.name)} · ${esc(pos(p.position))}"><div class="jersey"><svg viewBox="0 0 60 56" aria-hidden="true"><path d="M18 3L8 7 1 21l11 7 5-6v31h26V22l5 6 11-7L52 7 42 3Q30 11 18 3Z" fill="${p.role==='GK'?'#ce8a32':p.player_id===outgoing?'#ffadb0':p.player_id===incoming?'#ffe27b':'#f6fafb'}" stroke="#d1dedf" stroke-width="1.5"/></svg><span class="shirt-number">${esc(p.number??'?')}</span>${badges(p.player_id,stats)}</div><span class="player-name">${esc(p.name)}</span><span class="position-label">${esc(pos(p.position))}</span></div>`).join('');
 }
 function renderGame(){
  renderStats(matchStatsAt(fixture,elapsed));
  const score=scoreAt(fixture,elapsed);$('score').textContent=`${score[fixture.home.id]} : ${score[fixture.away.id]}`;
  const half=elapsed>=45+fixture.first_half_extra,clock=elapsed-(half?fixture.first_half_extra:0),total=Math.floor(clock*60+1e-5),m=Math.floor(total/60),s=String(total%60).padStart(2,'0'),limit=half?90:45;
  $('clock').textContent=elapsed?`${m>=limit?limit+'+'+(m-limit):String(m).padStart(2,'0')}:${s}`:'00:00';$('rail').style.width=Math.min(elapsed/fixture.final_elapsed,1)*100+'%';
  const observed=visibleTimeline(view.lineup_timeline,elapsed);renderPitch('pitchCurrent',observed.lineup);$('observedFormation').textContent=observed.formation;$('initialFormation').textContent=t(data.data_mode==='synthetic'?'synthetic_initial':'initial',{shape:view.lineup_timeline[0].formation});
  if(record)renderPitch('pitchPlan',chosen?.proposed_lineup||record.observed.lineup,chosen?.in_player?.id,chosen?.repositioned.map(p=>p.player_id)||[]);
  $('events').innerHTML=fixture.events.filter(e=>e.elapsed<elapsed&&($('eventFilter').value==='all'||!['pressure','tackle','recovery'].includes(e.kind))).reverse().map(e=>`<li class="${e.kind}"><time>${e.minute}:${String(e.second).padStart(2,'0')}</time>${esc(t(e.kind))} ${esc(e.player||'')}${e.replacement?' → '+esc(e.replacement):''}${e.xg!=null?' · xG '+fmt(e.xg,2):''}</li>`).join('')||`<li class="muted">${t('emptyEvents')}</li>`;
 }
 function controls(){
  $('next').disabled=playing||pending||index===stages.length-1;$('back').disabled=playing||pending||!index;$('reset').disabled=pending;
  $('next').textContent=t(index===18?'extra':'next');$('finish').hidden=!playing;
  $('check').disabled=playing||pending||!record||!minutes();$('check').textContent=t(opened?'close':'inspect')+(minutes()?' · '+t('atMinute',{minute:minutes()}):'');
  $('sensitivity').disabled=playing||pending||minutes()==null;
  ['stance','objective','freshness','team'].forEach(id=>$(id).disabled=playing);
 }
 function updateShare(){if(view)$('share').href='/?'+new URLSearchParams({team:view.team_id,minute:minutes()??90,...config(),lang,inspect:opened?'1':'0'});}
 function showPlan(candidate){
  chosen=candidate;resetExplain();const plan=candidate?.proposed_lineup||record?.observed.lineup;
  $('planFormation').textContent=candidate?.formation||record?.observed.formation||'';
  $('planLabel').textContent=candidate?planName(candidate)+(candidate.out_player?' · '+t(candidate.recommended?'recommended':'rejected'):''):t('unchanged');
  renderPitch('pitchPlan',plan,candidate?.in_player?.id,candidate?.repositioned.map(p=>p.player_id)||[]);
  if(record)renderPitch('pitchCurrent',record.observed.lineup,null,[],candidate?.out_player?.id);
  $('moves').textContent=(candidate?t('legend')+' ':'')+(candidate?.repositioned.length?t('moves',{moves:candidate.repositioned.map(p=>`${p.name}: ${pos(p.before_position)} → ${pos(p.after_position)}`).join(' · ')}):'');
  $('fitTable').innerHTML=candidate?`<details><summary>${t('fitTitle')}</summary><p class="muted small">${t('fitHelp')}</p><table><tr><th>${t('player')}</th><th>${t('position')}</th><th>${t('fit')}</th></tr>`+plan.map(p=>`<tr><td>${esc(p.name)}</td><td>${esc(pos(p.position))}</td><td class="num">${fmt(p.fit??1,2)}</td></tr>`).join('')+'</table></details>':'';
 }
 function renderAnalysis(){
  $('analysis').hidden=!opened;if(!opened||!record)return;
  const s=record.selected;$('verdict').className=record.selected_plan?'yes':'';
  $('verdict').textContent=s?t('verdict',{off:s.out_player.name,on:s.in_player.name,shape:s.formation,benefit:fmt(s.expected_benefit,4),threshold:fmt(record.threshold,4)}):record.recommendation==='TACTICAL_ADJUSTMENT'?t('tacticalVerdict',{shape:record.selected_plan.formation}):t('wait')+' '+(messages.en[record.no_substitution_reason]?t(record.no_substitution_reason):'');
  $('tactical').hidden=!record.tactical_plan;$('tactical').textContent=record.tactical_plan?planName(record.tactical_plan):'';
  $('candidates').innerHTML=record.alternatives.map((c,i)=>`<button class="candidate ${chosen?.plan_id===c.plan_id?'chosen':''}" data-index="${i}" aria-pressed="${chosen?.plan_id===c.plan_id}"><strong>${esc(planName(c))}</strong><span class="${c.recommended?'positive':'negative'}">${t(c.recommended?'passes':!c.quality_gate_passed?'qualityFail':'below')} · ${fmt(c.expected_benefit,4)} / ${fmt(record.threshold,4)}</span> · ${c.formation} · ${t(c.change_type==='FORMATION_CHANGE'?'shapeChange':c.change_type==='REPOSITIONING'?'reposition':'same')} · ${t('moveCount',{count:c.repositioned.length})} · ${t(c.decision_basis==='FRESH_LEGS'?'fresh':'tactics')}</button>`).join('')||`<p class="muted">${t('noOptions')}</p>`;
  if(chosen?.out_player){
   const c=chosen,x=c.score_components,out=data.profiles[c.out_player.id],inc=data.profiles[c.in_player.id];
   $('comparison').innerHTML=`<h3>${t('profiles')}</h3><table><tr><th></th><th>${t('off')}</th><th>${t('on')}</th></tr>`+[[t('name'),out.name,inc.name],[t('goalsAssists'),out.season.totals.goals+' / '+out.season.totals.assists,inc.season.totals.goals+' / '+inc.season.totals.assists],[t('stamina'),fmt(out.physical.stamina,0),fmt(inc.physical.stamina,0)],[t('seasonMinutes'),fmt(out.general.minutes,0),fmt(inc.general.minutes,0)]].map(([l,a,b])=>`<tr><td>${l}</td><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')+`</table><h3>${t('components')}</h3><table>`+[['tacticalBenefit',x.tactical_benefit],['freshBenefit',x.freshness_benefit],['fit',c.position_fit],['outgoingFatigue',x.outgoing_fatigue],['moveCost',-x.tactical_support],['reference',c.reference_benefit],['allowedLoss',c.allowed_tactical_loss]].map(([label,v])=>`<tr><td>${t(label)}</td><td class="num">${fmt(v,4)}</td></tr>`).join('')+`</table><h3>${t('dimensions')}</h3><table><tr><th>${t('dimension')}</th><th>${t('offNow')}</th><th>${t('incomingRating')}</th><th>${t('cardDelta')}</th><th>${t('delta')}</th></tr>`+Object.keys(record.team_needs).map(d=>`<tr><td>${t(d)}</td><td class="num">${fmt(inc.recent.ratings[d]-c.expected_changes[d],1)}</td><td class="num">${fmt(inc.recent.ratings[d],1)}</td><td class="num">${fmt(c.expected_changes[d],2)}</td><td class="num">${fmt(c.lineup_changes[d],2)}</td></tr>`).join('')+`</table><p class="muted small">${t('deltaHelp')}</p>`;
  }else $('comparison').textContent=chosen?t('noSwap'):'';
  $('raw').textContent=JSON.stringify({...record,alternatives:chosen?[chosen]:[],player_live:undefined},null,2);
 }
 function renderRecord(){
  if(!record)return;
  $('needs').innerHTML=Object.entries(record.team_needs).map(([d,v])=>`<span class="need">${t(d)} ${fmt(v,2)}</span>`).join('');
  $('weights').innerHTML=`<table><tr><th>${t('dimension')}</th><th>${t('metricWeight')}</th><th>${t('deficit')}</th></tr>`+Object.keys(record.team_needs).map(d=>`<tr><td>${t(d)}</td><td class="num">${fmt(record.importance[d],3)}</td><td class="num">${fmt(record.performance_deficit_z[d],3)}</td></tr>`).join('')+'</table>';
  $('shiftInfo').textContent=record.observed.shifts.length?t('observedShift',{shifts:record.observed.shifts.map(s=>`${s.minute}:${String(s.second).padStart(2,'0')} → ${s.formation}`).join(' · ')}):t('noShift');
  $('searchStats').textContent=t('search',{pairs:record.search.pairs_considered,trials:record.search.formation_trials,feasible:record.search.feasible_plans,ms:record.search.elapsed_ms});$('policy').textContent=t('policy',{cap:config().freshness_cap});
  renderAnalysis();updateShare();
 }
 async function analyze(){
  resetExplain();if(minutes()==null){record=null;showPlan(null);$('status').textContent=t('fullTime');controls();return;}
  const token=++requestToken,cfg=config(),key=currentContext();pending=true;record=null;chosen=null;$('analysis').hidden=true;renderPitch('pitchPlan',[]);$('planLabel').textContent=t('loading');$('needs').replaceChildren();controls();$('status').textContent=t('loading');
  try{const response=await fetch('/api/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({match_id:view.match_id,team_id:view.team_id,minute:minutes(),config:cfg})});if(!response.ok)throw Error();const r=await response.json();if(token!==requestToken||key!==currentContext())return;record=r;
   const candidate=r.alternatives.find(p=>p.plan_id===r.selected_plan_id)||(r.selected_plan_id==='tactical'?r.tactical_plan:null);
   showPlan(opened?candidate:null);renderRecord();$('status').textContent=t('ready',{minute:minutes()});
  }catch(error){if(token===requestToken){record=null;$('status').textContent=t('failed');}}
  finally{if(token===requestToken){pending=false;controls();}}
 }
 function goto(i){cancelAnimationFrame(animation);playing=false;index=i;elapsed=stages[index].elapsed;opened=false;$('analysis').hidden=true;$('sensitivityResult').innerHTML='';resetExplain();renderGame();analyze();}
 function finish(){goto(Math.min(index+1,stages.length-1));}
 function next(){if(playing||pending||index>=stages.length-1)return;resetExplain();const duration=Number($('speed').value);if(!duration){finish();return;}playing=true;opened=false;$('analysis').hidden=true;controls();const from=elapsed,to=stages[index+1].elapsed,start=performance.now();function frame(now){const f=Math.min(1,(now-start)/duration);elapsed=from+(to-from)*f;renderGame();if(f<1)animation=requestAnimationFrame(frame);else finish();}animation=requestAnimationFrame(frame);}
 function chooseTeam(start=0){requestToken++;pending=false;view=data.views.find(v=>v.team_id===$('team').value);fixture=data.fixtures[view.match_id];stages=[{minute:0,elapsed:0},...Array.from({length:18},(_,i)=>{const m=(i+1)*5;return{minute:m,elapsed:m+(m>45?fixture.first_half_extra:0)}}),{minute:null,elapsed:fixture.final_elapsed}];$('home').textContent=fixture.home.name;$('away').textContent=fixture.away.name;goto(start/5);}
 $('eventFilter').onchange=renderGame;
 $('next').onclick=next;$('finish').onclick=finish;$('back').onclick=()=>goto(Math.max(0,index-1));$('reset').onclick=()=>goto(0);$('team').onchange=()=>chooseTeam();
 ['stance','objective','freshness'].forEach(id=>$(id).onchange=()=>{$('sensitivityResult').innerHTML='';analyze();});
 $('check').onclick=()=>{opened=!opened;const candidate=record.alternatives.find(p=>p.plan_id===record.selected_plan_id)||(record.selected_plan_id==='tactical'?record.tactical_plan:null);showPlan(opened?candidate:null);renderAnalysis();controls();updateShare();};
 $('candidates').onclick=e=>{const b=e.target.closest('[data-index]');if(b){showPlan(record.alternatives[Number(b.dataset.index)]);renderAnalysis();}};
 $('tactical').onclick=()=>{showPlan(record.tactical_plan);renderAnalysis();};
 $('audience').onchange=resetExplain;
 $('language').onchange=()=>{lang=$('language').value;applyLanguage();resetExplain();if(view){renderGame();showPlan(chosen);renderRecord();$('status').textContent=record?t('ready',{minute:minutes()}):t('loading');controls();$('sensitivityResult').innerHTML='';}};
 $('explainBtn').onclick=async()=>{
  const key=currentExplanation(),token=++explainToken,id=planId();explainAbort?.abort();explainAbort=new AbortController();$('explainBtn').disabled=true;$('explainText').textContent=t('explaining');$('explainSource').textContent='';
  try{const response=await fetch('/api/explain',{method:'POST',signal:explainAbort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({match_id:view.match_id,team_id:view.team_id,minute:minutes(),config:config(),plan_id:id,audience:$('audience').value,lang})});if(!response.ok)throw Error();const result=await response.json();if(token!==explainToken||key!==currentExplanation()||result.plan_id!==id)return;
   $('explainText').textContent=result.text;$('explainSource').textContent=result.source==='llm'?t('modelSource',{model:result.model||'Foundry'}):t('templateSource',{reason:t(result.note||'LLM_NOT_CONFIGURED')});if(result.diagnostic)$('explainSource').textContent+=' · '+t('diagnosticRef',result.diagnostic);
  }catch(error){if(token===explainToken&&error.name!=='AbortError')$('explainText').textContent=t('explainFailed');}
  finally{if(token===explainToken)$('explainBtn').disabled=false;}
 };
 $('sensitivity').onclick=async()=>{const key=currentContext();$('sensitivity').disabled=true;$('sensitivityResult').textContent=t('capLoading');try{const rows=[];for(const cap of [0,.5,1,1.5]){const response=await fetch('/api/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({match_id:view.match_id,team_id:view.team_id,minute:minutes(),config:{...config(),freshness_cap:cap}})});if(!response.ok)throw Error();rows.push([cap,await response.json()]);}if(key!==currentContext())return;$('sensitivityResult').innerHTML=`<table><tr><th>${t('cap')}</th><th>${t('plan')}</th><th>${t('benefit')}</th><th>${t('alternatives')}</th></tr>`+rows.map(([cap,r])=>`<tr><td>${cap}</td><td>${esc(r.selected?planName(r.selected):r.recommendation==='TACTICAL_ADJUSTMENT'?planName(r.selected_plan):t('noChange'))}</td><td class="num">${fmt(r.alternatives[0]?.expected_benefit,4)}</td><td>${r.alternatives.filter(c=>c.recommended).length}</td></tr>`).join('')+`</table><p class="small muted">${t('sensitivityHelp')}</p>`;}catch(error){$('sensitivityResult').textContent=t('failed');}finally{controls();}};
 applyLanguage();
 fetch('/api/bootstrap').then(r=>{if(!r.ok)throw Error();return r.json()}).then(d=>{data=d;applyLanguage();d.views.forEach(v=>$('team').add(new Option(v.team+' · '+d.fixtures[v.match_id].home.name+' / '+d.fixtures[v.match_id].away.name,v.team_id)));$('team').value=d.views.some(v=>v.team_id===q.get('team'))?q.get('team'):d.views[0].team_id;for(const id of ['stance','objective','freshness']){const value=q.get(id==='freshness'?'freshness_cap':id);if([...$(id).options].some(o=>o.value===value))$(id).value=value;}const m=Number(q.get('minute')||0);chooseTeam(Number.isInteger(m)&&m>=0&&m<=90&&m%5===0?m:0);if(q.get('inspect')==='1')opened=true;}).catch(()=>$('status').textContent=t('failed'));
}
