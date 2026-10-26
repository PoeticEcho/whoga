import RFB from './core/rfb.js';

const $ = id => document.getElementById(id);
let rfb;
async function connect() {
  if (rfb) rfb.disconnect();
  $('connection').textContent = '연결 중';
  try {
    const response = await fetch('/api/desktop-session', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Whoga-Request': '1'}, body: '{}'
    });
    if (!response.ok) throw Error('관리 화면 로그인 또는 연결 상태를 확인하세요.');
    const {ticket} = await response.json();
    const url = new URL('/desktop/websockify', location.href);
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    url.searchParams.set('ticket', ticket);
    rfb = new RFB($('screen'), url.href);
    rfb.scaleViewport = true;
    rfb.resizeSession = false;
    rfb.viewOnly = $('viewOnly').checked;
    rfb.addEventListener('connect', () => {$('connection').textContent = '● 화면 연결됨';});
    rfb.addEventListener('disconnect', () => {$('connection').textContent = '연결 끊김 · 다시 연결을 누르세요';});
    rfb.addEventListener('securityfailure', () => {$('connection').textContent = '화면 연결 인증 실패';});
  } catch (error) {
    $('connection').textContent = error.message;
  }
}
$('reconnect').addEventListener('click', connect);
$('viewOnly').addEventListener('change', () => {if (rfb) rfb.viewOnly = $('viewOnly').checked;});
$('fullscreen').addEventListener('click', async () => {
  try {await $('screen').requestFullscreen();} catch {$('hint').textContent = '이 기기에서는 브라우저의 가로 화면 보기를 이용하세요.';}
});
connect();
