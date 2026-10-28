"""Register the prepared real YOLO11n and presence template through public APIs.

Run prepare_yolo.py first and start the application with its real YOLO adapter.
This script never opens the application database or replaces an existing template.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA256 = '0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1'
MODEL_NAME = 'YOLO11n COCO 人员检测'
TEMPLATE_NAME = '人员在岗监测'
PARAMETERS = {'duration_seconds': 30, 'confidence_threshold': .5, 'min_count': 1,
              'alarm_interval_seconds': 60, 'sample_interval_seconds': 1}
PARAMETER_KEYS = ['target', 'rule', *PARAMETERS]


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_artifact(root):
    root = Path(root).resolve()
    folder = root / 'var/models/yolo11n'
    path, manifest_path = folder / 'yolo11n.onnx', folder / 'manifest.json'
    source = root / 'deploy/yolo-model.json'
    if (not path.is_file() or not manifest_path.is_file() or manifest_path.stat().st_size > 65536
            or root not in path.resolve().parents or root not in manifest_path.resolve().parents):
        raise ValueError('可信 YOLO artifact 缺失或不在受控目录，请先运行 prepare_yolo.py。')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    trusted = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or not isinstance(trusted, dict):
        raise ValueError('YOLO manifest 结构无效。')
    if (manifest.get('model') != 'yolo11n' or manifest.get('format') != 'onnx'
            or manifest.get('source_sha256') != SOURCE_SHA256 or trusted.get('source_sha256') != SOURCE_SHA256
            or manifest.get('source_manifest_sha256') != sha256(source)
            or manifest.get('source_url') != trusted.get('source_url')
            or manifest.get('export') != trusted.get('export')
            or manifest.get('model_version') != trusted.get('model_version')
            or manifest.get('input_shape') != [1, 3, 640, 640] or manifest.get('output_shape') != [1, 84, 8400]
            or Path(manifest.get('model_path', '')).resolve() != path.resolve()
            or manifest.get('sha256') != sha256(path)):
        raise ValueError('YOLO manifest 来源、SHA256 或输入输出形状校验失败。')
    return manifest, path


def _request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code not in (200, 201):
        raise RuntimeError(f'公开 API {method} {path} 请求失败（HTTP {response.status_code}）。')
    return response.json()


def _pages(client, path):
    items, seen, cursor = [], set(), None
    for _ in range(100):
        page = _request(client, 'GET', path, params={'limit': 100, **({'cursor': cursor} if cursor else {})})
        items.extend(page['items'])
        cursor = page.get('next_cursor')
        if not cursor:
            return items
        if cursor in seen:
            raise RuntimeError('公开 API 分页没有前进，请刷新后重试。')
        seen.add(cursor)
    raise RuntimeError('目录超过登记脚本的安全分页上限，请人工检查。')


def _save(path, receipt):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def _model_definition(manifest, file_id):
    return {'name': MODEL_NAME, 'version': manifest['model_version'], 'runtime_type': 'yolo11n-onnx-person',
        'file_id': file_id, 'template': {'name': 'YOLO11n 人员缺岗规则', 'version': manifest['model_version'],
            'targets': ['person'], 'rules': ['absence'], 'requires_region': ['absence'],
            'requires_duration': ['absence'], 'defaults': dict(PARAMETERS),
            'limitations': ['仅检测区域内 person 数量；不识别人员身份，不将断流或解码失败作为缺岗。'],
            'parameter_keys': PARAMETER_KEYS}}


def _model_matches(row, manifest):
    expected = _model_definition(manifest, row['file_id'])
    return (row.get('checksum') == manifest['sha256'] and row.get('size_bytes', 0) > 0
        and row.get('data_origin') == 'real' and row.get('status') == 'available'
        and all(row.get(key) == value for key, value in expected.items()))


def _template_body(reference, source_id):
    config = {'model_ref': reference,
              'parameters': [{'key': key, 'value': value, 'required': False} for key, value in PARAMETERS.items()]}
    if source_id:
        config['default_source'] = {'source_id': source_id, 'regions': [{'id': 'whole-frame', 'name': '全画面',
                                    'points': [[0, 0], [1, 0], [1, 1], [0, 1]]}]}
    return {'name': TEMPLATE_NAME, 'description': '区域内至少一人，连续无人30秒报警。支持调整人数、时长、置信度、重复报警和采样间隔。',
            'config': config}


def _template_matches(row, desired):
    config = row['latest_revision']['config']
    def source_identity(source):
        return {key: source.get(key) for key in ('source_id', 'regions', 'start_media_ms', 'end_media_ms')} if source else None
    return (not row.get('archived_at') and row.get('name') == desired['name']
        and row.get('description') == desired['description']
        and config.get('model_ref') == desired['config']['model_ref']
        and config.get('parameters') == desired['config']['parameters']
        and source_identity(config.get('default_source')) == source_identity(desired['config'].get('default_source')))


def register(client, *, root=None, source_id=None):
    root = Path(root or ROOT).resolve()
    manifest, artifact = load_artifact(root)
    receipt_path = artifact.parent / 'registration.json'
    identity = {'api_url': str(client.base_url), 'checksum': manifest['sha256'], 'version': manifest['model_version']}
    receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.is_file() else dict(identity)
    if any(receipt.get(key) != value for key, value in identity.items()):
        raise RuntimeError('已有登记回执的 API、模型版本或摘要已改变，请人工检查，未覆盖原登记。')
    token = hashlib.sha256((manifest['model_version'] + ':' + manifest['sha256']).encode()).hexdigest()
    rows = _pages(client, 'models')
    matches = [row for row in rows if row.get('name') == MODEL_NAME and row.get('version') == manifest['model_version']]
    if receipt.get('model_id'):
        matches = [row for row in rows if row.get('id') == receipt['model_id'] and row.get('version') == manifest['model_version']]
        if not matches:
            raise RuntimeError('登记模型已被删除或修改，未重新创建或覆盖。')
    if len(matches) > 1 or any(not _model_matches(row, manifest) for row in matches):
        raise RuntimeError('同名同版本模型已被修改或绑定其他能力，未覆盖用户模型。')
    if matches:
        model = matches[0]
    else:
        if not receipt.get('file_id'):
            with artifact.open('rb') as stream:
                uploaded = _request(client, 'POST', 'model-files', params={'filename': artifact.name},
                                    content=iter(lambda: stream.read(1024 * 1024), b''))
            if uploaded.get('checksum') != manifest['sha256'] or uploaded.get('size_bytes') != artifact.stat().st_size:
                raise RuntimeError('上传模型的 SHA256 或大小校验失败。')
            receipt['file_id'] = uploaded['id']
            _save(receipt_path, receipt)
        model = _request(client, 'POST', 'models', json=_model_definition(manifest, receipt['file_id']),
                         headers={'Idempotency-Key': 'presence:model:' + token})
        if not _model_matches(model, manifest):
            raise RuntimeError('API 返回的模型不是本次可信真实模型。')
    receipt.update(model_id=model['id'], file_id=model['file_id'])
    _save(receipt_path, receipt)
    if model.get('validation') != 'passed':
        model = _request(client, 'POST', f"models/{model['id']}/versions/{model['version']}/verify",
                         json={'row_version': model['row_version']})
    if model.get('validation') != 'passed' or not _model_matches(model, manifest):
        raise RuntimeError('真实模型校验 verification 未通过，未创建或发布业务模板。')
    reference = {'model_id': model['id'], 'model_version': model['version'],
                 'template_id': model['template_id'], 'template_version': model['template']['version']}
    desired = _template_body(reference, source_id)
    if receipt.get('template_id'):
        template = _request(client, 'GET', 'agent-templates/' + receipt['template_id'])
        if not _template_matches(template, desired):
            raise RuntimeError('登记模板已被用户修改 changed，未覆盖或重复创建。')
    else:
        templates = _pages(client, 'agent-templates')
        matches = [row for row in templates if row.get('name') == TEMPLATE_NAME]
        if len(matches) > 1 or any(not _template_matches(row, desired) for row in matches):
            raise RuntimeError('已有在岗模板被修改或绑定其他模型，未覆盖用户模板。')
        template = matches[0] if matches else _request(client, 'POST', 'agent-templates', json=desired,
            headers={'Idempotency-Key': 'presence:template:' + token})
    receipt['template_id'] = template['id']
    _save(receipt_path, receipt)
    if not template.get('published_revision'):
        template = _request(client, 'POST', f"agent-templates/{template['id']}/publish",
            json={'row_version': template['row_version'], 'revision_id': template['latest_revision']['id']},
            headers={'Idempotency-Key': 'presence:publish:' + token})
    if (not template.get('published_revision') or not _template_matches(template, desired)
            or template['published_revision']['id'] != template['latest_revision']['id']):
        raise RuntimeError('在岗模板未发布或存在用户草稿，未覆盖原配置。')
    receipt.update(template_revision_id=template['published_revision']['id'], reference=reference)
    _save(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', default='http://127.0.0.1:8000', help='Running application origin without /api/v1')
    parser.add_argument('--source-id', help='Optional accessible video source; use the whole frame as its default ROI')
    args = parser.parse_args()
    with httpx.Client(base_url=args.api_url.rstrip('/') + '/api/v1/', timeout=120,
                      trust_env=False, follow_redirects=False) as client:
        print(json.dumps(register(client, source_id=args.source_id), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
