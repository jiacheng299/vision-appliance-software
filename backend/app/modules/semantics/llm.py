"""Official LLM APIs for semantic-profile frame analysis.

Kimi (Moonshot) speaks an OpenAI-compatible chat protocol with vision input.
DeepSeek's official chat API has no vision support, so frame analysis refuses
that combination with an explicit error instead of pretending to analyze.
"""
import base64
import json

import httpx
from pydantic import ValidationError, BaseModel, Field, ConfigDict

from ...shared.errors import Error

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
VISION_PROVIDERS = {'kimi'}

ANALYZE_PROMPT = '''你是视觉监测场景的语义画像分析器。用户会给你按时间排序的同一视频源连续画面。
请判断以下动态属性的当前取值，只依据画面中可见的证据，不确定或画面无法支持时该项必须为 null。
可取值必须是简短的英文小写标签（如 bright、rain、night、fixed、dense 等），不要写句子。
只返回 JSON 对象，字段为 lighting（光照）、weather（天气）、season_appearance（季节/着装外观）、
camera_pose（相机姿态，如 fixed/ptz）、background_texture（背景纹理复杂度）、occlusion（明显遮挡比例，
取 none/partial/heavy）。
每个字段为 null 或 {"label": 标签, "confidence": 0到1之间的小数}。'''

ATTRIBUTE_KEYS = ('lighting', 'weather', 'season_appearance', 'camera_pose',
                  'background_texture', 'occlusion')

MAX_RESPONSE_BYTES = 64 * 1024


class _AttributeItem(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class _AnalysisResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lighting: _AttributeItem | None = None
    weather: _AttributeItem | None = None
    season_appearance: _AttributeItem | None = None
    camera_pose: _AttributeItem | None = None
    background_texture: _AttributeItem | None = None
    occlusion: _AttributeItem | None = None


class ProfileLlm:
    def __init__(self, values: dict, *, transport=None):
        self.values = values
        self.transport = transport

    def _settings(self):
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
        if provider not in VISION_PROVIDERS:
            raise Error(422, 'llm_no_vision',
                        'DeepSeek 官方接口暂不支持图像输入；画面分析请选用 Kimi。')
        if provider == 'kimi' and key.startswith(KIMI_SUBSCRIPTION_PREFIX):
            # 会员订阅 Key 走 Anthropic 兼容端点；模型按用户选择原样传递。
            return KIMI_SUBSCRIPTION_ENDPOINT, model, key, 'anthropic'
        return endpoint, model, key, 'openai'

    def analyze_frames(self, jpegs: list[bytes]) -> dict:
        endpoint, model, key, protocol = self._settings()
        if not jpegs or len(jpegs) > 8:
            raise Error(422, 'llm_frame_count_invalid', '画面分析需要 1 到 8 张采样帧。')
        for jpeg in jpegs:
            if not isinstance(jpeg, bytes) or not jpeg.startswith(b'\xff\xd8') \
                    or not jpeg.endswith(b'\xff\xd9'):
                raise Error(422, 'llm_frame_invalid', '采样帧必须是有效 JPEG 数据。')
        if protocol == 'anthropic':
            content = [{'type': 'image', 'source': {'type': 'base64',
                        'media_type': 'image/jpeg',
                        'data': base64.b64encode(jpeg).decode('ascii')}} for jpeg in jpegs]
            payload = {'model': model, 'max_tokens': 2048,
                       'system': ANALYZE_PROMPT,
                       'messages': [{'role': 'user', 'content': content}]}
        else:
            images = [{'type': 'image_url',
                       'image_url': {'url': 'data:image/jpeg;base64,'
                                            + base64.b64encode(jpeg).decode('ascii')}}
                      for jpeg in jpegs]
            payload = {'model': model, 'stream': False, 'temperature': 0,
                       'response_format': {'type': 'json_object'},
                       'messages': [{'role': 'system', 'content': ANALYZE_PROMPT},
                                    {'role': 'user', 'content': images}]}
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
                    if response.status_code != 200 \
                            or response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
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
            result = _AnalysisResult.model_validate_json(content)
            return result.model_dump()
        except Error:
            raise
        except httpx.TimeoutException:
            raise Error(504, 'llm_timeout', '大模型接口请求超时，请稍后重试。', retryable=True) from None
        except httpx.HTTPError:
            raise Error(502, 'llm_invalid_response', '大模型接口连接失败，请稍后重试。',
                        retryable=True) from None
        except (ValidationError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
            raise Error(502, 'llm_invalid_response',
                        '大模型接口返回的画像分析不符合受控结构。') from None
