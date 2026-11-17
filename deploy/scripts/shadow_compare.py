"""Shadow-compare two inference sessions on the same frames (S14).

本机只有一份可信 ONNX，因此两次加载的是同一份产物：这个脚本能证明
「影子通道与主通道在同一批帧上给出相同结果且代价可测」，
不能证明「换成另一个模型会更准」。

Run with Python 3.13:
    .venv/Scripts/python.exe deploy/scripts/shadow_compare.py
    .venv/Scripts/python.exe deploy/scripts/shadow_compare.py --video var/camera-lab/downloads/plaza.mp4
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.modules.routing import shadow  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=int, default=8)
    parser.add_argument('--candidate', default=None, help='候选会话用的 ONNX，默认与主通道相同')
    parser.add_argument('--model', default=None, help='主会话 ONNX，默认 var/models/yolo11n')
    parser.add_argument('--video', default=None,
                        help='取样用的本地录像；缺省时用确定性的合成帧')
    args = parser.parse_args()
    model = Path(args.model) if args.model else ROOT / 'var/models/yolo11n/yolo11n.onnx'
    candidate = Path(args.candidate) if args.candidate else model
    if not model.is_file():
        print(json.dumps({'available': False, 'reason': f'模型不存在：{model}'},
                         ensure_ascii=False, indent=2))
        return 1
    if not candidate.is_file():
        print(json.dumps({'available': False, 'reason': f'候选模型不存在：{candidate}'},
                         ensure_ascii=False, indent=2))
        return 1
    mode = 'synthetic'
    frames = None
    if args.video:
        frames = shadow.frames_from_video(args.video, count=args.frames)
        mode = 'file' if frames else 'synthetic'
    if not frames:
        frames = shadow.synthetic_frames(args.frames)
        mode = 'synthetic'
    try:
        comparison = shadow.compare(model, candidate, frames)
    except ImportError as error:
        print(json.dumps({'available': False, 'reason': f'缺少推理依赖：{error}'},
                         ensure_ascii=False, indent=2))
        return 1
    payload = comparison.as_dict()
    payload['mode'] = mode
    if args.video:
        payload['video'] = str(args.video)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if comparison.available else 1


if __name__ == '__main__':
    sys.exit(main())
