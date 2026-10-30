"""Real browser interactions against fictional SQLite data; no production URL."""
from pathlib import Path
from threading import Thread
import pytest
from werkzeug.serving import make_server
from test_intervention_programmes import library, SCOPE
from test_assessment_reliability import world, login

playwright_api=pytest.importorskip('playwright.sync_api',reason='Browser tests run in the dedicated CI job')


def test_programme_menu_drag_drop_and_note_save(library,tmp_path):
    app,ids=library
    app.config['WTF_CSRF_ENABLED']=True
    client=app.test_client();login(client,ids['teacher'])
    client.get('/teacher/interventions',query_string=SCOPE)
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with playwright_api.sync_playwright() as playwright:
            browser=playwright.chromium.launch()
            context=browser.new_context(viewport={'width':1440,'height':1050})
            context.add_cookies([{'name':'session','value':client.get_cookie('session').value,'url':base}])
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base+'/teacher/interventions?academic_year=2026/27&term=autumn&subject=maths')
            page.locator(f'#programme-{ids["record"]}').select_option(str(ids['programme']))
            with page.expect_navigation(): page.get_by_role('button',name='Assign',exact=True).click()
            card=page.locator(f'[data-programme-drop="{ids["programme"]}"]')
            playwright_api.expect(card).to_contain_text('Alice Test')
            row=page.locator(f'[data-pupil-drag="{ids["pupils"][0]}"]')
            with page.expect_navigation(): row.drag_to(page.locator(f'[data-programme-drop="{ids["second_programme"]}"]'))
            playwright_api.expect(page.locator(f'[data-programme-drop="{ids["second_programme"]}"]')).to_contain_text('Alice Test')
            page.get_by_text('View / edit plan',exact=True).click()
            page.locator(f'#plan-{ids["record"]}').fill('Fictional plan saved in browser')
            playwright_api.expect(page.locator(f'[data-note-status="{ids["record"]}"]')).to_have_text('Saved')
            screenshot_dir=Path('test-artifacts');screenshot_dir.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_dir/'interventions-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(screenshot_dir/'interventions-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.get_by_role('button',name='Add pupil / programme').click()
            page.locator('#add-pupil').select_option(str(ids['pupils'][1]))
            page.locator('#add-programme').select_option(str(ids['programme']))
            with page.expect_navigation(): page.get_by_role('button',name='Add support',exact=True).click()
            playwright_api.expect(page.locator(f'[data-programme-drop="{ids["programme"]}"]')).to_contain_text('Beth Test')
            # Navigating immediately after typing must finish the pending note first.
            page.set_viewport_size({'width':1440,'height':1050})
            page.get_by_text('View / edit plan',exact=True).click()
            page.locator(f'#plan-{ids["record"]}').fill('Latest fictional plan before navigation')
            with page.expect_navigation(): page.get_by_role('button',name='Close intervention',exact=True).first.click()
            page.get_by_role('link',name='Closed 1',exact=True).click()
            playwright_api.expect(page.locator(f'#plan-{ids["record"]}')).to_have_value('Latest fictional plan before navigation')
            # Admin creates a programme through the real form.
            admin_client=app.test_client();login(admin_client,ids['admin']);admin_client.get('/admin/intervention-programmes')
            context.add_cookies([{'name':'session','value':admin_client.get_cookie('session').value,'url':base}])
            page.goto(base+'/admin/intervention-programmes')
            page.locator('#new-name').fill('Browser-created maths group')
            page.locator('#new-subject').select_option('maths')
            with page.expect_navigation(): page.get_by_role('button',name='Create programme',exact=True).click()
            playwright_api.expect(page.get_by_role('heading',name='Browser-created maths group',exact=True)).to_be_visible()
            page.screenshot(path=str(screenshot_dir/'programme-library.png'),full_page=True)
            assert errors==[]
            browser.close()
    finally:
        server.shutdown();thread.join(timeout=5)
