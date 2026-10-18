const test=require('node:test');
const assert=require('node:assert/strict');
const {checkpointStages,visibleEvents,scoreAt,clockAt,effectiveRatings,thresholdGap}=require('../web/match-replay/app.js');

const fixture={home:{id:'38'},away:{id:'22'},first_half_extra:1,final_elapsed:95.651,events:[
 {kind:'goal',team_id:'22',elapsed:83.7166667},
 {kind:'substitution',team_id:'38',elapsed:91.2},
 {kind:'period_end',team_id:'38',elapsed:95.65}
]};

test('no result or event leaks across a five-minute boundary',()=>{
 assert.deepEqual(scoreAt(fixture,80),{'38':0,'22':0});
 assert.equal(visibleEvents(fixture,83.7166667).length,0);
 assert.deepEqual(scoreAt(fixture,86),{'38':0,'22':1});
 assert.equal(visibleEvents(fixture,fixture.final_elapsed).length,3);
});
test('stages preserve first-half added time and include final stoppage events',()=>{
 const stages=checkpointStages(fixture);
 assert.equal(stages.length,20);
 assert.equal(stages[9].elapsed,45);
 assert.equal(stages[10].elapsed,51);
 assert.equal(stages[18].elapsed,91);
 assert.equal(stages[19].final,true);
 assert.equal(clockAt(fixture,45.5).text,'45+0:30');
 assert.equal(clockAt(fixture,51).text,'50:00');
 assert.equal(clockAt(fixture,95.65,true).text,'90+4:39');
});
test('profile comparison uses the live correction once and reports signed threshold gaps',()=>{
 const profile={recent:{ratings:{threat:75,creation:99,aerial:60}}};
 const now=effectiveRatings(profile,{dimensions:{threat:-.5,creation:1,aerial:null}});
 assert.deepEqual(now,{threat:73,creation:100,aerial:60});
 assert.equal(thresholdGap({expected_benefit:.1},.15),-.04999999999999999);
 assert.ok(thresholdGap({expected_benefit:.2},.15)>0);
});
