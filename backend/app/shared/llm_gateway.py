"""官方大模型网关：Kimi / DeepSeek 的统一传输层。

负责 provider 端点路由（含 Kimi 会员订阅 Key 的 Anthropic 兼容端点自动识别）、
协议差异（OpenAI chat completions vs Anthropic messages）、鉴权与错误细分
（llm_auth_invalid / llm_timeout / llm_invalid_response）。业务语义（视觉门禁、
prompt、结构校验）由各调用方自己负责。
"""
import base64
import json

import httpx

from .errors import Error

ENDPOINTS = {
    'kimi': 'https://api.moonshot.cn/v1/chat/completions',
    'deepseek': 'https://api.deepseek.com/chat/completions',
}
# Kimi 会员订阅（Kimi Code 控制台）发放的 sk-kimi- Key 走 Anthropic 兼容协议。
KIMI_SUBSCRIPTION_ENDPOINT = 'https://api.kimi.com/coding/v1/messages'
KIMI_SUBSCRIPTION_PREFIX = 'sk-kimi-'
SUPPORTED_MODELS = {
    'kimi': ['kimi-latest', 'kimi-k3.1-pro', 'kimi-k3.1-pro-highspeed',
             'kimi-k3', 'kimi-k2.8'],
    'deepseek': ['deepseek-chat'],
}

MAX_RESPONSE_BYTES = 64 * 1024


class OfficialLlmClient:
    """values 为 llm 设置分类的字典（provider/api_key/model/timeout_seconds）。"""

    def __init__(self, values: dict, *, transport=None):
        self.values = values
        self.transport = transport

    def resolve(self):
        """-> (endpoint, model, key, protocol, provider)；缺配置抛 llm_* 错误。"""
        provider = str(self.values.get('provider') or 'kimi')
        model = str(self.values.get('model') or '').strip()
        key = str(self.values.get('api_key') or '').strip()
        endpoint = ENDPOINTS.get(provider)
        if endpoint is None:
            raise Error(422, 'llm_provider_invalid', '大模型官方来源仅支持 Kimi 与 DeepSeek。')
        if not key:
            raise Error(422, 'llm_not_configured',
                        '请先在系统设置的大模型接口中填写 API Key。')
        if not model:
            raise Error(422, 'llm_model_required', '请先在系统设置中选择大模型模型。')
        if provider == 'kimi' and key.startswith(KIMI_SUBSCRIPTION_PREFIX):
            return KIMI_SUBSCRIPTION_ENDPOINT, model, key, 'anthropic', provider
        return endpoint, model, key, 'openai', provider

    def image_content(self, jpegs: list[bytes]):
        """JPEG 字节 → 当前协议的内容块列表（Anthropic image / OpenAI image_url）。"""
        _endpoint, _model, _key, protocol, _provider = self.resolve()
        encoded = [base64.b64encode(jpeg).decode('ascii') for jpeg in jpegs]
        if protocol == 'anthropic':
            return [{'type': 'image',
                     'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': data}}
                    for data in encoded]
        return [{'type': 'image_url',
                 'image_url': {'url': 'data:image/jpeg;base64,' + data}} for data in encoded]

    def chat(self, *, system: str, user, max_tokens: int = 2048, payload_extra=None) -> str:
        """一次非流式对话。user 为字符串（纯文本）或内容块列表（含图像）。

        返回助手文本。两个协议都按 JSON 输出约束：OpenAI 用 response_format，
        Anthropic 依赖 prompt 约束（其端点不支持 response_format）。
        """
        endpoint, _model, key, protocol, _provider = self.resolve()
        if protocol == 'anthropic':
            payload = {'model': _model, 'max_tokens': max_tokens,
                       'system': system,
                       'messages': [{'role': 'user', 'content': user}]}
        else:
            payload = {'model': _model, 'stream': False, 'temperature': 0,
                       'response_format': {'type': 'json_object'},
                       'messages': [{'role': 'system', 'content': system},
                                    {'role': 'user', 'content': user}]}
            if payload_extra:
                payload.update(payload_extra)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key,
                   'Accept-Encoding': 'identity'}
        if protocol == 'anthropic':
            headers['x-api-key'] = key
            headers['anthropic-version'] = '2023-06-01'
        timeout = int(self.values.get('timeout_seconds') or 60)
        try:
            with httpx.Client(transport=self.transport,
                              timeout=httpx.Timeout(timeout, connect=10),
                              follow_redirects=False, trust_env=False) as client:
                with client.stream('POST', endpoint, content=encoded, headers=headers) as response:
                    if response.status_code in (401, 403):
                        raise Error(401, 'llm_auth_invalid',
                                    'API Key 未被该官方接口认可，请在系统设置中核对大模型接口配置。')
                    if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                        raise Error(502, 'llm_bad_encoding', '大模型接口返回了意外的内容编码。')
                    if response.status_code != 200:
                        raise Error(502, 'llm_invalid_response',
                                    '大模型接口暂时无法返回有效结果，请稍后重试。', retryable=True)
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise Error(502, 'llm_invalid_response',
                                        '大模型接口返回内容超过安全限制。')
                        body.extend(chunk)
            envelope = json.loads(body)
            if protocol == 'anthropic':
                blocks = envelope['content']
                content = ''.join(block['text'] for block in blocks
                                  if isinstance(block, dict) and block.get('type') == 'text')
            else:
                content = envelope['choices'][0]['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ValueError('Expected JSON text')
            return content
        except Error:
            raise
        except httpx.TimeoutException:
            raise Error(504, 'llm_timeout', '大模型接口请求超时，请稍后重试。', retryable=True) from None
        except httpx.HTTPError:
            raise Error(502, 'llm_invalid_response', '大模型接口连接失败，请稍后重试。',
                        retryable=True) from None
