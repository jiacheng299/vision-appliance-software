"""Continuous absence is evidence only between successfully decoded observations."""
from dataclasses import dataclass
import math
from typing import Literal


@dataclass(frozen=True)
class PresenceObservation:
    count: int
    absent_seconds: float
    present_seconds: float
    state: Literal['normal', 'absence']
    transition: Literal['absence', 'restored'] | None
    alarm: bool


def contains(polygon, point):
    x,y = point
    inside = False
    for i,(ax,ay) in enumerate(polygon):
        bx,by = polygon[(i+1)%len(polygon)]
        cross = (bx-ax)*(y-ay)-(by-ay)*(x-ax)
        if abs(cross)<1e-10 and min(ax,bx)<=x<=max(ax,bx) and min(ay,by)<=y<=max(ay,by):
            return True
        if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:
            inside = not inside
    return inside


class PresenceRule:
    def __init__(self, regions, min_count=1, duration_seconds=30, alarm_interval_seconds=60, max_gap_seconds=3):
        if (type(min_count) is not int or min_count<1 or not math.isfinite(duration_seconds)
                or duration_seconds<=0 or not math.isfinite(alarm_interval_seconds) or alarm_interval_seconds<0
                or not math.isfinite(max_gap_seconds) or max_gap_seconds<=0 or not regions
                or any(len(p)<3 for p in regions)):
            raise ValueError('Invalid presence monitoring conditions')
        self.regions,self.min_count = regions,min_count
        self.duration,self.interval,self.max_gap = duration_seconds,alarm_interval_seconds,max_gap_seconds
        self.state: Literal['normal', 'absence'] = 'normal'
        self.last_alarm = None
        self.mark_unavailable()

    def mark_unavailable(self):
        self.absent_since = self.present_since = self.last_observed = None
        self.last_alarm = None

    def observe(self, timestamp, boxes):
        if not math.isfinite(timestamp) or timestamp<0:
            raise ValueError('Invalid observation time')
        if self.last_observed is not None and (timestamp<self.last_observed or timestamp-self.last_observed>self.max_gap):
            self.mark_unavailable()
        self.last_observed = timestamp
        # Feet are a stable ground-plane reference. Overlapping regions never double-count a person.
        count = sum(box.get('label')=='person' and any(contains(polygon,
            (box['x']+box['width']/2,box['y']+box['height'])) for polygon in self.regions) for box in boxes)
        present = count>=self.min_count
        if self.state == 'normal':
            self.present_since = None
            if present:
                self.absent_since = None
                return PresenceObservation(count,0,0,self.state,None,False)
            if self.absent_since is None:
                self.absent_since = timestamp
            absent = timestamp-self.absent_since
            if absent >= self.duration:
                self.state = 'absence'
                self.last_alarm = timestamp
                return PresenceObservation(count,absent,0,self.state,'absence',True)
            return PresenceObservation(count,absent,0,self.state,None,False)
        if not present:
            self.present_since = None
            if self.absent_since is None:
                self.absent_since = timestamp
            absent = timestamp-self.absent_since
            repeat = self.last_alarm is None or timestamp-self.last_alarm >= self.interval
            if repeat:
                self.last_alarm = timestamp
            return PresenceObservation(count,absent,0,self.state,None,repeat)
        self.absent_since = None
        if self.present_since is None:
            self.present_since = timestamp
        present_seconds = timestamp-self.present_since
        if present_seconds >= self.duration:
            self.state = 'normal'
            self.absent_since = None
            self.present_since = None
            self.last_alarm = None
            return PresenceObservation(count,0,present_seconds,self.state,'restored',False)
        return PresenceObservation(count,0,present_seconds,self.state,None,False)
