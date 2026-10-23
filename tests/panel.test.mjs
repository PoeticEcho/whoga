import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

test('panel preserves article IDs across direct and observed out-link-bridge URLs', () => {
  const source=fs.readFileSync(new URL('../whoga-naver-collector/panel.js',import.meta.url),'utf8');
  for (const href of ['/articles/2651166087','/articles/2651166087/out-link-bridge?cpId=asil',
                      '/articles/2651166087?cpId=asil']) {
    const card={innerText:'수성범어더블유 101동\n매매 6억\n오피스텔168OB㎡ (전용78.36OB)중/58층남서향\n확인매물 2026.10.19',
      querySelectorAll:()=>[{getAttribute:()=>href}]};
    const panel={innerText:'매물 1 개\n매매\n전체면적\n전체동\n'+card.innerText,
      querySelectorAll:()=>[card],scrollTop:0,clientHeight:900,scrollHeight:900};
    const read=vm.runInNewContext('('+source+')',{document:{body:{innerText:panel.innerText},querySelectorAll:()=>[panel]},
      innerWidth:1440,innerHeight:900});
    const state=read(false);
    assert.equal(state.rows[0].representativeArticleId,'2651166087');
    assert.equal(state.rows[0].grouped,false);
  }
});
