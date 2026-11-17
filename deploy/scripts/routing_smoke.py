"""Drive the routing state machine against a running local application.

Walks the demonstration path: baseline → refresh → confirmed drift with no
alternative (blocked) → recovery → decision audit, then removes the temporary
profile attribute it created.

Run with Python 3.13 after `start.cmd`:
    .venv/Scripts/python.exe deploy/scripts/routing_smoke.py
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TEXT = {
    'baseline': '建立基线', 'refresh': '无漂移刷新', 'drift': '确认漂移',
    'expiry': '属性过期', 'blocked': '无可行组合', 'cancel': '人工取消',
    'window': '观察窗口',
}


class Client:
    def __init__(self, base):
        self.base = base.rstrip('/')

    def call(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode('utf8')
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode('utf8')
                return response.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as error:
            body = error.read().decode('utf8')
            return error.code, (json.loads(body) if body else None)


def discover(client):
    agents = client.call('GET', '/agents?limit=20')[1].get('items', [])
    for agent in agents:
        detail = client.call('GET', f"/agents/{agent['id']}")[1]
        revision = detail.get('latest_revision') or {}
        for channel in (revision.get('config') or {}).get('channels', []):
            sources = channel.get('sources') or []
            if channel.get('rule') == 'absence' and sources and sources[0].get('regions'):
                return agent, channel, sources[0]['source_id']
    return None, None, None


def describe(tag, status, body, failures):
    if status >= 300:
        print(f'  {tag}: {status} {str(body)[:160]}')
        failures.append(tag)
        return
    print(f"  {tag}: 版本={body['active_version']} 模式={body['mode']} "
          f"成员={body['active_members']} 候选={body['candidate_members']} "
          f"窗口={body['valid_windows']} ΔJ={body['delta_j']}")
    for item in body.get('drift') or []:
        print(f"      漂移 {item['attribute']}: {item['previous']} -> {item['current']}"
              f"（{item['kind']}）")
    for notice in body.get('notices') or []:
        print(f"      说明：{notice}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000/api/v1')
    args = parser.parse_args()
    client = Client(args.base_url)
    failures = []

    agent, channel, source_id = discover(client)
    if agent is None:
        raise SystemExit('没有找到带区域的人员在岗任务；请先创建任务')
    print(f"task: {agent['name']} | channel: {channel['channel_id']} | source: {source_id[:8]}…")

    def attribute(label):
        now = time.time()
        return client.call('PUT', f'/sources/{source_id}/semantic-profile/attributes/lighting',
                           {'value': {'label': label}, 'source_kind': 'frame',
                            'observed_at': now, 'confidence': 0.85,
                            'hard_expiry_at': now + 3600.0})[0]

    def propose():
        return client.call('POST', f"/agents/{agent['id']}/routing/propose",
                           {'channel_id': channel['channel_id'], 'source_id': source_id,
                            'rule': 'absence'})

    print('\n[1] 建立基线')
    attribute('daylight')
    describe('propose', *propose(), failures)

    print('\n[2] 同一场景再次提议')
    describe('propose', *propose(), failures)

    print('\n[3] 新帧确认眩光（本机没有替代能力）')
    attribute('strong_glare')
    status, body = propose()
    describe('propose', status, body, failures)
    if status == 200 and body.get('mode') != 'stable':
        failures.append('眩光且无替代时不应进入候选')

    print('\n[4] 恢复常规场景')
    attribute('daylight')
    describe('propose', *propose(), failures)

    print('\n[5] 决策审计')
    status, rows = client.call('GET', f"/agents/{agent['id']}/routing/decisions?limit=8")
    for row in rows or []:
        print(f"  [{TEXT.get(row['kind'], row['kind']):8s}] {row['action']:7s} "
              f"{row['reason'][:56]}")
    if not any(row['kind'] == 'blocked' for row in rows or []):
        failures.append('审计里应有 blocked 记录')

    print('\n[6] 路由状态')
    status, states = client.call('GET', f"/agents/{agent['id']}/routing")
    for row in states or []:
        if row['source_id'] == source_id:
            print(f"  {row['active_version']} {row['mode']} {row['active_members']}")

    print('\n清理临时属性')
    print('  delete:', client.call('DELETE',
                                  f'/sources/{source_id}/semantic-profile/attributes/lighting')[0])

    if failures:
        print(f'\n失败 {len(failures)} 项：' + '、'.join(failures))
        return 1
    print('\n全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
