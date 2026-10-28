"""Cross-module growth-to-operations acceptance, temporary files only."""
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import httpx
from fastapi import FastAPI
from app.local_os.bridge import culture_service_type
from app.local_os.integration import install_local_os

HEADERS = {'X-Yantian-Local': '1', 'Origin': 'http://testserver'}

class GrowthBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.app = FastAPI()
        install_local_os(self.app, service=culture_service_type()(root/'culture.sqlite3'), operations_db_path=root/'operations.sqlite3')
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://testserver')
        self.addAsyncCleanup(self.client.aclose)

    async def post(self, path, payload):
        r = await self.client.post(path, json=payload, headers=HEADERS)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    async def test_growth_inherits_os_scope_and_origin(self):
        path = '/api/local-os/growth/campaigns'
        payload = dict(title='隔离合成任务', audience='策划假设', product_summary='合成资料', objective='咨询演练',primary_channel='direct',source_code='test-growth',notes='')
        r = await self.client.get('/api/local-os/growth',headers={'X-Site-ID':'other'})
        self.assertEqual(r.status_code,403)
        for headers in [{}, {**HEADERS,'Origin':'https://foreign.invalid'}]:
            r = await self.client.post(path,json=payload,headers=headers)
            self.assertEqual(r.status_code,403)
        r = await self.client.post(path,json={**payload,'tenant_id':'other'},headers=HEADERS)
        self.assertEqual(r.status_code,403)
        self.assertEqual((await self.client.get('/api/local-os/growth')).json()['campaigns'],[])

    async def test_material_export_and_single_source_attribution_use_original_ledger(self):
        before = (await self.client.get('/studio/api/export')).json()
        campaign = await self.post('/api/local-os/growth/campaigns',dict(title='隔离合成住宿任务',audience='待验证受众',product_summary='住宿和文化体验',objective='收集日期咨询',primary_channel='direct',source_code='test-growth',notes='合成测试'))
        package = await self.post(f"/api/local-os/growth/campaigns/{campaign['id']}/compile",dict(base_version=1,angle='stay',duration_seconds=30,knowledge_ids=[],asset_ids=[],notes=''))
        self.assertEqual(package['material_kind'],'production_materials')
        self.assertFalse(package['distribution_ready'])
        self.assertEqual(package['provider_calls'],[])
        self.assertEqual(package['external_side_effects'],[])
        export = await self.client.get(package['export_url'])
        self.assertEqual(export.status_code,200)
        with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
            self.assertIn('字幕.srt',archive.namelist())
            self.assertIn('分镜.csv',archive.namelist())
        lead = await self.post('/api/local-os/operations/inquiries',dict(label='合成测试咨询',channel_id='direct',source_code='test-growth',notes='无真实客户',people=2))
        room = await self.post('/api/local-os/operations/rooms',dict(code='TEST-GROWTH',name='隔离合成房',room_type='合成房型'))
        product = await self.post('/api/local-os/operations/products',dict(title='合成住宿',kind='stay',status='active'))
        order = await self.post('/api/local-os/operations/orders',dict(label='隔离合成订单',product_id=product['id'],room_ids=[room['id']],start_date='2030-01-01',end_date='2030-01-02',amount_cents=38000,channel_id='direct',source_code='test-growth',lead_id=lead['id'],idempotency_key='growth-test-order'))
        await self.post(f"/api/local-os/operations/orders/{order['id']}/payments",dict(amount_cents=38000,receipt_ref='SYNTHETIC-NO-CASH',idempotency_key='growth-test-payment'))
        for _ in range(2):
            snapshot = (await self.client.get('/api/local-os/growth')).json()
            attribution = snapshot['campaigns'][0]['attribution']
            self.assertEqual((attribution['leads_count'],attribution['orders_count'],attribution['net_cash_cents']),(1,1,38000))
            self.assertIsNone(attribution['valid_leads_count'])
            self.assertIsNone(attribution['views'])
        after = (await self.client.get('/studio/api/export')).json()
        self.assertEqual({k:v for k,v in before.items() if isinstance(v,list)}, {k:v for k,v in after.items() if isinstance(v,list)})

if __name__=='__main__': unittest.main()
