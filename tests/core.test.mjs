import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { validateSnapshot, compareSnapshots, stats, parseRaw, csvCell, pickPrevious, groupedRows, briefing, formatPrice } from '../assets/core.mjs';

const row = (price = 6, id = null, high = price) => ({ id: 'item_1', articleId: id, dong: '101동', type: '84OA', floor: '20/58층', floorCat: '중층', direction: '북서향', minPrice: price, maxPrice: high });
const snap = (items = [row()], declared = items.length) => ({ date: '2026-10-17', declaredCount: declared, count: items.length, items });

test('numbered price changes are separate from candidates', () => {
  assert.equal(compareSnapshots(snap([row(5.8, '1')]), snap([row(6, '1')])).changed.length, 1);
  assert.equal(compareSnapshots(snap([row(5.8)]), snap([row(6)])).candidates.length, 1);
});
test('different listing IDs never merge', () => {
  const diff = compareSnapshots(snap([row(5.8, '2')]), snap([row(6, '1')]));
  assert.equal(diff.changed.length + diff.candidates.length, 0);
  assert.equal(diff.added.length, 1); assert.equal(diff.unobserved.length, 1);
});
test('ambiguous floors do not become confirmed changes', () => {
  const diff = compareSnapshots(snap([row(5.8), row(5.9)]), snap([row(6), row(6.1)]));
  assert.equal(diff.changed.length + diff.candidates.length, 0); assert.equal(diff.added.length, 2);
});
test('range maximum change is detected', () => assert.equal(compareSnapshots(snap([row(6, '1', 6.3)]), snap([row(6, '1', 6.2)])).changed.length, 1));
test('partial snapshots cannot produce false removals', () => {
  const diff = compareSnapshots(snap([row()], 120), snap([row(), row()]));
  assert.equal(diff.available, false); assert.equal(diff.unobserved.length, 0);
});
test('counts are a multiset, grouping makes no ownership claim', () => {
  assert.equal(compareSnapshots(snap([row(), row()]), snap()).added.length, 1);
  assert.equal(groupedRows([row(), row()])[0].quantity, 2);
});
test('parse copied text and refuse incomplete copies', () => {
  const raw = fs.readFileSync(new URL('./fixtures/naver_copied.txt', import.meta.url), 'utf8');
  const result = parseRaw(raw, '2026-10-17');
  assert.equal(result.items.length, 2); assert.equal(result.items[1].maxPrice, 6.2);
  assert.throws(() => parseRaw(raw.replace('매물 2개', '매물 3개'), '2026-10-17'));
  assert.throws(() => parseRaw(raw, '2026-02-30'));
});
test('bad prices, duplicate IDs, unrecognized types are rejected', () => {
  assert.throws(() => validateSnapshot(snap([row(NaN)])));
  assert.throws(() => validateSnapshot(snap([row(6, 'a'), row(6, 'a')])));
  assert.throws(() => validateSnapshot(snap([{ ...row(), type: 'unknown' }])));
});
test('CSV formula characters are made literal', () => {
  assert.equal(csvCell('=HYPERLINK("x")'), '"\'=HYPERLINK(""x"")"');
  assert.equal(csvCell('행1\n행2'), '"행1\n행2"');
});
test('median is the middle value or mean of the middle pair', () => { assert.equal(stats([row(5), row(7)]).median, 6); assert.equal(stats([]).min, null); });
test('default comparison skips same-day alternatives and partials', () => {
  assert.equal(pickPrevious([{ id: 'same-day', date: '2026-10-17', complete: true }, { id: 'previous', date: '2026-10-16', complete: true }], { date: '2026-10-17' }).id, 'previous');
});
test('briefing describes source and observations without inferring sales', () => {
  const text = briefing(snap(), null); assert.ok(text.includes('실시간 수집 아님')); assert.ok(text.includes('거래 완료를 뜻하지 않습니다'));
  assert.equal(formatPrice(6.5123), '6억 5,123만 원');
});
test('all provided snapshots validate and latest remains canonical', () => {
  const index = JSON.parse(fs.readFileSync(new URL('../data/index.json', import.meta.url)));
  const latest = index.snapshots.find(e => e.id === index.latest);
  assert.ok(latest && latest.complete);
  assert.equal(latest.id, latest.date);
  for (const e of index.snapshots) assert.equal(validateSnapshot(JSON.parse(fs.readFileSync(new URL('../data/' + e.file, import.meta.url)))).complete, e.complete);
});
test('app DOM references exist, no external CDN or inline credentials', () => {
  const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8'), app = fs.readFileSync(new URL('../assets/app.mjs', import.meta.url), 'utf8');
  for (const match of app.matchAll(/\$\('([^']+)'\)/g)) assert.ok(html.includes(`id="${match[1]}"`), match[1]);
  assert.ok(!html.includes('cdn.') && !app.includes('api.telegram.org'));
});
