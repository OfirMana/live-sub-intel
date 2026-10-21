const test=require('node:test'),assert=require('node:assert/strict');
const {explanationKey,contextKey}=require('../web/coach-room/app.js');
const {messages,translate}=require('../web/coach-room/i18n.js');
test('explanation identity changes with candidate, context, audience or language',()=>{
 const ctx=contextKey({match_id:'m',team_id:'t'},65,{stance:'attack'});
 const base=explanationKey(ctx,'swap:a:b','fan','en');
 for(const args of [[ctx,'swap:c:d','fan','en'],[ctx,'tactical','fan','en'],[ctx,'swap:a:b','analyst','en'],[ctx,'swap:a:b','fan','he'],[ctx+'changed','swap:a:b','fan','en']])assert.notEqual(base,explanationKey(...args));
});
test('English base and Hebrew cover the same interface with interpolation and fallback',()=>{
 assert.deepEqual(Object.keys(messages.en).sort(),Object.keys(messages.he).sort());
 assert.equal(translate('future-locale','headline'),messages.en.headline);
 assert.equal(translate('en','ready',{minute:65}),'Ready · 65′');
 assert.match(translate('he','ready',{minute:65}),/65/);
});

const {matchStatsAt}=require('../web/coach-room/app.js');
const statFixture={home:{id:'h'},away:{id:'a'},stat_events:[
 {id:'p1',kind:'pass',elapsed:10,team_id:'h',player_id:'creator',recipient_id:'scorer',success:true},
 {id:'p2',kind:'pass',elapsed:11,team_id:'a',player_id:'opponent',success:false},
 {id:'s1',kind:'shot',elapsed:12,team_id:'a',player_id:'opponent',xg:.2,on_target:false},
 {id:'g1',kind:'goal',elapsed:13,team_id:'h',player_id:'scorer',xg:.3,on_target:true,key_pass_id:'p1'},
 {id:'y1',kind:'card',elapsed:14,team_id:'h',player_id:'creator',card:'yellow'},
 {id:'r1',kind:'card',elapsed:16,team_id:'h',player_id:'creator',card:'second_yellow'}
]};
test('match totals and player markers include only past events and rewind cleanly',()=>{
 const early=matchStatsAt(statFixture,13);
 assert.equal(early.teams.h.shots,0);assert.equal(early.teams.a.shots,1);assert.deepEqual(early.players,{});
 const scored=matchStatsAt(statFixture,14);
 assert.equal(scored.teams.h.xg,.3);assert.equal(scored.teams.h.onTarget,1);
 assert.equal(scored.players.scorer.goals,1);assert.equal(scored.players.creator.assists,1);
 assert.equal(scored.players.creator.yellows,0);
 assert.equal(matchStatsAt(statFixture,15).players.creator.yellows,1);
 assert.equal(matchStatsAt(statFixture,16).players.creator.red,false);
 const red=matchStatsAt(statFixture,17).players.creator;
 assert.equal(red.red,true);assert.equal(red.yellows,2);
 assert.deepEqual(matchStatsAt(statFixture,13),early);
});
test('pass accuracy and pass-share proxy are distinct and zero attempts remain unknown',()=>{
 const empty=matchStatsAt(statFixture,0);assert.equal(empty.teams.h.accuracy,null);assert.equal(empty.teams.h.possessionProxy,null);
 const stats=matchStatsAt(statFixture,15);
 assert.equal(stats.teams.h.accuracy,100);assert.equal(stats.teams.a.accuracy,0);
 assert.equal(stats.teams.h.possessionProxy,50);assert.equal(stats.teams.a.possessionProxy,50);
});
test('duplicate records and invalid assist links cannot inflate player achievements',()=>{
 const f={...statFixture,stat_events:[...statFixture.stat_events,statFixture.stat_events[3],
  {id:'g2',kind:'goal',elapsed:18,team_id:'a',player_id:'opponent',xg:.1,key_pass_id:'p1'},
  {id:'g3',kind:'goal',elapsed:19,team_id:'h',player_id:'creator',xg:.1,key_pass_id:'p1'}]};
 const stats=matchStatsAt(f,20);
 assert.equal(stats.players.scorer.goals,1);assert.equal(stats.players.creator.assists,1);
 assert.equal(stats.players.opponent.assists,0);
});

const {possessionAt}=require('../web/coach-room/app.js');
test('possession integrates control time: pressure and lost tackles cannot steal it',()=>{
 const event=(id,sec,team_id,kind,success)=>({id,elapsed:sec/60,team_id,kind,success});
 const f={home:{id:'h'},away:{id:'a'},stat_events:[
  event('p',0,'h','pass',true),event('press',10,'a','pressure'),event('lost',15,'a','tackle',false),
  event('recover',20,'a','recovery',true),event('goal',30,'a','goal'),event('restart',40,'h','pass',true)
 ]};
 const before=possessionAt(f,20/60);assert.equal(before.seconds.h,20);assert.equal(before.seconds.a,0);
 const at=possessionAt(f,50/60);assert.equal(at.seconds.h,30);assert.equal(at.seconds.a,10);
 assert.equal(at.percent.h,75);assert.equal(at.percent.a,25);assert.equal(at.unknownSeconds,10);assert.equal(at.coverage,80);
 const gap=possessionAt(f,100/60);assert.equal(gap.seconds.h,50);assert.equal(gap.unknownSeconds,40);
 assert.deepEqual(possessionAt(f,20/60),before);
});
test('failed passes end inferred control and future events cannot fill unknown time',()=>{
 const f={home:{id:'h'},away:{id:'a'},stat_events:[
  {id:'a',elapsed:0,kind:'pass',team_id:'h',success:true},
  {id:'b',elapsed:10/60,kind:'pass',team_id:'h',success:false},
  {id:'c',elapsed:30/60,kind:'recovery',team_id:'a',success:true}
 ]};
 const s=possessionAt(f,20/60);assert.equal(s.seconds.h,10);assert.equal(s.seconds.a,0);assert.equal(s.unknownSeconds,10);
 const empty=possessionAt({...f,stat_events:[]},2);assert.equal(empty.percent.h,null);assert.equal(empty.unknownSeconds,120);
});
