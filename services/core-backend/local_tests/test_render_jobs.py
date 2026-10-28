"""Persistent local-render tests, temporary files and synthetic data only."""
import asyncio,copy,hashlib,json,sqlite3,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from app.local_os.render_jobs import create_render_router,RenderManager,RENDERER_VERSION
from app.local_os.growth import create_growth_router
from app.local_os.bridge import culture_service_type
from app.local_os.integration import install_local_os
from local_tests.test_growth import image
BASE='/api/local-os/growth'


def fake_render(*,job_dir,package_snapshot,assets,progress=None,cancel_event=None):
    if progress:progress(60,'encoding')
    output=job_dir/'output';output.mkdir(exist_ok=True)
    files={'video':'video.mp4','poster':'poster.jpg','subtitles':'subtitles.srt','receipt':'receipt.json'}
    for k,n in files.items():(output/n).write_bytes(b'{}' if k=='receipt' else ('ISOLATED-'+k).encode())
    return dict(files=files,metadata=dict(duration_seconds=15,width=1080,height=1920,sha256=hashlib.sha256((output/'video.mp4').read_bytes()).hexdigest()),warnings=[])


class RenderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'operations.sqlite3'
        self.state=dict(package=dict(id='package-SYN',hash='a'*64,campaign_id='campaign-SYN'),fingerprint='b'*64,blockers=[],warnings=['仅本地待审'],assets=[])
        async def snapshot(package_id):return copy.deepcopy(self.state)
        self.calls=0;self.fail_next=False;self.entered=threading.Event();self.release=threading.Event();self.block=False
        def render(**kwargs):
            self.calls+=1
            if self.block:self.entered.set();self.release.wait(3)
            if self.fail_next:self.fail_next=False;raise ValueError('Do not expose private paths in public errors')
            return fake_render(**kwargs)
        router=create_render_router(str(self.path),snapshot,render_fn=render);self.manager=router.render_manager
        app=FastAPI();app.include_router(router)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver')
    async def asyncTearDown(self):
        self.release.set();await asyncio.to_thread(self.manager.close);await self.client.aclose();self.folder.cleanup()
    async def request(self,method,path,value=None):return await self.client.request(method,BASE+path,json=value)
    async def confirm(self):
        r=await self.request('POST','/packages/package-SYN/render-confirmations',dict(package_hash='a'*64,confirmations=dict(script=True,storyboard=True,reference_labels=True),note='合成本地预览确认'))
        self.assertEqual(r.status_code,200,r.text);return r.json()['confirmation']
    async def create(self,confirmation=None):
        confirmation=confirmation or await self.confirm();r=await self.request('POST','/packages/package-SYN/renders',dict(package_hash='a'*64,confirmation_id=confirmation['id']))
        self.assertEqual(r.status_code,200,r.text);return r.json()
    async def terminal(self,job):
        for _ in range(200):
            r=await self.request('GET','/renders/'+job['id']);self.assertEqual(r.status_code,200,r.text)
            if r.json()['status'] in {'succeeded','failed'}:return r.json()
            await asyncio.sleep(.01)
        self.fail('synthetic worker timeout')
    async def test_confirmation_dedupe_separation_and_staleness(self):
        state=(await self.request('GET','/packages/package-SYN/render-state')).json();self.assertIsNone(state['confirmation']);self.assertEqual(state['jobs'],[])
        c=await self.confirm();self.assertTrue(c['valid']);self.assertEqual((await self.confirm())['id'],c['id']);self.assertEqual(self.calls,0)
        j=await self.create(c);same=await self.create(c);self.assertEqual(j['id'],same['id']);done=await self.terminal(j)
        self.assertEqual(done['status'],'succeeded');self.assertEqual(done['progress'],100);self.assertEqual(self.calls,1);self.assertTrue(done['preview_only']);self.assertFalse(done['published']);self.assertFalse(done['stale'])
        self.assertIn('subtitles',done['artifacts']);self.assertTrue(done['artifacts']['download'].endswith('?download=1'))
        self.state['fingerprint']='c'*64;state=(await self.request('GET','/packages/package-SYN/render-state')).json();self.assertFalse(state['confirmation']['valid']);self.assertTrue(state['jobs'][0]['stale'])
        r=await self.request('POST','/packages/package-SYN/renders',dict(package_hash='a'*64,confirmation_id=c['id']));self.assertEqual(r.status_code,409)
        self.assertNotEqual((await self.confirm())['id'],c['id'])
        with sqlite3.connect(self.path) as db:self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'op_%'").fetchone()[0],0)
    async def test_failure_explicit_retry_receipt_and_no_auto_retry(self):
        self.fail_next=True;c=await self.confirm();j=await self.create(c);failed=await self.terminal(j)
        self.assertEqual(failed['status'],'failed');self.assertEqual(self.calls,1);self.assertNotIn('private',failed['error']['message']);self.assertIn('receipt',failed['artifacts'])
        r=await self.client.get(failed['artifacts']['receipt']);self.assertEqual(r.status_code,200);self.assertEqual(r.json()['status'],'failed')
        again=await self.create(c);self.assertEqual(again['id'],j['id']);self.assertEqual(again['status'],'failed');self.assertEqual(self.calls,1)
        r=await self.request('POST','/renders/'+j['id']+'/retry',dict(package_hash='a'*64,confirmation_id=c['id']));self.assertEqual(r.status_code,200,r.text)
        done=await self.terminal(j);self.assertEqual(done['status'],'succeeded');self.assertEqual(done['attempt'],2);self.assertEqual(self.calls,2)
        old=await self.client.get(done['attempt_history'][0]['receipt']);self.assertEqual(old.status_code,200);self.assertEqual(old.json()['status'],'failed');self.assertEqual(old.json()['attempt'],1)
        self.assertEqual((await self.request('POST','/renders/'+j['id']+'/retry',dict(package_hash='a'*64,confirmation_id=c['id']))).status_code,409)
    async def test_running_progress_and_post_render_source_gate(self):
        self.block=True;c=await self.confirm();j=await self.create(c);self.assertTrue(await asyncio.to_thread(self.entered.wait,2))
        active=(await self.request('GET','/renders/'+j['id'])).json();self.assertEqual(active['status'],'running')
        self.state['blockers']=['来源版本已更新'];self.release.set();done=await self.terminal(j)
        self.assertEqual(done['status'],'failed');self.assertEqual(done['error']['code'],'INPUT_CHANGED');self.assertNotIn('video',done['artifacts']);self.assertTrue(done['stale'])
    async def test_video_ranges_hash_symlink_and_input_scope(self):
        done=await self.terminal(await self.create());url=done['artifacts']['video'];video=await self.client.get(url);self.assertEqual(video.status_code,200)
        part=await self.client.get(url,headers={'Range':'bytes=1-4'});self.assertEqual(part.status_code,206);self.assertEqual(part.content,video.content[1:5]);self.assertEqual(part.headers['accept-ranges'],'bytes')
        suffix=await self.client.get(url,headers={'Range':'bytes=-4'});self.assertEqual(suffix.content,video.content[-4:])
        self.assertEqual((await self.client.get(url,headers={'Range':'bytes=99999-'})).status_code,416)
        head=await self.client.head(url);self.assertEqual(head.status_code,200);self.assertEqual(head.content,b'')
        with self.manager.transaction() as db:stored=self.manager.get(db,'jobs',done['id'])
        target=self.manager.root/stored['artifacts']['video']['storage_path'];target.write_bytes(b'changed');self.assertEqual((await self.client.get(url)).status_code,409)
        target.unlink();target.symlink_to(self.path);self.assertEqual((await self.client.get(url)).status_code,409)
        self.assertEqual((await self.request('GET','/packages/package-SYN/render-state?site_id=other')).status_code,403)
        r=await self.request('POST','/packages/package-SYN/renders',dict(package_hash='a'*64,confirmation_id='x',path='/tmp/arbitrary',command='curl'));self.assertEqual(r.status_code,422)
    async def test_restart_running_failure_not_automatic_retry(self):
        c=await self.confirm();j=await self.terminal(await self.create(c))
        with self.manager.transaction() as db:
            stored=self.manager.get(db,'jobs',j['id']);stored['status']='running';stored['phase']='encoding';self.manager.save_job(db,stored)
        restored=RenderManager(str(self.path),self.manager.snapshot,render_fn=fake_render)
        try:
            with restored.transaction() as db:r=restored.get(db,'jobs',j['id'])
            self.assertEqual(r['status'],'failed');self.assertEqual(r['error']['code'],'INTERRUPTED');self.assertEqual(r['attempt'],1)
        finally:restored.close()


class GrowthRenderGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_rights_warnings_and_new_compilation_invalidates(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'operations.sqlite3'
            with patch('app.local_os.render_jobs._default_render',fake_render),patch('app.local_os.render_jobs._renderer_capabilities',lambda:dict(available=True,missing=[],renderer_version=RENDERER_VERSION)):
                app=FastAPI();app.include_router(create_growth_router(str(db)))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                    c=(await client.post(BASE+'/campaigns',json=dict(title='合成测试',audience='假设',product_summary='住宿与文化',objective='咨询',primary_channel='direct',source_code='SYN',notes=''))).json()
                    a=(await client.post(BASE+'/assets',data=dict(title='合成历史图',kind='photo',rights_confirmed='false',evidence_status='historical_photo',caption='合成',source_note='2099测试'),files={'file':('synthetic.png',image(),'image/png')})).json()
                    payload=dict(base_version=1,angle='stay',duration_seconds=15,knowledge_ids=[],asset_ids=[a['id']],notes='')
                    p=(await client.post(BASE+'/campaigns/'+c['id']+'/compile',json=payload)).json();url=BASE+'/packages/'+p['id']
                    s=await client.get(url+'/render-state');self.assertEqual(s.status_code,200,s.text);self.assertTrue(s.json()['readiness']['available']);self.assertTrue(s.json()['readiness']['warnings'])
                    r=await client.post(url+'/render-confirmations',json=dict(package_hash=p['hash'],confirmations=dict(script=True,storyboard=True,reference_labels=True),note='仅预览'));self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['confirmation']['valid'])
                    snapshot=(await client.get(BASE)).json();self.assertEqual(snapshot['reviews'],[]);self.assertEqual(snapshot['distributions'],[])
                    await client.post(BASE+'/campaigns/'+c['id']+'/compile',json={**payload,'angle':'culture'})
                    s=(await client.get(url+'/render-state')).json();self.assertFalse(s['confirmation']['valid']);self.assertFalse(s['readiness']['available'])
                    r=await client.post(url+'/renders',json=dict(package_hash=p['hash'],confirmation_id=r.json()['confirmation']['id']));self.assertEqual(r.status_code,409)
    async def test_origin_and_scope_are_inherited(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);app=FastAPI();install_local_os(app,service=culture_service_type()(root/'culture.sqlite3'),operations_db_path=root/'operations.sqlite3')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                payload=dict(package_hash='a'*64,confirmations=dict(script=True,storyboard=True,reference_labels=True),note='')
                for headers in [{},{'X-Yantian-Local':'1','Origin':'https://foreign.invalid'},{'X-Yantian-Local':'1','Origin':'http://testserver','X-Site-ID':'other'}]:
                    self.assertEqual((await client.post(BASE+'/packages/missing/render-confirmations',json=payload,headers=headers)).status_code,403)
                self.assertEqual((await client.get(BASE+'/renders/missing',headers={'X-Tenant-ID':'other'})).status_code,403)


if __name__=='__main__':unittest.main()
