import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html=readFileSync(new URL('../url-converter.html',import.meta.url),'utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
const context=vm.createContext({URL});
vm.runInContext(scripts[0],context);
const extract=context.WhogaComplexUrl.extractComplexId;
assert.equal(scripts[0].trim(),readFileSync(new URL('../nas/static/complex-url.js',import.meta.url),'utf8').trim());
const map=layers=>'https://fin.land.naver.com/map?layer='+encodeURIComponent(context.LZString.compressToEncodedURIComponent(JSON.stringify(layers)));
const complex=id=>({id:'complex_detail',params:{complexId:id}});

test('the supplied real map URL resolves to 150278, including URL-encoded plus',()=>{
 const sample=scripts[1].match(/const exampleUrl = '([^']+)'/)[1];
 assert.equal(extract(sample),'150278');
 assert.equal(extract(sample.replaceAll('%2B','+')),'150278');
 assert.equal(extract(sample.replaceAll('&','\\&')),'150278');
});
test('direct complex URLs preserve the ID with optional query and slash',()=>{
 for(const url of ['https://fin.land.naver.com/complexes/140635?tab=article','fin.land.naver.com/complexes/140635/']) assert.equal(extract(url),'140635');
});
test('only a selected complex detail identifies a complex',()=>{
 assert.equal(extract(map([{id:'article_detail',params:{complexId:42}},complex('150278')])),'150278');
 assert.throws(()=>extract(map([{id:'article_detail',params:{complexId:42}}])),/선택된 단지/);
 assert.throws(()=>extract('https://fin.land.naver.com/map?zoom=17'),/선택되지 않은/);
 assert.throws(()=>extract(map([complex(1),complex(2)])),/여러 개/);
});
test('malformed layer, invalid identifiers, and lookalike hosts fail clearly',()=>{
 for(const value of [-1,0,1.2,9007199254740992,null,'<script>']) assert.throws(()=>extract(map([complex(value)])),/단지 번호/);
 for(const url of ['javascript:alert(1)','https://fin.land.naver.com.evil.test/complexes/1','https://user:pass@fin.land.naver.com/complexes/1']) assert.throws(()=>extract(url),/네이버 부동산 주소/);
 assert.throws(()=>extract('https://fin.land.naver.com/map?layer=broken'),/정보/);
 assert.throws(()=>extract(map({id:'complex_detail'})),/형식/);
});

test('legacy Naver URLs map the complex ID, not articleNo or map coordinates',()=>{
 for(const [id,query] of [['140634','?ms=2zClPZ,3AoFvS,16&a=APT:PRE:ABYG:JGC&e=RETAIL&articleNo=2657827868'],['150278','?ms=2zCC5s,3AoEvz,16&a=APT:PRE:ABYG:JGC&e=RETAIL']]) {
  const url='https://new.land.naver.com/complexes/'+id+query;
  assert.equal(extract(url),id);
  assert.equal(context.WhogaComplexUrl.normalize(url),'https://fin.land.naver.com/complexes/'+id);
 }
 assert.throws(()=>extract('https://new.land.naver.com/articles?articleNo=2657827868'),/단지 페이지/);
});
