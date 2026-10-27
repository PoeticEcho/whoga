import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const code=fs.readFileSync('assets/complex-url.js','utf8');
const context=vm.createContext({URL,setTimeout});vm.runInContext(code,context);
const parse=context.WhogaComplexUrl.extractComplexId;
test('shared NAS/public parser: numbers, direct URLs and compressed maps',()=>{
 assert.equal(code,fs.readFileSync('nas/static/complex-url.js','utf8'));
 for(const id of ['140635','140634','150278']){
  for(const value of [id,'https://fin.land.naver.com/complexes/'+id,'https://new.land.naver.com/complexes/'+id])assert.equal(parse(value),id);
  const layer=context.LZString.compressToEncodedURIComponent(JSON.stringify([{id:'complex_detail',params:{complexId:id}}]));
  assert.equal(parse('https://fin.land.naver.com/map?layer='+encodeURIComponent(layer)),id);
 }
});
test('invalid, foreign and ambiguous links never select a guessed target',()=>{
 for(const value of ['https://evil.test/complexes/123','https://fin.land.naver.com/map','javascript:alert(1)','1234567890123','https://user:pass@fin.land.naver.com/complexes/1'])assert.throws(()=>parse(value));
 const layer=context.LZString.compressToEncodedURIComponent(JSON.stringify(['123','456'].map(id=>({id:'complex_detail',params:{complexId:id}}))));
 assert.throws(()=>parse('https://fin.land.naver.com/map?layer='+encodeURIComponent(layer)));
});
