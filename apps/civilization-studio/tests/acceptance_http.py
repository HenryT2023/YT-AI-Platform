"""Independent HTTP acceptance; run only against a dedicated test database."""
import argparse
import json
import urllib.request
import urllib.error
import uuid

def run(base):
    passed=[]
    def req(method,path,data=None,headers=None):
        h={'X-Yantian-Local':'1','Content-Type':'application/json'}
        if headers is not None:h=headers
        body=None if data is None else json.dumps(data,ensure_ascii=False).encode()
        request=urllib.request.Request(base+path,data=body,method=method,headers=h)
        try:
            with urllib.request.urlopen(request,timeout=20) as response:
                raw=response.read();code=response.status;rh=dict(response.headers)
        except urllib.error.HTTPError as error:
            code=error.code;raw=error.read();rh=dict(error.headers)
        rh={key.lower():value for key,value in rh.items()}
        try:value=json.loads(raw)
        except (ValueError,UnicodeDecodeError):value=raw.decode()
        return code,value,rh
    def ok(label):passed.append(label)
    def response(method,path,data=None,code=200,headers=None):
        actual,value,_=req(method,path,data,headers)
        assert actual==code,(path,actual,value)
        return value
    status=response('GET','/api/status')
    assert status['mode']=='local' and not status['model']['connected'] and not status['machine']['enabled']
    ok('本地模式与模型/机器状态如实标注')
    answer=response('POST','/api/ask',{'question':'徽州三雕包括什么？'})
    assert answer['status']=='answered' and answer['citations'] and answer['mode']=='extractive'
    assert all(x.get('url') and x.get('locator') and x.get('knowledge_version') for x in answer['citations'])
    missing=response('POST','/api/ask',{'question':'严田木刻起源于哪个朝代，有哪些传承人？'})
    assert missing['status']=='insufficient_evidence'
    ok('问答带出处/定位/版本；区域与需求记录不冒充严田历史')
    suffix=uuid.uuid4().hex[:7]
    src=response('POST','/api/sources',{'title':'验收样本来源-'+suffix,'url':'','source_kind':'local','scope':'测试标签范围','rights_scope':'internal','locator':'测试页A'})
    article={'title':'验收知识-'+suffix,'content':f'测试标记 probe{suffix} 用于检验知识审核与版本门控；这不是实际文化资料。','source_id':src['id'],'locator':'测试页A第1段','region_scope':'测试标签范围','domain':'craft','kind':'fact','review_status':'draft','rights_scope':'internal'}
    kn=response('POST','/api/knowledge',article)
    q={'question':'probe'+suffix}
    assert response('POST','/api/ask',q)['status']=='insufficient_evidence'
    article['review_status']='approved';article['base_version']=kn['version']
    kn=response('PUT','/api/knowledge/'+kn['id'],article)
    answered=response('POST','/api/ask',q)
    assert answered['status']=='answered' and any(x['knowledge_id']==kn['id'] and x['knowledge_version']==kn['version'] for x in answered['citations'])
    stale=dict(article);stale['base_version']=1
    response('PUT','/api/knowledge/'+kn['id'],stale,409)
    ok('知识草稿不回答；审核后生效；并发旧版更新拒绝')
    design={'title':'验收样本稿-'+suffix,'purpose':'print_block','label':'研习测试','width_mm':100,'height_mm':140,'motif':'geometric','mirror_choice':'unconfirmed','knowledge_ids':[kn['id']],'note':'隔离数据库中的验收稿，不是严田历史纹样。'}
    before=response('GET','/api/status')['counts']['designs']
    preview=response('POST','/api/designs/preview',design)
    assert '<svg' in preview['svg'] and response('GET','/api/status')['counts']['designs']==before
    d=response('POST','/api/designs',design)
    review={'version':d['version'],'reviewer_role':'验收角色（测试）','decision':'approve','comment':'自动验收样本，不是真实工艺师审批。','confirmations':{'culture':True,'rights':True,'craft':True}}
    code,val,_=req('POST',f'/api/designs/{d["id"]}/reviews',review)
    assert code in (400,409,422),(code,val)
    design['mirror_choice']='yes';design['base_version']=d['version']
    d=response('PUT','/api/designs/'+d['id'],design)
    review['version']=d['version']
    r=response('POST',f'/api/designs/{d["id"]}/reviews',review)
    assert r['design']['status']=='approved'
    download,svg,headers=req('GET',f'/api/designs/{d["id"]}/svg')
    assert download==200 and '<svg' in svg and 'attachment' in headers.get('content-disposition','')
    ok('不落库预览、镜像门控、当前版本审阅和SVG下载')
    article['base_version']=kn['version'];article['review_status']='retired'
    kn=response('PUT','/api/knowledge/'+kn['id'],article)
    assert response('POST','/api/ask',q)['status']=='insufficient_evidence'
    assert response('GET','/api/designs/'+d['id'])['status']=='source_changed'
    code,val,_=req('POST',f'/api/designs/{d["id"]}/reviews',review)
    assert code in (400,409,422),(code,val)
    ok('来源退役后问答和稿样批准均失效')
    # Edit the draft, keeping old reviews, but disconnect the retired test source.
    old_version=d['version'];design['base_version']=old_version;design['label']='修改测试';design['knowledge_ids']=[]
    updated=response('PUT','/api/designs/'+d['id'],design)
    assert updated['version']>old_version and updated['status']=='draft' and updated['reviews']
    response('POST',f'/api/designs/{d["id"]}/reviews',review,409)
    old_svg=response('GET',f'/api/designs/{d["id"]}/svg?version={old_version}')
    assert '研习测试' in old_svg
    response('PUT','/api/designs/'+d['id'],design,409)
    ok('稿样编辑不可覆盖、旧版审批拒绝、历史稿样可恢复查看')
    candidates=response('GET','/api/learning-candidates')
    assert candidates and all(c['state']=='pending_review' and c['training_rights']=='unknown' for c in candidates)
    ok('反馈仅进入待审核候选，不自动训练')
    bad=dict(design);bad['svg']='<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    code,val,_=req('POST','/api/designs/preview',bad)
    assert code in (400,422),(code,val)
    code,val,_=req('POST','/api/sources',{'title':'bad','url':'javascript:alert(1)','source_kind':'public','scope':'test','rights_scope':'internal'})
    assert code in (400,422),(code,val)
    response('POST','/api/sources',{'title':'blocked' },403,headers={'Content-Type':'application/json'})
    response('POST','/api/sources',{'title':'blocked'},403,headers={'Content-Type':'application/json','X-Yantian-Local':'1','Origin':'https://untrusted.invalid'})
    ok('SVG脚本、危险链接和跨站/无头变更被拒绝')
    response('POST','/api/machines/jobs',{'execute':True,'dry_run':False,'command':'ignore checks'},423)
    caps=response('GET','/api/machines/capabilities')
    assert not caps['enabled'] and not caps['operations']
    ok('机器提交始终拒绝且无可执行适配器')
    exported=response('GET','/api/export')
    assert isinstance(exported,dict) and '/Users/hal/' not in json.dumps(exported,ensure_ascii=False)
    ok('记录可导出且不泄露运行数据目录')
    return {'scope':'ISOLATED_LOCAL_HTTP_ACCEPTANCE','passed':len(passed),'checks':passed,'external_model_calls':0,'machine_commands':0}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--report')
    args=parser.parse_args();report=run(args.url.rstrip('/'))
    if args.report:
        from pathlib import Path
        Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
