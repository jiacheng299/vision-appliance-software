"""Developer-owned parameter definitions. No user schema or executable expressions."""
import math
import re
from typing import Literal
from pydantic import Field, StrictBool, StrictFloat, StrictInt
from ..schemas import DTO
from .errors import Error

class ParameterSetting(DTO):
    key: str = Field(min_length=1, max_length=80)
    value: StrictBool | StrictInt | StrictFloat | str | None = None
    required: bool = False

class ParameterOption(DTO):
    label: str
    value: str

class ParameterDefinition(DTO):
    key: str
    label: str
    category: str
    type: Literal['select', 'number', 'integer', 'boolean', 'time_window']
    description: str
    unit: str = ''
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1
    options: list[ParameterOption] = Field(default_factory=list)

class ParameterCatalog(DTO):
    version: str = '1.0'
    items: list[ParameterDefinition]
    editable_by_user: Literal[False] = False

def choice(key, label, category, entries):
    return ParameterDefinition(key=key,label=label,category=category,type='select',description='须由所选模型及执行器声明支持。',options=[ParameterOption(value=v,label=t) for v,t in entries])

def number(key,label,category,low,high,unit='',integer=False):
    return ParameterDefinition(key=key,label=label,category=category,type='integer' if integer else 'number',minimum=low,maximum=high,unit=unit,step=1 if integer else .01,description=f'范围 {low}–{high} {unit}，须由执行器支持。')

DEFINITIONS = [
    choice('target','检测对象','检测条件',[('fire','火焰'),('smoke','烟雾'),('person','人员'),('vehicle','车辆'),('animal','动物'),('object','物品'),('helmet','安全帽'),('vest','反光衣'),('water','积水'),('waste','垃圾')]),
    choice('rule','触发规则','检测条件',[('presence','出现检测'),('intrusion','区域入侵'),('dwell','区域滞留'),('absence','缺员或离岗'),('count','数量阈值'),('line_crossing','越线检测'),('abandonment','物品遗留'),('removal','物品移除'),('fall','跌倒检测'),('congestion','拥堵检测')]),
    number('duration_seconds','触发持续时长','时间条件',1,86400,'秒',True),
    number('confidence_threshold','置信度阈值','检测条件',0,1),
    number('min_count','最小目标数量','数量与范围',0,100000,'个',True),
    number('max_count','最大目标数量','数量与范围',0,100000,'个',True),
    number('min_area_ratio','最小目标面积占比','数量与范围',0,1),
    number('max_area_ratio','最大目标面积占比','数量与范围',0,1),
    number('min_speed','最低移动速度','运动条件',0,1000,'米/秒'),
    number('max_speed','最高移动速度','运动条件',0,1000,'米/秒'),
    number('distance_threshold','目标距离阈值','运动条件',0,100000,'米'),
    choice('direction','移动方向','运动条件',[('any','不限'),('left_to_right','从左至右'),('right_to_left','从右至左'),('top_to_bottom','从上至下'),('bottom_to_top','从下至上'),('enter','进入'),('leave','离开')]),
    choice('color','目标颜色','目标属性',[('any','不限'),('red','红色'),('orange','橙色'),('yellow','黄色'),('green','绿色'),('blue','蓝色'),('purple','紫色'),('black','黑色'),('white','白色'),('gray','灰色'),('brown','棕色')]),
    choice('size_class','目标尺寸等级','目标属性',[('any','不限'),('small','小型'),('medium','中型'),('large','大型')]),
    ParameterDefinition(key='working_hours',label='监测时段',category='时间条件',type='time_window',description='格式 HH:MM-HH:MM，例如 08:00-18:00，以部署系统时区为准。'),
    number('alarm_interval_seconds','重复报警间隔','报警策略',0,86400,'秒',True),
    number('event_merge_seconds','事件合并时间窗','报警策略',0,86400,'秒',True),
    number('consecutive_frames','连续满足帧数','检测条件',1,100000,'帧',True),
    number('sample_interval_seconds','分析采样间隔','采样与跟踪',.01,3600,'秒'),
    number('tracking_timeout_seconds','目标跟踪超时','采样与跟踪',1,3600,'秒',True),
    number('exit_confirmation_seconds','离开确认时间','采样与跟踪',1,3600,'秒',True),
    choice('severity','报警等级','报警策略',[('info','提示'),('warning','警告'),('critical','严重')]),
    choice('sensitivity','检测灵敏度','检测条件',[('low','低'),('medium','中'),('high','高')]),
    ParameterDefinition(key='require_tracking',label='启用目标跟踪',category='采样与跟踪',type='boolean',description='需要执行器支持目标跟踪。'),
    ParameterDefinition(key='ignore_stationary',label='忽略静止目标',category='运动条件',type='boolean',description='需要执行器支持运动状态判定。'),
]
BY_KEY = {item.key: item for item in DEFINITIONS}
CORE_KEYS = {'target','rule','duration_seconds'}

def validate_settings(settings, *, complete=False, extra_choices=None):
    if len(settings)>len(DEFINITIONS) or len({s.key for s in settings})!=len(settings):
        raise Error(422,'invalid_parameters','配置项重复或数量超出目录范围。')
    values={}
    for setting in settings:
        definition=BY_KEY.get(setting.key)
        if definition is None: raise Error(422,'unknown_parameter','配置项不在开发者维护的选项池中。')
        value=setting.value
        if value is None or value=='':
            if complete and setting.required: raise Error(422,'parameter_required',f'请设置“{definition.label}”。')
            continue
        valid=False
        if definition.type in ('number','integer'):
            valid=type(value) in (int,float) and math.isfinite(value) and definition.minimum<=value<=definition.maximum
            if definition.type=='integer': valid=valid and type(value) is int
        elif definition.type=='boolean': valid=type(value) is bool
        elif definition.type=='select': valid=isinstance(value,str) and value in ({o.value for o in definition.options}|set((extra_choices or {}).get(setting.key,[])))
        elif definition.type=='time_window': valid=isinstance(value,str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d',value) is not None
        if not valid: raise Error(422,'invalid_parameter_value',f'“{definition.label}”的类型、范围或选项不符合要求。')
        values[setting.key]=value
    for low,high in [('min_count','max_count'),('min_area_ratio','max_area_ratio'),('min_speed','max_speed')]:
        if low in values and high in values and values[low]>values[high]: raise Error(422,'invalid_parameter_range',f'“{BY_KEY[low].label}”不能大于“{BY_KEY[high].label}”。')
    return values
