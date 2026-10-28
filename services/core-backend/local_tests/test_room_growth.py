"""Synthetic source-window bindings, material provenance and stale approvals."""
import copy
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.local_os.growth import create_growth_router

BASE='/api/local-os/growth'

class RoomGrowthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        folder=tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/'operations.sqlite3'
        self.source={'id':'rs-synthetic-v1', 'source':{'filename':'synthetic.xlsx','sha256':'a'*64},
                     'room_capacity':{'source_reported_total':28},
                     'opportunities':[{'id':'window-zero', 'start_date':'2099-11-14', 'end_date':'2099-11-14',
                                       'kind':'ALL_TYPES_ZERO', 'days':1, 'room_types':['双床','大床'],
                                       'source_cells':['J4','J5'], 'verification_required':True}]}
        self.latest=self.source
        self.patcher=patch('app.local_os.room_status.read_room_status_snapshot',side_effect=self.read_source)
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        app=FastAPI();app.include_router(create_growth_router(str(self.path)))
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver')
        self.addAsyncCleanup(self.client.aclose)

    def read_source(self, path, snapshot_id=None):
        return copy.deepcopy(self.latest if snapshot_id is None else self.source if snapshot_id==self.source['id'] else None)

    def brief(self):
        return dict(title='隔离日期任务', audience='测试受众假设', product_summary='住宿与文化体验待核提纲',
                    objective='日期咨询', primary_channel='direct', source_code='SYN-ZERO-WINDOW', notes='',
                    room_status_ref={'snapshot_id':self.source['id'],'opportunity_id':'window-zero'})

    async def test_reference_validation_exact_provenance_and_replay(self):
        bad=self.brief();bad['room_status_ref']['opportunity_id']='unknown-or-tentative'
        r=await self.client.post(BASE+'/campaigns',json=bad); self.assertEqual(r.status_code,422)
        r=await self.client.post(BASE+'/campaigns',json=self.brief());self.assertEqual(r.status_code,200,r.text)
        c=r.json(); payload=dict(base_version=1,angle='stay',duration_seconds=30,knowledge_ids=[],asset_ids=[],notes='')
        r=await self.client.post(BASE+'/campaigns/'+c['id']+'/compile',json=payload);self.assertEqual(r.status_code,200,r.text)
        p=r.json();self.assertEqual(p['room_status_context']['source']['sha256'],'a'*64)
        self.assertIn('11月14日',p['materials']['voiceover'])
        self.assertNotIn('380',p['materials']['voiceover'])
        self.assertNotIn('零预订',p['materials']['channel_copy']['xiaohongshu'])
        self.assertIn('source_cells',p['materials']['task_brief']['room_window'])
        self.assertFalse(p['distribution_ready']);self.assertEqual(p['provider_calls'],[])
        replay=await self.client.post(BASE+'/campaigns/'+c['id']+'/compile',json=payload)
        self.assertEqual(replay.json()['id'],p['id'])
        z=zipfile.ZipFile(io.BytesIO((await self.client.get(p['export_url'])).content))
        self.assertIn('synthetic.xlsx',z.read('出处与使用清单.md').decode())
        self.assertIn('J4',z.read('任务简报.json').decode())

    async def test_new_source_invalidates_approval_and_stops_old_compilation(self):
        c=(await self.client.post(BASE+'/campaigns',json=self.brief())).json()
        payload=dict(base_version=1,angle='stay',duration_seconds=15,knowledge_ids=[],asset_ids=[],notes='')
        p=(await self.client.post(BASE+'/campaigns/'+c['id']+'/compile',json=payload)).json()
        r=await self.client.post(BASE+'/packages/'+p['id']+'/reviews',json=dict(package_hash=p['hash'],decision='approve',note='合成测试声明',confirmations=dict(facts=True,rights=True,delivery=True)))
        self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['package']['approval_valid'])
        self.latest={**self.source,'id':'rs-synthetic-v2'}
        data=(await self.client.get(BASE)).json();self.assertFalse(data['packages'][0]['approval_valid'])
        self.assertTrue(any('房态来源版本已更新' in b for b in data['packages'][0]['blockers']))
        r=await self.client.post(BASE+'/campaigns/'+c['id']+'/compile',json=payload);self.assertEqual(r.status_code,409)
