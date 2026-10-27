import { validateSnapshot, compareSnapshots, stats, formatPrice, formatEok, priceRange, groupedRows, pickPrevious, parseRaw, csvCell, briefing, plainListings } from './core.mjs?v=3.2.0';
import { saveSnapshot, loadSharedIndex, loadSharedSnapshot, sortEntries } from './repository.mjs?v=3.2.0';

const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
let DONGS = ['101동', '102동', '103동', '105동'];
let TYPES = ['78OB', '84OA'];
let LOCAL_KEY = 'beomeoW_pages_v1_manual';
const state = { entries: [], data: new Map(), local: {}, status: {}, current: null, previous: null, diff: null, pending: 0, filtered: [], config: {}, serverRef: null, saving: false };
let githubToken = '';
const complexNo = new URL(document.baseURI).searchParams.get('complex') || '140635';
const dataPath = complexNo==='140635' ? 'data' : /^\d{1,12}$/.test(complexNo) ? 'data/complexes/'+complexNo : 'invalid';
if(complexNo!=='140635')LOCAL_KEY += '_'+complexNo;
const todayKst = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const dateText = value => value ? String(value).replace('T', ' ').replace(/\+09:00$/, ' KST') : '기록 없음';
const empty = text => `<div class="empty">${escape(text)}</div>`;
let toastTimer;

function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4500);
}

async function getJson(path) {
  const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 16000);
  try {
    const response = await fetch(new URL(path, document.baseURI), { cache: 'no-store', signal: abort.signal });
    if (!response.ok) throw new Error(`자료 요청 실패 (${response.status})`);
    return await response.json();
  } finally { clearTimeout(timer); }
}

async function snapshotFor(id) {
  if (!id) return null;
  if (state.data.has(id)) return state.data.get(id);
  const entry = state.entries.find(e => e.id === id);
  if (!entry || !/^[\w가-힣.-]+\.json$/.test(entry.file)) throw new Error('스냅샷 경로를 확인해 주세요.');
  let snap;
  if (state.serverRef) snap = await loadSharedSnapshot(entry.file, state.serverRef);
  else snap = await getJson(dataPath+'/' + entry.file);
  validateSnapshot(snap);
  if ((snap.complexNo||'140635')!==complexNo) throw Error('단지 자료가 일치하지 않습니다.');
  state.data.set(id, snap);
  return snap;
}

function selectOptions() {
  const selected = $('snapshotSelect').value;
  $('snapshotSelect').innerHTML = state.entries.map(e => `<option value="${escape(e.id)}">${escape(e.label)}${e.local ? ' · 서버 미저장' : ''}${e.complete ? '' : ' · 일부 자료'}</option>`).join('');
  if (state.entries.some(e => e.id === selected)) $('snapshotSelect').value = selected;
  $('snapshotSelect').disabled = !state.entries.length;
  compareOptions();
}

function compareOptions(preferred) {
  const current = state.entries.find(e => e.id === $('snapshotSelect').value);
  const old = preferred ?? $('compareSelect').value;
  const entries = state.entries.filter(e => e.id !== current?.id && e.date <= (current?.date || ''));
  $('compareSelect').innerHTML = '<option value="">비교 없음</option>' + entries.map(e => `<option value="${escape(e.id)}">${escape(e.label)}${e.local ? ' · 이 기기' : ''}${e.complete ? '' : ' · 일부 자료'}</option>`).join('');
  $('compareSelect').value = entries.some(e => e.id === old) ? old : (current && pickPrevious(entries, current)?.id) || '';
  $('compareSelect').disabled = !current;
}

function renderBanner() {
  const snap = state.current, entry = state.entries.find(e => e.id === $('snapshotSelect').value);
  if (!snap) return;
  const source = snap.source?.kind || 'provided', complete = validateSnapshot(snap).complete;
  const pieces = [], banner = $('statusBanner');
  let title, tone = '';
  if (entry?.local) { title = '분석 완료 · 서버에 아직 저장하지 않은 자료입니다.'; tone = 'warn'; pieces.push('수동 자료의 ‘서버에 저장’을 눌러 누적자료로 등록하세요.'); }
  else if (source === 'manual') { title = '서버에 저장된 수동 자료입니다.'; pieces.push('날짜별 누적자료로 보존되며 다른 기기에서도 조회할 수 있습니다.'); }
  else if (state.status.lastAttemptResult === 'failed') { title = '최근 수집에 실패했습니다. 저장된 자료를 표시합니다.'; tone = 'error'; pieces.push(state.status.message || '수집 실행 기록을 확인해 주세요.'); }
  else if (source !== 'naver-live') { title = '제공된 기준 자료를 보고 있습니다.'; tone = 'warn'; pieces.push('네이버 자동 수집 성공은 아직 확인되지 않았습니다.'); }
  else { title = `자동 수집 자료 · ${snap.date.slice(0, 10)}`; }
  if (!complete) { tone = 'warn'; pieces.push(`원문 ${snap.declaredCount}건 중 ${snap.items.length}건만 있는 자료입니다. 신규·미관측 비교에서 제외합니다.`); }
  else pieces.push(`원문 ${snap.declaredCount}건 / 확인 ${snap.items.length}건 · 수량 일치`);
  if (source === 'naver-live' && snap.date.slice(0, 10) < todayKst()) { tone = tone || 'warn'; pieces.push('오늘 자료가 아닙니다. 기준일을 확인하세요.'); }
  if (snap.collectedAt) pieces.push(`자료 입력·수집 시각 ${dateText(snap.collectedAt)}`);
  if (state.status.lastAttemptAt && !entry?.local && (!snap.collectedAt || Date.parse(state.status.lastAttemptAt)>=Date.parse(snap.collectedAt))) pieces.push(`최근 시도 ${dateText(state.status.lastAttemptAt)}`);
  banner.className = 'status-banner ' + tone;
  banner.innerHTML = `<span class="status-dot"></span><div><strong>${escape(title)}</strong><p>${pieces.map(escape).join(' · ')}</p></div>`;
}

async function loadSelection() {
  $('selectionInfo').textContent='선택한 시점의 자료를 확인하고 있습니다.';
  const op = ++state.pending;
  $('saveServerBtn').disabled = true;
  $('content').setAttribute('aria-busy', 'true');
  try {
    const [current, previous] = await Promise.all([snapshotFor($('snapshotSelect').value), snapshotFor($('compareSelect').value)]);
    if (op !== state.pending) return;
    DONGS=[...new Set(current.items.map(r=>r.dong))].sort((a,b)=>a.localeCompare(b,'ko',{numeric:true}));
    TYPES=[...new Set(current.items.map(r=>r.type))].sort();
    for(const [id,values,label] of [['dongFilter',DONGS,'전체 동'],['typeFilter',TYPES,'전체 타입']]) { const old=$(id).value;$(id).innerHTML='<option value="">'+label+'</option>'+values.map(v=>`<option>${escape(v)}</option>`).join('');if(values.includes(old))$(id).value=old; }
    state.current = current; state.previous = previous; state.diff = compareSnapshots(current, previous);
    renderAll();
    $('exportJsonBtn').disabled = false;
  } catch (error) {
    if (op !== state.pending) return;
    // 선택한 날짜와 예전 자료가 어긋나지 않도록 실패한 선택은 표시하지 않습니다.
    state.current = null; state.previous = null; $('selectionInfo').textContent='자료를 확인할 수 없습니다. 다른 시점을 선택하거나 새로고침하세요.';
    $('content').hidden = false;
    for(const panel of document.querySelectorAll('[role=tabpanel]')) panel.hidden=panel.id!=='panel-manage';
    document.querySelectorAll('[role=tab]').forEach(t=>{t.setAttribute('aria-selected',String(t.id==='tab-manage'));t.tabIndex=t.id==='tab-manage'?0:-1;}); $('exportJsonBtn').disabled = true;
    $('statusBanner').className = 'status-banner error';
    $('statusBanner').innerHTML = `<span class="status-dot"></span><div><strong>선택한 자료를 불러오지 못했습니다.</strong><p>${escape(error.message)} · 새로고침하거나 다른 날짜를 선택해 주세요.</p></div>`;
  } finally { if (op === state.pending) { $('content').setAttribute('aria-busy', 'false'); renderSaveState(); } }
}

function renderSaveState() {
  const entry = state.entries.find(e => e.id === $('snapshotSelect').value);
  $('saveServerBtn').disabled = state.saving || !state.current || !entry?.local;
  $('saveServerBtn').textContent = state.saving ? '저장 확인 중…' : '서버에 저장';
  $('pendingSaveCount').textContent = `서버 미저장 ${Object.keys(state.local).length}개`;
}

async function saveCurrentToServer() {
  if (state.saving) return;
  const id = $('snapshotSelect').value, snapshot = state.local[id];
  if (!snapshot || !state.current) return;
  const typed = $('githubToken').value.trim();
  if (typed) githubToken = typed;
  $('githubToken').value = '';
  if (!githubToken) {
    $('githubSetup').open = true; $('githubToken').focus();
    $('serverSaveStatus').textContent = 'GitHub 연결 토큰을 입력한 뒤 서버에 저장을 눌러 주세요.';
    return;
  }
  state.saving = true; renderSaveState();
  for (const control of ['refreshBtn', 'snapshotSelect', 'compareSelect', 'clearLocalBtn', 'parseRawBtn', 'jsonInput']) $(control).disabled = true;
  $('serverSaveLink').hidden = true;
  try {
    const result = await saveSnapshot(snapshot, { token: githubToken, onProgress: message => { $('serverSaveStatus').textContent = message; } });
    // Remove a local draft only after its server file and index were read back.
    delete state.local[id]; state.data.delete(id); persistLocal();
    state.serverRef = result.ref;
    state.entries = sortEntries([...result.index.snapshots, ...state.entries.filter(e => e.local && e.id !== id)]);
    state.data.set(result.id, result.snapshot);
    selectOptions(); $('snapshotSelect').value = result.id; compareOptions('');
    await loadSelection();
    $('serverSaveStatus').textContent = `${result.duplicate ? '이미 저장된 동일 자료를 확인했습니다.' : '서버 저장 완료.'} ${result.snapshot.date} · ${result.snapshot.items.length}건 재조회 확인. 다른 기기의 새로고침에서도 조회할 수 있습니다.`;
    $('githubConnectionStatus').textContent = 'GitHub 연결 확인 · 이 탭에서 유지';
    $('githubSetup').open = false;
    $('serverSaveLink').href = result.commitUrl; $('serverSaveLink').hidden = false;
    toast('서버 저장과 재조회 확인을 완료했습니다.');
  } catch (error) {
    $('serverSaveStatus').textContent = `저장 미완료 · ${error.message} 기기 자료는 그대로 남아 있습니다.`;
    if ([401, 403, 404].includes(error.status)) { githubToken = ''; $('githubSetup').open = true; $('githubConnectionStatus').textContent = 'GitHub 연결을 다시 확인해 주세요.'; }
    toast('서버 저장을 완료하지 못했습니다. 아래 상태를 확인해 주세요.');
  } finally {
    state.saving = false;
    for (const control of ['refreshBtn', 'snapshotSelect', 'compareSelect', 'clearLocalBtn', 'parseRawBtn', 'jsonInput']) $(control).disabled = false;
    renderSaveState();
  }
}

function renderAll() {
  if (!state.current) return;
  const snap=state.current;
  $('selectionInfo').textContent=[snap.complexName||state.config.complexName||('단지 '+complexNo),`${snap.items.length}개 매물 카드`,snap.source?.articleCount?`중개 등록 ${snap.source.articleCount}건`:null,snap.collectedAt?'수집 '+dateText(snap.collectedAt):'수집 시각 미기록'].filter(Boolean).join(' · ');
  $('content').hidden = false;
  renderBanner(); renderOverview(); renderListings(); renderStats();
  renderBriefing();
  $('listTabCount').textContent = state.current.items.length;
}

function renderOverview() {
  const current = state.current, diff = state.diff, previous = state.previous;
  const net = diff.available ? current.items.length - previous.items.length : null;
  const cards = [
    ['전체 관측', current.items.length, '건', `원문 ${current.declaredCount}건 · 관측 건수 기준`, 'blue'],
    ['비교일 대비', net === null ? '—' : `${net > 0 ? '+' : ''}${net}`, net === null ? '' : '건', diff.available ? `${previous.date.slice(0, 10)} 대비 순증감` : diff.reason, ''],
    ['매물번호 확인 변동', diff.available ? diff.changed.length : '—', '건', '같은 번호의 최소·최대 호가 변화', 'mint'],
    ['조건 기준 변동 후보', diff.available ? diff.candidates.length : '—', '건', '같은 호수인지 추가 확인 필요', 'amber'],
  ];
  $('kpiGrid').innerHTML = cards.map(([label, value, unit, note, cls]) => `<article class="kpi ${cls}"><p>${escape(label)}</p><strong>${escape(value)}<span class="unit">${unit}</span></strong><small>${escape(note)}</small></article>`).join('');
  $('typeCards').innerHTML = TYPES.map(area => {
    const s = stats(current.items.filter(r => r.type === area));
    return `<article class="type-card"><h3>${escape(area)}</h3><div class="type-min">${formatEok(s.min)}<span>억 원부터</span></div><div class="type-meta"><div><span>관측 건수</span>${s.count}건</div><div><span>중앙값</span>${formatEok(s.median)}억</div><div><span>평균</span>${formatEok(s.mean)}억</div><div><span>최고</span>${formatEok(s.max)}억</div></div></article>`;
  }).join('');
  const max = Math.max(1, ...current.items.map(r => r.minPrice));
  $('dongChart').innerHTML = DONGS.map(dong => `<div class="dong-row"><span>${escape(dong)}</span><div class="dong-bars">${TYPES.map((area, n) => {
    const s = stats(current.items.filter(r => r.dong === dong && r.type === area));
    return `<div class="price-bar ${n ? 'mint' : ''}"><i style="width:${s.min === null ? 0 : s.min / max * 100}%"></i><span>${escape(area)} · ${s.count ? formatEok(s.min) + '억' : '관측 없음'}</span></div>`;
  }).join('')}</div></div>`).join('') + '<div class="chart-legend">'+TYPES.map(t=>'<span>'+escape(t)+'</span>').join('')+'</div>';
  $('compareLabel').textContent = previous ? `${previous.date} → ${current.date}` : '비교 자료 없음';
  $('diffNote').textContent = diff.available ? '추가·미관측은 목록에서 관측한 변화입니다. 매물번호가 없는 자료의 변동 후보는 같은 호수인지 확인해야 합니다.' : diff.reason;
  const columns = [['번호 확인 변동', diff.changed, true], ['변동 후보', diff.candidates, true], ['추가 관측', diff.added, false], ['미관측', diff.unobserved, false]];
  $('diffCards').innerHTML = columns.map(([label, items, isPair]) => `<section class="diff-column"><h3 class="diff-title">${label}<span>${diff.available ? items.length + '건' : '—'}</span></h3><div class="diff-list">${!diff.available ? empty('비교할 수 없습니다.') : items.length ? items.map(pair => {
    const row = isPair ? pair.current : pair;
    return `<article class="diff-item"><strong>${escape(row.dong)} · ${escape(row.type)}</strong><p>${escape(row.floor)} · ${escape(row.direction)}</p><span class="price">${isPair ? escape(priceRange(pair.previous)) + ' → ' : ''}${escape(priceRange(row))}</span>${row.articleId ? `<p>매물번호 ${escape(row.articleId)}</p>` : ''}</article>`;
  }).join('') : empty('관측된 변화가 없습니다.')}</div></section>`).join('');
}

function annotatedRows() {
  const marks = new Map(), diff = state.diff;
  for (const [field, status] of [['unchanged', 'SAME'], ['changed', 'CHANGED'], ['candidates', 'CANDIDATE']]) for (const p of diff[field]) marks.set(p.current, status);
  for (const row of diff.added) marks.set(row, 'OBSERVED');
  return state.current.items.map(row => ({ ...row, status: diff.available ? marks.get(row) || '' : '' }));
}

function renderListings() {
  if (!state.current) return;
  const search = $('searchInput').value.trim().toLocaleLowerCase('ko-KR');
  let rows = annotatedRows().filter(r => (!$('dongFilter').value || r.dong === $('dongFilter').value) && (!$('typeFilter').value || r.type === $('typeFilter').value) && (!$('floorFilter').value || r.floorCat === $('floorFilter').value) && (!$('stateFilter').value || r.status === $('stateFilter').value) && (!search || ['dong', 'type', 'floor', 'direction', 'agencyInfo', 'desc'].some(k => String(r[k] || '').toLocaleLowerCase('ko-KR').includes(search))));
  const order = $('sortSelect').value;
  rows.sort((a, b) => order === 'priceDesc' ? b.minPrice - a.minPrice : order === 'confirmDesc' ? String(b.confirmDate).localeCompare(String(a.confirmDate)) : order === 'agencyDesc' ? (b.agencyCount || 0) - (a.agencyCount || 0) : a.minPrice - b.minPrice);
  state.filtered = rows;
  const textView = $('listingView').value === 'text';
  const grouped = !textView && $('groupToggle').checked;
  const visible = grouped ? groupedRows(rows) : rows;
  $('groupToggle').disabled = textView;
  $('listingGrid').hidden = textView;
  $('listingTextPanel').hidden = !textView;
  $('listingText').textContent = plainListings(state.current, rows, order, $('showAgency').checked);
  $('listingDetails').innerHTML = rows.map(row => `<details class="listing-detail-row"><summary>${escape(row.dong)} · ${escape(row.type)} · ${escape(row.floor)} · ${escape(priceRange(row))}</summary><p>${escape(row.direction)} · 확인 ${escape(row.confirmDate || '미표기')}</p><p>${escape(row.agencyInfo || '중개사명 미표기')}${row.articleId ? ` · 매물번호 ${escape(row.articleId)}` : ''}</p>${row.desc ? `<p>${escape(row.desc)}</p>` : ''}</details>`).join('') || empty('조건에 맞는 매물이 없습니다.');
  $('groupNotice').hidden = !grouped;
  $('filterCount').textContent = `${rows.length}건 / 전체 ${state.current.items.length}건${grouped ? ` · ${visible.length}개 조건 묶음` : ''}`;
  const labels = { OBSERVED: '추가 관측', CHANGED: '번호 확인 변동', CANDIDATE: '변동 후보', SAME: '같은 조건 유지' };
  $('listingGrid').innerHTML = visible.length ? visible.map(row => `<article class="listing-card"><div class="listing-head"><strong>${escape(row.dong)} · ${escape(row.type)}</strong>${row.status && !grouped ? `<span class="badge ${row.status}">${labels[row.status]}</span>` : ''}</div><div class="listing-price">${escape(priceRange(row))}</div><p class="listing-meta">${escape(row.floor)} · ${escape(row.direction)}</p>${grouped ? `<span class="listing-count">같은 조건 ${row.quantity}건</span>` : ''}${row.desc ? `<p class="listing-desc">${escape(row.desc)}</p>` : ''}<div class="listing-foot"><span>${escape(row.agencyInfo || (row.agencyCount > 1 ? `공동중개 ${row.agencyCount}곳` : '중개 정보 없음'))}</span><span>확인 ${escape(row.confirmDate || '미표기')}</span></div>${row.articleId && !grouped ? `<p class="listing-desc">매물번호 ${escape(row.articleId)}</p>` : ''}</article>`).join('') : empty('조건에 맞는 매물이 없습니다. 필터를 초기화해 보세요.');
}

function renderBriefing() {
  if (state.current) $('briefingText').textContent = briefing(state.current, state.previous, $('briefingFormat').value || 'all');
}

async function copyText(id, message) {
  if (!state.current) return;
  try { await navigator.clipboard.writeText($(id).textContent); toast(message); }
  catch { const range = document.createRange(); range.selectNodeContents($(id)); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); toast('복사할 내용을 선택했습니다. 길게 누르거나 Ctrl+C로 복사하세요.'); }
}

function renderStats() {
  const rows = state.current.items;
  $('statsRows').innerHTML = DONGS.flatMap(dong => TYPES.map(area => {
    const s = stats(rows.filter(r => r.dong === dong && r.type === area));
    return `<tr><td>${escape(dong)}</td><td>${escape(area)}</td><td>${s.count}</td><td>${formatEok(s.min)}</td><td>${formatEok(s.median)}</td><td>${formatEok(s.mean)}</td><td>${formatEok(s.max)}</td></tr>`;
  })).join('');
  const ranges = [[0, 5, '5억 미만'], [5, 6, '5 ~ 6억'], [6, 7, '6 ~ 7억'], [7, 8, '7 ~ 8억'], [8, 9, '8 ~ 9억'], [9, 10, '9 ~ 10억'], [10, Infinity, '10억 이상']];
  const bands = ranges.map(([low, high, label]) => ({ label, values: TYPES.map(type => rows.filter(r => r.type === type && r.minPrice >= low && r.minPrice < high).length) }));
  const max = Math.max(1, ...bands.map(b => b.values.reduce((a,v)=>a+v,0)));
  $('bandChart').innerHTML = bands.map(b => `<div class="band-row"><span>${b.label}</span><div class="band-track" aria-label="${b.values.reduce((a,v)=>a+v,0)}건">${b.values.map(v=>`<i style="width:${v/max*100}%"></i>`).join('')}</div><strong>${b.values.reduce((a,v)=>a+v,0)}건</strong></div>`).join('');
  $('historyList').innerHTML = state.entries.map(e => `<div class="history-row"><strong>${escape(e.label)}</strong><span>${e.count} / 원문 ${e.declaredCount}건</span><span class="${e.complete ? 'good-text' : 'warn-text'}">${e.complete ? '수량 일치' : '일부 자료'}</span><span class="muted">${e.local ? '서버 미저장 · 이 기기' : e.sourceKind === 'naver-live' ? '네이버 자동 수집' : e.sourceKind === 'manual' ? '서버 저장 · 수동 입력' : '첨부 기준 자료'}</span></div>`).join('');
}

function download(name, type, data) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement('a'); a.href = url; a.download = name; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function persistLocal() {
  try { localStorage.setItem(LOCAL_KEY, JSON.stringify(state.local)); return true; }
  catch { toast('기기 저장 공간이 부족해 이번 화면에서만 표시합니다. JSON을 내려받아 보관하세요.'); return false; }
}

function addLocal(data) {
  const snapshots = Array.isArray(data?.items) ? [data] : Object.values(data || {});
  if (!snapshots.length || snapshots.length > 60) throw new Error('날짜별 스냅샷 또는 최대 60개의 스냅샷 모음이 필요합니다.');
  snapshots.forEach(s => { validateSnapshot(s); if (s.items.length > 5000) throw new Error('한 스냅샷은 최대 5,000건까지 지원합니다.'); });
  const prefix = globalThis.crypto.randomUUID();
  let selected;
  snapshots.forEach((s, n) => {
    const id = `local-${prefix}-${n}`, snapshot = { ...s, source: { ...s.source, kind: 'manual-local' } };
    state.local[id] = snapshot; state.data.set(id, snapshot);
    state.entries.unshift({ id, date: s.date.slice(0, 10), label: s.label || s.date, count: s.items.length, declaredCount: s.declaredCount, complete: validateSnapshot(s).complete, local: true });
    selected = selected || id;
  });
  persistLocal(); selectOptions(); $('snapshotSelect').value = selected; compareOptions(''); loadSelection();
  $('importResult').textContent = `${snapshots.length}개 자료 분석 완료. 선택한 자료를 확인하고 서버에 저장을 눌러 주세요.`;
  $('serverSaveStatus').textContent = '분석 결과는 기기에 보관 중입니다. 서버에 저장하면 누적자료로 사용할 수 있습니다.';
  $('serverSaveLink').hidden = true;
}

async function initialize() {
  $('openImportBtn').hidden=complexNo!=='140635';
  if (state.saving) return;
  $('refreshBtn').disabled = true; $('refreshBtn').textContent = '확인 중…';
  try {
    const [shared, status, config, plan] = await Promise.all([
      complexNo==='140635' ? loadSharedIndex().catch(async () => ({index:await getJson(dataPath+'/index.json'),ref:null})) : getJson(dataPath+'/index.json').then(index=>({index,ref:null})),
      getJson(dataPath+'/status.json'), getJson('config.json'),getJson('collection-plan.json').catch(()=>null)]);
    const index = shared.index; state.serverRef = shared.ref;
    if (!Array.isArray(index.snapshots) || !index.snapshots.length) throw new Error('스냅샷 목록이 없습니다.');
    if(complexNo!=='140635'){ config.complexId=complexNo;config.sourceUrl='https://fin.land.naver.com/complexes/'+complexNo; }
    state.data.clear(); state.entries = index.snapshots; state.status = status; state.config = config;
    state.local = {};
    try { const saved = JSON.parse(localStorage.getItem(LOCAL_KEY) || '{}'); for (const [id, snap] of Object.entries(saved)) { validateSnapshot(snap); state.local[id] = snap; } } catch { /* 손상된 기기 자료가 공개 자료 조회를 막지 않습니다. */ }
    for (const [id, snap] of Object.entries(state.local)) {
      state.data.set(id, snap);
      state.entries.push({ id, date: snap.date.slice(0, 10), label: snap.label || snap.date, count: snap.items.length, declaredCount: snap.declaredCount, complete: validateSnapshot(snap).complete, local: true });
    }
    $('scheduleLabel').textContent = plan ? (plan.enabled ? `${plan.intervalHours}시간 간격 · ${plan.targets.length}개 단지 순환 예약` : '순환 수집 예약 꺼짐') : complexNo==='140635' ? config.dailyTimeLabel : 'NAS 순환 수집 · 마지막 수집 시각 확인';
    if (/^https:\/\/fin\.land\.naver\.com\//.test(config.sourceUrl || '')) $('sourceLink').href = config.sourceUrl;
    selectOptions(); $('snapshotSelect').value = index.latest || state.entries[0].id; compareOptions('');
    await loadSelection();
  } catch (error) {
    state.current = null; state.previous = null; $('selectionInfo').textContent='자료를 확인할 수 없습니다. 다른 시점을 선택하거나 새로고침하세요.'; $('exportJsonBtn').disabled = true;
    $('content').hidden = false;
    for(const panel of document.querySelectorAll('[role=tabpanel]')) panel.hidden=panel.id!=='panel-manage';
    document.querySelectorAll('[role=tab]').forEach(t=>{t.setAttribute('aria-selected',String(t.id==='tab-manage'));t.tabIndex=t.id==='tab-manage'?0:-1;});
    $('statusBanner').className = 'status-banner error';
    $('statusBanner').innerHTML = `<span class="status-dot"></span><div><strong>자료를 불러오지 못했습니다.</strong><p>${escape(error.message)} · 새로고침하거나 수동 자료를 가져오세요. HTML 파일을 직접 열었다면 README의 실행 안내를 확인하세요.</p></div>`;
  } finally { $('refreshBtn').disabled = false; $('refreshBtn').textContent = '새로고침'; $('content').setAttribute('aria-busy', 'false'); renderSaveState(); }
}

function setTab(button, focus = false) {
  for (const tab of document.querySelectorAll('[role="tab"]')) {
    const active = tab === button; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; $(tab.getAttribute('aria-controls')).hidden = !active;
  }
  if (focus) button.focus();
}

function bindEvents() {
  $('saveServerBtn').addEventListener('click', saveCurrentToServer);
  $('disconnectGithubBtn').addEventListener('click', () => { githubToken = ''; $('githubToken').value = ''; $('githubConnectionStatus').textContent = 'GitHub 연결 해제 · 저장한 자료는 유지됩니다.'; });
  $('refreshBtn').addEventListener('click', initialize);
  $('snapshotSelect').addEventListener('change', () => { compareOptions(''); loadSelection(); });
  $('compareSelect').addEventListener('change', loadSelection);
  for (const tab of document.querySelectorAll('[role="tab"]')) {
    tab.addEventListener('click', () => setTab(tab));
    tab.addEventListener('keydown', event => {
      const tabs = [...document.querySelectorAll('[role="tab"]')], index = tabs.indexOf(tab);
      let target;
      if (event.key === 'ArrowRight') target = tabs[(index + 1) % tabs.length];
      else if (event.key === 'ArrowLeft') target = tabs[(index + tabs.length - 1) % tabs.length];
      else if (event.key === 'Home') target = tabs[0];
      else if (event.key === 'End') target = tabs.at(-1);
      if (target) { event.preventDefault(); setTab(target, true); }
    });
  }
  for (const id of ['dongFilter', 'typeFilter', 'floorFilter', 'stateFilter', 'sortSelect', 'groupToggle', 'listingView']) $(id).addEventListener('change', renderListings);
  $('briefingFormat').addEventListener('change', renderBriefing);
  $('searchInput').addEventListener('input', renderListings);
  $('resetFiltersBtn').addEventListener('click', () => { for (const id of ['dongFilter', 'typeFilter', 'floorFilter', 'stateFilter', 'searchInput']) $(id).value = ''; $('sortSelect').value = 'priceAsc'; $('groupToggle').checked = false; renderListings(); });
  const toggleImport = open => { $('importPanel').hidden = !open; $('openImportBtn').setAttribute('aria-expanded', String(open)); };
  $('openImportBtn').addEventListener('click', () => toggleImport($('importPanel').hidden));
  $('closeImportBtn').addEventListener('click', () => toggleImport(false));
  $('exportJsonBtn').addEventListener('click', () => { if (state.current) download(`beomeoW_${state.current.date.slice(0, 10)}.json`, 'application/json;charset=utf-8', JSON.stringify(state.current, null, 2)); });
  $('exportCsvBtn').addEventListener('click', () => {
    if (!state.current) return;
    const fields = ['dong', 'type', 'floor', 'direction', 'minPrice', 'maxPrice', 'confirmDate', 'agencyCount', 'agencyInfo', 'desc', 'articleId', 'status'];
    const header = ['동', '타입', '층', '향', '최소호가(억)', '최대호가(억)', '확인일', '중개사수', '중개정보', '설명', '매물번호', '관측상태'];
    const csv = [header, ...state.filtered.map(row => fields.map(k => row[k]))].map(row => row.map(csvCell).join(',')).join('\r\n');
    download(`beomeoW_${state.current.date.slice(0, 10)}.csv`, 'text/csv;charset=utf-8', '\ufeff' + csv);
    toast('현재 필터에 해당하는 원본 행을 CSV로 저장했습니다.');
  });
  $('copyBriefBtn').addEventListener('click', () => copyText('briefingText', '선택한 리포트를 복사했습니다.'));
  $('showAgency').addEventListener('change',renderAll);
  $('copyListingsBottom').addEventListener('click',()=>copyText('listingText','현재 표시된 매물 텍스트를 전체 복사했습니다.'));
  $('copyListingsBtn').addEventListener('click', () => copyText('listingText', '현재 필터의 매물 텍스트를 복사했습니다.'));
  $('saveBriefBtn').addEventListener('click', () => { if (state.current) download(`whoga_${state.current.date.slice(0, 10)}_${$('briefingFormat').value}.txt`, 'text/plain;charset=utf-8', $('briefingText').textContent); });
  $('saveListingsBtn').addEventListener('click', () => { if (state.current) download(`whoga_${state.current.date.slice(0, 10)}_listings.txt`, 'text/plain;charset=utf-8', $('listingText').textContent); });
  $('jsonInput').addEventListener('change', async event => {
    try { const file = event.target.files?.[0]; if (!file) return; if (file.size > 8 * 1024 * 1024) throw new Error('8MB 이하의 JSON 파일을 선택해 주세요.'); addLocal(JSON.parse((await file.text()).replace(/^\uFEFF/, ''))); }
    catch (error) { $('importResult').textContent = error.message; toast(error.message); }
    finally { event.target.value = ''; }
  });
  $('parseRawBtn').addEventListener('click', () => {
    try { if (!$('rawDate').value) throw new Error('원문 기준일을 선택해 주세요.'); addLocal(parseRaw($('rawInput').value, $('rawDate').value)); }
    catch (error) { $('importResult').textContent = error.message; toast(error.message); }
  });
  $('clearLocalBtn').addEventListener('click', () => {
    if (!Object.keys(state.local).length) { toast('지울 수동 자료가 없습니다.'); return; }
    if (window.confirm('이 기기에 가져온 수동 자료를 모두 지울까요? 필요한 자료는 먼저 JSON으로 저장하세요.')) { try { localStorage.removeItem(LOCAL_KEY); } catch {} initialize(); toast('이 기기의 수동 자료를 지웠습니다.'); }
  });
}

bindEvents(); $('rawDate').value = todayKst(); initialize();

