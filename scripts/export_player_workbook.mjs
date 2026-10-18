import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL,fileURLToPath} from 'node:url';
import os from 'node:os';
const require=createRequire(import.meta.url);
let packageEntry;
try { packageEntry=require.resolve('@oai/artifact-tool'); } catch {
 const packages=process.env.ARTIFACT_NODE_MODULES || path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
 packageEntry=require.resolve('@oai/artifact-tool',{paths:[packages]});
}
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(packageEntry).href);

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const qa=path.join(root,'data/player_cards_qa');
await fs.mkdir(qa,{recursive:true});
const data=JSON.parse(await fs.readFile(path.join(root,'demo_data/demo_player_profiles.json'),'utf8'));
const out=path.join(root,'docs/player-cards');
await fs.mkdir(out,{recursive:true});
const players=[...data.players].sort((a,b)=>a.team.localeCompare(b.team)||a.positions.primary.localeCompare(b.positions.primary)||a.name.localeCompare(b.name));
const dims=['threat','creation','progression','retention','defense','aerial'];
const wb=Workbook.create();
const col=n=>{let s=''; for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
const sheets=[];
function build(name,title,headers,rows,widths={},subtitle='Pre-match cards frozen before 13 January 2016. No live-match performance.'){
 const sh=wb.worksheets.add(name);sheets.push(sh);sh.showGridLines=false;
 const last=col(headers.length-1), end=rows.length+5;
 sh.getRange(`A1:${last}${end}`).format.font={name:'Arial',size:10,color:'#172B46'};
 sh.getRange('A2').values=[[title]];sh.getRange('A2').format.font={name:'Arial',size:15,bold:true,color:'#17365D'};
 sh.getRange('A3').values=[[subtitle]];sh.getRange('A3').format.font={name:'Arial',size:10,italic:true,color:'#596579'};
 sh.getRange(`A5:${last}5`).values=[headers];
 if(rows.length)sh.getRange(`A6:${last}${end}`).values=rows;
 sh.getRange(`A5:${last}${end}`).format.rowHeight=23;
 sh.getRange(`A5:${last}5`).format={fill:'#17365D',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:38,horizontalAlignment:'center',verticalAlignment:'center'};
 sh.getRange(`A6:${last}${end}`).format.verticalAlignment='center';
 for(let c=0;c<headers.length;c++){
  const r=sh.getRange(`${col(c)}6:${col(c)}${end}`);
  r.format.columnWidth=widths[c]||14;
  const sample=rows.map(x=>x[c]).find(v=>v!==null&&v!=='n.a.');
  r.format.horizontalAlignment=typeof sample==='number'?'right':'left';
  if(typeof sample==='number')r.setNumberFormat('0.0');
 }
 const table=sh.tables.add(`A5:${last}${end}`,true,'PlayerTable'+sheets.length);
 table.showFilterButton=true;
 sh.freezePanes.freezeRows(5);sh.freezePanes.freezeColumns(2);
 if(name==='Cards')sh.tabColor='#17365D';
 return sh;
}

const cardRows=players.map(p=>[p.name,p.team,p.positions.primary,p.primary_role,...dims.map(d=>p.general.ratings[d]??'n.a.'),...dims.map(d=>p.recent.ratings[d]??'n.a.'),p.recent.minutes,p.recent.reliability,p.identity.height_cm,p.physical.pace??'n.a.',p.physical.tracking?.max_speed_kmh??'n.a.',p.physical.stamina,p.physical.strength,p.provenance.fifa.startsWith('SYNTHETIC')?'SYNTHETIC FALLBACK':'FIFA16 anchored']);
const cards=build('Cards','Four-club player cards',['Player','Team','Primary position','Role',...dims.map(d=>'General '+d),...dims.map(d=>'Recent '+d),'Recent minutes','Recent evidence','Height (cm)','FIFA pace','Max speed (km/h)*','Stamina','Strength','Ability source'],cardRows,{0:29,1:16,2:30,3:11,23:24});
cards.getRange(`R6:R${players.length+5}`).setNumberFormat('0.0%');
cards.getRange(`E6:P${players.length+5}`).conditionalFormats.add('colorScale',{colors:['#F5F7FA','#D9E8F5','#7BA8C8'],thresholds:[0,50,100]});
const brad=players.findIndex(p=>p.name==='Brad Smith')+6;
cards.getRange(`X${brad}`).format.fill='#FFF1C9';

const ratingRows=[];
for(const p of players)for(const d of dims)ratingRows.push([p.name,p.team,d,p.general.fifa_prior[d]??'n.a.',p.general.statsbomb_adjustment[d]??'n.a.',null,p.recent.form_delta[d]??'n.a.',null,p.general.reliability[d],p.recent.reliability_by_dimension[d],p.general.minutes,p.recent.minutes]);
const ratings=build('Rating detail','Ability prior and bounded adjustments',['Player','Team','Dimension','FIFA prior','Season adjustment','General','Recent delta','Recent','Season evidence','Recent evidence','Season minutes','Recent minutes'],ratingRows,{0:29,1:16,2:19,4:20});
for(let i=0;i<ratingRows.length;i++){
 const r=i+6;if(typeof ratingRows[i][3]==='number'){
  ratings.getRange(`F${r}`).formulas=[[`=ROUND(MAX(0,MIN(100,D${r}+E${r})),3)`]];
  ratings.getRange(`H${r}`).formulas=[[`=ROUND(MAX(0,MIN(100,F${r}+G${r})),3)`]];
 }else{ratings.getRange(`F${r}`).values=[['n.a.']];ratings.getRange(`H${r}`).values=[['n.a.']];}
}
ratings.getRange('I6:J221').setNumberFormat('0.0%');
for(const c of ['F','H']){ratings.getRange(`${c}6:${c}221`).setNumberFormat('0.0');ratings.getRange(`${c}6:${c}221`).format.horizontalAlignment='right';}
ratings.getRange('E6:E221').setNumberFormat('+0.0;-0.0;0.0');ratings.getRange('G6:G221').setNumberFormat('+0.0;-0.0;0.0');
// Overview links to the one calculation that owns each final rating.
for(let i=0;i<players.length;i++)for(let d=0;d<6;d++){
 const sr=6+i*6+d, dr=6+i;
 cards.getRange(`${col(4+d)}${dr}`).formulas=[[`='Rating detail'!F${sr}`]];
 cards.getRange(`${col(10+d)}${dr}`).formulas=[[`='Rating detail'!H${sr}`]];
}


const seasonKeys=['goals','non_penalty_goals','penalty_goals','assists','dribble_attempts','dribbles_completed','pass_attempts','passes_completed'];
const seasonRows=players.map(p=>[p.name,p.team,p.season.totals.minutes,...seasonKeys.map(k=>p.season.totals[k]),null,null,null,null]);
const season=build('Season output','Observed PL output before 13 January 2016',['Player','Team','Season minutes','Goals','Non-penalty goals','Penalty goals','Assists','Dribble attempts','Completed dribbles','Pass attempts','Completed passes','Goals / 90','Assists / 90','Dribble success','Pass completion'],seasonRows,{0:29,1:23,2:18,4:20,7:20,8:23,10:23},'Source: pinned StatsBomb events; PL only, before cutoff. Raw completion percentages are not pressure/difficulty adjusted.');
for(let i=0;i<seasonRows.length;i++){
 const r=i+6;
 season.getRange(`L${r}`).formulas=[[`=IF(C${r}>0,D${r}/C${r}*90,"n.a.")`]];
 season.getRange(`M${r}`).formulas=[[`=IF(C${r}>0,G${r}/C${r}*90,"n.a.")`]];
 season.getRange(`N${r}`).formulas=[[`=IF(H${r}>0,I${r}/H${r},"n.a.")`]];
 season.getRange(`O${r}`).formulas=[[`=IF(J${r}>0,K${r}/J${r},"n.a.")`]];
}
season.getRange(`D6:K${players.length+5}`).setNumberFormat('0');
season.getRange(`L6:M${players.length+5}`).setNumberFormat('0.00');
season.getRange(`N6:O${players.length+5}`).setNumberFormat('0.0%');
season.getRange(`L6:O${players.length+5}`).format.horizontalAlignment='right';
season.getRange(`N6:O${players.length+5}`).format.columnWidth=19;

const physicalRows=players.map(p=>{const f=p.fifa16,t=p.physical.tracking||{};return[p.name,p.team,p.primary_role,p.identity.height_cm,f.weight_kg??'n.a.',p.identity.preferred_foot,p.physical.pace??'n.a.',f.movement_acceleration,f.movement_sprint_speed,f.movement_agility??'n.a.',p.physical.stamina,p.physical.strength,f.power_jumping,t.max_speed_kmh??'n.a.',t.meters_per_minute??'n.a.',t.hsr_distance_90??'n.a.',t.hsr_count_90??'n.a.',t.sprint_distance_90??'n.a.',t.sprint_count_90??'n.a.',t.high_accel_90??'n.a.',t.high_decel_90??'n.a.',false,p.provenance.fifa.startsWith('SYNTHETIC')?'SYNTHETIC identity + ability':'FIFA16 attributes; SYNTHETIC tracking'];});
build('Physical','Physical capability and synthetic tracking references',['Player','Team','Role','Height (cm)','Weight (kg)','Foot','Pace','Acceleration','Sprint speed','Agility','Stamina','Strength','Jumping','Max km/h*','Meters/min*','HSR m/90*','HSR count/90*','Sprint m/90*','Sprints/90*','High accel/90*','High decel/90*','Tracking observed?','Source'],physicalRows,{0:29,1:16,5:12,22:52},'* Synthetic capability estimates. HSR: 20–25 km/h; sprint: >25 km/h. Unsupported GK tracking is n.a.');
const positionRows=[];
for(const p of players){const all=new Set([p.positions.primary,...p.positions.secondary,...p.positions.all_positions_played]);for(const pos of all)positionRows.push([p.name,p.team,pos,pos===p.positions.primary?'Primary':p.positions.secondary.includes(pos)?'Secondary':'Historical only',p.positions.minutes_by_position[pos]??0,p.positions.evidence[pos]||'Insufficient eligibility evidence',p.positions.broad_roles.join(', '),JSON.stringify(p.positions.suitability)]);}
build('Positions','Positions and pre-match evidence',['Player','Team','Exact position','Card status','Historical minutes','Position evidence','Eligible broad roles','Role suitability'],positionRows,{0:29,1:16,2:32,3:20,4:21,5:52,6:25,7:38});

const fieldRows=[];
function flatten(value,key,player){
 if(value===null||typeof value!=='object'){fieldRows.push([player.name,player.team,String(player.player_id),key,value===null?'n.a.':value]);return;}
 if(Array.isArray(value)){if(!value.length)fieldRows.push([player.name,player.team,String(player.player_id),key,'[]']);else value.forEach((v,i)=>flatten(v,`${key}[${i}]`,player));return;}
 for(const [k,v] of Object.entries(value))flatten(v,key?`${key}.${k}`:k,player);
}
for(const p of players)flatten(p,'',p);
const allFields=build('All fields','All stored player-card fields',['Player','Team','StatsBomb ID','Field path','Stored value'],fieldRows,{0:29,1:16,2:18,3:64,4:110},'Complete pre-match JSON fields. Filter Player / Field path; n.a. means unavailable or unsupported, not zero.');
allFields.getRange(`E6:E${fieldRows.length+5}`).setNumberFormat('General');

const guideRows=[
 ['Scope','72 players: Liverpool, Arsenal, Chelsea and Tottenham matchday squads, 13 January 2016. Player cards only; no live-match state.'],
 ['Reading the cards','General = stable ability. Recent = General + bounded last-five-team-match delta. All ability ratings are 0..100.'],
 ['Evidence strength','0..1 describes sample strength, not a probability that a rating is correct. Zero recent minutes means no recent delta.'],
 ['Missing values','n.a. is unknown / unsupported. GK outfield ratings and tracking are unsupported. Original FIFA goalkeeper ratings are preserved in All fields.'],
 ['Synthetic fallback','Brad Smith and Son are absent from this FIFA16 CSV. Same-role numeric medians: Brad overall 60..68, Son 75..85. Bands and foot are explicit demo assumptions; not observed personal ratings.'],
 ['FIFA16 source','https://github.com/kushal-gopal/EA-Sports-Fifa/blob/658e9f96cafcfdb636d6ca96fcc9bfdb1c064868/players_16.csv'],
 ['FIFA16 date','The precise SoFIFA update date is unverified. Ratings are video-game source values, not measured football ability.'],
 ['StatsBomb source','https://github.com/hudl/open-data/tree/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb'],
 ['StatsBomb scope','All 203 Premier League matches before 2016-01-13 define the evidence and calibration. No target-match performance enters the cards.'],
 ['Physical reference source','https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/data/aggregates/aus1league_physicalaggregates_20242025.csv'],
 ['Physical source meaning','A-League 2024/25 positional means guide SYNTHETIC estimates. They are not observed player tracking.'],
 ['General calculation','General = clamp(FIFA prior + 6 × season reliability × tanh(season signal / 2), 0, 100).'],
 ['Recent calculation','Recent = clamp(General + 6 × recent reliability × tanh(recent-vs-season signal / 2), 0, 100).'],
 ['Outcome signals','Threat = .7 npxG/90 + .3 non-penalty goals/90 + .05 box presence/90; creation = .7 xA/90 + .3 assists/90 + .1 box passes/90. Both use the existing +/-6 capped adjustment.'],
 ['Technical signals','Progression adds .5 completed dribbles/90; retention blends 80% ball retention and 20% raw pass completion, if observed. No pressure/difficulty adjustment.'],
 ['Volume rates','SUM(component) / SUM(minutes) × 90. Ball retention = 1 − SUM(losses) / SUM(ball actions).'],
 ['Season reliability','minutes / (minutes + 900), additionally constrained by actions/(actions+100) for retention and aerial attempts/(attempts+20) for aerial.'],
 ['Recent reliability','minutes / (minutes + 180), additionally constrained by the same retention/aerial opportunity counts.'],
 ['Recent team fixtures','Liverpool: 3754251, 3754226, 3754343, 3754051, 3754255. Arsenal: 3754069, 3754173, 3754309, 3754296, 3754117.'],
 ['Position eligibility','FIFA position OR historical position with BOTH at least 180 minutes AND 15% of historical minutes. Broad-role eligibility does not fully enforce left/right side.'],
 ['Aerial','FIFA heading 40%, jumping 25%, strength 20%, height-derived score 15%, plus capped observed adjustment.'],
 ['Speed estimate','max_speed_kmh = clip(24 + 0.12 × FIFA sprint speed, 25, 36). This is a heuristic conversion, not measured top speed.'],
 ['HSR / sprint','HSR scales role reference by pace factor and stamina factor. Sprint volume scales by pace_factor^1.5. No randomness.'],
 ...Object.entries(data.metadata.mapping).map(([d,weights])=>['FIFA mapping: '+d,Object.entries(weights).map(([k,v])=>`${k}: ${(v*100).toFixed(0)}%`).join('; ')]),
 ['Height score','height_rating = clip((height_cm − 150) × 2, 0, 100).'],
 ['Recalculation','Rating detail formulas reconstruct General and Recent from frozen priors and deltas; they do not regenerate event evidence or FIFA mappings.'],
];
build('Guide','Definitions, formulas and sources',['Topic','Explanation'],guideRows,{0:32,1:155},'Review assumptions before using these demo cards as football judgments.');

wb.recalculate();
for(let i=0;i<players.length;i++){
 const p=players[i], r=i+6;
 for(const [cell,expected] of [['L',p.season.p90.goals],['M',p.season.p90.assists],['N',p.season.dribble_success],['O',p.season.pass_completion]]){
  const actual=season.getRange(`${cell}${r}`).values[0][0];
  if(expected===null ? actual!=='n.a.' : Math.abs(actual-expected)>1e-8)throw Error('Season formula mismatch '+p.name+' '+cell);
 }
}
for(let i=0;i<players.length;i++)for(let d=0;d<6;d++){
 const actual=cards.getRange(`${col(4+d)}${6+i}`).values[0][0];
 const expected=players[i].general.ratings[dims[d]];
 if(expected!==null&&Math.abs(actual-expected)>.0011)throw Error('General mismatch '+players[i].name);
 const recent=cards.getRange(`${col(10+d)}${6+i}`).values[0][0];
 if(expected!==null&&Math.abs(recent-players[i].recent.ratings[dims[d]])>.0011)throw Error('Recent mismatch '+players[i].name);
}
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:10},maxChars:1500})).ndjson);
for(const [name,range] of [['Cards','A1:J13'],['Season output','A1:O13'],['Rating detail','A1:L13'],['Physical','A1:N13'],['Positions','A1:G13'],['All fields','A1:E13'],['Guide','A1:B12']]){
 const png=await wb.render({sheetName:name,range,scale:1.4,format:'png'});
 await fs.writeFile(path.join(qa,`cards-preview-${name.replaceAll(' ','_')}.png`),new Uint8Array(await png.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,'Four_Club_Player_Cards.xlsx'));
console.log(JSON.stringify({players:players.length,sheets:sheets.length,allFields:fieldRows.length,output:path.join(out,'Four_Club_Player_Cards.xlsx')}));
