"""Aggregate the frames of one observation window before judging it.

A window is the unit the patent's S7/S8 talk about: only inside a window that
actually closed may the system claim "not detected". Frames that arrive out of
order, or after a transport gap longer than the task allows, invalidate the
window instead of being silently dropped.
"""
from dataclasses import dataclass


@dataclass
class ObservationWindow:
    seconds: float
    started_at: float | None = None
    last_frame_at: float | None = None
    frames: int = 0
    max_gap: float = 0.0
    samples: int = 0
    overexposure: float | None = None
    blur: float | None = None
    brightness: float = 0.0
    detections: int = 0
    target_scale: float | None = None
    roi_visible: float | None = None
    continuous: bool = True

    def add_frame(self, timestamp: float) -> None:
        if not timestamp == timestamp:
            self.continuous = False
            return
        if self.started_at is None:
            self.started_at = timestamp
        elif self.last_frame_at is not None:
            if timestamp <= self.last_frame_at:
                # A repeated or backward timestamp cannot support any interval.
                self.continuous = False
            else:
                self.max_gap = max(self.max_gap, timestamp - self.last_frame_at)
        self.last_frame_at = timestamp
        self.frames += 1

    def add_sample(self, measurement, detection_count: int = 0,
                   target_scale: float | None = None) -> None:
        """Worst case wins: the region is only as observable as its weakest sample."""
        self.samples += 1
        if measurement.brightness is not None:
            self.brightness += measurement.brightness
        if measurement.overexposure_ratio is not None:
            self.overexposure = (measurement.overexposure_ratio if self.overexposure is None
                                 else max(self.overexposure, measurement.overexposure_ratio))
        if measurement.blur_score is not None:
            self.blur = (measurement.blur_score if self.blur is None
                         else min(self.blur, measurement.blur_score))
        if measurement.roi_visible_ratio is not None:
            self.roi_visible = (measurement.roi_visible_ratio if self.roi_visible is None
                                else min(self.roi_visible, measurement.roi_visible_ratio))
        self.detections = max(self.detections, int(detection_count))
        if target_scale is not None:
            self.target_scale = (target_scale if self.target_scale is None
                                 else max(self.target_scale, target_scale))

    def due(self, timestamp: float) -> bool:
        return self.started_at is not None and timestamp - self.started_at >= self.seconds

    @property
    def usable(self) -> bool:
        return self.frames > 0 and self.samples > 0

    def metrics(self) -> dict:
        duration = None
        if self.continuous and self.started_at is not None and self.last_frame_at is not None:
            duration = self.last_frame_at - self.started_at
        return {'frame_count': self.frames, 'time_continuous': self.continuous,
                'duration_seconds': duration,
                'actual_fps': (self.frames / duration) if duration else None,
                'max_gap_seconds': self.max_gap,
                'brightness': (self.brightness / self.samples) if self.samples else None,
                'roi_visible_ratio': self.roi_visible,
                'overexposure_ratio': self.overexposure,
                'blur_score': self.blur,
                # Occlusion cannot be measured from a single frame; leave it unmeasured.
                'occlusion_ratio': None,
                'target_scale_px': self.target_scale}

    def reset(self, timestamp: float | None = None) -> None:
        self.started_at = timestamp
        self.last_frame_at = timestamp
        self.frames = 0
        self.max_gap = 0.0
        self.samples = 0
        self.overexposure = None
        self.blur = None
        self.brightness = 0.0
        self.detections = 0
        self.target_scale = None
        self.roi_visible = None
        self.continuous = True
