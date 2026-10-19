'use strict';

function checkpointStages(fixture) {
  return [{minute:0,elapsed:0},...Array.from({length:18},(_,i)=>{
    const minute=(i+1)*5;
    return {minute,elapsed:minute+(minute>45?fixture.first_half_extra:0)};
  }),{minute:null,elapsed:fixture.final_elapsed,final:true}];
}
function visibleEvents(fixture,elapsed) { return fixture.events.filter(e=>e.elapsed<elapsed); }
function scoreAt(fixture,elapsed) {
  const score={[fixture.home.id]:0,[fixture.away.id]:0};
  for(const e of visibleEvents(fixture,elapsed)) if(e.kind==='goal'||e.kind==='own_goal') score[e.team_id]++;
  return score;
}
function clockAt(fixture,elapsed,final=false) {
  if(!elapsed)return {text:'00:00',period:'לפני שריקת הפתיחה'};
  const secondHalf=elapsed>=45+fixture.first_half_extra;
  const clock=elapsed-(secondHalf?fixture.first_half_extra:0);
  const seconds=Math.floor(clock*60+1e-6),min=Math.floor(seconds/60),sec=String(seconds%60).padStart(2,'0');
  const limit=secondHalf?90:45;
  const text=min>=limit?`${limit}+${min-limit}:${sec}`:`${String(min).padStart(2,'0')}:${sec}`;
  return {text,period:final?'שריקת סיום':secondHalf?'מחצית שנייה':'מחצית ראשונה'};
}
function effectiveRatings(profile,live) {
  return Object.fromEntries(Object.entries(profile.recent.ratings).map(([d,r])=>[d,r===null?null:Math.max(0,Math.min(100,r+4*(live?.dimensions?.[d]??0)))]));
}
function thresholdGap(candidate,threshold) { return candidate.expected_benefit-threshold; }

if(typeof module!=='undefined') module.exports={checkpointStages,visibleEvents,scoreAt,clockAt,effectiveRatings,thresholdGap};
if(typeof document!=='undefined') initializeReplay();

function initializeReplay(){
  const data=JSON.parse(document.getElementById('replay-data').textContent);
  const $=id=>document.getElementById(id);
  const dims={threat:'איום לשער',creation:'יצירת מצבים',progression:'קידום הכדור',retention:'שמירת כדור',defense:'הגנה',aerial:'אוויר'};
  const teamHebrew={'Tottenham Hotspur':'טוטנהאם','Liverpool':'ליברפול','Arsenal':'ארסנל','Chelsea':'צ׳לסי'};
  const roleLabels={GK:'שוער',CB:'בלם',FB:'מגן',CM:'קשר מרכזי',AM_W:'קשר התקפי / כנף',ST:'חלוץ'};
  const abbreviations={'Tottenham Hotspur':'TOT','Leicester City':'LEI','Liverpool':'LIV','Arsenal':'ARS','Chelsea':'CHE','West Bromwich Albion':'WBA'};
  const shotOutcomes={'Saved':'נעצרה','Saved to Post':'נעצרה ופגעה בקורה','Post':'לקורה','Off T':'מחוץ למסגרת','Blocked':'נחסמה','Wayward':'מחוץ למסגרת','Saved Off Target':'נעצרה מחוץ למסגרת'};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=(v,n=3)=>v===null||v===undefined?'—':Number(v).toFixed(n);
  let view,fixture,stages,index=0,elapsed=0,playing=false,raf=null,token=0,targetIndex=0,candidateIndex=0,lastEventCount=-1;
  for(const v of [...data.views].sort((a,b)=>(a.team==='Tottenham Hotspur'?-1:b.team==='Tottenham Hotspur'?1:a.team.localeCompare(b.team)))) $('team').add(new Option(teamHebrew[v.team]||v.team,v.team_id));
  for(const f of Object.values(data.fixtures))$('fixture').add(new Option(`${f.home.name} / ${f.away.name}`,f.id));
  $('team').value=new URLSearchParams(location.search).get('team')||'38';
  if(!$('team').value)$('team').value='38';

  function cancel(){token++;if(raf!==null)cancelAnimationFrame(raf);raf=null;playing=false;}
  function snapshot(){return index>0&&!stages[index].final?view.snapshots.find(s=>s.minute===stages[index].minute):null;}
  function hideAnalysis(){ $('analysis').hidden=true;$('check').setAttribute('aria-expanded','false');candidateIndex=0; }
  function chooseTeam(){
    cancel();view=data.views.find(v=>v.team_id===$('team').value);fixture=data.fixtures[view.match_id];stages=checkpointStages(fixture);index=0;elapsed=0;lastEventCount=-1;
    $('fixture').value=fixture.id;
    $('home').textContent=fixture.home.name;$('away').textContent=fixture.away.name;
    $('homeBadge').textContent=abbreviations[fixture.home.name]||fixture.home.name.slice(0,3);
    $('awayBadge').textContent=abbreviations[fixture.away.name]||fixture.away.name.slice(0,3);
    $('homePerspective').textContent=view.team_id===fixture.home.id?'הקבוצה שלך':'';
    $('awayPerspective').textContent=view.team_id===fixture.away.id?'הקבוצה שלך':'';
    $('fixtureDate').textContent=`${fixture.date.split('-').reverse().join('.')} · מחזור ${fixture.matchweek}`;
    $('eventFlash').hidden=true;hideAnalysis();renderGame();renderControls();
  }
  function eventClock(e){const max=e.period===1?45:90;return e.minute>=max?`${max}+${e.minute-max}:${String(e.second).padStart(2,'0')}`:`${e.minute}:${String(e.second).padStart(2,'0')}`;}
  function teamName(tid){return fixture.home.id===tid?fixture.home.name:fixture.away.name;}
  function eventTitle(e){
    if(e.kind==='goal')return 'שער!';
    if(e.kind==='own_goal')return 'שער עצמי לזכות '+teamName(e.team_id);
    if(e.kind==='substitution')return 'חילוף המאמן';
    if(e.kind==='card')return e.card==='yellow'?'כרטיס צהוב':e.card==='second_yellow'?'צהוב שני ואדום':'כרטיס אדום';
    if(e.kind==='period_start')return e.period===1?'שריקת פתיחה':'תחילת המחצית השנייה';
    if(e.kind==='period_end')return e.period===1?'סיום המחצית הראשונה':'שריקת הסיום';
    return 'בעיטה — '+(shotOutcomes[e.outcome]||e.outcome||'');
  }
  function eventBody(e){
    if(e.kind==='substitution')return `<p class="event-player">${esc(e.player)} → ${esc(e.replacement)}</p><p>${esc(teamName(e.team_id))} · חילוף היסטורי שבוצע בפועל</p>`;
    if(e.kind.startsWith('period_'))return '';
    return (e.player?`<p class="event-player">${esc(e.player)}</p>`:'')+`<p>${esc(teamName(e.team_id))}${e.xg!==null?' · xG '+fmt(e.xg,2):''}</p>`;
  }
  function renderGame(){
    const score=scoreAt(fixture,elapsed);$('score').textContent=`${score[fixture.home.id]} : ${score[fixture.away.id]}`;
    $('score').setAttribute('aria-label',`${fixture.home.name} ${score[fixture.home.id]}, ${fixture.away.name} ${score[fixture.away.id]}`);
    const clock=clockAt(fixture,elapsed,!!stages[index]?.final&&!playing);$('clock').textContent=clock.text;$('period').textContent=clock.period;
    const progress=Math.min(elapsed/fixture.final_elapsed,1)*100;$('railFill').style.width=progress+'%';$('railDot').style.left=progress+'%';
    const visible=visibleEvents(fixture,elapsed);
    if(visible.length!==lastEventCount){
      if(playing&&lastEventCount>=0){const fresh=visible.slice(lastEventCount).filter(e=>['goal','own_goal','substitution','card'].includes(e.kind));if(fresh.length){const e=fresh.at(-1);$('eventFlash').textContent=`${eventClock(e)} · ${eventTitle(e)}${e.player?' · '+e.player:''}`;$('eventFlash').hidden=false;}}
      lastEventCount=visible.length;renderEvents(visible);
    }
  }
  function renderEvents(visible=visibleEvents(fixture,elapsed)){
    const filtered=visible.filter(e=>$('showShots').checked||e.kind!=='shot');
    $('events').innerHTML=filtered.length?[...filtered].reverse().map(e=>`<li class="event ${esc(e.kind)}"><time>${eventClock(e)}</time><div><strong>${esc(eventTitle(e))}</strong>${eventBody(e)}</div></li>`).join(''):'<li class="empty">המשחק עוד לפנינו. התקדמו חמש דקות כדי להתחיל.</li>';
  }
  function renderControls(){
    const final=!!stages[index].final;
    $('next').disabled=playing||final;$('back').disabled=playing||index===0;$('finishSegment').hidden=!playing;
    $('next').textContent=index===18?'המשך לתוספת הזמן ולסיום ←':'התקדם 5 דקות ←';
    const s=snapshot();$('check').disabled=playing||!s;$('check').textContent=playing?'המשחק מתקדם…':final?'המשחק הסתיים':s?`בדוק חילופים בדקה ${s.minute}`:'בדוק חילופים';
    $('decisionMinute').textContent=playing?'במהלך מקטע':final?'סיום המשחק':s?`דקה ${s.minute}`:'ממתין למשחק';
    $('checkHint').textContent=playing?'הבדיקה תהיה זמינה בסוף המקטע.':final?'אפשר לחזור לנקודת בדיקה קודמת ולבחון את ההחלטה.':!s?'התקדם לנקודת הבדיקה הראשונה.':'לחיצה תחשוף את ההמלצה ואת כל האפשרויות החוקיות.';
    $('segmentStatus').textContent=playing?'מריץ את המקטע הבא…':final?'המשחק הסתיים':index?`המקטע הושלם · נקודת בדיקה ${stages[index].minute}′`:'מוכן לשריקת הפתיחה';
  }
  function goTo(i){cancel();index=i;elapsed=stages[i].elapsed;hideAnalysis();$('eventFlash').hidden=true;lastEventCount=-1;renderGame();renderControls();}
  function complete(){if(!playing)return;cancel();index=targetIndex;elapsed=stages[index].elapsed;renderGame();renderControls();}
  function next(){
    if(playing||index>=stages.length-1)return;targetIndex=index+1;hideAnalysis();$('eventFlash').hidden=true;
    const duration=Number($('speed').value);if(!duration){goTo(targetIndex);return;}
    playing=true;const start=elapsed,end=stages[targetIndex].elapsed,began=performance.now(),currentToken=++token;renderControls();
    function frame(now){if(currentToken!==token)return;const t=Math.min((now-began)/duration,1);elapsed=start+(end-start)*t;renderGame();if(t<1)raf=requestAnimationFrame(frame);else complete();}
    raf=requestAnimationFrame(frame);
  }
  const harmful=(c,s)=>(c.score_components?.tactical_benefit??0)<-(s.max_tactical_loss_for_freshness??0);
  const kind=c=>(c.decision_basis==='FRESH_LEGS'?'רענון':'טקטי')+(c.change_type==='FORMATION_CHANGE'?' · שינוי מערך':'');
  function gapText(c,s){const gap=thresholdGap(c,s.threshold);if(gap>=0&&harmful(c,s))return 'עובר את הסף בזכות רענון, אבל המחליף חלש מדי';return gap>=0?`עובר את הסף ב־${fmt(gap,4)}`:`חסר לסף ${fmt(-gap,4)}`;}
  function showAnalysis(){
    const s=snapshot();if(!s||playing)return;
    if(!$('analysis').hidden){hideAnalysis();renderControls();return;}
    $('analysis').hidden=false;$('check').setAttribute('aria-expanded','true');
    $('check').textContent='סגור את בדיקת החילופים';
    const best=s.alternatives[0],yes=!!s.selected;
    $('verdict').className='verdict'+(yes?' yes':'');
    $('verdict').innerHTML=yes?`<b>מומלץ לבצע חילוף</b><span dir="ltr">${esc(s.selected.out_player.name)} → ${esc(s.selected.in_player.name)}</span><br>סוג: ${kind(s.selected)} · תועלת ${fmt(s.selected.expected_benefit,4)} מול סף ${fmt(s.threshold,4)}`:best?(s.no_substitution_reason==='QUALITY_LOSS_TOO_LARGE'?`<b>אין המלצת חילוף כרגע</b>יש אפשרויות שעוברות את הסף בזכות רענון, אבל בכולן המחליף חלש מדי ביחס לשחקן שיוצא.`:`<b>אין המלצת חילוף כרגע</b>האפשרות המובילה: ${gapText(best,s)}. הסף הוא ${fmt(s.threshold,4)}.`):`<b>אין מועמד חוקי בנקודה הזאת</b>${s.minute<20?'המנוע אינו ממליץ על חילופים לפני דקה 20.':s.state.subs_left===0?'כל החילופים הזמינים כבר נוצלו.':'אין מחליף זמין שתואם לתפקידים הנתמכים.'}`;
    if(s.unavailable_profile_ids.length)$('verdict').innerHTML+=`<br>חסרים ${s.unavailable_profile_ids.length} כרטיסים של שחקנים פעילים.`;
    $('needs').innerHTML=Object.entries(s.team_needs).map(([d,v])=>`<span class="need">${dims[d]} ${fmt(v,2)}</span>`).join('');
    $('comparison').hidden=!best;
    $('optionsHeading').textContent=`כל האפשרויות החוקיות (${s.alternatives.length}), לפי הציון`;
    if(best)selectCandidate(0);else $('candidates').innerHTML='<p class="muted small">כשתהיה אפשרות חוקית היא תופיע כאן, גם אם לא תעבור את הסף.</p>';
  }
  function renderCandidates(s){
    const previousScroll=$('candidates').scrollTop,hadFocus=$('candidates').contains(document.activeElement);
    $('candidates').innerHTML=s.alternatives.map((c,i)=>{
      const max=Math.max(s.threshold*1.5,c.expected_benefit*1.1),pass=c.expected_benefit>=s.threshold&&!harmful(c,s);
      return `<button class="candidate${i===candidateIndex?' chosen':''}${pass?' passes':''}" data-candidate="${i}" aria-pressed="${i===candidateIndex}"><span class="names">${esc(c.out_player.name)} → ${esc(c.in_player.name)}${c.change_type==='FORMATION_CHANGE'?' · שינוי מערך':''}</span><span class="candidate-top"><span class="gap ${pass?'pass':'fail'}">${gapText(c,s)}</span><span class="value">${fmt(c.expected_benefit,4)} / ${fmt(s.threshold,4)}</span></span><span class="gauge"><span class="gauge-fill" style="display:block;width:${Math.max(0,c.expected_benefit)/max*100}%"></span><span class="threshold-marker" style="left:${s.threshold/max*100}%"></span></span></button>`;
    }).join('');
    $('candidates').scrollTop=previousScroll;
    if(hadFocus)$('candidates').querySelector(`[data-candidate="${candidateIndex}"]`)?.focus({preventScroll:true});
  }
  function playerCard(p,incoming,live,activeRole){
    const rel=Object.values(p.general.reliability).reduce((a,b)=>a+b,0)/6;
    return `<div class="player-card${incoming?' incoming':''}"><span class="label">${incoming?'נכנס · ספסל':'יוצא · על המגרש'}</span><h4>${esc(p.name)}</h4><span class="small muted">${incoming?'תפקיד מוצע':'תפקיד במשחק'}: ${roleLabels[activeRole]||activeRole}</span><dl><dt>תפקיד ראשי בכרטיס</dt><dd>${p.primary_role}</dd><dt>שערים / בישולים בעונה</dt><dd>${p.season.totals.goals} / ${p.season.totals.assists}</dd><dt>דקות עונה</dt><dd>${fmt(p.general.minutes,0)}</dd><dt>דקות במשחק</dt><dd>${incoming?'0':fmt(live?.minutes_played,0)}</dd><dt>מדד עייפות משוער</dt><dd>${incoming?'0.00':fmt(live?.fatigue,2)} / 1</dd><dt>Stamina</dt><dd>${fmt(p.physical.stamina,0)}</dd><dt>חוזק ראיות עונתי</dt><dd>${fmt(rel,2)} / 1</dd></dl>${p.provenance.fifa.startsWith('SYNTHETIC')?'<span class="synthetic">עוגן FIFA סינתטי — אין רשומת מקור אישית</span>':''}</div>`;
  }
  function selectCandidate(i){
    const s=snapshot();if(!s||!s.alternatives[i])return;candidateIndex=i;renderCandidates(s);
    const c=s.alternatives[i],out=data.profiles[c.out_player.id],incoming=data.profiles[c.in_player.id],live=s.live[c.out_player.id];
    const activeRole=fixture.active_roles[c.out_player.id];
    $('players').innerHTML=playerCard(out,false,live,activeRole)+playerCard(incoming,true,null,activeRole);
    $('fit').textContent=`התאמת עמדה ${fmt(c.position_fit,2)}`;
    const effective=effectiveRatings(out,live);
    $('deltas').innerHTML=Object.keys(dims).map(d=>{const delta=c.expected_changes[d]??incoming.recent.ratings[d]-effective[d];return `<tr><td>${dims[d]}</td><td class="num">${fmt(effective[d],1)}</td><td class="num">${fmt(incoming.recent.ratings[d],1)}</td><td class="num ${delta>=0?'positive':'negative'}">${delta>=0?'+':''}${fmt(delta,1)}</td></tr>`;}).join('');
    const x=c.score_components,e=x.evidence_multiplier,fit=c.position_fit;
    const parts=[['שיפור טקטי ומחיר אובדן איכות',x.tactical_core],['תמיכה טקטית — אוויר ומהירות',x.tactical_support],['ערך רענון לפני מכפילים',x.freshness_relief],['מקדם חוזק ראיות',e],['התאמת עמדה',fit],['מקדם זמן טקטי',x.remaining_time_multiplier],['מקדם זמן לרענון',x.freshness_time_multiplier],['תרומה טקטית לאחר מכפילים',(x.tactical_core+x.tactical_support)*e*fit*x.remaining_time_multiplier],['תרומת רענון לאחר מכפילים',x.freshness_relief*e*fit*x.freshness_time_multiplier]];
    $('components').innerHTML=parts.map(([label,v])=>`<div class="component"><span>${label}</span><strong>${fmt(v,4)}</strong></div>`).join('')+`<div class="component total"><span>תועלת החילוף</span><strong>${fmt(c.expected_benefit,4)}</strong></div><div class="component"><span>סף ההמלצה</span><strong>${fmt(s.threshold,4)}</strong></div><p class="small">${gapText(c,s)}. הרכיבים מוצגים בעיגול.</p>`;
    $('prematch').innerHTML='<div class="table-scroll"><table><thead><tr><th>ממד</th><th>יוצא General</th><th>יוצא Recent</th><th>נכנס General</th><th>נכנס Recent</th></tr></thead><tbody>'+Object.keys(dims).map(d=>`<tr><td>${dims[d]}</td>${[out.general.ratings[d],out.recent.ratings[d],incoming.general.ratings[d],incoming.recent.ratings[d]].map(v=>'<td class="num">'+fmt(v,1)+'</td>').join('')}</tr>`).join('')+'</tbody></table></div>';
    $('raw').textContent=JSON.stringify({minute:s.minute,state:s.state,threshold:s.threshold,team_needs:s.team_needs,candidate:c,outgoing_live:live},null,2);
  }
  $('team').onchange=chooseTeam;$('next').onclick=next;$('finishSegment').onclick=complete;$('back').onclick=()=>goTo(Math.max(0,index-1));$('reset').onclick=()=>goTo(0);$('check').onclick=showAnalysis;$('showShots').onchange=()=>renderEvents();
  $('fixture').onchange=()=>{const nextView=data.views.find(v=>v.match_id===$('fixture').value&&v.team_id===$('team').value)||data.views.find(v=>v.match_id===$('fixture').value);$('team').value=nextView.team_id;chooseTeam();};
  $('candidates').onclick=e=>{const b=e.target.closest('button[data-candidate]');if(b)selectCandidate(Number(b.dataset.candidate));};
  chooseTeam();
}
