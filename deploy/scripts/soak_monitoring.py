"""Observe existing real monitoring runs without restarting or repairing them.

Example: python deploy/scripts/soak_monitoring.py --agent ID --seconds 600 --output var/soak.json
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', action='append', required=True)
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    origin = 'http://127.0.0.1:8000'
    def request(path, method='GET', json_result=True):
        req = urllib.request.Request(origin + '/api/v1' + path, method=method,
            headers={'Origin': origin})
        with http.open(req, timeout=10) as response:
            body = response.read()
            return json.loads(body) if json_result else body
    start = time.monotonic()
    report = {'started_at':datetime.now(timezone.utc).isoformat(), 'required_seconds':args.seconds,
              'runs':{}, 'samples':[], 'failures':[], 'probe_jobs':[]}
    for agent in args.agent:
        runs = request(f'/agents/{agent}/workspace')['runs']
        active = [r for r in runs if r['state']=='running']
        if not active:
            raise RuntimeError(f'Agent {agent} has no running inference to observe')
        report['runs'][agent] = [{'id':r['id'],'source_id':r['source_id']} for r in active]
    next_media = 0
    probes = {30:False, 330:False}
    try:
        while True:
            elapsed = time.monotonic()-start
            sample = {'elapsed_seconds':round(elapsed,2), 'runs':[], 'media':[]}
            try:
                for agent, expected in report['runs'].items():
                    runs = {r['id']:r for r in request(f'/agents/{agent}/workspace')['runs']}
                    for pinned in expected:
                        run = runs.get(pinned['id'])
                        if not run or run['state']!='running':
                            raise RuntimeError(f'Pinned run changed state: {pinned["id"]} / {run and run["state"]} / {run and run.get("error_code")}')
                        playback = request(f'/agents/{agent}/runs/{run["id"]}/playback','POST')
                        stamp = playback.get('observed_at')
                        age = (datetime.now(timezone.utc)-datetime.fromisoformat(stamp.replace('Z','+00:00'))).total_seconds() if stamp else float('inf')
                        if age>10:
                            raise RuntimeError(f'Inference observation stalled for {age:.1f} seconds: {run["id"]}')
                        sample['runs'].append({'id':run['id'],'state':run['state'],'observed_at':stamp,
                            'observation_age_seconds':round(age,2),'target_count':len(playback.get('targets',[])),
                            'message':run['message']})
                        if elapsed>=next_media:
                            root = f'/sources/{pinned["source_id"]}/live/'
                            master = request(root+'index.m3u8',json_result=False).decode()
                            child = next(line for line in master.splitlines() if line and not line.startswith('#'))
                            if not child.startswith('/api/v1/'):
                                raise RuntimeError('Unexpected media playlist scope')
                            playlist = request(child.removeprefix('/api/v1'),json_result=False).decode()
                            segments = [line for line in playlist.splitlines() if line and not line.startswith('#')]
                            segment = segments[-1]
                            media = request(segment.removeprefix('/api/v1'),json_result=False)
                            if len(media)<100:
                                raise RuntimeError('Live media segment is empty')
                            sample['media'].append({'source_id':pinned['source_id'],'segment_bytes':len(media)})
                for threshold,done in probes.items():
                    if elapsed>=threshold and not done:
                        for expected in report['runs'].values():
                            for run in expected:
                                job = request(f'/sources/{run["source_id"]}/tests','POST')
                                report['probe_jobs'].append({'elapsed':round(elapsed,2),'id':job['id']})
                        probes[threshold] = True
                if elapsed>=next_media: next_media = elapsed+30
            except Exception as error:
                report['failures'].append({'elapsed_seconds':round(elapsed,2),'error':str(error)})
                raise
            finally:
                report['samples'].append(sample)
                report['elapsed_seconds'] = round(time.monotonic()-start,2)
                report['passed'] = report['elapsed_seconds']>=args.seconds and not report['failures']
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps({'elapsed':round(elapsed,1),'states':[r['state'] for r in sample['runs']],
                'media_checks':len(sample['media']),'failures':len(report['failures'])}),flush=True)
            if elapsed>=args.seconds: break
            time.sleep(min(5,max(0,args.seconds-(time.monotonic()-start))))
    finally:
        print('Report: '+str(args.output),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
