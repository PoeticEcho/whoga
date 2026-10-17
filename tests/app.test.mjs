/* 실제 브라우저를 대신하지 않는 DOM 모의 통합 검사. 저장소 하위 경로의 데이터 로딩을 검증합니다. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

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
    elements.get('dongFilter').value = '102동'; await elements.get('dongFilter').emit('change');
    assert.ok(!elements.get('listingGrid').innerHTML.includes('101동'));
    assert.ok(elements.get('listingGrid').innerHTML.includes('102동'));
    elements.get('searchInput').value = '일치할수없는검색어'; await elements.get('searchInput').emit('input');
    assert.ok(elements.get('listingGrid').innerHTML.includes('조건에 맞는 매물이 없습니다'));
    await elements.get('resetFiltersBtn').emit('click');
    assert.equal((elements.get('listingGrid').innerHTML.match(/class="listing-card"/g) || []).length, 2);
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
  } finally {
    delete globalThis.document; delete globalThis.localStorage; delete globalThis.fetch;
  }
});
