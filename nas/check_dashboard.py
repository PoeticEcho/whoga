"""CI browser test: real dashboard and local browser smoke, no Naver or GitHub writes."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, chromium_sandbox=True)
    context = browser.new_context(http_credentials={'username': 'admin', 'password': os.environ['DASHBOARD_PASSWORD']}, viewport={'width': 1280, 'height': 1100})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8899')
    page.wait_for_function("document.getElementById('url').value.includes('140635')")
    page.locator('#url').fill('https://fin.land.naver.com/complexes/140635')
    page.get_by_role('button', name='설정 저장', exact=True).click()
    page.wait_for_function("document.getElementById('dirty').textContent === '저장됨'")
    page.locator('[data-mode="smoke"]').click()
    page.wait_for_function("document.getElementById('result').textContent === '브라우저 정상'", timeout=60000)
    assert page.locator('#upload').is_disabled()
    page.screenshot(path='/output/dashboard-desktop.png', full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path='/output/dashboard-mobile.png', full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile overflow'
    assert not errors, errors
    print('PASS: authenticated dashboard, settings, real browser smoke, upload gate, desktop/mobile layout')
    browser.close()
