"""HTTP 端到端流程测试：uvicorn + SQLite（无 Redis 依赖路径）。

覆盖：种子数据 → 两份研究完成 → 发起对照 → 结论与采用版本 →
客群并发更新时受理对照锁定同版分组/占比/组合限制 → 冲突版本报告 → 权限与校验。

运行：python3 test_http.py  （自动启动/停止本地 uvicorn，端口 19299）
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:19299'
WORK = '/tmp/gb45-http'
BACKEND = '/workspace/backend'
PASS = []


def check(name, cond, extra=''):
    assert cond, f'FAIL {name} {extra}'
    PASS.append(name)
    print('  ✓', name)


def req(method, path, body=None, token=None, expect=None):
    r = urllib.request.Request(BASE + path, method=method)
    if body is not None:
        r.add_header('Content-Type', 'application/json')
        r.data = json.dumps(body).encode()
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r) as resp:
            code, data = resp.status, json.loads(resp.read() or b'null')
    except urllib.error.HTTPError as e:
        code, data = e.code, json.loads(e.read() or b'null')
    if expect is not None:
        check(f'{method} {path} -> {expect}', code == expect, f'got {code}: {str(data)[:200]}')
    return code, data


def wait_up():
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE + '/catalog', timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK + '/artifacts')
    env = dict(os.environ, DATABASE_URL=f'sqlite:///{WORK}/test.db',
               ARTIFACT_DIR=WORK + '/artifacts', SEED_DEMO='true',
               JWT_SECRET='gb45-test-secret', REDIS_URL='redis://127.0.0.1:1/0')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'src.main:app',
                               '--host', '127.0.0.1', '--port', '19299'],
                              cwd=BACKEND, env=env,
                              stdout=open(WORK + '/server.log', 'w'), stderr=subprocess.STDOUT)
    try:
        if not wait_up():
            raise RuntimeError('server did not start; see ' + WORK + '/server.log')
        print('server up')
        # 先登录拿 token；种子任务由独立 worker 计算（本地无 Redis，直接调用 worker.execute）
        code, login = req('POST', '/auth/login',
                          {'email': 'admin@exhibit-neighbors.demo', 'password': 'Research2026!'}, expect=200)
        token = login['token']
        code, runs = req('GET', '/runs', token=token, expect=200)
        check('种子两份研究', len([r for r in runs if r['state'] == 'queued']) >= 2, runs)
        ids = sorted(r['id'] for r in runs)[:2]
        for rid in ids:
            subprocess.run([sys.executable, '-c',
                            f'from src.worker import execute;execute({rid})'],
                           cwd=BACKEND, env=env, check=True)
        code, runs = req('GET', '/runs', token=token, expect=200)
        done = {r['id']: r for r in runs if r['state'] == 'completed'}
        check('两份研究均完成', all(i in done for i in ids), [r['state'] for r in runs])
        a, b = ids[0], ids[1]

        # 客群当前版本
        code, aud = req('GET', '/audience', token=token, expect=200)
        check('种子客群版本v1', aud['current'] and aud['current']['id'] == 1, aud.get('current'))
        check('客群分组与限制', len(aud['current']['payload']['age_groups']) == 4
              and len(aud['current']['payload']['visit_methods']) == 3
              and len(aud['current']['payload']['forbidden']) == 2)

        # 发起对照
        code, comp = req('POST', '/comparisons', {'run_a_id': a, 'run_b_id': b, 'name': '冬季对照'}, token=token, expect=200)
        check('对照锁定v1', comp['profile_version'] == 1, comp.get('profile_version'))
        check('结论字段齐全', comp['verdict'] in ('a_better', 'b_better', 'inconclusive', 'infeasible')
              and 'bounds' in comp['result'] and 'achieving' in comp['result'])
        check('配对40条留出记录', comp['result']['pairs'] == 40, comp['result']['pairs'])
        check('含无配对组范围标注', any((not c['observed']) and (not c['forbidden']) for c in comp['result']['cells']))
        if comp['result']['bounds']:
            lo, hi = comp['result']['bounds']['lower'], comp['result']['bounds']['upper']
            check('界有序', lo <= hi + 1e-9)
            if lo > 0:
                check('界正判B准', comp['verdict'] == 'b_better')
            elif hi < 0:
                check('界负判A准', comp['verdict'] == 'a_better')
            else:
                check('含零不判胜负', comp['verdict'] == 'inconclusive')
        code, detail = req('GET', f"/comparisons/{comp['id']}", token=token, expect=200)
        check('详情回读同版快照', detail['profile_snapshot'] == aud['current']['payload'])

        # 并发：客群更新与对照受理同时发生，每份对照必须锁定单一同版数据
        errors = []

        def bump(i):
            try:
                p = json.loads(json.dumps(aud['current']['payload']))
                p['age_groups'][0]['share'] = round(0.2 + 0.01 * (i % 5), 2)
                p['age_groups'][1]['share'] = round(1.0 - p['age_groups'][0]['share'] - 0.23 - 0.15, 2)
                req('POST', '/audience', {'name': f'并发版本{i}', **p}, token=token, expect=200)
            except Exception as e:
                errors.append(('audience', i, e))

        def compare(i):
            try:
                req('POST', '/comparisons', {'run_a_id': a, 'run_b_id': b, 'name': f'并发对照{i}'}, token=token, expect=200)
            except Exception as e:
                errors.append(('compare', i, e))

        threads = [threading.Thread(target=f, args=(i,)) for i in range(8) for f in (bump, compare)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        check('并发请求无异常', not errors, errors[:3])
        code, comps = req('GET', '/comparisons', token=token, expect=200)
        code, aud2 = req('GET', '/audience', token=token, expect=200)
        payloads = {}
        for v in aud2['versions']:
            c, d = req('GET', f"/audience/{v['id']}", token=token, expect=200)
            payloads[v['id']] = d['payload']
        mismatches = []
        for c in comps:
            c, d = req('GET', f"/comparisons/{c['id']}", token=token, expect=200)
            if d['profile_snapshot'] != payloads[d['profile_version']]:
                mismatches.append(d['id'])
        check('并发下每份对照均为同版锁定数据', not mismatches, mismatches)
        used = {c['profile_version'] for c in comps}
        check('并发产生了多版本且被各自锁定', len(used) >= 2, used)

        # 冲突版本：两侧合计不等 → 对照报告冲突
        bad = json.loads(json.dumps(aud2['current']['payload']))
        bad['visit_methods'][0]['share'] = 0.9
        code, bv = req('POST', '/audience', {'name': '冲突版本', **bad}, token=token, expect=200)
        code, bc = req('POST', '/comparisons', {'run_a_id': a, 'run_b_id': b, 'name': '冲突对照'}, token=token, expect=200)
        check('无可行构成指出冲突', bc['verdict'] == 'infeasible' and bc['result']['conflicts'], bc['result'].get('conflicts'))
        check('冲突含类型与说明', all('type' in c and 'message' in c for c in bc['result']['conflicts']))

        # 权限与校验
        code, viewer = req('POST', '/auth/login', {'email': 'viewer@exhibit-neighbors.demo', 'password': 'Research2026!'}, expect=200)
        req('POST', '/comparisons', {'run_a_id': a, 'run_b_id': b, 'name': '越权对照'}, token=viewer['token'], expect=403)
        req('POST', '/audience', {'name': '越权版本'}, token=viewer['token'], expect=403)
        req('GET', '/comparisons', expect=401)
        req('POST', '/comparisons', {'run_a_id': a, 'run_b_id': a, 'name': '同研究'}, token=token, expect=422)
        req('POST', '/comparisons', {'run_a_id': a, 'run_b_id': 99999, 'name': '不存在'}, token=token, expect=404)
        req('POST', '/audience', {'name': '坏版本', 'age_groups': [{'key': 'a', 'label': 'a', 'share': -1}],
                                  'visit_methods': [{'key': 'm', 'label': 'm', 'share': 1}]}, token=token, expect=422)
        req('GET', '/comparisons/99999', token=token, expect=404)
    finally:
        server.terminate()
        server.wait(timeout=10)
    print(f'HTTP 流程全部通过：{len(PASS)} 项')


if __name__ == '__main__':
    main()
