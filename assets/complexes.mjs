import {loadCollectionPlan,saveCollectionPlan,loadPlanAcknowledgement} from './repository.mjs?v=3';
const $=id=>document.getElementById(id);
let revision=null;
const selected=new URLSearchParams(location.search).get('complex')||'140635';
const defaultPlan={schemaVersion:1,enabled:true,intervalHours:6,targets:[{complexNo:'140635',label:'수성범어W'}]};
function scheduleText(){const count=[0,1,2].filter(i=>$('complexNumber'+i).value.trim()).length||1;const hours=Number($('rotationHours').value);$('rotationSummary').textContent=`${hours}시간마다 한 단지씩 순서대로 수집합니다. ${count}개 단지는 각각 ${hours*count}시간마다 다시 수집합니다. 한 번에 하나만 실행합니다.`;}
async function init(){
  $('collectionPlan').querySelectorAll('input,select,button').forEach(e=>e.disabled=true);
  try {
    const response=await fetch('complexes.json',{cache:'no-store'});if(!response.ok)throw Error('목록 대기');
    const catalog=await response.json();
    $('complexTabs').replaceChildren();
    for(const row of catalog.complexes){
      const link=document.createElement('a');link.className='button '+(selected===row.complexNo?'primary':'quiet');
      link.href='?complex='+encodeURIComponent(row.complexNo);link.textContent=row.label+(row.archived?' · 보관':row.ready?'':' · 수집 대기');
      if(selected===row.complexNo){link.setAttribute('aria-current','page');document.querySelector('.brand small').textContent=row.label;document.title='호가정리 · '+row.label;}
      $('complexTabs').append(link);
    }
  } catch { $('complexTabs').textContent='수성범어W · 단지 관리에서 수집 대상을 등록할 수 있습니다.'; }
  try {
    const {plan,sha}=await loadCollectionPlan();revision=sha;const value=plan||defaultPlan;
    value.targets.forEach((t,i)=>{$('complexNumber'+i).value=t.complexNo;$('complexLabel'+i).value=t.label;});
    $('rotationHours').value=value.intervalHours;$('rotationEnabled').checked=value.enabled;scheduleText();
    $('collectionPlan').querySelectorAll('input,select,button').forEach(e=>e.disabled=false);
    if(!plan){$('planMessage').textContent='등록된 원격 설정이 없습니다. 저장 전까지 기존 NAS 예약을 유지합니다.';return;}
    const ack=await loadPlanAcknowledgement();
    $('planMessage').textContent=ack?.revision===sha?`NAS ${ack.version} 적용 확인 · ${ack.appliedAt} · ${ack.enabled?'순환 수집 켜짐':'예약 꺼짐'}`:'GitHub 설정 저장됨 · NAS 적용은 아직 확인되지 않았습니다. NAS 3.0 이상에서 약 5분마다 확인합니다.';
  } catch(error){$('planMessage').textContent=error.message;$('savePlan').disabled=true;}
}
$('collectionPlan').addEventListener('input',scheduleText);
$('collectionPlan').addEventListener('submit',async event=>{
  event.preventDefault();$('savePlan').disabled=true;
  const token=$('planToken').value;$('planToken').value='';
  try {
    const targets=[0,1,2].map(i=>({complexNo:$('complexNumber'+i).value.trim(),label:$('complexLabel'+i).value.trim()})).filter(t=>t.complexNo);
    const result=await saveCollectionPlan({schemaVersion:1,enabled:$('rotationEnabled').checked,intervalHours:Number($('rotationHours').value),targets},{token,sha:revision});revision=result.sha;
    $('planMessage').textContent='GitHub에 설정을 저장했습니다. NAS 적용 확인은 새로고침으로 확인하세요. NAS 3.0 이상과 저장된 NAS 토큰이 필요합니다.';
    $('planCommit').href=result.url;$('planCommit').hidden=false;
  }catch(error){$('planMessage').textContent=error.message;}
  finally{$('savePlan').disabled=false;}
});
$('refreshBtn').addEventListener('click',init);
init();
