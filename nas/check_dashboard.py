"""Real Docker browser test: authenticated VNC display, input, CDP and saved settings.

Only local fixture content is used. No Naver requests or GitHub writes.
"""
import os
import json
import base64
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as pw:
    controller = pw.chromium.launch(headless=True, chromium_sandbox=False)
    context = controller.new_context(http_credentials={'username': 'admin', 'password': os.environ['DASHBOARD_PASSWORD']}, viewport={'width': 1280, 'height': 1100})
    dashboard = context.new_page()
    errors = []
    dashboard.on('pageerror', lambda error: errors.append(str(error)))
    dashboard.goto('http://127.0.0.1:8899')
    expect(dashboard.locator('#url')).to_have_value('https://fin.land.naver.com/complexes/140635')
    expect(dashboard.locator('#buildVersion')).to_contain_text('WhoGa NAS 2.3')
    expect(dashboard.locator('#buildVersion')).to_contain_text(os.environ['WHOGA_EXPECT_SOURCE_COMMIT'][:7])
    if os.environ.get('WHOGA_EXPECT_RESTART'):
        expect(dashboard.locator('#scheduleMode')).to_have_value('daily')
        expect(dashboard.locator('#dailyTime')).to_have_value('09:17')
        expect(dashboard.locator('#dailyControls')).to_be_visible()
        expect(dashboard.locator('#intervalControls')).to_be_hidden()
        dashboard.locator('#scheduleMode').select_option('interval')
        expect(dashboard.locator('#intervalMinutes')).to_have_value('67')
    else:
        expect(dashboard.locator('#scheduleMode')).to_have_value('daily')
        dashboard.locator('#scheduleMode').select_option('interval')
    dashboard.locator('#intervalMinutes').fill('67')
    dashboard.locator('#scheduleMode').select_option('daily')
    dashboard.locator('#dailyTime').fill('09:17')
    dashboard.get_by_role('button', name='설정 저장', exact=True).click()
    expect(dashboard.locator('#dirty')).to_have_text('저장됨')

    # Set a local fixture in the persistent desktop; remote input must reach it.
    remote = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    page = remote.contexts[0].pages[0]
    page.set_content('<title>WhoGa 화면·입력 검사</title><body style="background:#edf3ed"><button style="position:absolute;left:80px;top:100px;width:400px;height:160px;font-size:30px" onclick="this.dataset.clicked=\'yes\';this.textContent=\'원격 클릭 확인\'">원격 입력 검사</button></body>')
    page.bring_to_front()
    viewer = context.new_page()
    viewer.on('pageerror', lambda error: errors.append(str(error)))
    viewer.goto('http://127.0.0.1:8899/desktop/')
    expect(viewer.locator('#connection')).to_have_text('● 화면 연결됨', timeout=30000)
    canvas = viewer.locator('#screen canvas')
    expect(canvas).to_be_visible()
    framebuffer = """() => {
      const c=document.querySelector('#screen canvas');
      if(!c)return {width:0,height:0,colors:0};
      const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
      const colors=new Set();for(let i=0;i<p.length;i+=400)colors.add(p.slice(i,i+3).join(','));
      return {width:c.width,height:c.height,colors:colors.size,firstPixel:Array.from(p.slice(0,4))};
    }"""
    try:
        viewer.wait_for_function('() => {const f=('+framebuffer+')();return f.width===1440 && f.height===1000 && f.colors>10}', timeout=15000)
    except Exception:
        print('FRAMEBUFFER_INFO: '+json.dumps(viewer.evaluate(framebuffer)),flush=True)
        # Local fixture only: retain an inspectable image even if artifact storage
        # is unavailable to the review environment. No credentials are displayed.
        png=viewer.screenshot(path='/output/browser-failure.png',full_page=True)
        encoded=base64.b64encode(png).decode()
        for start in range(0,len(encoded),8000): print('WHOGA_FRAME:'+encoded[start:start+8000],flush=True)
        raise
    button = page.locator('button').bounding_box()
    geometry = page.evaluate('({x:screenX,y:screenY,w:outerWidth-innerWidth,h:outerHeight-innerHeight})')
    box = canvas.bounding_box()
    x = geometry['x'] + geometry['w']/2 + button['x'] + button['width']/2
    y = geometry['y'] + geometry['h'] - geometry['w']/2 + button['y'] + button['height']/2
    canvas.click(position={'x': x*box['width']/1440, 'y': y*box['height']/1000})
    page.wait_for_function("document.querySelector('button').dataset.clicked === 'yes'", timeout=10000)
    viewer.screenshot(path='/output/browser-desktop.png', full_page=True)
    viewer.set_viewport_size({'width':390,'height':844})
    viewer.screenshot(path='/output/browser-mobile.png',full_page=True)
    assert viewer.evaluate('document.documentElement.scrollWidth <= innerWidth')
    viewer.close()

    # The actual collection worker attaches to that same browser without closing it.
    dashboard.locator('[data-mode="smoke"]').click()
    expect(dashboard.locator('#result')).to_have_text('브라우저 정상', timeout=60000)
    assert page.title() == 'WhoGa 화면·입력 검사'
    assert dashboard.locator('#upload').is_disabled()
    expect(dashboard.locator('#diagnosticDownload')).to_be_visible()
    expect(dashboard.locator('#diagnosticScreenshot')).to_be_visible()
    dashboard.screenshot(path='/output/dashboard-desktop.png', full_page=True)
    dashboard.set_viewport_size({'width':390,'height':844})
    dashboard.screenshot(path='/output/dashboard-mobile.png', full_page=True)
    assert dashboard.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    print('PASS: authenticated framebuffer, real remote mouse input, same visible CDP browser, smoke, upload gate, mobile layouts and daily/interval schedule settings')
    controller.close()
