/* 실제 브라우저를 대신하지 않는 DOM 모의 통합 검사. 저장소 하위 경로의 데이터 로딩을 검증합니다. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fakeRepository } from './fixtures/github-api.mjs';

class Element {
  constructor(id, tag = 'div', initial = '') {
    this.id = id; this.tagName = tag; this.value = ''; this.hidden = false; this.disabled = false;
    this.checked = false; this.attrs = {}; this.events = {}; this.textContent = ''; this._html = '';
    this.innerHTML = initial;
  }
  set innerHTML(text) {
    this._html = text;
    if (this.tagName === 'select') {
      const option = text.match(/<option(?: value="([^"]*)")?[^>]*>([^<]*)<\/option>/);
      this.value = option ? option[1] ?? option[2] : '';
    }
  }
  get innerHTML() { return this._html; }
  addEventListener(event, fn) { (this.events[event] ||= []).push(fn); }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
  focus() {}
  async emit(event) { for (const fn of this.events[event] || []) await fn({ target: this, preventDefault() {} }); }
}

test('dashboard loads from a project path and filters actual supplied data', async () => {
  const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const elements = new Map();
  for (const m of html.matchAll(/<(\w+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const tag = m[1], start = m.index + m[0].length;
    const initial = html.slice(start, html.indexOf(`</${tag}>`, start));
    elements.set(m[2], new Element(m[2], tag, initial));
  }
  const tabs = [...elements.values()].filter(e => e.id.startsWith('tab-'));
  for (const e of tabs) e.attrs['aria-controls'] = 'panel-' + e.id.slice(4);
  const requested = [];
  const storage = new Map();
  const oldNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  let copied = '';
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: { writeText: async text => { copied = text; } } } });
  const originalTimeout = globalThis.setTimeout, timers = new Set();
  globalThis.setTimeout = (...args) => { const timer = originalTimeout(...args); timers.add(timer); return timer; };
  const row = dong => ({ dong, type: '84OA', floor: '20/58층', direction: '북서향', minPrice: 6, maxPrice: 6, floorCat: '중층' });
  const files = {
    'data/index.json': { latest: '2026-10-17', snapshots: [
      { id: '2026-10-17', date: '2026-10-17', label: '2026-10-17', file: '2026-10-17.json', count: 2, declaredCount: 2, complete: true },
      { id: '2026-10-16', date: '2026-10-16', label: '2026-10-16', file: '2026-10-16.json', count: 1, declaredCount: 1, complete: true },
      { id: '2026-08-06', date: '2026-08-06', label: '2026-08-06', file: '2026-08-06.json', count: 1, declaredCount: 2, complete: false },
    ] },
    'data/2026-10-17.json': { date: '2026-10-17', declaredCount: 2, items: [row('101동'), row('102동')] },
    'data/2026-10-16.json': { date: '2026-10-16', declaredCount: 1, items: [row('101동')] },
    'data/2026-08-06.json': { date: '2026-08-06', declaredCount: 2, items: [row('101동')] },
    'data/status.json': { lastAttemptResult: 'not_run' },
    'config.json': {},
  };
  let denied = '';
  globalThis.document = { baseURI: 'https://example.github.io/beomeo-w-monitor/', getElementById: id => elements.get(id), querySelectorAll: () => tabs };
  globalThis.localStorage = { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) };
  globalThis.fetch = async url => {
    requested.push(String(url));
    assert.ok(url.pathname.startsWith('/beomeo-w-monitor/'));
    const name = url.pathname.slice('/beomeo-w-monitor/'.length);
    if (name === denied) return { ok: false, status: 503 };
    return { ok: true, json: async () => structuredClone(files[name]) };
  };
  const flush = async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve)); };
  try {
    await import('../assets/app.mjs?integration'); await flush();
    assert.equal(elements.get('snapshotSelect').value, '2026-10-17');
    assert.equal(elements.get('compareSelect').value, '2026-10-16');
    assert.equal(elements.get('listTabCount').textContent, 2);
    assert.ok(elements.get('statusBanner').innerHTML.includes('제공된 기준 자료'));
    assert.equal((elements.get('listingGrid').innerHTML.match(/class="listing-card"/g) || []).length, 2);
    assert.ok(elements.get('briefingText').textContent.includes('[시장 핵심 요약]'));
    assert.ok(elements.get('briefingText').textContent.includes('[일일 변동 리포트]'));
    elements.get('briefingFormat').value = 'summary'; await elements.get('briefingFormat').emit('change');
    assert.ok(elements.get('briefingText').textContent.includes('[동별 호가 범위]'));
    assert.ok(!elements.get('briefingText').textContent.includes('[일일 변동 리포트]'));
    elements.get('briefingFormat').value = 'changes'; await elements.get('briefingFormat').emit('change');
    assert.ok(elements.get('briefingText').textContent.includes('[일일 변동 리포트]'));
    assert.ok(!elements.get('briefingText').textContent.includes('[시장 핵심 요약]'));
    await elements.get('copyBriefBtn').emit('click');
    assert.equal(copied, elements.get('briefingText').textContent);
    elements.get('briefingFormat').value = 'listings'; await elements.get('briefingFormat').emit('change');
    assert.equal((elements.get('briefingText').textContent.match(/^(78OB|84OA)  (?:\d+|저|중|고)층/gm) || []).length, 2);
    elements.get('groupToggle').checked = true;
    elements.get('listingView').value = 'text'; await elements.get('listingView').emit('change');
    assert.equal(elements.get('listingGrid').hidden, true);
    assert.ok(elements.get('listingDetails').innerHTML.includes('북서향'));
    assert.equal(elements.get('listingTextPanel').hidden, false);
    assert.equal(elements.get('groupToggle').disabled, true);
    assert.equal((elements.get('listingText').textContent.match(/^(78OB|84OA)  (?:\d+|저|중|고)층/gm) || []).length, 2);
    elements.get('dongFilter').value = '102동'; await elements.get('dongFilter').emit('change');
    assert.ok(!elements.get('listingGrid').innerHTML.includes('101동'));
    assert.ok(elements.get('listingGrid').innerHTML.includes('102동'));
    assert.ok(elements.get('listingText').textContent.includes('필터 결과: 1건 / 전체 관측 2건'));
    assert.ok(elements.get('listingText').textContent.includes('102동 · 필터 1건'));
    assert.ok(!elements.get('listingText').textContent.includes('101동 ·'));
    await elements.get('copyListingsBtn').emit('click');
    assert.equal(copied, elements.get('listingText').textContent);
    elements.get('searchInput').value = '일치할수없는검색어'; await elements.get('searchInput').emit('input');
    assert.ok(elements.get('listingGrid').innerHTML.includes('조건에 맞는 매물이 없습니다'));
    assert.ok(elements.get('listingText').textContent.includes('조건에 맞는 매물이 없습니다'));
    await elements.get('resetFiltersBtn').emit('click');
    assert.equal((elements.get('listingGrid').innerHTML.match(/class="listing-card"/g) || []).length, 2);
    elements.get('listingView').value = 'cards'; await elements.get('listingView').emit('change');
    assert.equal(elements.get('listingGrid').hidden, false);
    assert.equal(elements.get('listingTextPanel').hidden, true);
    assert.equal(elements.get('groupToggle').disabled, false);
    elements.get('snapshotSelect').value = '2026-08-06'; await elements.get('snapshotSelect').emit('change'); await flush();
    assert.equal(elements.get('listTabCount').textContent, 1);
    assert.ok(elements.get('statusBanner').innerHTML.includes('1건만 있는 자료'));
    assert.ok(elements.get('diffNote').textContent.includes('비교'));
    assert.ok(requested.some(url => url.endsWith('/data/2026-10-17.json')));
    files['data/status.json'] = { lastAttemptResult: 'failed', message: '접근 제한' };
    files['data/2026-10-17.json'].items[0].desc = '<img src=x onerror=alert(1)>';
    await elements.get('refreshBtn').emit('click'); await flush();
    assert.ok(elements.get('statusBanner').innerHTML.includes('최근 수집에 실패'));
    assert.ok(elements.get('listingGrid').innerHTML.includes('&lt;img'));
    assert.ok(!elements.get('listingGrid').innerHTML.includes('<img'));
    denied = 'data/2026-10-17.json';
    await elements.get('refreshBtn').emit('click'); await flush();
    assert.equal(elements.get('content').hidden, true);
    assert.equal(elements.get('exportJsonBtn').disabled, true);
    assert.ok(elements.get('statusBanner').innerHTML.includes('선택한 자료를 불러오지 못했습니다'));

    // Existing drafts migrate only after successful server read-back.
    denied = '';
    const repo = fakeRepository(files['data/index.json'], Object.fromEntries(Object.entries(files).filter(([name]) => name.startsWith('data/') && name !== 'data/index.json')));
    const staticFetch = globalThis.fetch;
    globalThis.fetch = (url, options) => String(url).startsWith('https://api.github.com/') ? repo.fetch(url, options) : staticFetch(url, options);
    const draft = { date: '2026-10-21', count: 1, declaredCount: 1, items: [row('103동')], source: { kind: 'manual-local' } };
    storage.set('beomeoW_pages_v1_manual', JSON.stringify({ legacy: draft }));
    await elements.get('refreshBtn').emit('click'); await flush();
    assert.equal(elements.get('pendingSaveCount').textContent, '서버 미저장 1개');
    elements.get('snapshotSelect').value = 'legacy'; await elements.get('snapshotSelect').emit('change'); await flush();
    assert.equal(elements.get('saveServerBtn').disabled, false);
    assert.ok(elements.get('statusBanner').innerHTML.includes('서버에 아직 저장하지 않은'));
    await elements.get('saveServerBtn').emit('click');
    assert.ok(elements.get('serverSaveStatus').textContent.includes('연결 토큰'));
    repo.denyWrites = true;
    elements.get('githubToken').value = 'test-token'; await elements.get('saveServerBtn').emit('click');
    assert.ok(elements.get('serverSaveStatus').textContent.includes('저장 미완료'));
    assert.ok(JSON.parse(storage.get('beomeoW_pages_v1_manual')).legacy);
    assert.equal(elements.get('saveServerBtn').disabled, false);
    repo.denyWrites = false;
    elements.get('githubToken').value = 'test-token'; await elements.get('saveServerBtn').emit('click'); await flush();
    assert.ok(elements.get('serverSaveStatus').textContent.includes('서버 저장 완료'));
    assert.ok(elements.get('serverSaveStatus').textContent.includes('1건 재조회 확인'));
    assert.deepEqual(JSON.parse(storage.get('beomeoW_pages_v1_manual')), {});
    assert.ok(!JSON.stringify([...storage.values()]).includes('test-token'));
    assert.equal(elements.get('githubToken').value, '');
    assert.equal(elements.get('saveServerBtn').disabled, true);
    await elements.get('refreshBtn').emit('click'); await flush();
    assert.ok(elements.get('statusBanner').innerHTML.includes('서버에 저장된 수동 자료'));
    assert.equal(elements.get('listTabCount').textContent, 1);
    assert.equal(elements.get('pendingSaveCount').textContent, '서버 미저장 0개');
  } finally {
    for (const timer of timers) clearTimeout(timer);
    globalThis.setTimeout = originalTimeout;
    if (oldNavigator) Object.defineProperty(globalThis, 'navigator', oldNavigator); else delete globalThis.navigator;
    delete globalThis.document; delete globalThis.localStorage; delete globalThis.fetch;
  }
});

