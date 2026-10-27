(() => {
  const el=id=>document.getElementById(id);
  let busy=false,pairing=false,pairTimer=null,pairUrl=null;
  async function api(body){
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),40000);
    try {
      const response=await fetch('/api/telegram',{method:body?'POST':'GET',cache:'no-store',signal:abort.signal,
        headers:body?{'Content-Type':'application/json','X-Whoga-Request':'1'}:{},body:body?JSON.stringify(body):undefined});
      let data;try{data=await response.json();}catch{throw Error('NAS 응답을 읽지 못했습니다. 새로고침 후 다시 시도하세요.');}
      if(!response.ok)throw Error(data.error||'Telegram 요청 실패');return data;
    }catch(error){if(error.name==='AbortError')throw Error('40초 안에 응답이 없습니다. NAS 인터넷·Telegram 연결을 확인하고 다시 시도하세요.');throw error;}
    finally{clearTimeout(timer);}
  }
  async function refresh(){try{
    const data=await api();
    el('tgState').textContent=data.connected?`연결됨: @${data.username} · 자동 알림 ${data.enabled?'켜짐':'꺼짐'}`:'연결되지 않음 · 먼저 토큰 확인을 누르세요.';
    el('tgManual').hidden=!data.pairingCommand;el('tgCommand').value=data.pairingCommand||'';
    pairUrl=data.pairingUrl;
    if(pairUrl&&!busy&&!pairing&&!pairTimer)pairTimer=setTimeout(autoPair,4000);
    if(!pairUrl&&pairTimer){clearTimeout(pairTimer);pairTimer=null;}
    el('tgOpen').hidden=!data.pairingUrl;if(data.pairingUrl)el('tgOpen').href=data.pairingUrl;else el('tgOpen').removeAttribute('href');
    el('tgBegin').disabled=busy;el('tgPair').disabled=busy||!data.pairingUrl;
    for(const id of ['tgTest','tgOff'])el(id).disabled=busy||!data.connected;
    el('tgEnable').disabled=busy||!data.connected||data.enabled;
    el('tgDisable').disabled=busy||!data.connected||!data.enabled;
  }catch(error){el('tgState').textContent='연결 상태를 확인하지 못했습니다.';el('tgMessage').textContent=error.message;el('tgBegin').disabled=busy;}}
  async function autoPair(){
    pairTimer=null;
    if(busy||pairing||!pairUrl)return;
    pairing=true;
    try{
      const data=await api({action:'auto-pair'});
      el('tgMessage').textContent=data.message||'개인 대화 연결 완료.';
      if(data.pending)el('tgMessage').textContent='봇에서 시작을 눌러 주세요. 메시지를 자동으로 확인하고 있습니다.';
    }catch(error){el('tgMessage').textContent=error.message;}
    finally{pairing=false;await refresh();}
  }
  async function action(name){if(busy)return;busy=true;
    el('tgMessage').textContent=name==='begin'?'봇 토큰과 연결 설정을 확인하고 있습니다. 최대 40초 정도 기다려 주세요.':'Telegram에 확인하고 있습니다…';
    el('telegramPanel').querySelectorAll('button').forEach(button=>button.disabled=true);
    const body={action:name,enabled:name==='enable'};
    if(name==='begin'){body.token=el('tgToken').value.trim();el('tgToken').value='';}
    try{const data=await api(body);el('tgMessage').textContent=data.message||'봇 확인 완료. ‘Telegram에서 봇 열기’ → 시작을 누르면 자동으로 연결됩니다.';}
    catch(error){el('tgMessage').textContent=error.message;}
    finally{busy=false;await refresh();}
  }
  for(const [id,name]of [['tgBegin','begin'],['tgPair','pair'],['tgTest','test'],['tgEnable','enable'],['tgDisable','disable'],['tgOff','disconnect']])
    el(id).addEventListener('click',()=>action(name==='disable'?'disable':name));
  el('tgCommand').addEventListener('click',()=>el('tgCommand').select());
  window.addEventListener('focus',()=>{if(!busy&&!pairing)refresh();});
  el('tgState').textContent='연결 상태 확인 중…';refresh();setInterval(()=>{if(!busy)refresh();},10000);
})();
