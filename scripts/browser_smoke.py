"""Three real browser sessions: owner review, supervisor authoring, staff preparation."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def register(page, email):
    page.locator('#auth-button').click()
    page.get_by_role('button', name='New here? Create an account').click()
    page.get_by_label('Email', exact=True).fill(email)
    page.get_by_label('Password', exact=True).fill('browser-test-password')
    page.get_by_role('button', name='Create account', exact=True).click()
    page.get_by_role('heading', name='Your team workspace.').wait_for()


def invite(page, role):
    page.locator('#team-button').click()
    page.locator('#invite-role').select_option(role)
    page.get_by_role('button', name='Generate invitation').click()
    expect(page.locator('#invite-token')).not_to_have_value('')
    token = page.locator('#invite-token').input_value()
    page.locator('#team-dialog [data-close]').click()
    return token


def join(page, token):
    page.get_by_label('Have an invitation?').fill(token)
    page.get_by_role('button', name='Join team', exact=True).click()
    page.locator('#team-dialog').wait_for(state='hidden')


def to_review(page):
    for _ in range(3):
        page.locator('#wizard-next').click()
    expect(page.locator('[data-panel="3"]')).to_be_visible()


with tempfile.TemporaryDirectory() as tmp:
    port = '8011'
    process = subprocess.Popen(['bash', 'scripts/start.sh'], cwd=ROOT,
        env={**os.environ, 'PORT': port, 'MYSOP_DB': tmp + '/browser.sqlite3'},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f'http://127.0.0.1:{port}'
        for _ in range(80):
            try:
                if httpx.get(url + '/health').status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError('Server failed to start')
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
            errors = []
            def new_page(width, height):
                context = browser.new_context(viewport={'width': width, 'height': height})
                page = context.new_page()
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(url)
                expect(page.locator('.card')).to_have_count(3)
                return page
            owner = new_page(1440, 1000)
            owner.screenshot(path=str(ROOT / 'docs/preview-desktop.png'), full_page=True)
            owner.locator('[data-category=food]').click()
            expect(owner.locator('.card')).to_have_count(1)
            owner.locator('.card').click()
            owner.locator('#detail-dialog').get_by_role('heading', name='Avocado sourdough').wait_for()
            owner.get_by_role('button', name='Back to library').click()
            owner.locator('[data-category=all]').click()
            register(owner, 'owner@browser.test')
            owner.get_by_label('Create a new team').fill('Browser Kitchen')
            owner.get_by_role('button', name='Create team', exact=True).click()
            owner.locator('#team-dialog').wait_for(state='hidden')
            supervisor = new_page(1024, 900)
            register(supervisor, 'supervisor@browser.test')
            join(supervisor, invite(owner, 'supervisor'))
            staff = new_page(390, 844)
            staff.screenshot(path=str(ROOT / 'docs/preview-mobile.png'), full_page=True)
            register(staff, 'staff@browser.test')
            join(staff, invite(owner, 'staff'))
            expect(staff.locator('#new-sop')).to_be_hidden()
            expect(staff.locator('[data-view=drafts]')).to_be_hidden()
            supervisor.locator('#new-sop').click()
            supervisor.get_by_label('SOP name').fill('Kitchen iced latte')
            supervisor.get_by_label('Description', exact=True).fill('A consistent recipe for our kitchen team.')
            supervisor.get_by_label('Servings', exact=True).fill('2')
            supervisor.locator('#wizard-next').click()
            supervisor.get_by_label('Ingredient name').fill('Milk')
            supervisor.get_by_label('Quantity', exact=True).fill('200')
            supervisor.get_by_label('Unit', exact=True).fill('ml')
            supervisor.get_by_label('Pack size', exact=True).fill('1000')
            supervisor.get_by_label('Pack price', exact=True).fill('8')
            supervisor.locator('#add-ingredient').click()
            row = supervisor.locator('.ingredient-row').nth(1)
            row.get_by_label('Ingredient name').fill('Coffee')
            row.get_by_label('Quantity', exact=True).fill('20')
            row.get_by_label('Unit', exact=True).fill('g')
            row.get_by_label('Pack size', exact=True).fill('1000')
            row.get_by_label('Pack price', exact=True).fill('60')
            expect(supervisor.locator('#cost-estimate')).to_contain_text('MYR 2.80')
            supervisor.locator('#wizard-next').click()
            supervisor.get_by_label('Preparation steps', exact=False).fill('Measure milk and coffee.\nBrew coffee and pour over milk.')
            supervisor.get_by_label('Allergens', exact=False).fill('Milk')
            supervisor.get_by_label('Safety & storage notes').fill('Keep milk refrigerated.')
            supervisor.locator('#wizard-next').click()
            supervisor.locator('#save-draft').click()
            supervisor.locator('#editor-dialog').wait_for(state='hidden')
            expect(staff.locator('.card')).to_have_count(0)
            supervisor.locator('[data-view=drafts]').click()
            supervisor.get_by_role('heading', name='Kitchen iced latte').wait_for()
            supervisor.locator('.card').click()
            to_review(supervisor)
            supervisor.locator('#save-publish').click()
            supervisor.locator('#editor-dialog').wait_for(state='hidden')
            expect(supervisor.locator('.status-label')).to_have_text('Awaiting owner review')
            owner.locator('[data-view=approvals]').click()
            owner.get_by_role('heading', name='Kitchen iced latte').wait_for()
            owner.locator('.card').click()
            owner.get_by_label('Review notes').fill('Add the approved storage temperature.')
            owner.get_by_role('button', name='Request changes', exact=True).click()
            owner.locator('#detail-dialog').wait_for(state='hidden')
            expect(supervisor.locator('.status-label')).to_have_text('Changes requested')
            supervisor.locator('.card').click()
            expect(supervisor.locator('#editor-notice')).to_contain_text('storage temperature')
            supervisor.locator('#wizard-next').click()
            supervisor.locator('#wizard-next').click()
            supervisor.get_by_label('Safety & storage notes').fill('Keep milk refrigerated at the approved temperature. Follow local food safety rules.')
            supervisor.locator('#wizard-next').click()
            supervisor.locator('#save-publish').click()
            supervisor.locator('#editor-dialog').wait_for(state='hidden')
            owner.get_by_role('heading', name='Kitchen iced latte').wait_for()
            owner.locator('.card').click()
            expect(owner.locator('#detail-content .cost-summary')).to_contain_text('MYR 2.80')
            expect(staff.locator('.card')).to_have_count(0)
            owner.locator('#review-form').scroll_into_view_if_needed()
            owner.screenshot(path=str(ROOT / 'docs/preview-approval.png'), full_page=True)
            owner.get_by_role('button', name='Approve & publish', exact=True).click()
            owner.locator('#detail-dialog').wait_for(state='hidden')
            staff.get_by_role('heading', name='Kitchen iced latte').wait_for(timeout=10000)
            staff.locator('.card').click()
            staff.locator('#start-prep').click()
            expect(staff.locator('#prep-step')).to_have_text('Measure milk and coffee.')
            staff.locator('#prep-next').click()
            expect(staff.locator('#prep-step')).to_have_text('Brew coffee and pour over milk.')
            staff.locator('#prep-next').click()
            expect(staff.locator('#prep-position')).to_have_text('COMPLETE')
            staff.locator('#prep-next').click()
            staff.locator('#acknowledge').click()
            expect(staff.locator('#acknowledge')).to_have_text('Acknowledged')
            staff.screenshot(path=str(ROOT / 'docs/preview-staff.png'), full_page=True)
            staff.get_by_role('button', name='Back to library').click()
            staff.reload()
            expect(staff.locator('.status-label')).to_have_text('Acknowledged')
            owner.locator('[data-view=published]').click()
            owner.locator('.card').click()
            expect(owner.locator('#ack-report')).to_contain_text('staff@browser.test')
            expect(owner.locator('#ack-report')).to_contain_text('Read')
            # A new approved version invalidates an open preparation view and old acknowledgment.
            owner.get_by_role('button', name='Back to library').click()
            staff.locator('.card').click()
            staff.locator('#start-prep').click()
            supervisor.locator('.card').click()
            supervisor.get_by_label('Description', exact=True).fill('Updated preparation standard, version two.')
            to_review(supervisor)
            supervisor.locator('#save-publish').click()
            supervisor.locator('#editor-dialog').wait_for(state='hidden')
            owner.locator('[data-view=approvals]').click()
            owner.locator('.card').click()
            owner.get_by_role('button', name='Approve & publish', exact=True).click()
            owner.locator('#detail-dialog').wait_for(state='hidden')
            expect(staff.locator('#prep-warning')).to_be_visible()
            expect(staff.locator('#prep-next')).to_be_disabled()
            staff.get_by_label('Close preparation', exact=True).click()
            expect(staff.locator('#version-warning')).to_be_visible()
            staff.locator('#open-latest').click()
            expect(staff.locator('#acknowledge')).to_have_text('I have read this version')
            expect(staff.locator('#detail-content')).to_contain_text('Version 2')
            staff.locator('#acknowledge').click()
            expect(staff.locator('.ack-note')).to_contain_text('You acknowledged version 2.')
            staff.screenshot(path=str(ROOT / 'docs/preview-staff.png'), full_page=True)
            staff.get_by_role('button', name='Back to library').click()
            owner.locator('[data-view=published]').click()
            for page in [owner, supervisor, staff]:
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            staff.locator('#logout').click()
            expect(staff.locator('#auth-button')).to_be_visible()
            staff.locator('#auth-button').click()
            staff.get_by_label('Email', exact=True).fill('staff@browser.test')
            staff.get_by_label('Password', exact=True).fill('browser-test-password')
            staff.get_by_role('button', name='Sign in', exact=True).click()
            staff.locator('#auth-dialog').wait_for(state='hidden')
            expect(staff.locator('.status-label')).to_have_text('Acknowledged')
            expect(staff.locator('#new-sop')).to_be_hidden()
            assert not errors, errors
            browser.close()
            print('Browser smoke passed: desktop/tablet/phone, login, role invitations, guided costing, draft privacy, submission, owner return/revision/approval, live staff update, preparation mode, acknowledgment persistence/report and shared-device sign out. No JavaScript errors.')
    finally:
        process.terminate()
        process.wait(timeout=10)
