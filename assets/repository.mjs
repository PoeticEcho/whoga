import { validateSnapshot } from './core.mjs?v=3.0.0';

// Pages serves files; GitHub is the durable store. Credentials stay in tab memory.
export const REPOSITORY = 'PoeticEcho/whoga';
const ROOT = `https://api.github.com/repos/${REPOSITORY}`;
const BRANCH = 'main';
const json = value => JSON.stringify(value, null, 2) + '\n';
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;

export async function contentHash(snapshot) {
  const rows = snapshot.items.map(row => JSON.stringify(stable(row))).sort();
  const bytes = new TextEncoder().encode(JSON.stringify([snapshot.date.slice(0, 10), snapshot.declaredCount, rows]));
  return [...new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', bytes))].map(v => v.toString(16).padStart(2, '0')).join('');
}

export function sortEntries(entries) {
  return [...entries].sort((a, b) => b.date.localeCompare(a.date)
    || (Date.parse(b.savedAt || b.collectedAt || '') || 0) - (Date.parse(a.savedAt || a.collectedAt || '') || 0)
    || Number(b.id === b.date) - Number(a.id === a.date) || b.id.localeCompare(a.id));
}

function apiError(status) {
  const message = status === 401 ? 'GitHub 연결 토큰이 만료되었거나 올바르지 않습니다.'
    : status === 403 ? '저장 권한 또는 API 사용 한도를 확인하세요. whoga 저장소의 Contents: Read and write 권한이 필요합니다.'
    : status === 404 ? 'whoga 저장소 접근 권한 또는 저장 경로를 확인하세요.'
    : [409, 422].includes(status) ? '다른 저장 작업과 겹쳤습니다. 다시 저장해 주세요.'
    : `서버 요청에 실패했습니다 (${status}). 기기 자료는 보존됩니다.`;
  return Object.assign(new Error(message), { status });
}

function client(token = '', fetchImpl = globalThis.fetch) {
  return async (path, method = 'GET', body, raw = false) => {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetchImpl(ROOT + path, {
        method, cache: 'no-store', redirect: 'error', credentials: 'omit', signal: controller.signal,
        headers: { Accept: raw ? 'application/vnd.github.raw+json' : 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2026-03-10', ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (!response.ok) throw apiError(response.status);
      return await response.json();
    } catch (error) {
      if (error.status) throw error;
      throw new Error('서버 응답을 확인하지 못했습니다. 기기 자료는 보존되며 다시 저장할 수 있습니다.');
    } finally { clearTimeout(timer); }
  };
}

const fileAt = (api, file, ref) => api(`/contents/data/${encodeURIComponent(file)}?ref=${encodeURIComponent(ref)}`, 'GET', undefined, true);
function checkIndex(index) {
  if (!Array.isArray(index?.snapshots)) throw new Error('서버 자료 목록이 올바르지 않아 저장을 중단했습니다.');
  const ids = new Set();
  for (const entry of index.snapshots) {
    if (!entry || typeof entry.id !== 'string' || ids.has(entry.id) || !/^\d{4}-\d{2}-\d{2}$/.test(entry.date)
      || !/^[\w가-힣.-]+\.json$/.test(entry.file)) throw new Error('서버 자료 목록을 확인해 주세요.');
    ids.add(entry.id);
  }
  return index;
}

export async function loadSharedIndex(fetchImpl = globalThis.fetch) {
  const api = client('', fetchImpl);
  const ref = await api(`/git/ref/heads/${BRANCH}`);
  return { index: checkIndex(await fileAt(api, 'index.json', ref.object.sha)), ref: ref.object.sha };
}

export async function loadSharedSnapshot(file, ref, fetchImpl = globalThis.fetch) {
  if (!/^[\w가-힣.-]+\.json$/.test(file) || !/^[a-f\d]{40}$/.test(ref)) throw new Error('서버 자료 경로를 확인해 주세요.');
  const snapshot = await fileAt(client('', fetchImpl), file, ref);
  validateSnapshot(snapshot);
  return snapshot;
}

export async function saveSnapshot(snapshot, { token, fetchImpl = globalThis.fetch, onProgress = () => {} } = {}) {
  const quality = validateSnapshot(snapshot);
  if (!quality.complete || !snapshot.items.length || snapshot.items.length > 5000) throw new Error('전체 수량과 필수 항목을 통과한 1~5,000건 자료만 서버에 저장할 수 있습니다.');
  token = String(token || '').trim();
  if (!token) throw new Error('서버 저장을 위해 GitHub 연결 토큰을 입력해 주세요.');
  const hash = await contentHash(snapshot), id = `${snapshot.date.slice(0, 10)}_manual_${hash.slice(0, 20)}`, file = id + '.json';
  const savedAt = new Date().toISOString();
  const saved = { ...snapshot, schemaVersion: 2, date: snapshot.date.slice(0, 10), count: snapshot.items.length,
    label: `${snapshot.date.slice(0, 10)} · 수동 ${new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(savedAt))} 저장`,
    source: { kind: 'manual', url: 'https://fin.land.naver.com/complexes/140635' },
    savedAt, storage: { kind: 'github', contentHash: hash },
    validation: { ...quality, method: 'declared-count-and-required-fields' } };
  const entry = { id, date: saved.date, label: saved.label, file, count: quality.count, declaredCount: quality.declaredCount,
    complete: true, sourceKind: 'manual', collectedAt: saved.collectedAt || null, savedAt };
  const api = client(token, fetchImpl);

  const verify = async (index, ref) => {
    const listed = index.snapshots.find(e => e.id === id);
    if (!listed) return null;
    if (listed.file !== file || listed.count !== quality.count || listed.declaredCount !== quality.declaredCount || !listed.complete) throw new Error('서버 자료 목록과 저장 결과가 일치하지 않습니다. 기기 자료는 보존됩니다.');
    const remote = await fileAt(api, file, ref);
    validateSnapshot(remote);
    if (await contentHash(remote) !== hash) throw new Error('서버 재조회 결과가 원본과 다릅니다. 기기 자료는 보존됩니다.');
    return { id, snapshot: remote, index, ref, commitUrl: `https://github.com/${REPOSITORY}/commit/${ref}` };
  };

  for (let attempt = 0; attempt < 3; attempt++) {
    onProgress(attempt ? '다른 저장 내용을 합치는 중…' : '서버의 최신 자료를 확인하는 중…');
    const ref = await api(`/git/ref/heads/${BRANCH}`), head = ref.object.sha;
    const index = checkIndex(await fileAt(api, 'index.json', head));
    const existing = await verify(index, head);
    if (existing) return { ...existing, duplicate: true };
    const commit = await api(`/git/commits/${head}`);
    const entries = sortEntries([...index.snapshots, entry]);
    const updatedIndex = { ...index, schemaVersion: 2, latest: entries.find(e => e.complete)?.id || entries[0]?.id || null, snapshots: entries };
    onProgress('날짜별 자료와 조회 목록을 함께 저장하는 중…');
    const tree = await api('/git/trees', 'POST', { base_tree: commit.tree.sha, tree: [
      { path: `data/${file}`, mode: '100644', type: 'blob', content: json(saved) },
      { path: 'data/index.json', mode: '100644', type: 'blob', content: json(updatedIndex) },
    ] });
    const created = await api('/git/commits', 'POST', { message: `data: save manual observation ${saved.date} (${quality.count} items)`, tree: tree.sha, parents: [head] });
    let updateError;
    try { await api(`/git/refs/heads/${BRANCH}`, 'PATCH', { sha: created.sha, force: false }); }
    catch (error) { updateError = error; }
    onProgress('저장한 자료를 서버에서 다시 읽어 확인하는 중…');
    // A response can be lost after a successful write. Read the branch before retrying.
    const current = await api(`/git/ref/heads/${BRANCH}`);
    const currentIndex = checkIndex(await fileAt(api, 'index.json', current.object.sha));
    const confirmed = await verify(currentIndex, current.object.sha);
    if (confirmed) return { ...confirmed, duplicate: false };
    if (updateError && ![409, 422].includes(updateError.status)) throw updateError;
    if (current.object.sha === head) throw updateError || new Error('서버 저장을 확인하지 못했습니다. 다시 저장해 주세요.');
  }
  throw new Error('동시에 진행 중인 저장이 많습니다. 기기 자료는 보존되며 잠시 후 다시 저장할 수 있습니다.');
}

export function validatePlan(plan) {
  if (plan?.schemaVersion !== 1 || typeof plan.enabled !== 'boolean' || ![1,3,6].includes(plan.intervalHours)
      || !Array.isArray(plan.targets) || plan.targets.length < 1 || plan.targets.length > 3) throw Error('단지 1~3개와 1·3·6시간 간격을 선택하세요.');
  const seen = new Set();
  const targets = plan.targets.map(row => {
    if (!row || typeof row.complexNo !== 'string' || !/^[1-9][0-9]{0,11}$/.test(row.complexNo) || seen.has(row.complexNo)) throw Error('중복 없는 숫자 단지 번호를 입력하세요.');
    const label = row.label || '';
    if (typeof label !== 'string' || label.length>60 || /[\x00-\x1f]/.test(label)) throw Error('별칭은 60자 이내로 입력하세요.');
    seen.add(row.complexNo);return {complexNo:row.complexNo,label:label.trim()};
  });
  return {schemaVersion:1,enabled:plan.enabled,intervalHours:plan.intervalHours,targets};
}
export async function loadCollectionPlan(fetchImpl=globalThis.fetch) {
  const api=client('',fetchImpl);
  try {
    const file=await api('/contents/collection-plan.json?ref=main');
    const plan=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(file.content.replace(/\s/g,'')),c=>c.charCodeAt(0))));
    return {plan:validatePlan(plan),sha:file.sha};
  } catch(error) {if(error.status===404)return {plan:null,sha:null};throw error;}
}
export async function loadPlanAcknowledgement(fetchImpl=globalThis.fetch) {
  try {return await client('',fetchImpl)('/contents/_state/nas-plan.json?ref=main','GET',undefined,true);}
  catch(error){if(error.status===404)return null;throw error;}
}
export async function saveCollectionPlan(plan,{token,sha=null,fetchImpl=globalThis.fetch}={}) {
  const value=validatePlan(plan);
  if(!token?.trim())throw Error('설정을 저장할 GitHub 토큰을 입력하세요.');
  const content=btoa(Array.from(new TextEncoder().encode(json(value)),b=>String.fromCharCode(b)).join(''));
  const result=await client(token.trim(),fetchImpl)('/contents/collection-plan.json','PUT',{
    message:'feat: update NAS complex rotation plan',branch:'main',content,...(sha?{sha}:{}),
  });
  return {sha:result.content.sha,url:result.commit.html_url};
}
