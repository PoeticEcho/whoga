/* DOM·네트워크에 의존하지 않는 데이터 검증·비교 함수입니다. */
export function validateSnapshot(s) {
  if (!s || !Array.isArray(s.items) || typeof s.date !== 'string' || !/^\d{4}-\d{2}-\d{2}/.test(s.date)) throw new Error('날짜와 items 배열이 있는 스냅샷이 필요합니다.');
  const iso = s.date.slice(0, 10);
  if (Number.isNaN(Date.parse(iso)) || new Date(iso).toISOString().slice(0, 10) !== iso) throw new Error('유효한 기준일을 입력해 주세요.');
  if (!Number.isInteger(s.declaredCount) || s.declaredCount < 0) throw new Error('원문 총 매물 수가 필요합니다.');
  if (s.count !== undefined && s.count !== s.items.length) throw new Error('count와 실제 매물 수가 다릅니다.');
  const ids = new Set();
  for (const row of s.items) {
    if (!row || ['dong', 'type', 'floor', 'direction'].some(k => typeof row[k] !== 'string' || !row[k].trim())) throw new Error('동·타입·층·향을 확인해 주세요.');
    if (!['78OB', '84OA'].includes(row.type) || !['101동', '102동', '103동', '105동'].includes(row.dong)) throw new Error('범어W 오피스텔 대상 동·타입을 확인해 주세요.');
    if (![row.minPrice, row.maxPrice].every(v => typeof v === 'number' && Number.isFinite(v) && v > 0) || row.maxPrice < row.minPrice) throw new Error('호가 숫자를 확인해 주세요.');
    if (row.articleId) {
      if (!/^[\w-]{1,80}$/.test(String(row.articleId)) || ids.has(String(row.articleId))) throw new Error('매물번호가 중복되거나 형식이 올바르지 않습니다.');
      ids.add(String(row.articleId));
    }
  }
  return { complete: s.declaredCount === s.items.length, declaredCount: s.declaredCount, count: s.items.length };
}

export const locationKey = row => JSON.stringify(['dong', 'type', 'floor', 'direction'].map(k => row[k] || ''));
export const priceKey = row => JSON.stringify([row.minPrice, row.maxPrice].map(v => Math.round(v * 10000) / 10000));
export const exactKey = row => locationKey(row) + priceKey(row);

export function compareSnapshots(current, previous) {
  const out = { available: false, reason: '비교 스냅샷이 없습니다.', unchanged: [], changed: [], candidates: [], added: [], unobserved: [] };
  if (!previous) return out;
  if (!validateSnapshot(current).complete || !validateSnapshot(previous).complete) {
    out.reason = '일부 수집 스냅샷은 신규·미관측 비교에서 제외합니다.';
    return out;
  }
  out.available = true; out.reason = '';
  const curr = current.items, prev = previous.items, usedC = new Set(), usedP = new Set();
  const byId = new Map(prev.flatMap((row, j) => row.articleId ? [[String(row.articleId), j]] : []));
  const pair = (field, i, j) => { usedC.add(i); usedP.add(j); out[field].push({ current: curr[i], previous: prev[j] }); };
  curr.forEach((row, i) => {
    const j = row.articleId ? byId.get(String(row.articleId)) : undefined;
    if (j !== undefined) pair(priceKey(row) === priceKey(prev[j]) ? 'unchanged' : 'changed', i, j);
  });
  curr.forEach((row, i) => {
    if (usedC.has(i)) return;
    const j = prev.findIndex((old, j) => !usedP.has(j) && !(row.articleId && old.articleId) && exactKey(row) === exactKey(old));
    if (j >= 0) pair('unchanged', i, j);
  });
  const cg = new Map(), pg = new Map();
  const add = (map, key, i) => map.set(key, [...(map.get(key) || []), i]);
  curr.forEach((r, i) => { if (!usedC.has(i)) add(cg, locationKey(r), i); });
  prev.forEach((r, j) => { if (!usedP.has(j)) add(pg, locationKey(r), j); });
  for (const [key, indices] of cg) {
    const olds = pg.get(key) || [];
    if (indices.length === 1 && olds.length === 1) {
      const i = indices[0], j = olds[0];
      if (!(curr[i].articleId && prev[j].articleId) && JSON.parse(key).every(k => k && k !== '-')) pair('candidates', i, j);
    }
  }
  out.added = curr.filter((_, i) => !usedC.has(i));
  out.unobserved = prev.filter((_, j) => !usedP.has(j));
  return out;
}

export function stats(rows) {
  const prices = rows.map(r => r.minPrice).sort((a, b) => a - b), n = prices.length;
  if (!n) return { count: 0, min: null, max: null, median: null, mean: null };
  return { count: n, min: prices[0], max: prices[n - 1], median: n % 2 ? prices[(n - 1) / 2] : (prices[n / 2 - 1] + prices[n / 2]) / 2, mean: prices.reduce((a, b) => a + b, 0) / n };
}

export function formatPrice(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const man = Math.round(value * 10000), eok = Math.floor(man / 10000), rest = man % 10000;
  return `${eok ? `${eok}억` : ''}${rest ? ` ${rest.toLocaleString('ko-KR')}만` : ''}`.trim() + ' 원';
}
export const formatEok = value => value == null ? '—' : new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 3 }).format(value);
export const priceRange = row => row.minPrice === row.maxPrice ? formatPrice(row.minPrice) : `${formatEok(row.minPrice)} ~ ${formatEok(row.maxPrice)}억 원`;

export function groupedRows(rows) {
  const groups = new Map();
  rows.forEach(row => {
    const key = exactKey(row);
    if (groups.has(key)) groups.get(key).quantity++;
    else groups.set(key, { ...row, quantity: 1 });
  });
  return [...groups.values()];
}

export function pickPrevious(entries, current) {
  return entries.find(e => e.date < current.date && e.complete) || null;
}

export function priceEok(value) {
  const text = value.replaceAll(',', '').replace(/\s/g, '').replace(/원$/, '');
  let number;
  if (text.includes('억')) {
    const m = text.match(/^(\d+(?:\.\d+)?)억(?:(\d+)만?)?$/);
    if (!m) throw new Error('호가 형식을 확인해 주세요.');
    number = Number(m[1]) + Number(m[2] || 0) / 10000;
  } else number = Number(text.replace(/만$/, '')) / 10000;
  if (!Number.isFinite(number) || number <= 0) throw new Error('호가 숫자를 확인해 주세요.');
  return Math.round(number * 10000) / 10000;
}

export function parseRaw(raw, date) {
  const countMatch = raw.match(/(?:전체\s*)?매물\s*([\d,]+)\s*(?:개|건)/) || raw.match(/매매\s*([\d,]+)\s*건/) || raw.match(/매매\s*([\d,]+)\s*(?=전세|월세|단기임대|전체매물|매물목록)/);
  if (!countMatch) throw new Error('원문 상단의 전체 매물 수(예: 매물 120개)를 함께 복사해 주세요.');
  const items = [];
  for (const chunk of raw.split(/(?=(?:수성범어더블유|수성범어W)\s*\d+동)/)) {
    const building = chunk.match(/^(?:수성범어더블유|수성범어W)\s*(\d+동)/);
    const price = chunk.match(/매매\s*(\d[\d,]*(?:\.\d+)?\s*억(?:\s*[\d,]+)?(?:\s*~\s*\d[\d,]*(?:\.\d+)?\s*억(?:\s*[\d,]+)?)?)/);
    const area = chunk.match(/(168\s*OB|180\s*OA|78\.36|84\.02)/i), floor = chunk.match(/([\d저중고]+)\s*\/\s*(\d+)\s*층/), direction = chunk.match(/(남서향|남동향|북서향|북동향|서향|동향|남향|북향)/);
    if (!building || !price || !area || !floor || !direction || !['101동', '102동', '103동', '105동'].includes(building[1])) continue;
    const parts = price[1].split('~'), confirm = chunk.match(/(?:확인매물|등록)\s*(\d{4}[.-]\d{2}[.-]\d{2})/), agency = chunk.match(/중개사\s*(\d+)곳/), desc = chunk.match(/[“"]([^”"]+)[”"]/);
    const floorNum = Number(floor[1]);
    items.push({ id: `text_${items.length + 1}`, articleId: null, dong: building[1], type: /180|84\.02/.test(area[1]) ? '84OA' : '78OB', floor: `${floor[1]}/${floor[2]}층`, direction: direction[1], floorCat: Number.isFinite(floorNum) && floor[1].match(/^\d+$/) ? floorNum <= 19 ? '저층' : floorNum <= 38 ? '중층' : '고층' : `${floor[1]}층`, minPrice: priceEok(parts[0]), maxPrice: priceEok(parts.at(-1)), priceRaw: price[1].trim(), confirmDate: confirm?.[1] || '', agencyCount: Number(agency?.[1] || 1), agencyInfo: agency ? `중개사 ${agency[1]}곳 공동등록` : '', desc: desc?.[1] || '', baseTag: '' });
  }
  const snapshot = { date, declaredCount: Number(countMatch[1].replaceAll(',', '')), count: items.length, items, source: { kind: 'manual-local' } };
  if (!validateSnapshot(snapshot).complete || !items.length) throw new Error(`원문 ${snapshot.declaredCount}건 / 확인 ${items.length}건입니다. 빠진 원문을 확인해 주세요.`);
  return snapshot;
}

export function csvCell(value) {
  let str = String(value ?? '');
  if (/^[=+\-@\t\r]/.test(str)) str = "'" + str;
  return `"${str.replaceAll('"', '""')}"`;
}

export function briefing(current, previous) {
  const diff = compareSnapshots(current, previous);
  const lines = [`범어W 오피스텔 호가 · ${current.date.slice(0, 10)}`, `관측 ${current.items.length}건 / 원문 ${current.declaredCount}건`, current.source?.kind === 'naver-live' ? '네이버 자동 수집' : '제공·수동 입력 자료 (실시간 수집 아님)'];
  for (const area of ['78OB', '84OA']) {
    const s = stats(current.items.filter(r => r.type === area));
    if (s.count) lines.push(`${area} ${s.count}건 · 최저 ${formatEok(s.min)}억 · 중앙값 ${formatEok(s.median)}억`);
  }
  if (diff.available) {
    lines.push(`비교일 ${previous.date.slice(0, 10)}`, `추가 관측 ${diff.added.length} · 미관측 ${diff.unobserved.length}`, `번호 확인 호가 변동 ${diff.changed.length} · 조건 기준 변동 후보 ${diff.candidates.length}`);
  } else lines.push(diff.reason);
  lines.push('호가는 매도 희망가입니다. 미관측은 거래 완료를 뜻하지 않습니다.', '범위 호가의 통계는 최저값 기준입니다.');
  return lines.join('\n');
}
