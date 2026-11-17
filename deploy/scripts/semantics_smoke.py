"""Smoke test the semantics endpoints against a running local application.

Checks the three observation verdicts and the "expired becomes unknown" rule on
real sources and a real task. Read-only apart from writing profile attributes and
observation records, which are additive rows the workbench can display.

Run with Python 3.13 after `start.cmd`:
    .venv/Scripts/python.exe deploy/scripts/semantics_smoke.py
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ROI = [[0, 0], [1, 0], [1, 1], [0, 1]]
METRICS = dict(frame_count=30, duration_seconds=30.0, actual_fps=1.0, max_gap_seconds=1.1,
               roi_visible_ratio=1.0, overexposure_ratio=0.03, blur_score=140.0,
               occlusion_ratio=0.0, target_scale_px=48.0)
THRESHOLDS = dict(min_fps=0.9, max_gap_seconds=1.5, min_window_seconds=20.0,
                  min_roi_visible_ratio=0.9, max_overexposure_ratio=0.2,
                  min_blur_score=50.0, max_occlusion_ratio=0.3, min_target_scale_px=24.0)


class Client:
    def __init__(self, base):
        self.base = base.rstrip('/')

    def call(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode('utf8')
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, json.loads(response.read().decode('utf8'))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode('utf8'))


def check(condition, message, failures):
    print(('  ok   ' if condition else '  FAIL ') + message)
    if not condition:
        failures.append(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000/api/v1')
    args = parser.parse_args()
    client = Client(args.base_url)
    failures = []

    status, sources = client.call('GET', '/sources?limit=50')
    cameras = [item for item in sources.get('items', []) if item['kind'] == 'camera']
    status, agents = client.call('GET', '/agents?limit=5')
    tasks = agents.get('items', [])
    if not cameras or not tasks:
        raise SystemExit('需要至少一路摄像头和一个任务；请先启动摄像头资源并创建任务。')
    camera, task = cameras[0], tasks[0]
    print(f'camera: {camera["name"]} | task: {task.get("name")}')

    print('\n[1] 画像可读且不臆造属性')
    status, profile = client.call('GET', f'/sources/{camera["id"]}/semantic-profile')
    check(status == 200 and isinstance(profile['attributes'], list)
          and set(profile) >= {'source_id', 'view_version', 'version', 'intrinsic', 'runtime'},
          f'画像结构完整（当前版本 {profile.get("version")}）', failures)

    print('\n[2] 固有层写入使版本递增')
    before = profile['version']
    status, profile = client.call('PUT', f'/sources/{camera["id"]}/semantic-profile',
                                  {'values': {'resolution': f'{camera["width"]}x{camera["height"]}'}})
    check(status == 200 and profile['version'] == before + 1,
          f'版本 {before} -> {profile["version"]}', failures)

    print('\n[3] 动态属性必须带来源、时刻与有效期')
    observed = time.time() - 2.0
    status, profile = client.call('PUT', f'/sources/{camera["id"]}/semantic-profile/attributes/lighting',
                                  {'value': {'label': 'outdoor_daylight'}, 'source_kind': 'frame',
                                   'observed_at': observed, 'source_frame_ts': 3.5, 'roi': ROI,
                                   'confidence': 0.8, 'tau_seconds': 120.0,
                                   'hard_expiry_at': observed + 600.0})
    attribute = profile['attributes'][0] if status == 200 else {}
    check(attribute.get('state') == 'valid' and attribute.get('usable') is True,
          '属性有效并可用于路由', failures)
    status, profile = client.call('GET', f'/sources/{camera["id"]}/semantic-profile?at={observed + 900}')
    attribute = profile['attributes'][0]
    check(attribute['state'] == 'expired' and attribute['strength'] == 0.0
          and attribute['usable'] is False and attribute['value']['label'] == 'outdoor_daylight',
          '到期后转为未知，不转成相反事实', failures)

    print('\n[4] 三态结论')
    version = client.call('GET', f'/sources/{camera["id"]}/semantic-profile')[1]['version']
    base = dict(source_id=camera['id'], task_key='person/absence', roi=ROI,
                window_start=100.0, window_end=130.0, path_complete=True,
                metrics=dict(METRICS), thresholds=dict(THRESHOLDS),
                versions={'route_version': 'route-1', 'model_version': 'smoke',
                          'profile_version': version})
    cases = [('detected', {'detection_count': 2}),
             ('not_detected', {'detection_count': 0}),
             ('insufficient', {'detection_count': 0,
                               'metrics': dict(METRICS, overexposure_ratio=0.62)}),
             ('insufficient', {'detection_count': 0, 'metrics': dict(METRICS, blur_score=None)})]
    for expected, overrides in cases:
        payload = dict(base, **overrides)
        status, body = client.call('POST', f'/agents/{task["id"]}/observations', payload)
        check(status == 201 and body.get('verdict') == expected,
              f'{overrides} -> {expected}（实际 {body.get("verdict")}）', failures)

    print('\n[5] 观察记录可筛选与分页')
    status, page = client.call('GET', f'/agents/{task["id"]}/observations?limit=3')
    check(status == 200 and page['items'] and page['next_cursor'], '分页游标可用', failures)
    status, filtered = client.call('GET', f'/agents/{task["id"]}/observations?verdict=insufficient')
    check(all(item['verdict'] == 'insufficient' for item in filtered['items']),
          '按结论筛选生效', failures)

    if failures:
        print(f'\n失败 {len(failures)} 项')
        return 1
    print('\n全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
