#!/usr/bin/env python3
"""Start the existing OS + mounted studio locally; never use the host business DB."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / 'services/core-backend'
VISITOR = REPO / 'apps/visitor-h5'

def run(args, **kw):
    return subprocess.run([str(x) for x in args], check=True, **kw)

def wait_url(url, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200: return
        except Exception:
            time.sleep(.3)
    raise RuntimeError('本地服务未就绪：' + url)

def free_port(port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: s.bind(('127.0.0.1', port))
        except OSError: raise RuntimeError(f'本地端口{port}已占用；未停止该端口的现有进程。')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'start', 'stop', 'status'])
    p.add_argument('--state-dir', required=True, type=Path)
    p.add_argument('--culture-db', type=Path)
    p.add_argument('--operations-db', type=Path)
    p.add_argument('--port', type=int, default=8791)
    p.add_argument('--core-port', type=int, default=8793)
    p.add_argument('--pg-port', type=int, default=55479)
    p.add_argument('--redis-port', type=int, default=6389)
    p.add_argument('--database', choices=['yantian_local_os','yantian_local_os_test'], default='yantian_local_os')
    p.add_argument('--python', default=str(CORE / '.venv/bin/python'))
    p.add_argument('--python-deps', type=Path, default=REPO.parent / 'os-integration/python-deps')
    a = p.parse_args()
    state = a.state_dir.resolve(); state.mkdir(parents=True, exist_ok=True)
    if a.pg_port == 5432 or a.redis_port == 6379:
        raise RuntimeError('整合版禁止使用已有业务服务的默认端口。')
    pgdata = state / 'postgres'
    owner=state/'local-os-owner'
    if pgdata.exists() and (not owner.exists() or owner.read_text().strip()!='yantian-os-local-v1'):
        raise RuntimeError('未确认该数据库目录归本整合版所有，停止操作。')
    registry = state / 'processes.json'
    pg_ctl = shutil.which('pg_ctl') or '/opt/homebrew/bin/pg_ctl'
    env = os.environ.copy()
    env.update({
        'LOCAL_OS_MODE':'true', 'ENV':'local', 'DEBUG':'false', 'LOG_LEVEL':'WARNING',
        'DATABASE_URL':f'postgresql+asyncpg://yantian_local@127.0.0.1:{a.pg_port}/{a.database}',
        'POSTGRES_HOST':'127.0.0.1','POSTGRES_PORT':str(a.pg_port),'POSTGRES_USER':'yantian_local',
        'POSTGRES_PASSWORD':'','POSTGRES_DB':a.database,
        'REDIS_URL':f'redis://127.0.0.1:{a.redis_port}/0',
        'DEFAULT_TENANT_ID':'yantian','DEFAULT_SITE_ID':'yantian-main',
        'CIVILIZATION_DB_PATH':str((a.culture_db or state / 'civilization.sqlite3').resolve()),
        'OPERATIONS_DB_PATH':str((a.operations_db or state / 'operations.sqlite3').resolve()),
        'FEATURE_IOT_ENABLED':'false', 'QDRANT_ENABLED':'false',
        'OPENAI_API_KEY':'','DASHSCOPE_API_KEY':'','BAIDU_API_KEY':'','BAIDU_SECRET_KEY':'',
        'AI_ORCHESTRATOR_URL':'http://127.0.0.1:1',
        'JWT_SECRET_KEY':secrets.token_urlsafe(48),'INTERNAL_API_KEY':secrets.token_urlsafe(32),
        'NEXT_PUBLIC_LOCAL_OS_MODE':'1', 'YANTIAN_LOCAL_CORE_URL':f'http://127.0.0.1:{a.core_port}',
        'NEXT_PUBLIC_CORE_API_BASE_URL':'','NEXT_PUBLIC_AI_API_BASE_URL':'',
        'NEXT_TELEMETRY_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1',
    })
    env['PYTHONPATH'] = os.pathsep.join([str(a.python_deps.resolve()), str(CORE)])
    if a.action == 'status':
        for role, url in [('os', f'http://127.0.0.1:{a.port}/api/local-os/status'), ('core',f'http://127.0.0.1:{a.core_port}/api/local-os/status')]:
            try: wait_url(url, 1); print(role, 'running')
            except Exception: print(role, 'stopped')
        return
    if a.action == 'stop':
        if registry.exists():
            for item in reversed(json.loads(registry.read_text())):
                try:
                    stamp=subprocess.check_output(['ps','-p',str(item['pid']),'-o','lstart='],text=True).strip()
                    if stamp == item['start_stamp']: os.kill(item['pid'], signal.SIGTERM)
                except (ProcessLookupError, subprocess.CalledProcessError): pass
            registry.unlink()
            time.sleep(.7)
        if (pgdata/'postmaster.pid').exists(): run([pg_ctl,'-D',pgdata,'-w','stop','-m','fast'],stdout=subprocess.DEVNULL)
        print('本整合版服务已停止，工作数据保留。'); return
    if not pgdata.exists():
        free_port(a.pg_port)
        run([shutil.which('initdb') or '/opt/homebrew/bin/initdb','-D',pgdata,'-U','yantian_local','--auth-local=trust','--auth-host=trust','--encoding=UTF8','--locale=C'],stdout=subprocess.DEVNULL)
        owner.write_text('yantian-os-local-v1\n')
    if not (pgdata/'postmaster.pid').exists():
        free_port(a.pg_port)
        run([pg_ctl,'-D',pgdata,'-l',state/'postgres.log','-o',f'-p {a.pg_port} -h 127.0.0.1 -k /tmp -c shared_buffers=32MB -c max_connections=30','-w','start'],stdout=subprocess.DEVNULL)
    # Probe only this process-owned cluster and create its dedicated database.
    psql=shutil.which('psql') or '/opt/homebrew/bin/psql'
    probe=subprocess.check_output([psql,'-h','127.0.0.1','-p',str(a.pg_port),'-U','yantian_local','-d','postgres','-Atc',f"SELECT 1 FROM pg_database WHERE datname='{a.database}'"],text=True).strip()
    if probe != '1': run([shutil.which('createdb') or '/opt/homebrew/bin/createdb','-h','127.0.0.1','-p',str(a.pg_port),'-U','yantian_local',a.database])
    if a.action == 'prepare':
        with (state/'schema-setup.log').open('a') as log:
            run([a.python,REPO/'scripts/local_os_seed.py'],cwd=CORE,env=env,stdout=log,stderr=subprocess.STDOUT)
        print('独立本地业务库已准备；没有连接已有业务库。'); return
    free_port(a.core_port); free_port(a.port); free_port(a.redis_port)
    if not (VISITOR/'.next/BUILD_ID').exists():
        raise RuntimeError('请先以NEXT_PUBLIC_LOCAL_OS_MODE=1构建原游客端。')
    processes=[]
    try:
        commands=[
            ('redis',[shutil.which('redis-server') or '/opt/homebrew/bin/redis-server','--bind','127.0.0.1','--port',str(a.redis_port),'--dir',str(state),'--dbfilename','local-redis.rdb'],REPO),
            ('core',[a.python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(a.core_port)],CORE),
            ('visitor',[shutil.which('node') or 'node',VISITOR/'node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',str(a.port)],VISITOR),
        ]
        for role, cmd, cwd in commands:
            with (state/(role+'.log')).open('a') as log:
                proc=subprocess.Popen([str(x) for x in cmd],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            time.sleep(.15)
            stamp=subprocess.check_output(['ps','-p',str(proc.pid),'-o','lstart='],text=True).strip()
            processes.append({'role':role,'pid':proc.pid,'start_stamp':stamp})
            registry.write_text(json.dumps(processes,indent=2))
        wait_url(f'http://127.0.0.1:{a.core_port}/api/local-os/status')
        wait_url(f'http://127.0.0.1:{a.port}')
    except Exception:
        for item in reversed(processes):
            try: os.kill(item['pid'],signal.SIGTERM)
            except ProcessLookupError: pass
        registry.unlink(missing_ok=True)
        raise
    print(f'严田OS本地整合版：http://127.0.0.1:{a.port}')

if __name__ == '__main__': main()
