// Statics: the live gates, run out of the patched workflow JSON. No reimplementation.
const fs=require('fs');
let P=0,F=0;
const t=(n,c,e)=>{c?(P++,console.log('  PASS  '+n)):(F++,console.log('  FAIL  '+n+(e!==undefined?'  '+JSON.stringify(e):'')));};
function gate(file,node,{nodes={},json={},statics={}}){
  const wf=JSON.parse(fs.readFileSync(file,'utf8'));
  const code=wf.nodes.find(n=>n.name===node).parameters.jsCode;
  const $=(nm)=>{ if(!(nm in nodes)) throw new Error(`Node '${nm}' hasn't been executed`);
    const v=nodes[nm]; return {item:{json:v},first:()=>({json:v}),all:()=>[{json:v}]}; };
  const items=[{json}];
  const out=new Function('$','$json','$input','$getWorkflowStaticData',code)
    ($,json,{all:()=>items,first:()=>items[0]},()=>statics);
  return {out:out.map(o=>o.json),statics};
}
const CAMP={id:572715,name:'[Events Visiting] [FinovateFall 2026] - Noah - LinkedIn'};
const NORM={campaign:CAMP,lead:{member_id:null,public_id:null,li_url:'https://www.linkedin.com/in/pii-1ff60be7'},event:'every_message_reply_received'};
const CFG={labels:{},stageRank:{},fields:{}};

console.log('\n[WF-1] the Arnab regression: lead archived between two replies');
{
  const sd={};
  // reply 1 - lead LIVE
  let r=gate('wf1_live.json','M7 Alert Gate',{nodes:{CONFIG:CFG,Normalize:NORM},
    json:{lead_id:'8694ea30-a30b-11f1-8297-bb888c95b31f',person_id:85903},statics:sd});
  const k1=r.out[0].__alert_key;
  t('reply 1 alerts', r.out[0].__should_alert===true, r.out[0].__alert_reason);
  t('key is person-based, not lead-based', k1==='P85903|572715', k1);
  // simulate delivery being recorded (M7 Labels Compute does this on ok:true)
  (sd.__alerted_v1=sd.__alerted_v1||{})[k1]=new Date().toISOString();
  // reply 2 - lead now ARCHIVED, so lead_id is null
  r=gate('wf1_live.json','M7 Alert Gate',{nodes:{CONFIG:CFG,Normalize:NORM},
    json:{lead_id:null,person_id:85903},statics:sd});
  t('reply 2 is SUPPRESSED (the bug)', r.out[0].__should_alert===false, r.out[0].__alert_reason);
  t('key unchanged by archiving', r.out[0].__alert_key===k1, r.out[0].__alert_key);
  t('reason names it', r.out[0].__alert_reason==='already_delivered', r.out[0].__alert_reason);
}
console.log('\n[WF-1] legacy lead-keyed entries are still honoured (no re-alert wave)');
{
  const sd={__alerted_v1:{'L8694ea30-a30b-11f1-8297-bb888c95b31f|572715':'2026-08-28T18:23:45Z'}};
  const r=gate('wf1_live.json','M7 Alert Gate',{nodes:{CONFIG:CFG,Normalize:NORM},
    json:{lead_id:'8694ea30-a30b-11f1-8297-bb888c95b31f',person_id:85903},statics:sd});
  t('suppressed via the legacy key', r.out[0].__should_alert===false);
  t('and says so', r.out[0].__alert_reason==='already_delivered_legacy_lead_key', r.out[0].__alert_reason);
}
console.log('\n[WF-1] REGRESSION: a genuinely new person still alerts');
{
  const r=gate('wf1_live.json','M7 Alert Gate',{nodes:{CONFIG:CFG,Normalize:NORM},
    json:{lead_id:'ffffffff',person_id:99999},statics:{}});
  t('first alert for a new person', r.out[0].__should_alert===true && r.out[0].__alert_reason==='first_alert');
  t('key is theirs', r.out[0].__alert_key==='P99999|572715', r.out[0].__alert_key);
}
console.log('\n[WF-1] no campaign -> still suppressed as a manual conversation');
{
  const r=gate('wf1_live.json','M7 Alert Gate',{nodes:{CONFIG:CFG,Normalize:{...NORM,campaign:null}},
    json:{lead_id:null,person_id:85903},statics:{}});
  t('manual_conversation', r.out[0].__should_alert===false && r.out[0].__alert_reason==='manual_conversation', r.out[0].__alert_reason);
}
console.log('\n[WF-1] CONTROL: the original gate FAILS the regression');
{
  const sd={};
  let r=gate('wf1_backup.json','M7 Alert Gate',{nodes:{CONFIG:CFG,Normalize:NORM},
    json:{lead_id:'8694ea30-a30b-11f1-8297-bb888c95b31f',person_id:85903},statics:sd});
  (sd.__alerted_v1=sd.__alerted_v1||{})[r.out[0].__alert_key]=new Date().toISOString();
  r=gate('wf1_backup.json','M7 Alert Gate',{nodes:{CONFIG:CFG,Normalize:NORM},
    json:{lead_id:null,person_id:85903},statics:sd});
  t('original re-alerts on reply 2 (proves the test bites)', r.out[0].__should_alert===true, r.out[0].__alert_reason);
}
console.log('\n==== '+P+' passed, '+F+' failed');
process.exit(F?1:0);
