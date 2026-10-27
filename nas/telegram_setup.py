"""Dedicated bot pairing: getMe, webhook check, expiring /start challenge."""
import json,re,secrets,time,socket,ssl
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen

def call(token,method,data=None):
    if not isinstance(token,str) or not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,200}',token):raise ValueError('봇 토큰 형식을 확인하세요.')
    try:
        req=Request('https://api.telegram.org/bot'+token+'/'+method,data=json.dumps(data or {}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=15) as response:result=json.load(response)
        if not result.get('ok'):raise ValueError()
        return result['result']
    except HTTPError as error:
        messages={401:'봇 토큰이 유효하지 않습니다. BotFather에서 토큰을 다시 확인하세요.',403:'이 봇의 메시지 전송이 차단됐습니다. 봇 차단을 해제하세요.',409:'다른 프로그램이 이 봇의 메시지를 받고 있습니다. 호가정리 전용 봇을 사용하세요.',429:'Telegram 요청이 많습니다. 잠시 후 다시 시도하세요.'}
        raise ValueError(messages.get(error.code,f'Telegram 서버 오류 (HTTP {error.code}). 잠시 후 다시 시도하세요.')) from None
    except (TimeoutError,socket.timeout):raise ValueError('Telegram 응답 시간이 초과됐습니다. NAS 인터넷 연결을 확인하세요.') from None
    except URLError as error:
        message='NAS의 HTTPS 인증서 또는 시스템 시간을 확인하세요.' if isinstance(error.reason,ssl.SSLError) else 'NAS에서 api.telegram.org에 연결하지 못했습니다. DNS·인터넷 연결을 확인하세요.'
        raise ValueError(message) from None
    except Exception:raise ValueError('Telegram 응답을 확인하지 못했습니다. 잠시 후 다시 시도하세요.') from None

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
