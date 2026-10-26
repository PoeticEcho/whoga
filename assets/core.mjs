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
    if ((s.complexNo||'140635')==='140635' && (!['78OB', '84OA'].includes(row.type) || !['101동', '102동', '103동', '105동'].includes(row.dong))) throw new Error('범어W 오피스텔 대상 동·타입을 확인해 주세요.');
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
  if ((current.complexNo||'140635')!==(previous.complexNo||'140635')) { out.reason='서로 다른 단지는 비교하지 않습니다.'; return out; }
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

const REPORT_DONGS = ['101동', '102동', '103동', '105동'];
const REPORT_TYPES = ['78OB', '84OA'];
const reportTypes = s => (s.complexNo||'140635')==='140635' ? REPORT_TYPES : [...new Set(s.items.map(r=>r.type))].sort();
const reportDongs = s => (s.complexNo||'140635')==='140635' ? REPORT_DONGS : [...new Set(s.items.map(r=>r.dong))].sort();
const oneLine = value => String(value ?? '').replace(/\s+/g, ' ').trim();
export const reportEok = (value, minimumFractionDigits = 1) => new Intl.NumberFormat('en-US', { useGrouping: false, minimumFractionDigits, maximumFractionDigits: 4 }).format(value);
const reportRange = (row, digits = 1) => row.minPrice === row.maxPrice ? `${reportEok(row.minPrice, digits)}억` : `${reportEok(row.minPrice, digits)}~${reportEok(row.maxPrice, digits)}억`;
export const compactFloor = row => oneLine(row.floor).split('/')[0].replace(/층$/, '') + '층';

export function observationLabel(snapshot) {
  const day = snapshot.date.slice(0, 10);
  const stamp = snapshot.observation?.observedAt || snapshot.collectedAt;
  const date = stamp && /(?:Z|[+-]\d{2}:\d{2})$/.test(stamp) ? new Date(stamp) : null;
  const parts = date && !Number.isNaN(date.getTime()) ? Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(date).map(p => [p.type, p.value])) : null;
  const weekday = '일월화수목금토'[new Date(day + 'T12:00:00Z').getUTCDay()];
  const label = `📅 ${Number(day.slice(5, 7))}/${Number(day.slice(8, 10))} (${weekday})`;
  if (!parts || `${parts.year}-${parts.month}-${parts.day}` !== day) return `${label} 기준 · 수집 시각 미기록`;
  const hour = Number(parts.hour), minute = Number(parts.minute);
  return `${label} ${hour < 12 ? '오전' : '오후'} ${hour % 12 || 12}시${minute ? ` ${minute}분` : ''} 기준 (KST)`;
}

function marketLines(snapshot) {
  const quality = validateSnapshot(snapshot);
  const lines = ['🚨 [시장 핵심 요약]', `${quality.complete ? '전체' : '일부'} 관측: ${snapshot.items.length}건 (원문 ${snapshot.declaredCount}건${quality.complete ? ' · 수량 일치' : ' · 부분 자료'})`];
  if (snapshot.source?.kind !== 'naver-live') lines.push('제공·수동 입력 자료 (실시간 수집 아님)');
  for (const type of reportTypes(snapshot)) {
    const s = stats(snapshot.items.filter(row => row.type === type));
    lines.push(s.count ? `${type} (${s.count}건): ${quality.complete ? '최저' : '관측 최저'} ${reportEok(s.min)}억 ｜ 중앙값 ${reportEok(s.median)}억` : `${type}: 관측 없음`);
  }
  return lines;
}

export function morningBriefing(snapshot) {
  const lines = [`[${snapshot.complexName||'범어W 오피스텔'} 모닝 브리핑]`, observationLabel(snapshot), '', ...marketLines(snapshot), '', '📊 [동별 호가 범위]'];
  const most = Math.max(0, ...reportDongs(snapshot).map(dong => snapshot.items.filter(row => row.dong === dong).length));
  for (const dong of reportDongs(snapshot)) {
    const rows = snapshot.items.filter(row => row.dong === dong);
    if (!rows.length) continue;
    lines.push('', `${dong} (총 ${rows.length}건${rows.length === most ? ' · 관측 최다' : ''})`);
    for (const type of reportTypes(snapshot)) {
      const group = rows.filter(row => row.type === type), s = stats(group);
      lines.push(s.count ? `${type}: ${reportEok(s.min)}억 ~ ${reportEok(Math.max(...group.map(row => row.maxPrice)))}억 (중앙값 ${reportEok(s.median)}억)` : `${type}: 관측 없음`);
    }
  }
  lines.push('', '※ 호가 범위는 최저~최고, 중앙값은 각 매물의 최저 호가 기준입니다.');
  return lines.join('\n');
}

function changeRow(row) {
  return `${row.dong} ${row.type} (${compactFloor(row)} / ${oneLine(row.direction)}) : ${reportRange(row)}${row.articleId ? ` · 매물번호 ${oneLine(row.articleId)}` : ''}`;
}

function changePair(pair) {
  const row = pair.current, old = pair.previous, deltas = [];
  for (const [key, label] of [['minPrice', '하한'], ['maxPrice', '상한']]) {
    const delta = Math.round((row[key] - old[key]) * 10000) / 10000;
    if (delta) deltas.push(`${label} ${reportEok(Math.abs(delta))}억 ${delta < 0 ? '하락 ↓' : '상승 ↑'}`);
  }
  return `${row.dong} ${row.type} (${compactFloor(row)} / ${oneLine(row.direction)}) : ${reportRange(old)} ➔ ${reportRange(row)}${deltas.length ? ` (${deltas.join(' · ')})` : ''}${row.articleId ? ` · 매물번호 ${oneLine(row.articleId)}` : ''}`;
}

export function changeReport(current, previous) {
  const diff = compareSnapshots(current, previous), lines = ['🔔 [일일 변동 리포트]'];
  if (!diff.available) return [...lines, diff.reason, '', '※ 미관측은 거래 완료를 뜻하지 않습니다. 조건 일치 후보는 동일 호실 미확인입니다.'].join('\n');
  const gap = (Date.parse(current.date.slice(0, 10)) - Date.parse(previous.date.slice(0, 10))) / 86400000;
  const base = gap === 1 ? '전일 대비' : gap === 0 ? '같은 날 비교 자료 대비' : `비교일 ${previous.date.slice(0, 10)} 대비`;
  const delta = current.items.length - previous.items.length;
  lines.push(`(${base} 총 관측: ${previous.items.length}건 ➔ ${current.items.length}건 [${delta > 0 ? '+' : ''}${delta}건])`);
  for (const [title, rows, pair] of [['🔄 [호가 변동 · 매물번호 일치]', diff.changed, true], ['🟠 [호가 변동 후보 · 조건 일치]', diff.candidates, true], ['🟢 [추가 관측]', diff.added, false], ['🔴 [미관측]', diff.unobserved, false]]) {
    lines.push('', `${title} (총 ${rows.length}건)`, ...(rows.length ? rows.map(pair ? changePair : changeRow) : ['없음']));
  }
  lines.push('', '※ 미관측은 거래 완료를 뜻하지 않습니다. 조건 일치 후보는 동일 호실 미확인입니다.');
  return lines.join('\n');
}

// Hangul occupies two monospace cells; pad by display width rather than JS length.
function textCell(value, width) {
  const text = oneLine(String(value));
  const cells = [...text].reduce((sum, char) => sum + (/[^\u0000-\u007f]/.test(char) ? 2 : 1), 0);
  return text + ' '.repeat(Math.max(0, width - cells));
}

export function listingLine(row) {
  const count = Number.isInteger(row.agencyCount) && row.agencyCount > 0 ? `${row.agencyCount}곳` : '—';
  return `${textCell(row.type, 6)}${textCell(compactFloor(row), 6)}${textCell(reportRange(row, 2), 15)}${count}`;
}

export function plainListings(snapshot, rows = snapshot.items, order = 'priceAsc') {
  const subset = rows.length !== snapshot.items.length;
  const labels = { priceAsc: '최저 호가순', priceDesc: '최저 호가 역순', confirmDesc: '확인일 최신순', agencyDesc: '공동중개 많은순' };
  const sorted = [...rows].sort((a, b) => order === 'priceDesc' ? b.minPrice - a.minPrice : order === 'confirmDesc' ? String(b.confirmDate || '').localeCompare(String(a.confirmDate || '')) : order === 'agencyDesc' ? (b.agencyCount || 0) - (a.agencyCount || 0) : a.minPrice - b.minPrice);
  const quality = validateSnapshot(snapshot);
  const lines = [`[${snapshot.complexName||'범어W'} 매물 목록]`, observationLabel(snapshot), `${quality.complete ? '전체 관측' : '일부 관측'} ${snapshot.items.length}건 / 원문 ${snapshot.declaredCount}건`, ''];
  for (const type of reportTypes(snapshot)) {
    const summary = stats(snapshot.items.filter(row => row.type === type));
    if (summary.count) lines.push(`${type}  ${summary.count}건  ${quality.complete ? '최저' : '관측 최저'} ${reportEok(summary.min)}억  중앙 ${reportEok(summary.median)}억`);
  }
  lines.push('', `동·타입별 ${labels[order] || labels.priceAsc}`);
  if (subset) lines.push(`필터 결과: ${rows.length}건 / 전체 관측 ${snapshot.items.length}건 (위 요약은 기준 자료 전체)`);
  if (!rows.length) lines.push('', '조건에 맞는 매물이 없습니다.');
  for (const dong of reportDongs(snapshot)) {
    const group = sorted.filter(row => row.dong === dong);
    if (!group.length) continue;
    lines.push('', `${dong} · ${subset ? '필터 ' : ''}${group.length}건`, `${textCell('타입', 6)}${textCell('층', 6)}${textCell('호가', 15)}중개`);
    for (const type of reportTypes(snapshot)) {
      for (const row of group.filter(row => row.type === type)) lines.push(listingLine(row));
    }
  }
  lines.push('', '※ 중개 수는 세대 수가 아닙니다.', '같은 조건도 원본 행별로 표시합니다.');
  return lines.join('\n');
}

export function briefing(current, previous, mode = 'all') {
  if (mode === 'summary') return morningBriefing(current);
  if (mode === 'changes') return `[${current.complexName||'범어W 오피스텔'} 변동 리포트]\n${observationLabel(current)}\n\n${changeReport(current, previous)}`;
  if (mode === 'listings') return plainListings(current);
  return `${morningBriefing(current)}\n\n${changeReport(current, previous)}`;
}
