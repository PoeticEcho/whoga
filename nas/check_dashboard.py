"""Real Docker browser test: authenticated VNC display, input, CDP and saved settings.

Only local fixture content is used. No Naver requests or GitHub writes.
"""
import os
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as pw:
    controller = pw.chromium.launch(headless=True, chromium_sandbox=False)
    context = controller.new_context(http_credentials={'username': 'admin', 'password': os.environ['DASHBOARD_PASSWORD']}, viewport={'width': 1280, 'height': 1100})
    dashboard = context.new_page()
    errors = []
    dashboard.on('pageerror', lambda error: errors.append(str(error)))
    dashboard.goto('http://127.0.0.1:8899')
    expect(dashboard.locator('#url')).to_have_value('https://fin.land.naver.com/complexes/140635')
    if os.environ.get('WHOGA_EXPECT_RESTART'):
        expect(dashboard.locator('#intervalMinutes')).to_have_value('67')
    dashboard.locator('#intervalMinutes').fill('67')
    dashboard.get_by_role('button', name='설정 저장', exact=True).click()
    expect(dashboard.locator('#dirty')).to_have_text('저장됨')

    # Set a local fixture in the persistent desktop; remote input must reach it.
    remote = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    page = remote.contexts[0].pages[0]
    page.set_content('<title>WhoGa 화면·입력 검사</title><body style="background:#edf3ed"><button style="position:absolute;left:80px;top:100px;width:400px;height:160px;font-size:30px" onclick="this.dataset.clicked=\'yes\';this.textContent=\'원격 클릭 확인\'">원격 입력 검사</button></body>')
    viewer = context.new_page()
    viewer.on('pageerror', lambda error: errors.append(str(error)))
    viewer.goto('http://127.0.0.1:8899/desktop/')
    expect(viewer.locator('#connection')).to_have_text('● 화면 연결됨', timeout=30000)
    canvas = viewer.locator('#screen canvas')
    expect(canvas).to_be_visible()
    viewer.wait_for_timeout(1500)
    assert viewer.evaluate('''() => {
      const c=document.querySelector('#screen canvas');
      if(c.width!==1440 || c.height!==1000)return false;
      const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
      const colors=new Set();for(let i=0;i<p.length;i+=400)colors.add(p.slice(i,i+3).join(','));
      return colors.size>10;
    }'''), 'VNC framebuffer is missing or blank'
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
    dashboard.screenshot(path='/output/dashboard-desktop.png', full_page=True)
    dashboard.set_viewport_size({'width':390,'height':844})
    dashboard.screenshot(path='/output/dashboard-mobile.png', full_page=True)
    assert dashboard.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    print('PASS: authenticated framebuffer, real remote mouse input, same visible CDP browser, smoke, upload gate, mobile layouts and settings')
    controller.close()
