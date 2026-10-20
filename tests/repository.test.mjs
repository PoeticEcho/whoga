import test from 'node:test';
import assert from 'node:assert/strict';
import { saveSnapshot, loadSharedIndex, loadSharedSnapshot, contentHash } from '../assets/repository.mjs';
import { fakeRepository } from './fixtures/github-api.mjs';

const snapshot = (date = '2026-10-21', price = 6) => ({ date, count: 1, declaredCount: 1, items: [
  { dong: '101동', type: '84OA', floor: '20/58층', direction: '남향', minPrice: price, maxPrice: 7, desc: '한글 설명' },
] });
const baseline = { schemaVersion: 2, latest: '2026-10-20', snapshots: [
  { id: '2026-10-20', file: '2026-10-20.json', date: '2026-10-20', complete: true },
] };
const setup = () => fakeRepository(baseline, { 'data/2026-10-20.json': snapshot('2026-10-20') });
const save = (repo, data = snapshot()) => saveSnapshot(data, { token: 'test-token', fetchImpl: repo.fetch });

test('file and index commit atomically; fresh unauthenticated client reads exact Unicode data', async () => {
  const repo = setup(), before = repo.files();
  const result = await save(repo);
  assert.equal(result.duplicate, false);
  const treeWrite = repo.requests.find(r => r.path === '/git/trees' && r.method === 'POST');
  assert.equal(treeWrite.body.tree.length, 2);
  assert.equal(treeWrite.body.tree.filter(e => e.path === 'data/index.json').length, 1);
  assert.deepEqual(repo.files()['data/2026-10-20.json'], before['data/2026-10-20.json']);
  const fresh = await loadSharedIndex(repo.fetch);
  assert.equal(fresh.index.latest, result.id);
  const entry = fresh.index.snapshots.find(e => e.id === result.id);
  const loaded = await loadSharedSnapshot(entry.file, fresh.ref, repo.fetch);
  assert.deepEqual(loaded.items, snapshot().items);
  assert.equal(loaded.source.kind, 'manual');
  assert.equal(loaded.collectedAt, undefined); // Save time never invents observation time.
  assert.equal(repo.requests.at(-1).authorization, undefined);
  assert.ok(!JSON.stringify(repo.files()).includes('test-token'));
});

test('identical data is idempotent across refresh and uncertain response retry', async () => {
  const repo = setup(), first = await save(repo), head = repo.head;
  const second = await save(repo);
  assert.equal(second.id, first.id); assert.equal(second.duplicate, true); assert.equal(repo.head, head);
  assert.equal(repo.files()['data/index.json'].snapshots.length, 2);
});

test('same-day corrections append a separate observation and preserve earlier files', async () => {
  const repo = setup(), first = await save(repo), second = await save(repo, snapshot('2026-10-21', 6.5));
  assert.notEqual(first.id, second.id);
  assert.equal(repo.files()['data/index.json'].snapshots.length, 3);
  assert.equal(repo.files()[`data/${first.id}.json`].items[0].minPrice, 6);
});

test('importing an old date preserves the newer latest selection', async () => {
  const repo = setup(); await save(repo, snapshot('2026-10-01'));
  assert.equal(repo.files()['data/index.json'].latest, '2026-10-20');
});

test('concurrent branch update merges both entries without a force push', async () => {
  const repo = setup(); repo.race = true;
  const result = await save(repo);
  assert.ok(result.index.snapshots.some(e => e.id === '2026-10-18_other'));
  assert.ok(result.index.snapshots.some(e => e.id === result.id));
  assert.equal(repo.requests.filter(r => r.method === 'PATCH').length, 2);
});

test('a lost successful PATCH response is resolved by reading the server', async () => {
  const repo = setup(); repo.losePatchResponse = true;
  assert.equal((await save(repo)).duplicate, false);
  assert.equal(repo.requests.filter(r => r.method === 'PATCH').length, 1);
});

test('permission failure leaves the entire server branch unchanged', async () => {
  const repo = setup(), head = repo.head; repo.denyWrites = true;
  await assert.rejects(save(repo), /저장 권한/);
  assert.equal(repo.head, head); assert.deepEqual(repo.files()['data/index.json'], baseline);
});

test('server read-back mismatch never reports successful save', async () => {
  const repo = setup(); repo.corruptRead = true;
  await assert.rejects(save(repo), /원본과 다릅니다/);
});

test('partial, empty or unauthenticated saves make no server requests', async () => {
  const repo = setup(), partial = snapshot(); partial.declaredCount = 2;
  await assert.rejects(save(repo, partial), /전체 수량/);
  await assert.rejects(save(repo, { date: '2026-10-21', items: [], declaredCount: 0 }), /전체 수량/);
  await assert.rejects(saveSnapshot(snapshot(), { fetchImpl: repo.fetch }), /연결 토큰/);
  assert.equal(repo.requests.length, 0);
});

test('invalid shared index blocks the write instead of discarding existing records', async () => {
  const repo = fakeRepository({ snapshots: null });
  await assert.rejects(save(repo), /서버 자료 목록/);
  assert.equal(repo.requests.filter(r => r.method !== 'GET').length, 0);
});

test('content identity ignores item order and object key order, preserves duplicate count', async () => {
  const a = snapshot(); a.items.push({ ...a.items[0], floor: '21/58층' }); a.count = a.declaredCount = 2;
  const b = { ...a, items: [...a.items].reverse().map(row => Object.fromEntries(Object.entries(row).reverse())) };
  assert.equal(await contentHash(a), await contentHash(b));
  b.items[0].maxPrice += .1;
  assert.notEqual(await contentHash(a), await contentHash(b));
});
