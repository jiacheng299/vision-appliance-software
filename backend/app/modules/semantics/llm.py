"""Official LLM APIs for semantic-profile frame analysis.

Kimi (Moonshot) speaks an OpenAI-compatible chat protocol with vision input.
DeepSeek's official chat API has no vision support, so frame analysis refuses
that combination with an explicit error instead of pretending to analyze.
"""
from pydantic import ValidationError, BaseModel, Field, ConfigDict

from ...shared.errors import Error
from ...shared.llm_gateway import OfficialLlmClient, SUPPORTED_MODELS

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
        self.client = OfficialLlmClient(values, transport=transport)

    def _settings(self):
        endpoint, model, key, protocol, provider = self.client.resolve()
        if provider not in VISION_PROVIDERS:
            raise Error(422, 'llm_no_vision',
                        'DeepSeek 官方接口暂不支持图像输入；画面分析请选用 Kimi。')
        return endpoint, model, key, protocol, provider

    def analyze_frames(self, jpegs: list[bytes]) -> dict:
        self._settings()
        if not jpegs or len(jpegs) > 8:
            raise Error(422, 'llm_frame_count_invalid', '画面分析需要 1 到 8 张采样帧。')
        for jpeg in jpegs:
            if not isinstance(jpeg, bytes) or not jpeg.startswith(b'\xff\xd8') \
                    or not jpeg.endswith(b'\xff\xd9'):
                raise Error(422, 'llm_frame_invalid', '采样帧必须是有效 JPEG 数据。')
        user = self.client.image_content(jpegs)
        try:
            content = self.client.chat(system=ANALYZE_PROMPT, user=user, max_tokens=2048)
            result = _AnalysisResult.model_validate_json(content)
            return result.model_dump()
        except ValidationError:
            raise Error(502, 'llm_invalid_response',
                        '大模型接口返回的画像分析不符合受控结构。') from None
