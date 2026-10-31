const {test}=require('node:test');const assert=require('node:assert/strict');
const {createVision,parse,CONSENT}=require('../cloudfunctions/fridgeApi/glm-vision');
function setup(overrides={}){
 let user={homeId:'h'},calls=0,now=Date.now();let tail=Promise.resolve();
 const store={transaction(fn){const task=tail.then(()=>fn({get:async c=>c==='fridge_users'?user:{members:[{id:'u'}]},put:async(c,id,u)=>{user=u}}));tail=task.catch(()=>{});return task;}};
 const service=async()=>({ok:true,data:{user:{id:'u'}}});
 const run=createVision({store,service,env:{GLM_VISION_READY:'true',ZHIPU_API_KEY:'test'},clock:()=>now,request:async(url,opts)=>{calls++;assert.equal(JSON.parse(opts.body).model,'glm-4v-flash');return new Response(JSON.stringify({choices:[{message:{content:'{"candidates":[{"name":"苹果","quantity":99,"expiry":"2099-01-01"}]}'}}]}));},...overrides});
 const imageBase64=Buffer.from([255,216,255,0,0,0,0,0,0,0,0,0]).toString('base64');
 return {run,event:{action:'vision.recognize',data:{imageBase64,consentVersion:CONSENT}},calls:()=>calls,user:()=>user};
}
test('GLM only returns names, discarding invented quantity/date/confidence',async()=>{const f=setup();const r=await f.run(f.event,{});assert.equal(r.ok,true);assert.equal(r.data.candidates[0].quantity,null);assert.equal(r.data.candidates[0].expiry,'');assert.equal(JSON.stringify(f.user()).includes('imageBase64'),false);});
test('GLM rejects no consent and invalid images before provider',async()=>{const f=setup();assert.equal((await f.run({...f.event,data:{...f.event.data,consentVersion:''}},{})).ok,false);assert.equal((await f.run({...f.event,data:{...f.event.data,imageBase64:'https://evil'}},{})).ok,false);assert.equal(f.calls(),0);});
test('GLM session and server switch gate image transmission',async()=>{const f=setup({env:{}});assert.equal((await f.run(f.event,{})).error.code,'VISION_SETUP');const g=setup({service:async()=>({ok:false,error:{code:'UNAUTHENTICATED'}})});assert.equal((await g.run(g.event,{})).ok,false);assert.equal(g.calls(),0);});
test('GLM concurrent requests are rate limited atomically',async()=>{const f=setup();const r=await Promise.all([f.run(f.event,{}),f.run(f.event,{})]);assert.equal(r.filter(x=>x.ok).length,1);assert.equal(f.calls(),1);});
test('GLM upstream errors never expose credentials and malformed JSON is rejected',async()=>{const f=setup({request:async()=>{throw Error('secret credential')}});const r=await f.run(f.event,{});assert.equal(r.error.code,'VISION_FAILED');assert.equal(JSON.stringify(r).includes('secret'),false);assert.throws(()=>parse('not JSON'));assert.deepEqual(parse('{"candidates":[]}'),[]);});
test('GLM filters rare non-Chinese foods from free-text candidates',()=>{const out=parse(JSON.stringify({candidates:[{name:'鹰嘴豆'},{name:'塔可'},{name:'Taco'},{name:'苹果'}]}));assert.deepEqual(out.map(x=>x.name),['苹果']);});

test('GLM initializes and reports disabled on Node 16 without fetch or AbortSignal',async()=>{
 const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
 const file=path.resolve(__dirname,'../cloudfunctions/fridgeApi/glm-vision.js');
 const mod={exports:{}};vm.runInNewContext(fs.readFileSync(file,'utf8'),{module:mod,require:require('node:module').createRequire(file),Buffer,setTimeout,clearTimeout});
 const run=mod.exports.createVision({store:{},service:async()=>({ok:true,data:{user:{id:'u'}}})});
 const result=await run({action:'vision.status'},{});assert.equal(result.ok,true);assert.equal(result.data.ready,false);
});
