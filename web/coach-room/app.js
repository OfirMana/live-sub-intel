'use strict';
const dimLabels={threat:'איום לשער',creation:'יצירת מצבים',progression:'התקדמות',retention:'שמירת כדור',defense:'הגנה'};
const roleLabels={GK:'שוער',CB:'בלם',FB:'מגן',CM:'קשר',AM_W:'כנף / התקפי',ST:'חלוץ'};
const teamLabels={'24':'ליברפול','1':'ארסנל','33':'צ׳לסי','38':'טוטנהאם'};
function visibleTimeline(timeline,elapsed){return timeline.filter((t,i)=>i===0||t.elapsed<elapsed).at(-1);}
function scoreAt(fixture,elapsed){const s={[fixture.home.id]:0,[fixture.away.id]:0};for(const e of fixture.events)if(e.elapsed<elapsed&&['goal','own_goal'].includes(e.kind))s[e.team_id]++;return s;}
function contextKey(view,minute,config){return JSON.stringify([view.match_id,view.team_id,minute,config]);}
if(typeof module!=='undefined')module.exports={visibleTimeline,scoreAt,contextKey};
if(typeof document!=='undefined')initialize();

function initialize(){
 const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fmt=(v,n=3)=>v==null?'—':Number(v).toFixed(n);
 let data,view,fixture,record,index=0,elapsed=0,stages=[],requestToken=0,animation=0,playing=false,pending=false,opened=false,chosen=null;
 const config=()=>({stance:$('stance').value,objective:$('objective').value,formation:$('formation').value,freshness_cap:Number($('freshness').value)});
 const minutes=()=>stages[index]?.minute;
 function renderPitch(id,lineup,incoming=null,moved=[]){
  const markup='<div class="field-lines"><span class="center-circle"></span><span class="box-top"></span><span class="box-bottom"></span></div>';
  $(id).innerHTML=markup+(lineup||[]).map(p=>`<div class="footballer ${p.role==='GK'?'gk':''} ${p.player_id===incoming?'incoming':''} ${moved.includes(p.player_id)?'moved':''}" style="left:${p.x}%;top:${p.y}%" title="${esc(p.name)} · ${esc(p.position)}"><div class="jersey"><svg viewBox="0 0 60 56" aria-hidden="true"><path d="M18 3L8 7 1 21l11 7 5-6v31h26V22l5 6 11-7L52 7 42 3Q30 11 18 3Z" fill="${p.role==='GK'?'#ce8a32':p.player_id===incoming?'#ffe27b':'#f6fafb'}" stroke="#d1dedf" stroke-width="1.5"/></svg><span class="shirt-number">${esc(p.number??'?')}</span></div><span class="player-name">${esc(p.name)}</span><span class="position-label">${roleLabels[p.role]}</span></div>`).join('');
 }
 function renderGame(){
  const score=scoreAt(fixture,elapsed);$('score').textContent=`${score[fixture.home.id]} : ${score[fixture.away.id]}`;
  const secondHalf=elapsed>=45+fixture.first_half_extra,clock=elapsed-(secondHalf?fixture.first_half_extra:0),total=Math.floor(clock*60+1e-5),m=Math.floor(total/60),s=String(total%60).padStart(2,'0');
  const limit=secondHalf?90:45;$('clock').textContent=elapsed?`${m>=limit?limit+'+'+(m-limit):String(m).padStart(2,'0')}:${s}`:'00:00';
  $('rail').style.width=Math.min(elapsed/fixture.final_elapsed,1)*100+'%';
  const observed=visibleTimeline(view.lineup_timeline,elapsed);renderPitch('pitchCurrent',observed.lineup);
  $('observedFormation').textContent=observed.formation;$('initialFormation').textContent=`מערך פתיחה: ${view.lineup_timeline[0].formation} · מיקומים סכמטיים לפי עמדות StatsBomb`;
  $('events').innerHTML=fixture.events.filter(e=>e.elapsed<elapsed).reverse().map(e=>`<li class="${e.kind}"><time>${e.minute}:${String(e.second).padStart(2,'0')}</time>${esc(e.kind==='goal'?'שער!':e.kind==='own_goal'?'שער עצמי':e.kind==='substitution'?'חילוף היסטורי':e.kind==='card'?'כרטיס':e.kind==='shot'?'בעיטה':e.kind==='period_start'?'תחילת מחצית':'סיום מחצית')} ${esc(e.player||'')}${e.replacement?' → '+esc(e.replacement):''}${e.xg!=null?' · xG '+fmt(e.xg,2):''}</li>`).join('')||'<li class="muted">שריקת הפתיחה עוד לפנינו.</li>';
 }
 function controls(){
  $('next').disabled=playing||pending||index===stages.length-1;$('back').disabled=playing||pending||!index;$('reset').disabled=pending;
  $('next').textContent=index===18?'המשך לתוספת הזמן ולסיום ←':'התקדם 5 דקות ←';$('finish').hidden=!playing;
  $('check').disabled=playing||pending||!record||!minutes();$('check').textContent=opened?'סגור בדיקת חילופים':`בדוק חילופים${minutes()?' בדקה '+minutes():''}`;
  $('sensitivity').disabled=playing||pending||minutes()==null;
  ['stance','objective','formation','freshness','team'].forEach(id=>$(id).disabled=playing);
 }
 function showPlan(candidate){
  chosen=candidate;
  const plan=candidate?.proposed_lineup||record?.formation_only.lineup;
  $('planFormation').textContent=candidate?.formation||record?.formation_only.formation||'';
  $('planLabel').textContent=candidate?`${candidate.recommended?'חלופה שעוברת את תנאי ההמלצה':'תצוגת חלופה — אינה המלצה'}: ${candidate.out_player.name} → ${candidate.in_player.name}`:plan?'המערך המבוקש ללא חילוף — בסיס להשוואת החילופים.':'לא ניתן להציב את ההרכב הזה במערך המבוקש בתפקידים נתמכים; ייתכן שחילוף אחד יאפשר אותו.';
  renderPitch('pitchPlan',plan,candidate?.in_player.id,candidate?.repositioned.map(p=>p.player_id)||[]);
  $('moves').textContent=(candidate?'חולצה צהובה: נכנס · הילה כחולה: שינוי תפקיד. ':'')+(candidate?.repositioned.length?'שינויי תפקיד: '+candidate.repositioned.map(p=>`${p.name}: ${roleLabels[p.before]} → ${roleLabels[p.after]}`).join(' · '):'');
 }
 const reasonText={NO_SUBSTITUTIONS_LEFT:'כל החילופים נוצלו.',OUTSIDE_DECISION_WINDOW:'אין המלצות לפני דקה 20.',MISSING_PLAYER_PROFILES:'חסרים כרטיסי שחקנים לחישוב מלא.',UNSUPPORTED_PLAYER_COUNT:'בחינת מערך חלופי נתמכת כרגע ב־11 שחקנים בלבד.',NO_FEASIBLE_FORMATION_WITH_ONE_SUB:'אין הצבה חוקית למערך המבוקש באמצעות חילוף יחיד.',QUALITY_LOSS_TOO_LARGE:'חלק מהאפשרויות עוברות סף, אך אובדן האיכות הטקטית גדול מהמותר.',BELOW_THRESHOLD:'אף אפשרות לא עוברת את הסף.'};
 function renderAnalysis(){
  $('analysis').hidden=!opened;if(!opened||!record)return;
  const s=record.selected;$('verdict').className=s?'yes':'';$('verdict').textContent=s?`מומלץ: ${s.out_player.name} → ${s.in_player.name} · תועלת ${fmt(s.expected_benefit,4)} מול סף ${fmt(record.threshold,4)} · ${s.decision_basis==='FRESH_LEGS'?'מונע בעיקר מרענון':'מונע בעיקר מטקטיקה'}`:`אין המלצת חילוף. ${reasonText[record.no_substitution_reason]||record.no_substitution_reason}`;
  $('candidates').innerHTML=record.alternatives.map((c,i)=>`<button class="candidate ${chosen===c?'chosen':''}" data-index="${i}"><strong>${esc(c.out_player.name)} → ${esc(c.in_player.name)}</strong><span class="${c.recommended?'positive':'negative'}">${c.recommended?'עובר תנאים':!c.quality_gate_passed?'אובדן איכות גדול מדי':'מתחת לסף'} · ${fmt(c.expected_benefit,4)} / ${fmt(record.threshold,4)}</span> · ${c.change_type==='FORMATION_CHANGE'?'שינוי מערך':'אותו מערך'} · ${c.decision_basis==='FRESH_LEGS'?'רענון':'טקטי'}</button>`).join('')||'<p class="muted">אין חלופות חוקיות לפי המגבלות הנוכחיות.</p>';
  if(chosen){
   const c=chosen,x=c.score_components;
   const out=data.profiles[c.out_player.id],inc=data.profiles[c.in_player.id];
   $('comparison').innerHTML='<h3>פרופילי השחקנים</h3><table><thead><tr><th></th><th>יוצא</th><th>נכנס</th></tr></thead><tbody>'+[['שם',out.name,inc.name],['שערים / בישולים בעונה',out.season.totals.goals+' / '+out.season.totals.assists,inc.season.totals.goals+' / '+inc.season.totals.assists],['Stamina',fmt(out.physical.stamina,0),fmt(inc.physical.stamina,0)],['דקות עונה',fmt(out.general.minutes,0),fmt(inc.general.minutes,0)]].map(([l,a,b])=>`<tr><td>${l}</td><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')+'</tbody></table><h3>רכיבי ההחלטה</h3><table><tbody>'+[['תרומה טקטית',x.tactical_benefit],['תרומת רענון',x.freshness_benefit],['התאמת המחליף',c.position_fit],['עייפות היוצא — אומדן',x.outgoing_fatigue],['מחיר שינויי תפקיד',-x.tactical_support],['סף אובדן איכות מותר',record.max_tactical_loss_for_freshness]].map(([label,v])=>`<tr><td>${label}</td><td class="num">${fmt(v,4)}</td></tr>`).join('')+'</tbody></table><h3>הבדלי פרופיל: נכנס מול יוצא</h3><table><thead><tr><th>ממד</th><th>יוצא כעת</th><th>נכנס</th><th>הפרש כרטיס</th><th>שינוי בהרכב לפי תפקיד</th></tr></thead><tbody>'+Object.keys(dimLabels).map(d=>`<tr><td>${dimLabels[d]}</td><td class="num">${fmt(inc.recent.ratings[d]-c.expected_changes[d],1)}</td><td class="num">${fmt(inc.recent.ratings[d],1)}</td><td class="num">${fmt(c.expected_changes[d],2)}</td><td class="num">${fmt(c.lineup_changes[d],2)}</td></tr>`).join('')+'</tbody></table><p class="muted small">הפרשי ההרכב כוללים התאמת תפקיד והצבת יתר השחקנים; אינם שערים צפויים. אם ניתן לשנות מערך בלי חילוף, החילוף מושווה לאותה הצבה ללא חילוף.</p>';
  }else $('comparison').innerHTML='';
  $('raw').textContent=JSON.stringify({...record,alternatives:chosen?[chosen]:[],player_live:undefined},null,2);
 }
 async function analyze(){
  if(minutes()==null){record=null;showPlan(null);$('status').textContent='שריקת סיום · חזור לנקודת בדיקה כדי לבחון חילופים';controls();return;}
  const token=++requestToken,cfg=config(),key=contextKey(view,minutes(),cfg);pending=true;record=null;chosen=null;$('analysis').hidden=true;renderPitch('pitchPlan',[]);$('planLabel').textContent='מחשב הצבה לפי בחירת המאמן…';$('needs').replaceChildren();controls();$('status').textContent='מחשב לפי בחירת המאמן…';
  try{const response=await fetch('/api/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({match_id:view.match_id,team_id:view.team_id,minute:minutes(),config:cfg})});if(!response.ok)throw Error('request');const r=await response.json();if(token!==requestToken||key!==contextKey(view,minutes(),config()))return;record=r;
   $('needs').innerHTML=Object.entries(r.team_needs).map(([d,v])=>`<span class="need">${dimLabels[d]} ${fmt(v,2)}</span>`).join('');
   $('weights').innerHTML='<table><tr><th>ממד</th><th>משקל המאמן</th><th>חוסר תפוקה ביחס לרגיל</th></tr>'+Object.keys(dimLabels).map(d=>`<tr><td>${dimLabels[d]}</td><td class="num">${fmt(r.importance[d],3)}</td><td class="num">${fmt(r.performance_deficit_z[d],3)}</td></tr>`).join('')+'</table>';
   $('shiftInfo').textContent=r.observed.shifts.length?'שינוי מערך שנצפה: '+r.observed.shifts.map(s=>`${s.minute}:${String(s.second).padStart(2,'0')} → ${s.formation}`).join(' · '):'לא נצפה שינוי מערך עד נקודת הבדיקה הזאת.';
   showPlan(opened?(r.selected||r.alternatives[0]):null);renderAnalysis();$('status').textContent='מוכן · '+minutes()+'′ · החישוב עודכן לפי הבקרות';
   $('share').href='/?'+new URLSearchParams({team:view.team_id,minute:minutes(),...cfg,inspect:opened?'1':'0'});
  }catch(error){if(token===requestToken){record=null;$('status').textContent='החישוב נכשל. נסה לבחור שוב או בדוק שהשרת פועל.';}}
  finally{if(token===requestToken){pending=false;controls();}}
 }
 function goto(i){cancelAnimationFrame(animation);playing=false;index=i;elapsed=stages[index].elapsed;opened=false;$('analysis').hidden=true;$('sensitivityResult').innerHTML='';renderGame();analyze();}
 function finish(){goto(Math.min(index+1,stages.length-1));}
 function next(){if(playing||pending||index>=stages.length-1)return;const duration=Number($('speed').value);if(!duration){finish();return;}playing=true;opened=false;$('analysis').hidden=true;controls();const from=elapsed,to=stages[index+1].elapsed,start=performance.now();function frame(now){const t=Math.min(1,(now-start)/duration);elapsed=from+(to-from)*t;renderGame();if(t<1)animation=requestAnimationFrame(frame);else finish();}animation=requestAnimationFrame(frame);}
 function chooseTeam(start=0){requestToken++;pending=false;view=data.views.find(v=>v.team_id===$('team').value);fixture=data.fixtures[view.match_id];stages=[{minute:0,elapsed:0},...Array.from({length:18},(_,i)=>{const m=(i+1)*5;return{minute:m,elapsed:m+(m>45?fixture.first_half_extra:0)}}),{minute:null,elapsed:fixture.final_elapsed}];$('home').textContent=fixture.home.name;$('away').textContent=fixture.away.name;goto(start/5);}
 $('next').onclick=next;$('finish').onclick=finish;$('back').onclick=()=>goto(Math.max(0,index-1));$('reset').onclick=()=>goto(0);$('team').onchange=()=>chooseTeam();
 ['stance','objective','formation','freshness'].forEach(id=>$(id).onchange=()=>{$('sensitivityResult').innerHTML='';analyze();});
 $('check').onclick=()=>{opened=!opened;showPlan(opened?(record.selected||record.alternatives[0]):null);renderAnalysis();controls();};
 $('candidates').onclick=e=>{const b=e.target.closest('[data-index]');if(b){showPlan(record.alternatives[Number(b.dataset.index)]);renderAnalysis();}};
 $('sensitivity').onclick=async()=>{const key=contextKey(view,minutes(),config());$('sensitivity').disabled=true;$('sensitivityResult').textContent='משווה את אותם נתונים בארבעה משקלים…';try{const rows=[];for(const cap of [0,.5,1,1.5]){const r=await fetch('/api/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({match_id:view.match_id,team_id:view.team_id,minute:minutes(),config:{...config(),freshness_cap:cap}})});if(!r.ok)throw Error();rows.push([cap,await r.json()]);}if(key!==contextKey(view,minutes(),config()))return;$('sensitivityResult').innerHTML='<table><tr><th>רענון</th><th>המלצה</th><th>ציון מוביל</th><th>חלופות שעוברות</th></tr>'+rows.map(([cap,r])=>`<tr><td>${cap}</td><td>${r.selected?esc(r.selected.out_player.name+' → '+r.selected.in_player.name):'אין חילוף'}</td><td class="num">${fmt(r.alternatives[0]?.expected_benefit,4)}</td><td>${r.alternatives.filter(c=>c.recommended).length}</td></tr>`).join('')+'</table><p class="small muted">אותם נתונים ואותן בקרות; רק משקל הרענון השתנה. מספר המלצות אינו מדד לאיכות.</p>';}catch(error){$('sensitivityResult').textContent='לא ניתן להשלים את ההשוואה.';}finally{controls();}};
 fetch('/api/bootstrap').then(r=>{if(!r.ok)throw Error();return r.json()}).then(d=>{data=d;d.views.forEach(v=>$('team').add(new Option(teamLabels[v.team_id]+' · '+d.fixtures[v.match_id].home.name+' / '+d.fixtures[v.match_id].away.name,v.team_id)));d.formations.forEach(f=>$('formation').add(new Option(f,f)));const q=new URLSearchParams(location.search);$('team').value=d.views.some(v=>v.team_id===q.get('team'))?q.get('team'):'38';for(const id of ['stance','objective','formation','freshness']){const value=q.get(id==='freshness'?'freshness_cap':id);if([...$(id).options].some(o=>o.value===value))$(id).value=value;}const m=Number(q.get('minute')||0);chooseTeam(Number.isInteger(m)&&m>=0&&m<=90&&m%5===0?m:0);if(q.get('inspect')==='1')opened=true;}).catch(()=>$('status').textContent='לא ניתן לטעון. יש להפעיל scripts/serve_coach_room.py.');
}
