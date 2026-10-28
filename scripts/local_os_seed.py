"""Idempotent configuration for this task's isolated local database only."""
import asyncio
import os
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import select, MetaData, DefaultClause, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, ARRAY
from app.database.engine import async_session_maker, engine
from app.database.models import Tenant, Site, NPCProfile, Quest, QuestStep

async def main():
    if (os.environ.get('LOCAL_OS_MODE') != 'true' or os.environ.get('POSTGRES_PORT') == '5432'
        or os.environ.get('POSTGRES_DB') not in {'yantian_local_os','yantian_local_os_test'} or os.environ.get('POSTGRES_HOST') != '127.0.0.1'):
        raise RuntimeError('Only the dedicated local OS database may be prepared.')
    # The historical Alembic graph has an independent root (p26, down_revision=None)
    # which alters trace_ledger before its initial creation. This bounded local
    # profile builds an isolated runtime schema from the existing model registry;
    # it neither stamps production revisions nor changes that migration graph.
    from app.api import router  # registers all declared original model tables
    from app.database.base import Base
    from app.db.base import Base as LegacyBase
    metadata=MetaData()
    compatibility_defaults=[]
    for registry in (Base.metadata, LegacyBase.metadata):
        for table in registry.tables.values():
            if table.name not in metadata.tables: table.to_metadata(metadata)
            else:
                for col in table.columns:
                    if col.name not in metadata.tables[table.name].c:
                        copied=col._copy()
                        if not copied.nullable and copied.server_default is None and isinstance(copied.type,(JSONB,ARRAY)):
                            value="'{}'::jsonb" if isinstance(copied.type,JSONB) else "'{}'"
                            copied.server_default=DefaultClause(text(value))
                            compatibility_defaults.append((table.name,col.name,value))
                        elif not copied.nullable and copied.server_default is None and copied.default is not None and copied.default.is_scalar:
                            raw=copied.default.arg
                            value=("true" if raw else "false") if isinstance(raw,bool) else (str(raw) if isinstance(raw,(int,float)) else "'"+str(raw).replace("'","''")+"'")
                            copied.server_default=DefaultClause(text(value))
                            compatibility_defaults.append((table.name,col.name,value))
                        metadata.tables[table.name].append_column(copied)
    for table in metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type,PGUUID) and col.server_default is not None and str(col.server_default.arg)=='gen_random_uuid()':
                col.server_default=DefaultClause(text('gen_random_uuid()'))
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        for table,column,value in compatibility_defaults:
            await conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" SET DEFAULT {value}'))
    async with async_session_maker() as session:
        if not await session.get(Tenant,'yantian'):
            session.add(Tenant(id='yantian',name='yantian-local',display_name='严田OS本地研习空间',description='本地软件整合环境，不含实际经营记录。',config={'local_demo':True}))
            await session.flush()
        if not await session.get(Site,'yantian-main'):
            session.add(Site(id='yantian-main',tenant_id='yantian',name='yantian-main',display_name='严田OS本地研习空间',description='用于本地功能验证；角色和任务为演示配置。',config={'local_demo':True}))
            await session.flush()
        if not (await session.execute(select(NPCProfile).where(NPCProfile.npc_id=='culture-guide'))).scalar_one_or_none():
            session.add(NPCProfile(id=str(uuid5(NAMESPACE_URL,'yantian-local-os/culture-guide')),tenant_id='yantian',site_id='yantian-main',npc_id='culture-guide',name='文化资料助手',display_name='文化资料助手（演示角色）',npc_type='teacher',role='演示角色 · 本地知识查证',background='本地软件演示角色，没有实际村民、传承人或个人经历身份。',persona={'extra':{'intro':'从统一文化知识库查找出处；遇到缺失资料会明确说明。','avatar_emoji':'书','color':'from-emerald-700 to-teal-900','local_demo':True}},greeting_templates=['你好，我是本地研习空间的演示资料助手。可以问我“徽州三雕包括什么？”。'],knowledge_domains=['文化资料检索'],must_cite_sources=True))
        quest_id=str(uuid5(NAMESPACE_URL,'yantian-local-os/cited-note'))
        if not await session.get(Quest,quest_id):
            session.add(Quest(id=quest_id,tenant_id='yantian',site_id='yantian-main',name='一份有出处的文化笔记（演示任务）',display_name='一份有出处的文化笔记（演示任务）',description='本地研习演示：在文明工作室查找一条文化知识，记录来源标题与适用范围。本任务不是实际运营活动。',quest_type='learning',category='文化研习',difficulty='easy',estimated_duration_minutes=10,config={'local_demo':True},rewards={}))
            await session.flush()
            session.add(QuestStep(id=str(uuid5(NAMESPACE_URL,'yantian-local-os/cited-note/1')),tenant_id='yantian',site_id='yantian-main',quest_id=quest_id,step_number=1,name='记录知识与出处',description='阅读统一知识库并写明来源、定位及地域范围。',step_type='text',target_config={'local_demo':True},validation_config={}))
        await session.commit()
    await engine.dispose()
    print('Local demo configuration ready; no business/customer records imported.')

if __name__ == '__main__': asyncio.run(main())
