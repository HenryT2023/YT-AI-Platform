"""Run only against an isolated local acceptance database, never user records."""
import argparse, json, uuid, urllib.request, urllib.error, urllib.parse
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    assert a.url.startswith('http://127.0.0.1:')
    def call(path,method='GET',body=None,headers=None,expected=200):
        data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
        h={'Content-Type':'application/json','X-Yantian-Local':'1',**(headers or {})}
        req=urllib.request.Request(a.url+path,data=data,headers=h,method=method)
        try:
            with urllib.request.urlopen(req,timeout=10) as r: code=r.status;raw=r.read()
        except urllib.error.HTTPError as e:code=e.code;raw=e.read()
        assert code==expected,(path,code,raw[:800])
        try:return json.loads(raw)
        except ValueError:return raw
    checks=[]
    s=call('/api/local-os/status');assert s['local_os'] and s['canonical_knowledge']['storage']=='single_sqlite' and not s['machines']['enabled'];checks.append('原OS/Core持有唯一文化服务，机器关闭')
    old=call('/api/v1/knowledge');new=call('/studio/api/knowledge')
    assert {(x['id'],x['version']) for x in old}=={(x['id'],x['version']) for x in new};checks.append('旧知识API与工作室读取相同ID和版本')
    token='crossentry'+uuid.uuid4().hex
    source=call('/studio/api/sources','POST',{'title':'跨入口验收资料','url':'','source_kind':'local','scope':'隔离软件验收','rights_scope':'internal','locator':'验收第1项'})
    item=call('/api/v1/knowledge','POST',{'title':token,'content':token+'为本轮创建的软件验收标识，不是文化史实。','source_id':source['id'],'locator':'验收第1项','region_scope':'软件验收','domain':'craft','kind':'fact','review_status':'source_checked','rights_scope':'internal'},expected=201)
    assert any(x['id']==item['id'] for x in call('/studio/api/knowledge'))
    qa=call('/api/local-os/ask','POST',{'question':token});assert any(x['knowledge_id']==item['id'] and x['knowledge_version']==1 for x in qa['citations']);checks.append('原知识入口写入后工作室与NPC问答立即可读')
    payload={k:item[k] for k in ['title','content','source_id','locator','region_scope','domain','kind','review_status','rights_scope']};payload.update(base_version=1,review_status='retired')
    updated=call('/studio/api/knowledge/'+item['id'],'PUT',payload);assert updated['version']==2
    assert call('/api/v1/knowledge/'+item['id'])['version']==2
    assert call('/api/local-os/ask','POST',{'question':token})['status']=='insufficient_evidence'
    call('/api/v1/knowledge/'+item['id'],'PATCH',{'base_version':1,'content':'stale'},expected=409);checks.append('工作室更新立刻影响旧API与问答，旧版更新拒绝')
    call('/api/local-os/ask','POST',{'question':'严田木刻起源于哪个朝代？','site_id':'other'},expected=403)
    call('/api/v1/knowledge',headers={'X-Tenant-ID':'other'},expected=403)
    call('/studio/api/knowledge',headers={'X-Site-ID':'other'},expected=403)
    call('/api/local-os/ask','POST',{'question':'徽州三雕包括什么？'},headers={'Origin':'https://unrelated.invalid'},expected=403);checks.append('别名与挂载入口固定范围、拒绝跨源变更')
    trace=str(uuid.uuid4())
    tool=call('/api/tools/call','POST',{'tool_name':'retrieve_evidence','input':{'query':'徽州三雕包括什么？','top_k':3},'context':{'tenant_id':'yantian','site_id':'yantian-main','trace_id':trace}},headers={'X-Tenant-ID':'yantian','X-Site-ID':'yantian-main','X-Trace-ID':trace})
    assert tool['success'] and tool['output']['items'] and tool['output']['items'][0]['knowledge_version']==1,tool;checks.append('原工具HTTP检索返回统一库版本出处')
    assert call('/api/local-os/ask','POST',{'question':'严田木刻起源于哪个朝代？'})['status']=='insufficient_evidence';checks.append('区域资料不冒充严田具体起源')
    for path in ['/api/v1/iot-devices/any/command','/studio/api/machines/jobs']:
        call(path,'POST',{},expected=423)
    call('/api/v1/search/semantic',expected=423);checks.append('旧设备、新机器及向量外呼入口关闭')
    suffix='?tenant_id=yantian&site_id=yantian-main'
    npcs=call('/api/v1/public/npcs'+suffix);quests=call('/api/v1/public/quests'+suffix)
    assert npcs and npcs[0]['npc_id']=='culture-guide' and '演示' in npcs[0]['display_name'] and quests
    session='acceptance-'+uuid.uuid4().hex
    submission=call('/api/v1/public/quests/'+urllib.parse.quote(quests[0]['quest_id'],safe='')+'/submit','POST',{'tenant_id':'yantian','site_id':'yantian-main','session_id':session,'proof_type':'text','proof_payload':{'answer':'隔离验收记录：核对知识出处。'}})
    assert submission['status']=='submitted',submission
    progress=call('/api/v1/public/quests/progress'+suffix+'&session_id='+session)
    assert any(x['submission_id']==submission['submission_id'] and x['review_status']=='pending' for x in progress['submissions']) and not progress['completed_quest_ids'];checks.append('原研学提交与Redis限流/PG持久化可用，待审不冒充完成')
    export=call('/studio/api/export');assert 'knowledge_versions' in export and 'design_versions' in export and 'reviews' in export;checks.append('统一入口导出包含历史与审阅')
    a.report.write_text(json.dumps({'scope':'ISOLATED_LOCAL_OS_HTTP','passed':len(checks),'checks':checks,'machine_commands':0,'external_model_calls':0},ensure_ascii=False,indent=2))
    print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False))

if __name__=='__main__':main()
