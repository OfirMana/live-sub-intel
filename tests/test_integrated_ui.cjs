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
