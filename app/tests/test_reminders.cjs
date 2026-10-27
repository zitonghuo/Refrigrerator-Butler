const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createService, POLICY } = require('../cloudfunctions/fridgeApi/service');

// Same in-memory transaction model as test_cloud.cjs: it reproduces atomicity,
// but is not a substitute for a real CloudBase integration test.
class MemoryStore {
  constructor() { this.data = new Map(); this.tail = Promise.resolve(); }
  transaction(run) {
    const task = this.tail.then(async () => {
      const draft = structuredClone(this.data);
      const result = await run({
        get: async (c, id) => structuredClone(draft.get(c + '/' + id) || null),
        put: async (c, id, data) => draft.set(c + '/' + id, structuredClone(data)),
        remove: async (c, id) => draft.delete(c + '/' + id)
      });
      this.data = draft; return result;
    });
    this.tail = task.catch(() => {}); return task;
  }
}


const {settings,createDispatcher}=require('../cloudfunctions/fridgeApi/reminders');
const cfg=settings({REMINDERS_READY:'true',REMINDER_TEMPLATE_ID:'template_test_id',REMINDER_FIELDS:JSON.stringify({name:'thing1',date:'date2',note:'thing3'}),REMINDER_STATE:'trial'});
async function setup(send) {
 const store=new MemoryStore();let now=Date.parse('2026-10-27T02:00:00Z'),n=0;const delivered=[];
 const service=createService(store,{clock:()=>now,reminders:cfg});
 const call=(who,action,data={},key=now+'-'+(++n))=>service({action,data,key},{appid:'app',openid:who});
 const ok=async(...args)=>{const x=await call(...args);assert.equal(x.ok,true,JSON.stringify(x));return x.data};
 await ok('a','login',{policyVersion:POLICY});await ok('a','home.create',{name:'厨房'});
 const snap=await ok('a','snapshot');const uid=snap.user.id;
 const food=(expiry='2026-10-28')=>ok('a','item.add',{items:[{name:'牛奶',quantity:1,unit:'盒',location:'冷藏',expiry,source:'label'}]});
 const sub=()=>ok('a','reminder.subscribe',{templateId:cfg.templateId,accepted:true});
 const dispatch=createDispatcher({store,config:cfg,clock:()=>now,listUserIds:async after=>[...store.data.keys()].filter(k=>k.startsWith('fridge_users/')).map(k=>k.split('/')[1]).filter(id=>id>after).sort(),send:async args=>{delivered.push(args);if(send)return send(args);return {errCode:0}}});
 return {store,call,ok,food,sub,dispatch,delivered,uid,snap,advance:ms=>now+=ms};
}
test('reminder requires a configured template and explicit accepted result',async()=>{
 assert.equal(settings({REMINDERS_READY:'true',REMINDER_TEMPLATE_ID:'other_template_id'}).ready,false);
 assert.equal(settings({REMINDERS_READY:'true',REMINDER_TEMPLATE_ID:'template_test_id',REMINDER_FIELDS:'{"name":"thing1","date":"thing1"}'}).ready,false);
 const f=await setup();assert.equal((await f.call('a','reminder.subscribe',{templateId:'forged',accepted:true})).ok,false);
 assert.equal((await f.call('a','reminder.subscribe',{templateId:cfg.templateId,accepted:false})).ok,false);
});
test('timer rejects forged client calls and sends at most once under concurrent invocations',async()=>{
 const f=await setup();await f.food();await f.sub();
 for(const key of ['OPENID','APPID','UID','FROM_OPENID','UNIONID'])assert.equal((await f.dispatch({Type:'Timer'},{[key]:'forged'})).ok,false);
 await Promise.all([f.dispatch({Type:'Timer'},{}),f.dispatch({Type:'Timer'}, {})]);assert.equal(f.delivered.length,1);
 assert.equal(f.delivered[0].touser,'a');assert.equal(f.delivered[0].data.thing1.value,'冰箱临期食材');
 const status=await f.ok('a','reminder.status');assert.equal(status.pending,false);assert.equal(status.lastResult,'sent');assert.equal(JSON.stringify(status).includes('openid'),false);
 assert.equal(f.store.data.get('fridge_users/'+f.uid).reminder.openid,undefined);
});
test('cancelled subscriptions and departed family members receive nothing',async()=>{
 for(const action of ['reminder.cancel','home.leave','account.delete']){const f=await setup();await f.food();await f.sub();await f.ok('a',action);await f.dispatch({Type:'Timer'},{});assert.equal(f.delivered.length,0)}
});
test('no expiring stock means no send; expired subscriptions are cleared',async()=>{
 const f=await setup();await f.food('2026-12-01');await f.sub();await f.dispatch({Type:'Timer'},{});assert.equal(f.delivered.length,0);
 f.advance(8*86400000);await f.dispatch({Type:'Timer'},{});assert.equal((await f.ok('a','reminder.status')).pending,false);assert.equal(f.delivered.length,0);
});
test('uncertain send is never automatically retried, and quiet hours do not consume subscription',async()=>{
 const f=await setup(()=>{throw Error('timeout')});await f.food();await f.sub();f.advance(12*3600000);assert.equal((await f.dispatch({Type:'Timer'},{})).skipped,'QUIET_HOURS');assert.equal((await f.ok('a','reminder.status')).pending,true);
 f.advance(12*3600000);await f.dispatch({Type:'Timer'},{});await f.dispatch({Type:'Timer'},{});assert.equal(f.delivered.length,1);assert.equal((await f.ok('a','reminder.status')).lastResult,'unknown');
});
test('second subscription on the same day waits for a later day',async()=>{
 const f=await setup();await f.food();await f.sub();await f.dispatch({Type:'Timer'},{});await f.sub();await f.dispatch({Type:'Timer'},{});assert.equal(f.delivered.length,1);
 f.advance(86400000);await f.dispatch({Type:'Timer'},{});assert.equal(f.delivered.length,2);
});

test('actual five-field template is gated and has complete batch counts and Beijing days',async()=>{
 const actual=settings({REMINDERS_READY:'true',REMINDER_STATE:'trial'});
 assert.equal(actual.ready,true);
 assert.equal(settings({}).ready,false);
 assert.equal(settings({REMINDERS_READY:'true',REMINDER_FIELDS:'null'}).ready,false);
 assert.equal(settings({REMINDERS_READY:'true',REMINDER_FIELDS:'{"name":"thing1","date":"time2","note":"thing3"}'}).ready,false);
 const f=await setup();await f.food('2026-10-27');await f.food('2026-10-29');await f.sub();
 const custom={...actual,templateId:cfg.templateId};
 const dispatch=createDispatcher({store:f.store,config:custom,clock:()=>Date.parse('2026-10-27T11:59:00Z'),listUserIds:async after=>after?[]:[f.uid],send:async data=>{f.delivered.push(data);return {errCode:0}}});
 await dispatch({Type:'Timer'},{});
 assert.deepEqual(f.delivered[0].data,{thing1:{value:'冰箱临期食材'},time2:{value:'2026-10-27'},character_string5:{value:'2'},number6:{value:'0'},thing3:{value:'数量按临期批次计，请及时查看'}});
});
