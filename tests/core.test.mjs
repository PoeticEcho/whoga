import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { validateSnapshot, compareSnapshots, stats, parseRaw, csvCell, pickPrevious, groupedRows, briefing, formatPrice, morningBriefing, changeReport, plainListings, observationLabel } from '../assets/core.mjs';

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

test('report uses actual KST observation time, not a hardcoded 8 AM', () => {
  const source = { ...snap(), date: '2026-10-18', collectedAt: '2026-10-18T11:00:00+09:00', observation: { observedAt: '2026-10-17T23:38:33Z' } };
  assert.equal(observationLabel(source), '📅 10/18 (일) 오전 8시 38분 기준 (KST)');
  assert.ok(observationLabel({ ...source, observation: {}, collectedAt: null }).includes('수집 시각 미기록'));
  assert.ok(observationLabel({ ...source, observation: {}, collectedAt: '2026-10-19T08:00:00+09:00' }).includes('수집 시각 미기록'));
});

test('morning report computes building counts, range upper bound and median independently', () => {
  const text = morningBriefing(snap([row(6, null, 8.3), row(7)]));
  assert.ok(text.includes('101동 (총 2건 · 관측 최다)'));
  assert.ok(text.includes('84OA: 6.0억 ~ 8.3억 (중앙값 6.5억)'));
  assert.ok(!/역대|심리|적체|굴복|전쟁터/.test(text));
});

test('plain list keeps every duplicate and price range, sorts within buildings and preserves actual floors', () => {
  const current = snap([{ ...row(6.5), agencyCount: 2 }, { ...row(5.4, null, 5.6), agencyCount: 9 }, { ...row(6.5), agencyInfo: '범어W스타' }, { ...row(6), dong: '102동', floor: '고/58층', agencyCount: 1 }]);
  const text = plainListings(current);
  const records = text.split('\n').filter(line => /^(78OB|84OA)  (?:\d+|저|중|고)층/.test(line));
  assert.equal(records.length, 4);
  assert.deepEqual(records.slice(0, 3).map(line => line.trim().split(/\s+/)), [['84OA', '20층', '5.40~5.60억', '9곳'], ['84OA', '20층', '6.50억', '2곳'], ['84OA', '20층', '6.50억', '—']]);
  assert.equal(records[0].indexOf('5.40'), records[1].indexOf('6.50'));
  assert.deepEqual(records[3].trim().split(/\s+/), ['84OA', '고층', '6.00억', '1곳']);
  assert.ok(plainListings(current, current.items.slice(0, 1)).includes('필터 결과: 1건 / 전체 관측 4건'));
  assert.ok(plainListings(current, []).includes('조건에 맞는 매물이 없습니다'));
});

test('change report separates confirmed changes, candidates, additions and unobserved rows', () => {
  const old = snap([row(8.3, '123'), { ...row(6), dong: '102동' }, { ...row(5.7), dong: '105동' }]);
  const current = { ...snap([row(7, '123', 8.3), { ...row(5.8), dong: '102동' }, { ...row(9), dong: '103동' }]), date: '2026-10-18' };
  const text = changeReport(current, old);
  for (const label of ['[추가 관측] (총 1건)', '[미관측] (총 1건)', '[호가 변동 · 매물번호 일치] (총 1건)', '[호가 변동 후보 · 조건 일치] (총 1건)']) assert.ok(text.includes(label));
  assert.ok(text.includes('8.3억 ➔ 7.0~8.3억 (하한 1.3억 하락 ↓)'));
  assert.ok(text.includes('전일 대비 총 관측: 3건 ➔ 3건 [0건]'));
  assert.ok(text.indexOf('[호가 변동 ·') < text.indexOf('[호가 변동 후보'));
  assert.ok(text.indexOf('[호가 변동 후보') < text.indexOf('[추가 관측]'));
  assert.ok(text.indexOf('[추가 관측]') < text.indexOf('[미관측]'));
  assert.ok(changeReport({ ...current, date: '2026-10-20' }, old).includes('비교일 2026-10-17 대비'));
  assert.ok(!/거래 추정|거둠|소진|급매물.*감춤|굴복/.test(text));
});

test('partial reports identify observed statistics and refuse a changes report', () => {
  const current = snap([row()], 118), text = briefing(current, snap());
  assert.ok(text.includes('일부 관측: 1건 (원문 118건 · 부분 자료)'));
  assert.ok(text.includes('관측 최저'));
  assert.ok(text.includes('일부 수집 스냅샷은 신규·미관측 비교에서 제외'));
  assert.ok(!text.includes('[미관측] (총'));
});

test('real snapshot plain list preserves every original record and computes building totals', () => {
  const current = JSON.parse(fs.readFileSync(new URL('../data/2026-10-18.json', import.meta.url)));
  const text = plainListings(current), lines = text.split('\n').filter(line => /^(78OB|84OA)  (?:\d+|저|중|고)층/.test(line));
  assert.equal(lines.length, current.items.length);
  for (const dong of ['101동', '102동', '103동', '105동']) {
    const count = current.items.filter(row => row.dong === dong).length;
    const section = text.split(`${dong} · ${count}건`)[1].split(/\n10\d동 ·|\n※/)[0];
    assert.equal(section.split('\n').filter(line => /^(78OB|84OA)  (?:\d+|저|중|고)층/.test(line)).length, count);
  }
});

test('Python notification and browser combined report use the same facts and wording', () => {
  const current = JSON.parse(fs.readFileSync(new URL('../data/2026-10-18.json', import.meta.url)));
  const previous = JSON.parse(fs.readFileSync(new URL('../data/2026-10-17.json', import.meta.url)));
  for (const [now, old] of [[current, previous], [snap(), null], [snap([row()], 118), snap()], [{ ...snap([row(7, '123', 8.3)]), date: '2026-10-18' }, snap([row(8.3, '123')])]]) {
    const actual = execFileSync('python3', ['-c', 'import json,sys; from monitor import build_briefing; a,b=json.load(sys.stdin); print(build_briefing(a,b),end="")'], { cwd: new URL('..', import.meta.url), input: JSON.stringify([now, old]), encoding: 'utf8' });
    assert.equal(actual, briefing(now, old));
  }
});
