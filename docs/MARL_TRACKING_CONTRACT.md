# 多智能体强化学习追踪：接入契约与验收建议

本文件说明**如何把一个在仓库外训练好的多智能体强化学习（MARL）关联策略接进本系统**。
本仓库**不包含**训练循环、仿真环境与策略权重，因此下文所有内容都是"接入约定"，
不是"已实现的能力"。任何对外表述都必须遵守[第九节的红线](#九红线)。

## 一、边界先讲清楚

| 项目 | 本仓库 | 需要仓库外完成 |
| --- | --- | --- |
| 观测/动作契约 | ✅ 已固定（`modules/tracking/policy.py`） | — |
| 轨迹状态管理（超时、剪枝、编号） | ✅ 由框架持有 | — |
| 启发式基线策略 | ✅ `heuristic-iou`，有 120 步随机序列等价性测试 | — |
| 外部策略装载 | ✅ `VISION_TRACKER_POLICY=module:attribute` | — |
| 策略训练、奖励设计、仿真环境 | ❌ 不包含 | ✅ 训练工程 |
| 策略权重与标定 | ❌ 不包含 | ✅ 训练产出 |
| 关联质量的量化对比 | ❌ 只有同产物确定性对照 | ✅ 需要第二份标定结果 |

## 二、契约（代码位置：`backend/app/modules/tracking/policy.py`）

### 观测：策略看到什么

```python
@dataclass(frozen=True)
class Observation:
    timestamp: float                 # 秒；直播为采样时钟，录像为媒体时钟
    detections: tuple[Detection, ...]  # 本帧检测，坐标已归一化到 [0,1]
    roi: tuple = ()                  # 监测区域多边形（可空）
    frame: dict = {}                 # 可选画面指标：亮度/过曝/清晰率等

@dataclass(frozen=True)
class Detection:
    label: str
    x: float; y: float; width: float; height: float
    confidence: float
```

要点：**框架在入口处就丢弃非人员框与非法几何**（`observation_from` 调用 `valid_person`），
策略不需要自己过滤；坐标始终是相对原帧的归一化值，不是 640×640 的模型输入坐标。

### 动作：策略输出什么

```python
@dataclass(frozen=True)
class Decision:
    associations: tuple = ()      # ((track_id, detection_index), ...)
    new_detections: tuple = ()    # (detection_index, ...)
    lost: tuple = ()              # (track_id, ...)
    note: str = ''
```

- `detection_index` 指向**本次观测**的检测列表下标。
- 非法关联（不存在的 track_id、越界下标、重复关联）会被框架丢弃，不会污染状态。
- 策略**不能**修改轨迹表；它拿到的是 `Track` 只读视图（`box` 是副本）。

### 状态：谁维护

| 字段 | 归属 | 说明 |
| --- | --- | --- |
| `id` | 框架 | `heuristic-iou-N` 或策略的 `track_prefix-N` |
| `box` | 框架 | 策略只读 |
| `last_seen` / `missing_since` | 框架 | 超时与剪枝由框架统一执行 |
| 策略内部记忆 | 策略 | 允许有状态（如 LSTM 隐状态），但 `reset()` 必须清空 |

## 三、最小可运行策略

```python
# my_marl_policy.py  —— 放在任意可 import 的路径下
from app.modules.tracking.policy import Decision, Track


class MarlinAssociation:
    """示例：把"最近邻 + 距离阈值"包成策略骨架，真实实现替换 decide 内部即可。"""
    name = 'marl-association-v1'
    track_prefix = 'm'

    def __init__(self, weights_path=None):
        self.weights_path = weights_path
        # 真实实现：加载策略权重、初始化隐状态

    def reset(self):
        # 真实实现：清空每回合状态
        pass

    def decide(self, observation, tracks) -> Decision:
        # 真实实现：由观测与轨迹构造状态张量 → 策略前向 → 关联矩阵 → 动作
        return Decision(new_detections=tuple(range(len(observation.detections))))

    def describe(self):
        return {'name': self.name, 'kind': 'learned', 'weights': self.weights_path}
```

## 四、如何接入

1. 把策略模块装进项目虚拟环境（或放到可 import 的目录）。
2. 在 `.env.local` 里指定：

```dotenv
VISION_TRACKER_POLICY=my_marl_policy:MarlinAssociation
```

3. 重启应用。`IntrusionRule` 会通过 `registry.create()` 装载该策略；装载失败**不会
   静默回退**到启发式，而是让任务启动失败并给出原因：

| 失败情形 | 错误码 | HTTP |
| --- | --- | --- |
| 模块无法导入 / 没有该属性 / 初始化抛错 | `tracker_policy_unavailable` | 503 |
| 对象不满足 `TrackerPolicy` 协议（缺 name/reset/decide/describe） | `tracker_policy_incompatible` | 503 |
| 写成 `marl-association`（注册表里的预留位，未安装） | `tracker_policy_not_installed` | 503 |
| 完全未知的名字 | `tracker_policy_unknown` | 404 |

`GET /api/v1/tracking/policies` 会同时返回**目录**（`items`）与**实际装载结果**
（`resolved`：spec / available / name / kind / external / detail / reason）；
任务详情的"关联策略"区块显示"实际装载：<策略名>（外部策略）"，配置不可用时
用红色写明原因。

## 五、训练环境建议（仓库外）

- **数据**：MOT17 / MOT20 的行人序列，按摄像机分组，保留原始帧率与重叠度标注。
- **MDP 建模**：把"每个既有轨迹 + 每个检测"看作一个智能体或一个动作对；
  多智能体协作体现在"关联必须一一对应"这一全局约束上。
- **观测特征**：IoU、中心距、尺寸比、速度预测残差、置信度、轨迹年龄、
  丢失时长、画面指标（亮度/过曝/模糊）——这些在 `Observation`/`Track` 里都有对应。
- **动作空间**：关联矩阵 + 入场 + 离场（与 `Decision` 一致，不要引入第四类动作，
  否则接不回来）。
- **训练脚本与权重**放在独立仓库，用版本号管理；接入时只暴露 `module:attribute`。

## 六、评价指标建议

| 层次 | 指标 | 为什么要 |
| --- | --- | --- |
| 关联层 | 关联准确率、ID 切换次数（IDSW）、轨迹碎片数 | 直接对应策略的输出 |
| 任务层 | IDF1、MOTA、IDF1 的漂移方差 | 与业务报警质量挂钩 |
| 系统层 | 有效观察三态的分布、`insufficient` 占比 | 与交底书 F3 的门禁联动 |
| 成本层 | 单帧耗时、内存增量（参考 `deploy/scripts/preheat_measure.py`） | 过渡预算能否承受 |

**重要**：不要在"同产物"的影子里比较精度（`deploy/scripts/shadow_compare.py`
默认加载同一份 ONNX，只能证明确定性）。跨模型/跨策略对比需要各自独立的标定集。

## 七、验收流程建议

1. **离线回放**：用固定录像跑一遍启发式与候选策略，产出关联级指标与三态分布。
2. **确定性检查**：同一策略、同一序列重复运行，输出必须逐帧一致
   （参考 `test_the_policy_runtime_reproduces_the_previous_tracker_exactly`）。
3. **退化检查**：断流、长间隔、全空帧三种情况下，轨迹必须被正确剪枝且不产生幽灵目标。
4. **成本实测**：分桶记录单帧耗时与内存，和 200 ms / 1024 MB 的过渡预算对照。
5. **回滚预案**：`VISION_TRACKER_POLICY` 改回 `heuristic-iou` 即为回滚，无需改代码。

## 八、与交底书的衔接

追踪属于需求图里的 `person_track` 节点（`routing/graph.py` 的串联依赖）。
策略质量最终会通过两处影响系统：

- **组合求解**：`capability.py` 中 `heuristic-tracker` 已声明 `person_track` 质量；
  接入学习型策略后应新增一条能力记录（`installed=True`、`calibrated=True`）并填分桶质量。
- **有效观察**：轨迹质量下降会体现在 `insufficient` 的占比上（M8 门禁不动，
  它只看帧与路径，不看轨迹质量）。

## 九、红线

1. 本仓库**没有**训练循环、仿真环境与策略权重；只能说"预留了可插拔的接口"。
2. 未装载外部策略时，`marl-association` 在注册表里恒为 `installed=False`，创建即 503。
3. 界面与文档中**不得**把启发式策略的结果标成"强化学习追踪"。
4. 任何精度数字必须来自独立标定集，且注明数据、模型版本与硬件环境。
