"""Layer handoff is explicit; plan confirmation is not a video or publication."""
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException
from app.local_os.growth import create_growth_router, create_campaign_from_workspace_plan

class WorkspaceGrowthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'operations.sqlite3'
        app=FastAPI();app.include_router(create_growth_router(str(self.path)))
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver')
        self.addAsyncCleanup(self.client.aclose)
        self.plan={'id':'wsp-synthetic','hash':'a'*64,'version':1,'status':'draft','confirmation_valid':False,'source_stale':False,
                   'source_context':{},'plan':{'title':'合成住宿推广方案','one_line_strategy':'先推广住宿，再咨询文化体验。','objective':'收集日期人数咨询',
                                             'audiences':[{'name':'偏好慢游的人','rationale':'待验证','state':'hypothesis'}],
                                             'offering':{'stay_statement':'住宿＋文化体验为现成产品；具体供给待核。','experience_candidates':[{'id':'SYN-CREATE','title':'合成木刻目录候选'}]},
                                             'channels':[{'id':'xiaohongshu','title':'小红书','readiness':'待开通'}],'checks':['组合报价待核']}}
        mocked=patch('app.local_os.workspace.read_workspace_plan',side_effect=lambda db,identifier: copy.deepcopy(self.plan) if identifier==self.plan['id'] else None)
        mocked.start();self.addCleanup(mocked.stop)

    async def test_confirmed_plan_handoff_only_creates_one_task(self):
        with self.assertRaises(HTTPException) as error:
            create_campaign_from_workspace_plan(str(self.path),self.plan)
        self.assertEqual(error.exception.status_code,409)
        snapshot=(await self.client.get('/api/local-os/growth')).json()
        self.assertEqual(snapshot['campaigns'],[]);self.assertEqual(snapshot['packages'],[])
        self.plan.update(status='confirmed',confirmation_valid=True)
        first=create_campaign_from_workspace_plan(str(self.path),self.plan)
        second=create_campaign_from_workspace_plan(str(self.path),self.plan)
        self.assertTrue(first['created']);self.assertFalse(second['created'])
        self.assertEqual(first['campaign_id'],second['campaign_id']);self.assertFalse(first['scripts_generated'])
        data=(await self.client.get('/api/local-os/growth')).json();self.assertEqual(len(data['campaigns']),1);self.assertEqual(data['packages'],[])
        c=data['campaigns'][0];self.assertEqual(c['workspace_plan_ref'],{'plan_id':self.plan['id'],'plan_hash':self.plan['hash']})
        payload=dict(base_version=1,angle='stay',duration_seconds=30,knowledge_ids=[],asset_ids=[],notes='')
        response=await self.client.post('/api/local-os/growth/campaigns/'+c['id']+'/compile',json=payload)
        self.assertEqual(response.status_code,200,response.text)
        package=response.json();self.assertEqual(package['workspace_plan_context']['plan_hash'],'a'*64)
        self.assertIn('第一层运营方案', '\n'.join(package['materials']['usage_checklist']))
        self.assertIn('组合报价待核',package['materials']['missing_inputs'])
        self.assertFalse(package['approval_valid']);self.assertFalse(package['distribution_ready'])
        self.assertEqual(package['provider_calls'],[]);self.assertEqual(package['external_side_effects'],[])

    async def test_plan_revision_blocks_stale_script_and_approval(self):
        self.plan.update(status='confirmed',confirmation_valid=True)
        task=create_campaign_from_workspace_plan(str(self.path),self.plan)
        path='/api/local-os/growth/campaigns/'+task['campaign_id']+'/compile'
        payload=dict(base_version=1,angle='stay',duration_seconds=15,knowledge_ids=[],asset_ids=[],notes='')
        p=(await self.client.post(path,json=payload)).json()
        response=await self.client.post('/api/local-os/growth/packages/'+p['id']+'/reviews',json=dict(package_hash=p['hash'],decision='approve',note='合成临时库审核',confirmations=dict(facts=True,rights=True,delivery=True)))
        self.assertEqual(response.status_code,200,response.text)
        self.plan.update(confirmation_valid=False,source_stale=True)
        self.assertEqual((await self.client.post(path,json=payload)).status_code,409)
        package=(await self.client.get('/api/local-os/growth')).json()['packages'][0]
        self.assertFalse(package['approval_valid']);self.assertTrue(any('第一层运营方案版本已更新' in value for value in package['blockers']))
