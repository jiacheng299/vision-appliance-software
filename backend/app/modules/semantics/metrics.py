"""Picture indicators measured on the frames actually fed to the model.

Only physical, locally measurable quantities live here. Anything that would need
a scene model (for example occlusion) is left unmeasured instead of guessed, so a
caller can tell "not measured" apart from "measured and fine".
"""
from dataclasses import dataclass

# A pixel is saturated when every channel is at or above this level.
OVEREXPOSED_LEVEL = 250


@dataclass(frozen=True)
class FrameMetrics:
    width: int
    height: int
    brightness: float | None
    overexposure_ratio: float | None
    roi_visible_ratio: float | None
    blur_score: float | None


def polygon_area(points) -> float:
    if not points or len(points) < 3:
        return 0.0
    total = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def _clip_edge(points, inside, intersect):
    output = []
    for index, current in enumerate(points):
        previous = points[index - 1]
        if inside(current):
            if not inside(previous):
                output.append(intersect(previous, current))
            output.append(current)
        elif inside(previous):
            output.append(intersect(previous, current))
    return output


def clip_polygon(points, bounds=(0.0, 0.0, 1.0, 1.0)):
    """Sutherland-Hodgman clip of a normalised polygon to the frame rectangle."""
    left, top, right, bottom = bounds
    polygon = [(float(x), float(y)) for x, y in points]
    for inside, intersect in (
        (lambda p: p[0] >= left, lambda a, b: _vertical(a, b, left)),
        (lambda p: p[0] <= right, lambda a, b: _vertical(a, b, right)),
        (lambda p: p[1] >= top, lambda a, b: _horizontal(a, b, top)),
        (lambda p: p[1] <= bottom, lambda a, b: _horizontal(a, b, bottom)),
    ):
        if not polygon:
            return []
        polygon = _clip_edge(polygon, inside, intersect)
    return polygon


def _vertical(a, b, x):
    span = b[0] - a[0]
    ratio = 0.0 if span == 0 else (x - a[0]) / span
    return (x, a[1] + ratio * (b[1] - a[1]))


def _horizontal(a, b, y):
    span = b[1] - a[1]
    ratio = 0.0 if span == 0 else (y - a[1]) / span
    return (a[0] + ratio * (b[0] - a[0]), y)


def roi_visible_ratio(roi) -> float | None:
    """Fraction of the ROI polygon that is inside the picture, geometry only."""
    if not roi or len(roi) < 3:
        return None
    total = polygon_area(roi)
    if total <= 0:
        return None
    return min(1.0, max(0.0, polygon_area(clip_polygon(roi)) / total))


def _polygon_mask(shape, roi):
    import numpy as np
    import cv2
    height, width = shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    points = np.array([[(round(x * (width - 1)), round(y * (height - 1))) for x, y in roi]], dtype=np.int32)
    cv2.fillPoly(mask, points, 255)
    return mask.astype(bool)


def measure_frame(frame, roi=None) -> FrameMetrics:
    """Measure one BGR uint8 frame; missing dependencies are an error, not a zero."""
    import numpy as np
    import cv2
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3
            or frame.shape[2] != 3 or frame.shape[0] < 1 or frame.shape[1] < 1):
        raise ValueError('frame must be a nonempty uint8 BGR image with three channels')
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = _polygon_mask(frame.shape, roi) if roi and len(roi) >= 3 else None
    if mask is not None and not mask.any():
        overexposure = None
    else:
        saturated = frame.min(axis=2) >= OVEREXPOSED_LEVEL
        measured = saturated[mask] if mask is not None else saturated
        overexposure = float(measured.mean()) if measured.size else None
    region = gray[mask] if mask is not None and mask.any() else gray
    blur = float(cv2.Laplacian(region, cv2.CV_64F).var())
    return FrameMetrics(width=width, height=height, brightness=float(gray.mean()) / 255.0,
                        overexposure_ratio=overexposure,
                        roi_visible_ratio=roi_visible_ratio(roi), blur_score=blur)


def sequence_metrics(timestamps) -> tuple[float | None, float | None, float | None]:
    """Actual frame rate, largest gap and covered duration from received frames."""
    values = [float(value) for value in timestamps]
    if len(values) < 2:
        return (0.0 if values else None), 0.0, 0.0
    gaps = [later - earlier for earlier, later in zip(values, values[1:])]
    if any(gap < 0 for gap in gaps):
        raise ValueError('frame timestamps must not go backwards')
    span = values[-1] - values[0]
    if span <= 0:
        return None, max(gaps) if gaps else None, 0.0
    return len(values) / span, max(gaps), span


def combine(measurements) -> FrameMetrics:
    """Worst case over several regions: the task is only as observable as its
    least observable zone, so overexposure takes the maximum and every other
    quality figure the minimum."""
    items = list(measurements)
    if not items:
        raise ValueError('at least one measurement is required')
    first = items[0]

    def worst(attribute, pick):
        values = [getattr(item, attribute) for item in items]
        values = [value for value in values if value is not None]
        return pick(values) if values else None

    return FrameMetrics(width=first.width, height=first.height,
                        brightness=worst('brightness', min),
                        overexposure_ratio=worst('overexposure_ratio', max),
                        roi_visible_ratio=worst('roi_visible_ratio', min),
                        blur_score=worst('blur_score', min))


def measure_regions(frame, regions) -> FrameMetrics:
    """Measure the same frame over every monitoring region of one task."""
    polygons = [region for region in (regions or []) if region and len(region) >= 3]
    if not polygons:
        return measure_frame(frame)
    if len(polygons) == 1:
        return measure_frame(frame, polygons[0])
    return combine(measure_frame(frame, polygon) for polygon in polygons)
