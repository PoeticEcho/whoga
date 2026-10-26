const $ = id => document.getElementById(id);
let initialized=false, dirty=false, latest=null;
const labels={'comparison-complete':'비교 기록 완료','running':'실행 중','browser-ready':'브라우저 정상','page-opened':'원문 탭 열림','probe-passed':'표본 검사 통과','full-passed':'전체 수집 성공','failed':'실패','interrupted':'중단됨','success':'업로드 완료','not-configured':'미설정'};
function notice(message,error=false){$('notice').hidden=false;$('notice').textContent=message;$('notice').classList.toggle('error',error);}
async function api(path,data){const response=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json','X-Whoga-Request':'1'}:{},body:data?JSON.stringify(data):undefined});if(!response.ok){let msg='연결을 확인하세요.';try{msg=(await response.json()).error||msg;}catch{}throw Error(msg);}return response.json();}
function time(value){return value?new Date(value*1000).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'—';}
function scheduleControls(){$('dailyControls').hidden=$('scheduleMode').value!=='daily';$('intervalControls').hidden=$('scheduleMode').value!=='interval';}
function fill(config){for(const key of ['url','intervalMinutes','scheduleMode','dailyTime','repository','branch'])$(key).value=config[key];for(const key of ['scheduleEnabled','autoUpload'])$(key).checked=config[key];$('tokenStored').textContent=config.tokenStored?'저장됨':'미등록';scheduleControls();}
function uploadView(state, config, unsaved=false) {
  const upload=state.upload||{}, run=state.lastResult||{};
  const collected=state.result==='full-passed' && run.url===config.url;
  const key=`${config.repository}:${config.branch}:${run.runId}`;
  const current=Boolean(run.runId) && upload.key===key;
  const view=(label,message,enabled=false,link=null)=>({label,message,enabled,link});
  if(state.running) return view('수집 중','전체 수집과 검증이 끝나면 업로드할 수 있습니다.');
  if(upload.status==='running') return view('업로드 중','GitHub 전송 결과를 기다리고 있습니다.');
  if(unsaved) return view('설정 저장 필요','변경한 설정을 먼저 저장하세요. 수집 결과는 NAS에 보관되어 있습니다.');
  if(!config.tokenStored) return view('토큰 등록 필요',`${collected?'전체 수집은 성공했습니다. ':''}GitHub 토큰을 등록하고 설정을 저장하면 업로드할 수 있습니다.`);
  if(!collected) return view('전체 수집 대기','현재 감시 주소의 전체 수집이 성공해야 업로드할 수 있습니다.');
  if(current && upload.status==='success') return view('업로드 완료','이번 수집 결과를 GitHub에 저장했습니다. 운영 앱 반영은 별도입니다.',false,upload.url);
  if(current && upload.status==='failed') return view('업로드 실패',`${upload.message||'전송에 실패했습니다.'} 설정을 확인한 뒤 다시 업로드할 수 있습니다.`,true);
  return view('업로드 준비됨','전체 수집과 JSON 저장이 완료됐습니다. GitHub 업로드 버튼으로 이번 결과를 전송하세요.',true);
}
function renderUpload() {
  if(!latest)return;
  const {state,config}=latest, view=uploadView(state,config,dirty);
  $('uploadStatus').textContent=view.label;
  $('uploadMessage').textContent=view.message;
  $('uploadHelp').textContent=view.message;
  $('upload').disabled=!view.enabled;
  $('upload').title=view.message;
  $('autoUploadState').textContent=config.autoUpload
    ? (config.tokenStored?'자동 업로드 켜짐 · 이후 전체 수집 성공 시 전송합니다.':'자동 업로드 설정됨 · GitHub 토큰 등록이 필요합니다.')
    : '자동 업로드 꺼짐 · 예약 수집과 별도 설정입니다.';
  const link=$('uploadLink');
  link.hidden=!(view.link && /^https:\/\/github\.com\//.test(view.link));
  if(!link.hidden)link.href=view.link;
}
function bytes(value){return Number.isFinite(value)?(value/1024/1024).toFixed(0)+' MB':'확인하지 못함';}
function diagnostics(data){const {state,build}=data;if(build)$('buildVersion').textContent=`WhoGa NAS ${build.version} · 커밋 ${build.sourceCommit?.slice(0,7)||'미기록'} · 코드 ${build.sourceFingerprint.slice(0,12)}`;const result=state.lastResult;$('diagnostics').hidden=!result;if(!result)return;const phase=result.failedPhase||result.phase||result.mode;const parts=[`최종 결과: ${labels[result.status]||result.status||"확인하지 못함"}`,`마지막 단계: ${phase}`,`URL: ${result.finalUrl||result.url}`,`제목: ${result.pageTitle||'확인하지 못함'}`,`브라우저: ${result.browserVersion||'확인하지 못함'}`];if(result.assessment)parts.push(`화면 판정: ${result.assessment.pageState}`,`이번 실행 CSP 차단: ${result.assessment.cspBlockedDuringRun?'관측됨':'관측되지 않음'}`);if(result.assessment)parts.push(`이번 실행 자원 오류: ${result.assessment.resourceFailureDuringRun===undefined?'미수집':result.assessment.resourceFailureDuringRun?'관측됨':'관측되지 않음'}`);if(result.resources){const r=result.resources;parts.push(`컨테이너 메모리: ${bytes(r.memory.currentBytes)} / ${bytes(r.memory.limitBytes)}`,`/tmp 여유: ${bytes(r.filesystems.tmp.availableBytes)}`,`/dev/shm 여유: ${bytes(r.filesystems.sharedMemory.availableBytes)}`);if(r.browser&&typeof r.browser.sharedMemoryDisabled==='boolean')parts.push(`브라우저 공유 메모리: ${r.browser.sharedMemoryDisabled?'/tmp 우회':'기본 /dev/shm 사용'}`);}if(result.comparison){parts.push('조건별 결과 (최초 접속 → 새로고침)');for(const c of result.comparison)parts.push(`${c.condition}: ${c.attempts.map(a=>a.cardsVisible?'목록 표시':a.pageState).join(' → ')||c.outcome}`);if(result.stoppedReason)parts.push(`비교 중단 사유: ${result.stoppedReason}`);}if(result.error)parts.push(`오류: ${result.error.split('\n')[0]}`);$('diagnosticSummary').textContent=parts.join('\n');for(const [id,key]of [['diagnosticDownload','report'],['diagnosticScreenshot','screenshot']]){const link=$(id),href=state.diagnosticLinks?.[key];link.hidden=!href;if(href)link.href=href;}}
async function refresh(){
  try{
    latest=await api('/api/status');diagnostics(latest);
    const {state:s,config:c}=latest;
    if(!initialized){fill(c);initialized=true;}
    $('connection').textContent=s.running?'● 수집 중':'● 연결됨';
    $('result').textContent=labels[s.result]||'대기';
    $('message').textContent=s.result==='full-passed'?'전체 카드·개별 매물 검증을 통과하고 JSON을 NAS에 저장했습니다.':(s.message||'설정 후 표본 검사를 시작하세요.');
    const result=s.lastResult?.full||s.lastResult?.probe;
    $('counts').textContent=result?`${result.cards} / ${result.articles}`:'— / —';
    const busy=s.running||s.upload?.status==='running';
    document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=busy||dirty);
    renderUpload();
    $('stop').disabled=!s.running;
    $('settings').querySelectorAll('input,select,button').forEach(el=>el.disabled=busy);
    $('nextRun').textContent=c.scheduleEnabled?'다음 실행: '+time(s.nextRun)+' (한국 시각)':'예약 실행 꺼짐';
    $('lastRun').textContent=time(s.startedAt);
    $('runTrigger').textContent=s.trigger==='scheduled'?'예약 실행':s.trigger==='manual'?'수동 실행':'실행 방식 미기록';
    $('modeLabel').textContent=s.mode||'최근 실행';
    const log=$('log'),bottom=log.scrollHeight-log.scrollTop-log.clientHeight<30;
    log.textContent=latest.log||'아직 실행 기록이 없습니다.';
    if(bottom)log.scrollTop=log.scrollHeight;
  }catch(error){$('connection').textContent='● 연결 끊김';notice(error.message,true);}
}
$('settings').addEventListener('input',()=>{dirty=true;$('dirty').textContent='저장하지 않은 변경사항';document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=true);renderUpload();});
$('scheduleMode').addEventListener('change',scheduleControls);
$('settings').addEventListener('submit',async event=>{event.preventDefault();const data={};for(const key of ['url','repository','branch','githubToken','scheduleMode','dailyTime'])data[key]=$(key).value.trim();data.intervalMinutes=Number($('intervalMinutes').value);for(const key of ['scheduleEnabled','autoUpload','clearToken'])data[key]=$(key).checked;try{await api('/api/settings',data);dirty=false;$('dirty').textContent='저장됨';$('githubToken').value='';$('clearToken').checked=false;initialized=false;notice('설정을 저장했습니다.');await refresh();}catch(error){notice(error.message,true);}});
for(const button of document.querySelectorAll('[data-mode]'))button.addEventListener('click',async()=>{button.disabled=true;try{await api('/api/run',{mode:button.dataset.mode});notice('실행을 시작했습니다. 아래 로그에서 진행 상황을 확인하세요.');await refresh();}catch(error){notice(error.message,true);await refresh();}});
for(const [id,path] of [['stop','stop'],['upload','upload'],['githubTest','github-test']])$(id).addEventListener('click',async()=>{try{const r=await api('/api/'+path,{});notice(r.message);await refresh();}catch(error){notice(error.message,true);}});
$('copyLog').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('log').textContent);notice('로그를 복사했습니다.');}catch{const range=document.createRange();range.selectNodeContents($('log'));const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);notice('로그를 선택했습니다. 복사 메뉴를 사용하세요.');}});
$('openGithubSettings').addEventListener('click',()=>{
  $('githubSettings').open=true;
  $('githubSettings').scrollIntoView({behavior:'smooth',block:'start'});
  $('githubSettings').querySelector('summary').focus();
});
refresh();setInterval(refresh,2500);
