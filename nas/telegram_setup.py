"""Dedicated bot pairing: getMe, webhook check, expiring /start challenge."""
import json,re,secrets,time
from urllib.request import Request,urlopen

def call(token,method,data=None):
    if not isinstance(token,str) or not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,200}',token):raise ValueError('봇 토큰 형식을 확인하세요.')
    try:
        req=Request('https://api.telegram.org/bot'+token+'/'+method,data=json.dumps(data or {}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=15) as response:result=json.load(response)
        if not result.get('ok'):raise ValueError()
        return result['result']
    except Exception:raise ValueError('Telegram 연결 실패: 토큰·인터넷·다른 봇 수신기 사용 여부를 확인하세요.') from None

def begin(token):
    me=call(token,'getMe')
    if not me.get('is_bot') or not re.fullmatch(r'[A-Za-z0-9_]{5,32}',me.get('username','')):raise ValueError('봇 정보를 확인하지 못했습니다.')
    if call(token,'getWebhookInfo').get('url'):raise ValueError('기존 webhook은 변경하지 않습니다. 호가정리 전용 봇을 만드세요.')
    return dict(token=token,username=me['username'],challenge='hg_'+secrets.token_urlsafe(18),expires=time.time()+600,offset=0,nextCheck=0)

def pair(session):
    if not session or time.time()>session['expires']:raise ValueError('연결 시간이 만료됐습니다. 봇 확인부터 다시 진행하세요.')
    if time.time()<session['nextCheck']:raise ValueError('3초 뒤 다시 확인하세요.')
    session['nextCheck']=time.time()+3
    updates=call(session['token'],'getUpdates',dict(offset=session['offset'],timeout=0,limit=100,allowed_updates=['message']))
    matches=set()
    for event in updates:
        session['offset']=max(session['offset'],event.get('update_id',0)+1)
        msg=event.get('message',{});chat=msg.get('chat',{});uid=msg.get('from',{}).get('id')
        if type(uid) is int and uid>0 and chat.get('type')=='private' and chat.get('id')==uid and msg.get('text')=='/start '+session['challenge']:matches.add(uid)
    if len(matches)!=1:raise ValueError('전용 봇에서 시작을 누른 뒤 연결 확인을 다시 누르세요.')
    return dict(token=session['token'],chatId=matches.pop(),username=session['username'],enabled=False)
