import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePlan,saveCollectionPlan} from '../assets/repository.mjs';
import {compareSnapshots,validateSnapshot,plainListings} from '../assets/core.mjs';
const plan={schemaVersion:1,enabled:true,intervalHours:6,targets:[{complexNo:'123',label:'추가 단지'}]};
test('plan rejects unsafe IDs, duplicates, excess targets and invalid cadence',()=>{
  assert.deepEqual(validatePlan(plan),plan);
  for(const p of [{...plan,intervalHours:2},{...plan,targets:[]},{...plan,targets:[...plan.targets,...plan.targets]},{...plan,targets:[{complexNo:'../123'}]}])assert.throws(()=>validatePlan(p));
});
test('plan PUT uses expected SHA and token only in authorization header',async()=>{
  const seen=[];
  const fetchImpl=async(url,options)=>{seen.push({url,options});return {ok:true,json:async()=>({content:{sha:'new'},commit:{html_url:'https://github.com/PoeticEcho/whoga/commit/new'}})};};
  assert.equal((await saveCollectionPlan(plan,{token:'test-only',sha:'old',fetchImpl})).sha,'new');
  const body=JSON.parse(seen[0].options.body);assert.equal(body.sha,'old');assert.equal(body.branch,'main');
  assert.equal(seen[0].options.headers.Authorization,'Bearer test-only');assert.ok(!seen[0].options.body.includes('test-only'));
  assert.deepEqual(JSON.parse(Buffer.from(body.content,'base64')),plan);
});
test('generic apartment areas render without mixing complexes',()=>{
  const s={complexNo:'123',complexName:'새 아파트',date:'2026-10-26',declaredCount:1,items:[{dong:'201동',type:'110㎡ (전용84.9)',floor:'10/25층',direction:'남향',minPrice:9,maxPrice:10}]};
  assert.ok(validateSnapshot(s).complete);assert.match(plainListings(s),/201동/);assert.match(plainListings(s),/새 아파트/);
  assert.equal(compareSnapshots(s,{...s,complexNo:'456'}).available,false);
});
test('listing agency toggle removes header counts and note',()=>{
 const s={complexNo:'123',date:'2026-10-26',declaredCount:1,items:[{dong:'201동',type:'84㎡',floor:'10/25층',direction:'남향',minPrice:9,maxPrice:10,agencyCount:7}]};
 assert.match(plainListings(s),/7곳/);
 const text=plainListings(s,s.items,'priceAsc',false);assert.ok(!text.includes('중개'));assert.ok(!text.includes('7곳'));assert.match(text,/9.00~10.00억/);
});
