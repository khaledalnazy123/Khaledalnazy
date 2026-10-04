"""Browser-only UI smoke using stubbed API, no user data and no network."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE=Path(__file__).parents[1]
html=(HERE/'web/index.html').read_text().replace('{{APP_VERSION}}','2.0.0-rc.1').replace('{{APP_TOKEN}}','testing')
html=html.replace('<script src="/app.js"></script>','')
html=re.sub(r'<link[^>]+/style.css[^>]*>','',html)
movies=[dict(id=i+1,display_title=title,year=year,genres='Action, Drama',release_group='YTS',resolution_tag='1080p',resolution_verified=1,status='available',size_bytes=3_000_000,poster_path='',poster_locked=0,source='BluRay',subtitle_source='OSN',watched=0,imdb_rating=7.5,favorite=0,sub_count=2,arabic_count=1,english_count=1,subtitle_sources='OSN,Netflix') for i,(title,year) in enumerate([('Dont Look Up',2021),('Brick',2025),('The Dark Knight',2008)])]
film=dict(movies[0]);film.update({'root_path':r'D:\Movies','path':r'D:\Movies\Dont Look Up.mkv','original_filename':'Dont Look Up (2021) [1080p].mkv','current_filename':'Dont Look Up.mkv','notes':'','translation_quality':'Excellent','poster_credit':'','hdr':0,'resolution':'1920x1080','video_bitrate':1000000,'audio_bitrate':128000,'audio_codec':'aac','overall_bitrate':1128000,'channels':2,'audio_layout':'stereo','probe_error':'','raw_probe':'{}','added_at':'2026-10-04','last_seen':'2026-10-04','manual_fields':[],'imdb_id':'','personal_rating':None,'preferred_subtitle_id':None,'playback_preference':'auto','cast_names':'Actor One, Actor Two','overview':'Test overview','subtitles':[{'id':1,'kind':'external','filename':'Arabic.osn.srt','path':r'D:\Movies\Arabic.osn.srt','format':'SRT','language':'Arabic','source':'OSN','quality':'Excellent','translator':''},{'id':2,'kind':'external','filename':'English.netflix.srt','path':r'D:\Movies\English.netflix.srt','format':'SRT','language':'English','source':'Netflix','quality':'Good','translator':''}]})
base={'stats':{'total':3,'available':3,'missing':0,'offline':0,'disk_bytes':9000000,'catalog_bytes':9000000,'groups':1,'imdb_imported_at':None,'imdb_ratings_at':None,'ffprobe_found':True},'settings':{'poster_provider':'none','theme':'dark','default_external_subtitle_lang':'Arabic','auto_posters':'0','poster_in_folder':'0','archive_missing':'1','auto_imdb':'0'},'tmdb':{'connected':False},'gemini':{'connected':False},'roots':[],'data_dir':'D:\\MovieVault\\v2','active_job':None,'version':'2.0.0-rc.1'}
mock_data={'/api/bootstrap':base,'/api/subtitle-sources':{'items':['Unknown','Netflix','OSN','Amazon Prime Video','Disney+','Manual','Other']},'/api/movies':{'total':3,'items':movies},'/api/movies/1':film}
errors=[]
with sync_playwright() as p:
 browser=p.chromium.launch(**({'executable_path':'/usr/bin/chromium'} if Path('/usr/bin/chromium').exists() else {}),headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1550,'height':960},device_scale_factor=1)
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.set_content(html,wait_until="domcontentloaded",timeout=10000)
 page.add_style_tag(content=(HERE/'web/style.css').read_text())
 page.evaluate('''(mock)=>{window.fetch=async function(path,opts){let exact=String(path).split('?')[0];let d=mock[exact] || {ok:true};return {ok:true,status:200,json:async()=>structuredClone(d)};};}''',mock_data)
 page.add_script_tag(content=(HERE/'web/app.js').read_text())
 page.wait_for_timeout(700)
 print('Home: cards=',page.locator('.movie-card').count(),'errors=',errors)
 assert page.locator('.movie-card').count()==3,errors
 page.screenshot(path=str(HERE/'docs/V2_Home_UI_Test.png'),full_page=True)
 assert page.locator('#updateAllBtn').is_visible()
 page.locator('.nav[data-view=settings]').click();page.wait_for_timeout(250)
 print('Settings: migration=',page.locator('#migrationPanel').is_visible(),'gemini=',page.locator('#geminiPanel').is_visible(),'errors=',errors)
 assert page.locator('#migrationPanel').is_visible() and page.locator('#geminiPanel').is_visible()
 page.screenshot(path=str(HERE/'docs/V2_Settings_UI_Test.png'),full_page=True)
 page.locator('#themeChoice').select_option('light');page.wait_for_timeout(80)
 assert page.evaluate('document.documentElement.dataset.theme')=='light'
 page.locator('#themeChoice').select_option('dark')
 page.locator('.nav[data-view=home]').click();page.wait_for_timeout(250)
 page.locator('.movie-card').first.click();page.wait_for_timeout(300)
 print('Details: ',page.locator('#modalContent h2').first.text_content(),'subtitle rows=',page.locator('[data-apply-sub]').count(),'errors=',errors)
 assert page.locator('[data-apply-sub]').count()==2,errors
 page.screenshot(path=str(HERE/'docs/V2_Movie_Details_UI_Test.png'),full_page=True)
 page.locator('#editMovie').click();page.wait_for_timeout(200)
 page.locator('#modalOverlay').click(position={'x':5,'y':5});page.wait_for_timeout(250)
 print('Closing edit returns movie:',page.locator('#modalContent .detail-title').count())
 assert page.locator('#modalContent .detail-title').count()==1
 page.locator('#closeModal').click();page.wait_for_timeout(90)
 page.locator('#updateAllBtn').click();page.wait_for_timeout(90)
 assert 'Smart Library Update' in page.locator('#modalContent').inner_text()
 page.locator('#cancelUpdate').click()
 browser.close()
if errors:raise AssertionError(errors)
print('VISUAL SMOKE PASSED')
