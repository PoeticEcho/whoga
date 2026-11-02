"""Private owner commands. Claim updates durably before starting any work."""
import hashlib,re,time

HELP='호가정리 명령\n/collect — 기본 단지 전체 수집\n/collect 140635 — 등록 단지 수집\n/status — 진행 상태\n/help — 도움말'

def binding(config):
    return hashlib.sha256((config['token']+':'+str(config['chatId'])).encode()).hexdigest()

def owner(message, config):
    chat=message.get('chat') or {};sender=message.get('from') or {}
    return chat.get('type')=='private' and type(chat.get('id')) is int and chat['id']==config['chatId'] and sender.get('id')==config['chatId'] and not sender.get('is_bot',False)

def command(text, username):
    if not isinstance(text,str) or len(text)>100:return None,None
    match=re.fullmatch(r'/(collect|status|help|start)(?:@([A-Za-z0-9_]+))?(?:\s+([1-9][0-9]{0,11}))?\s*',text.strip())
    if not match or (match[2] and match[2].lower()!=username.lower()):return None,None
    if match[1]!='collect' and match[3]:return None,None
    return match[1],match[3]

def poll(app):
    from web import read,atomic
    import telegram_setup as telegram
    with app.lock:
        config=read(app.config_dir/'telegram.json',{})
        if app.telegram_session is not None and time.time()>=app.telegram_session.get('expires',0):app.telegram_session=None
        if not config.get('chatId') or not config.get('controlEnabled',True) or app.telegram_session is not None:return
    if not app.telegram_receive_lock.acquire(blocking=False):return
    try:
        path=app.config_dir/'telegram-control.json';key=binding(config);state=read(path,{})
        offset=state.get('offset',0) if state.get('binding')==key else 0
        updates=telegram.call(config['token'],'getUpdates',dict(offset=offset,timeout=0,limit=100,allowed_updates=['message']))
        for update in updates:
            uid=update.get('update_id')
            if type(uid) is not int or uid<offset:continue
            offset=uid+1
            # At most once: a reboot or lost reply cannot repeat /collect.
            atomic(path,dict(binding=key,offset=offset))
            message=update.get('message') or {}
            if not owner(message,config) or type(message.get('date')) is not int or message['date']<max(int(app.telegram_control_boot),int(config.get('controlSince',0))):continue
            with app.lock:
                current=read(app.config_dir/'telegram.json',{})
                if not current.get('chatId') or binding(current)!=key or not current.get('controlEnabled',True) or app.telegram_session is not None:return
            name,target=command(message.get('text'),config.get('username',''))
            if name=='collect':
                try:
                    with app.lock:
                        current=read(app.config_dir/'telegram.json',{})
                        if not current.get('chatId') or binding(current)!=key or not current.get('controlEnabled',True):return
                        app.start('full',target=target,trigger='telegram')
                    reply='수집을 시작했습니다.\n단지 '+(target or app.config['url'].rsplit('/',1)[-1])+'\n완료 후 결과를 알려드립니다.'
                except ValueError as error:reply=str(error)+'\n/status 로 상태를 확인하세요.'
            elif name=='status':
                with app.lock:
                    result=app.state.get('lastResult') or {};counts=result.get('full') or {};upload=app.state.get('upload',{})
                    reply='호가정리 상태\n'+('수집 중' if app.state['running'] else str(app.state.get('result','대기')))+'\n단지 '+app.state.get('activeUrl',app.config['url']).rsplit('/',1)[-1]+'\nGitHub: '+str(upload.get('status','대기'))
                    if counts:reply+=f"\n{counts.get('cards','—')}카드 / {counts.get('articles','—')}개별 매물"
            elif name in ('help','start') or str(message.get('text','')).startswith('/'):reply=HELP
            else:continue
            try:telegram.call(config['token'],'sendMessage',dict(chat_id=config['chatId'],text=reply))
            except ValueError:
                with app.lock:app.state['telegramControlError']='명령 응답 전송 실패. /status 로 실행 상태를 확인하세요.';app.save()
    finally:app.telegram_receive_lock.release()
