"""Measure the marginal cost of keeping a second inference session alive.

对应交底书 S14 的过渡预算：影子运行要先知道"多开一份会话"要多少内存与延迟。
本机只有一份可信 ONNX，因此这里测的是并存代价，不是模型能力差异。

Run with Python 3.13:
    .venv/Scripts/python.exe deploy/scripts/preheat_measure.py
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.modules.routing import preheat, solver  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=int, default=5, help='每个会话的计时轮数')
    parser.add_argument('--model', default=None, help='ONNX 路径，默认取 var/models/yolo11n')
    args = parser.parse_args()
    path = Path(args.model) if args.model else ROOT / 'var/models/yolo11n/yolo11n.onnx'
    measurement = preheat.measure(path, frames=args.frames)
    budgets = solver.Budgets()
    check = preheat.budget_check(measurement, budgets_cpu_ms=budgets.cpu_ms,
                                 budgets_memory_mb=budgets.memory_mb)
    print(json.dumps({'measurement': measurement.as_dict(), 'budget': check,
                      'budgets': budgets.as_dict()}, ensure_ascii=False, indent=2))
    return 0 if measurement.available else 1


if __name__ == '__main__':
    sys.exit(main())
