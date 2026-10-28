"""Synthetic isolated HTTP tests. Never use production data or conftest."""
import copy
import io
import json
from pathlib import Path
import re
import sqlite3
import struct
import tempfile
import unittest
import zipfile
import zlib
import httpx
from fastapi import FastAPI
from app.local_os.growth import create_growth_router

BASE='/api/local-os/growth'

def image():
    def ch(k,d): return struct.pack('!I',len(d))+k+d+struct.pack('!I',zlib.crc32(k+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+ch(b'IHDR',struct.pack('!2I5B',2,2,8,2,0,0,0))+ch(b'IDAT',zlib.compress(b'\x00\xff\x00\x00\x00\xff\x00'*2))+ch(b'IEND',b'')

class Culture:
    def __init__(self):
        self.k=[dict(id='SYN-K',source_id='SYN-S',version=1,title='隔离资料',content='木刻可观察线条与印痕。仅合成知识。',locator='测试页1',region_scope='huizhou',review_status='source_checked',rights_scope='internal',domain='humanities',kind='reference')]
        self.s=[dict(id='SYN-S',title='隔离来源',url='https://example.invalid',rights_scope='internal')]
    async def list_knowledge(self): return copy.deepcopy(self.k)
    async def list_sources(self): return copy.deepcopy(self.s)

class GrowthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.path=Path(self.t.name)/'operations.sqlite3';self.culture=Culture()
        app=FastAPI();app.include_router(create_growth_router(str(self.path),self.culture))
        self.c=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver')
    async def asyncTearDown(self): await self.c.aclose()
    async def send(self,m,p='',v=None): return await self.c.request(m,BASE+p,json=v)
    async def snap(self):
        r=await self.send('GET');self.assertEqual(r.status_code,200,r.text);return r.json()
    def brief(self,**v): return {**dict(title='合成住宿任务',audience='合成受众假设',product_summary='住宿与文化体验提纲',objective='合成咨询目标',primary_channel='direct',source_code='SYN-CODE',notes='隔离测试'),**v}
    async def campaign(self,**v):
        r=await self.send('POST','/campaigns',self.brief(**v));self.assertEqual(r.status_code,200,r.text);return r.json()
    async def compile(self,c,**v):
        d=dict(base_version=c['version'],angle='stay',duration_seconds=30,knowledge_ids=[],asset_ids=[],notes='待拍提纲');d.update(v)
        r=await self.send('POST','/campaigns/'+c['id']+'/compile',d);self.assertEqual(r.status_code,200,r.text);return r.json()
    async def asset(self,status='site_photo',rights=True):
        r=await self.c.post(BASE+'/assets',data=dict(title='合成测试PNG非庄园',kind='photo',rights_confirmed=str(rights).lower(),evidence_status=status,caption='仅隔离合成画面',source_note='测试生成2099-01-01'),files={'file':('synthetic.png',image(),'image/png')})
        self.assertEqual(r.status_code,200,r.text);return r.json()
    async def review(self,p): return await self.send('POST','/packages/'+p['id']+'/reviews',dict(package_hash=p['hash'],decision='approve',note='隔离人工声明',confirmations=dict(facts=True,rights=True,delivery=True)))
    def distribution(self,p): return dict(package_hash=p['hash'],channel_id='direct',external_url='https://example.invalid/test',reference='仅合成外部声明',note='未实际发布')

    async def test_unknown_empty_and_scopes(self):
        s=await self.snap();self.assertEqual(s['campaigns'],[]);self.assertEqual(s['assets'],[]);self.assertIsNone(s['business_facts']['bundle_price_cents']);self.assertFalse(s['capabilities']['provider_connected'])
        c=await self.campaign();a=(await self.snap())['campaigns'][0]['attribution'];self.assertIsNone(a['views']);self.assertIsNone(a['net_cash_cents']);self.assertIsNone(a['valid_leads_count'])
        self.assertEqual((await self.send('GET','?site_id=other')).status_code,403)
        self.assertEqual((await self.send('POST','/campaigns',{**self.brief(),'tenant_id':'other'})).status_code,403)
        self.assertEqual((await self.send('POST','/campaigns',self.brief())).status_code,409)

    async def test_lengths_speech_srt_time_and_replay(self):
        c=await self.campaign()
        for duration,lo,hi in [(15,40,55),(30,80,120),(60,150,220)]:
            p=await self.compile(c,duration_seconds=duration);m=p['materials'];shots=m['storyboard']
            self.assertEqual(m['voiceover'],'\n'.join(x['voiceover'] for x in shots));self.assertEqual(shots[0]['start_seconds'],0);self.assertEqual(shots[-1]['end_seconds'],duration)
            self.assertTrue(all(a['end_seconds']==b['start_seconds'] for a,b in zip(shots,shots[1:])))
            self.assertEqual([b.split('\n',2)[2] for b in m['srt'].strip().split('\n\n')],[x['voiceover'] for x in shots])
            count=len(re.findall('[\u3400-\u9fff]',m['voiceover']));self.assertTrue(lo<=count<=hi,(duration,count,m['voiceover']))
            self.assertNotIn('/stay',m['voiceover']);self.assertNotIn('380',m['voiceover']);self.assertEqual(m['task_brief']['objective'],c['objective'])
            self.assertEqual((await self.compile(c,duration_seconds=duration))['id'],p['id'])
            self.assertEqual(p['compiler_version'],'yantian-growth-materials-v1.4')
            self.assertTrue(all(x['end_seconds']>x['start_seconds'] for x in shots))

    async def test_draft_review_export_and_no_external_execution(self):
        c=await self.campaign();p=await self.compile(c)
        self.assertEqual((await self.send('POST','/packages/'+p['id']+'/distributions',self.distribution(p))).status_code,409)
        r=await self.review(p);self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['package']['approval_valid']);self.assertFalse(r.json()['package']['distribution_ready'])
        r=await self.send('GET','/packages/'+p['id']+'/export');z=zipfile.ZipFile(io.BytesIO(r.content))
        self.assertEqual(set(z.namelist()),{'README.txt','manifest.json','脚本.md','分镜.csv','字幕.srt','提示词.txt','渠道文案.md','拍摄清单.txt','出处与使用清单.md','任务简报.json'});self.assertIn('不是成片',z.read('README.txt').decode());self.assertIn('任务提纲',z.read('脚本.md').decode())
        for path in ['/publish','/providers/jobs']: self.assertEqual((await self.send('POST',path,{})).status_code,423)

    async def test_fake_files_and_concept_historical_unknown_not_current(self):
        for fn,mime,blob in [('x.svg','image/svg+xml',b'<svg/>'),('x.png','image/png',b'\x89PNG\r\n\x1a\nfake'),('../x.png','image/png',image()),('x.pdf','application/pdf',b'%PDF-fake')]:
            r=await self.c.post(BASE+'/assets',data=dict(title='合成',kind='reference' if fn.endswith('.pdf') else 'photo',rights_confirmed='true'),files={'file':(fn,blob,mime)});self.assertEqual(r.status_code,422,r.text)
        self.assertEqual((await self.snap())['assets'],[])
        c=await self.campaign()
        for status in ['unknown','historical_photo','generated_concept']:
            a=await self.asset(status);p=await self.compile(c,asset_ids=[a['id']]);self.assertTrue(p['blockers']);self.assertTrue(all(x['capture_needed'] and x['asset_id'] is None for x in p['materials']['storyboard']))

    async def test_hash_rights_real_file_and_manual_distribution(self):
        c=await self.campaign();a=await self.asset();p=await self.compile(c,asset_ids=[a['id']]);self.assertFalse(p['blockers'])
        self.assertEqual((await self.send('GET','/assets/'+a['id']+'/file')).content,image());self.assertEqual((await self.review(p)).status_code,200)
        r=await self.send('POST','/packages/'+p['id']+'/distributions',self.distribution(p));self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['actual_publication_performed']);self.assertEqual(r.json()['verification'],'operator_declared_unverified')
        replay=await self.send('POST','/packages/'+p['id']+'/distributions',self.distribution(p));self.assertEqual(r.json()['id'],replay.json()['id'])
        next((self.path.parent/'growth-assets').glob('*.png')).write_bytes(b'replaced')
        self.assertFalse((await self.snap())['packages'][0]['approval_valid']);self.assertEqual((await self.review(p)).status_code,409);self.assertEqual((await self.send('GET','/assets/'+a['id']+'/file')).status_code,409)

    async def test_stale_knowledge_and_unknown_rights_fail_closed(self):
        c=await self.campaign();a=await self.asset(rights=False);p=await self.compile(c,asset_ids=[a['id']]);self.assertEqual((await self.review(p)).status_code,409)
        p=await self.compile(c,angle='woodcut',knowledge_ids=['SYN-K']);self.assertIn('徽州资料',p['materials']['voiceover']);self.assertEqual((await self.review(p)).status_code,200)
        self.culture.k[0]['version']=2;self.assertEqual((await self.review(p)).status_code,409)
        self.culture.s[0]['rights_scope']='unknown'
        r=await self.send('POST','/campaigns/'+c['id']+'/compile',dict(base_version=1,angle='culture',duration_seconds=30,knowledge_ids=['SYN-K'],asset_ids=[]));self.assertEqual(r.status_code,422)

    async def test_internal_knowledge_allows_material_review_but_blocks_distribution(self):
        c=await self.campaign();a=await self.asset()
        p=await self.compile(c,angle='woodcut',knowledge_ids=['SYN-K'],asset_ids=[a['id']])
        r=await self.review(p);self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['package']['approval_valid'])
        self.assertFalse(r.json()['package']['distribution_ready'])
        self.assertTrue(any('仅限内部使用' in b for b in r.json()['package']['blockers']))
        r=await self.send('POST','/packages/'+p['id']+'/distributions',self.distribution(p))
        self.assertEqual(r.status_code,409,r.text)

    async def test_edit_new_version_invalidates_old_and_cannot_fake_media(self):
        c=await self.campaign();a=await self.asset();concept=await self.asset('generated_concept');p=await self.compile(c,asset_ids=[a['id'],concept['id']]);await self.review(p)
        m=copy.deepcopy(p['materials']);m['title']='新标题';r=await self.send('PUT','/packages/'+p['id'],dict(base_hash=p['hash'],materials=m));self.assertEqual(r.status_code,200,r.text);new=r.json();self.assertNotEqual(new['hash'],p['hash']);self.assertFalse(new['approval_valid'])
        old=next(x for x in (await self.snap())['packages'] if x['id']==p['id']);self.assertFalse(old['approval_valid']);self.assertEqual((await self.review(p)).status_code,409)
        m=copy.deepcopy(new['materials']);m['voiceover']='不一致';self.assertEqual((await self.send('PUT','/packages/'+new['id'],dict(base_hash=new['hash'],materials=m))).status_code,422)
        m=copy.deepcopy(new['materials']);m['storyboard'][1]['start_seconds']=0;self.assertEqual((await self.send('PUT','/packages/'+new['id'],dict(base_hash=new['hash'],materials=m))).status_code,422)
        m=copy.deepcopy(new['materials']);m['storyboard'][0]['asset_id']=concept['id'];self.assertEqual((await self.send('PUT','/packages/'+new['id'],dict(base_hash=new['hash'],materials=m))).status_code,422)
        m=copy.deepcopy(new['materials']);m['channel_copy']['direct']='严田千年木刻，380元套餐';self.assertEqual((await self.send('PUT','/packages/'+new['id'],dict(base_hash=new['hash'],materials=m))).status_code,422)

    async def test_campaign_versions_metrics_upsert_attribution_and_restore(self):
        c=await self.campaign();p=await self.compile(c)
        r=await self.send('PUT','/campaigns/'+c['id'],{**self.brief(),'title':'新版','base_version':1});self.assertEqual(r.status_code,200);self.assertEqual((await self.review(p)).status_code,409)
        self.assertEqual((await self.send('PUT','/campaigns/'+c['id'],{**self.brief(),'base_version':1})).status_code,409)
        with sqlite3.connect(self.path) as db:
            data={'leads':[dict(id='L',source_code='SYN-CODE')],'orders':[dict(id='O',source_code='SYN-CODE',status='confirmed')],'payments':[dict(id='P1',order_id='O',amount_cents=300),dict(id='P2',order_id='O',amount_cents=200)],'refunds':[dict(id='R',order_id='O',amount_cents=100)]}
            for table,records in data.items():
                db.execute('CREATE TABLE op_'+table+' (id TEXT PRIMARY KEY,data TEXT NOT NULL)');db.executemany('INSERT INTO op_'+table+' VALUES (?,?)',[(x['id'],json.dumps(x)) for x in records])
        metric=dict(channel_id='direct',views=None,likes=None,saves=None,spend_cents=None,period_start='2099-01-01',period_end='2099-01-02',note='合成')
        first=await self.send('POST','/campaigns/'+c['id']+'/metrics',metric);second=await self.send('POST','/campaigns/'+c['id']+'/metrics',{**metric,'views':0});self.assertEqual(first.json()['id'],second.json()['id'])
        snap=await self.snap();self.assertEqual(len(snap['metrics']),1);a=snap['campaigns'][0]['attribution'];self.assertEqual((a['leads_count'],a['orders_count'],a['received_cents'],a['refunded_cents'],a['net_cash_cents']),(1,1,500,100,400));self.assertEqual(a['views'],0);self.assertNotIn('revenue_cents',a)
        app=FastAPI();app.include_router(create_growth_router(str(self.path),self.culture))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as other: self.assertEqual(len((await other.get(BASE)).json()['packages']),1)
        self.assertEqual((await self.send('POST','/campaigns/'+c['id']+'/metrics',{**metric,'views':-1})).status_code,422)

    async def test_context_current_fact_and_catalog_plan_not_current_claim(self):
        refs=[dict(title='合成出处',locator='测试定位',evidence_status='user_confirmed')]
        context=dict(version=1,products=[dict(id='CURRENT',title='当前',summary='住宿与文化体验现成可咨询',status='user_confirmed',source_refs=refs),dict(id='SYN-PLAN',title='合成纸伞路线',summary='仅目录中的纸伞创意路线',experience_items=['试拍纸伞'],status='LOCAL_IMPLEMENTED_CATALOG',source_refs=refs,conditions=['待确认交付'])],materials=[],facts=[],missing=[])
        target=self.path.parent/'yantian-growth-context.json';target.write_text(json.dumps(context))
        c=await self.campaign(product_summary='住宿＋SYN-PLAN合成纸伞路线');p=await self.compile(c,duration_seconds=60)
        self.assertIn('现成可咨询',p['materials']['voiceover']);self.assertNotIn('纸伞',p['materials']['voiceover']);self.assertIn('纸伞',json.dumps(p['materials']['storyboard'],ensure_ascii=False));self.assertEqual(p['materials']['planning_references'][0]['id'],'SYN-PLAN')
        self.assertIn('本机目录已整合',(await self.snap())['business_facts']['experience_details_state']);await self.review(p);context['version']=2;target.write_text(json.dumps(context));self.assertFalse((await self.snap())['packages'][0]['approval_valid'])

if __name__=='__main__': unittest.main()
