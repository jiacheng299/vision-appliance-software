# Presence Alert Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist confirmed personnel-absence state, emit a confirmed recovery event after equal continuous presence time, and keep live video red until that recovery is confirmed.

**Architecture:** `PresenceRule` owns the two-state transition logic. `LocalAgentServices` persists transition state on `RunDTO` and writes one durable event per transition. The workspace polling already used by the frontend carries the current alert state to both single-view and video-wall players, so UI state survives refresh without deriving truth from paginated events.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, SQLAlchemy, pytest, Vue 3, TypeScript, Vitest, Vue Test Utils, SVG overlays.

**Spec:** `docs/superpowers/specs/2026-10-29-presence-alert-recovery-design.md`

## Global Constraints

- Recovery confirmation reuses the task's exact `duration_seconds`; no new user setting is added.
- A confirmed absence stays active through unavailable frames, time reversal, large observation gaps, browser refresh, and video disconnection.
- One absence episode emits exactly one `person_absence` event and one `person_presence_restored` event; `alarm_interval_seconds` remains accepted for configuration compatibility but does not repeat events.
- Only the local YOLO person-absence executor uses this state machine. Other templates, demo providers, and multimodal tasks default to a normal alert state.
- Single view and video wall must render the same persisted run state.
- Each independently reviewable change uses a Chinese Conventional Commit and includes its regression tests.

---

### Task 1: Two-way presence state machine

**Files:**
- Modify: `backend/app/modules/local_execution/presence.py`
- Test: `tests/backend/test_presence_rule.py`

**Interfaces:**
- Consumes: normalized person boxes and monotonic media timestamp from the existing executor.
- Produces: `PresenceObservation(count, absent_seconds, present_seconds, state, transition)` where `state` is `Literal['normal','absence']` and `transition` is `Literal['absence','restored'] | None`.
- Produces: `PresenceRule.mark_unavailable()` that clears only unconfirmed continuous timers and the last observation timestamp, while preserving confirmed `state`.

- [ ] **Step 1: Write failing transition tests**

Add tests that express one complete episode and interruption behavior:

```python
def test_absence_and_recovery_each_require_the_full_duration():
    detector = rule(duration_seconds=3)
    assert detector.observe(0, []).transition is None
    assert detector.observe(3, []).transition == 'absence'
    assert detector.observe(4, [PERSON]).present_seconds == 0
    assert detector.observe(6, [PERSON]).transition is None
    restored = detector.observe(7, [PERSON])
    assert restored.transition == 'restored'
    assert restored.state == 'normal'

def test_brief_presence_does_not_clear_confirmed_absence():
    detector = rule(duration_seconds=2)
    detector.observe(0, [])
    detector.observe(2, [])
    detector.observe(3, [PERSON])
    interrupted = detector.observe(4, [])
    assert interrupted.state == 'absence'
    assert interrupted.present_seconds == 0
    assert interrupted.transition is None

def test_unavailable_observation_preserves_alarm_but_resets_recovery_evidence():
    detector = rule(duration_seconds=2)
    detector.observe(0, [])
    detector.observe(2, [])
    detector.observe(3, [PERSON])
    detector.mark_unavailable()
    resumed = detector.observe(20, [PERSON])
    assert resumed.state == 'absence'
    assert resumed.present_seconds == 0
```

Update existing repeated-alarm assertions so sustained absence has no second transition.

- [ ] **Step 2: Run the state-machine tests and confirm RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/backend/test_presence_rule.py -q
```

Expected: failures because `present_seconds`, `state`, and `transition` do not exist and the old rule repeats alarms.

- [ ] **Step 3: Implement the minimal two-state rule**

Use explicit state and separate timers:

```python
from typing import Literal

@dataclass(frozen=True)
class PresenceObservation:
    count: int
    absent_seconds: float
    present_seconds: float
    state: Literal['normal', 'absence']
    transition: Literal['absence', 'restored'] | None

class PresenceRule:
    def __init__(self, regions, min_count=1, duration_seconds=30,
                 alarm_interval_seconds=60, max_gap_seconds=3):
        # Keep validating alarm_interval_seconds for saved-config compatibility.
        self.state: Literal['normal', 'absence'] = 'normal'
        self.absent_since = self.present_since = self.last_observed = None

    def mark_unavailable(self):
        self.absent_since = self.present_since = self.last_observed = None

    def observe(self, timestamp, boxes):
        if self.last_observed is not None and (
            timestamp < self.last_observed
            or timestamp - self.last_observed > self.max_gap
        ):
            self.mark_unavailable()
        self.last_observed = timestamp
        count = sum(
            box.get('label') == 'person'
            and any(contains(polygon, (
                box['x'] + box['width'] / 2,
                box['y'] + box['height'],
            )) for polygon in self.regions)
            for box in boxes
        )
        present = count >= self.min_count
        if self.state == 'normal':
            self.present_since = None
            if present:
                self.absent_since = None
                return PresenceObservation(count, 0, 0, self.state, None)
            if self.absent_since is None:
                self.absent_since = timestamp
            absent = timestamp - self.absent_since
            if absent >= self.duration:
                self.state = 'absence'
                self.absent_since = None
                return PresenceObservation(count, absent, 0, self.state, 'absence')
            return PresenceObservation(count, absent, 0, self.state, None)
        self.absent_since = None
        if not present:
            self.present_since = None
            return PresenceObservation(count, 0, 0, self.state, None)
        if self.present_since is None:
            self.present_since = timestamp
        present_seconds = timestamp - self.present_since
        if present_seconds >= self.duration:
            self.state = 'normal'
            self.present_since = None
            return PresenceObservation(count, 0, present_seconds, self.state, 'restored')
        return PresenceObservation(count, 0, present_seconds, self.state, None)
```

Keep the existing polygon/count calculation directly in `observe`. Do not keep `last_alarm`; a confirmed state prevents duplicate transitions naturally.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/backend/test_presence_rule.py -q
```

Expected: all presence-rule tests pass, including gap and second-episode coverage.

- [ ] **Step 5: Commit the state machine**

```powershell
git add backend/app/modules/local_execution/presence.py tests/backend/test_presence_rule.py
git commit -m "feat(检测): 增加缺岗复岗状态机"
```

---

### Task 2: Persist run alert state and transition events

**Files:**
- Modify: `backend/app/modules/agents/contracts.py`
- Modify: `backend/app/modules/local_execution/service.py`
- Modify: `backend/app/modules/agents/demo.py` only if an explicit fixture conflicts with the new defaults
- Test: `tests/backend/test_local_execution.py`
- Test: `tests/backend/test_agent_workflow.py` for contract/default compatibility if needed
- Regenerate: `contracts/openapi.json`
- Regenerate: `frontend/src/shared/api/generated.ts`

**Interfaces:**
- Consumes: Task 1 `PresenceObservation.state` and `.transition`.
- Produces: `RunDTO.alert_state: Literal['normal','absence'] = 'normal'` and `RunDTO.alert_started_at: str | None = None`.
- Produces: durable `person_absence` warning events and `person_presence_restored` info events.
- Produces: generated frontend `Run` type fields through the existing OpenAPI pipeline.

- [ ] **Step 1: Write failing executor tests for one absence/recovery episode**

Add a deterministic frame sequence with absence long enough to alarm, continuous presence long enough to restore, and continued presence afterward:

```python
PERSON = {'label':'person','x':.2,'y':.2,'width':.2,'height':.5,'confidence':.9}

def command(duration_seconds=30):
    config = RevisionConfig(channels=[dict(
        channel_id='channel', name='岗位', target='person', rule='absence',
        duration_seconds=duration_seconds,
        sources=[dict(source_id='video', start_media_ms=0, end_media_ms=60000,
                      regions=[dict(id='roi', points=[(0,0),(1,0),(1,1),(0,1)])])],
        capability_ref=dict(model_id='model', model_version='1',
                            template_id='template', template_version='1'),
        parameters=[dict(key='sample_interval_seconds', value=15),
                    dict(key='confidence_threshold', value=.5)],
    )])
    return RuntimeCommand(
        kind='start', agent_id='agent', revision_id='revision', revision_no=1,
        config=config, channel_ids=['channel'], source_kinds={'video':'file'},
        source_snapshots=[SourceSnapshot(
            id='video', row_version=1, kind='file', sha256='abc', width=640,
            height=480, duration_ms=60000,
        )],
    )

def test_absence_and_recovery_are_persisted_once(runtime):
    service, _, reader, _ = runtime
    reader.frames_to_read = [
        (0., []), (1., []), (2., []),
        (3., [PERSON]), (4., [PERSON]), (5., [PERSON]),
        (6., [PERSON]),
    ]
    run = finish(service, service.submit(command(duration_seconds=2), 'actor', 'cycle'))
    events = list(reversed(service.events('agent', 'actor', {'limit':100}).items))
    assert [event.event_type for event in events] == [
        'person_absence', 'person_presence_restored'
    ]
    assert events[0].severity == 'warning'
    assert events[1].severity == 'info'
    assert run.alert_state == 'normal'
    assert run.alert_started_at is None
```

Add a live-style test that stops while still absent and asserts `run.alert_state == 'absence'`, proving state is readable independently of event pagination.

- [ ] **Step 2: Run executor tests and confirm RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/backend/test_local_execution.py -q
```

Expected: contract validation or attribute failures because run alert fields and recovery events do not exist.

- [ ] **Step 3: Extend the run contract with safe defaults**

Add fields to `RunDTO` so demo and older serialized payloads remain readable:

```python
class RunDTO(DTO):
    # existing fields
    alert_state: Literal['normal', 'absence'] = 'normal'
    alert_started_at: str | None = None
```

Do not add schema columns: `LocalRun.payload` already persists the DTO JSON and is the existing ownership boundary for run state.

- [ ] **Step 4: Record transitions and persist state in one execution path**

Replace the boolean-alarm branch with transition handling:

```python
if observation.transition and not stop.is_set():
    self._record_transition_event(
        run, observation, timestamp, frame, boxes, binding, stop
    )
```

Keep per-frame count/targets in the existing observation transaction. Move the alert-state update into `_record_transition_event` so the durable event and the run's alert state commit atomically:

```python
with self.writing() as db:
    row = db.get(LocalRun, run.id)
    if stop.is_set() or row.state != 'running':
        return
    self._checked_source(db, run.source_snapshot)
    if observation.transition == 'absence':
        self._change(row, alert_state='absence', alert_started_at=stamp)
    else:
        self._change(row, alert_state='normal', alert_started_at=None)
    db.add(LocalEvent(
        id=identifier, agent_id=run.agent_id, actor_id=row.actor_id,
        run_id=run.id, payload=event.model_dump(mode='json'),
        evidence_key=key,
    ))
```

Generalize evidence/event creation with exact mappings:

```python
event_type = {
    'absence': 'person_absence',
    'restored': 'person_presence_restored',
}[observation.transition]
severity = 'warning' if observation.transition == 'absence' else 'info'
duration = (observation.absent_seconds if observation.transition == 'absence'
            else observation.present_seconds)
```

Absence evidence uses red text; recovery evidence uses green text. For file runs, event range starts at `timestamp - duration` and ends at `timestamp`. Stop/source ownership checks remain before durable write.

If the database transaction fails after an evidence image was written, delete that controlled evidence path before re-raising. This preserves the existing no-orphan evidence invariant.

- [ ] **Step 5: Run backend transition and compatibility tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/backend/test_presence_rule.py tests/backend/test_local_execution.py tests/backend/test_agent_workflow.py -q
```

Expected: all selected backend tests pass; old demo runs parse as `alert_state='normal'`.

- [ ] **Step 6: Regenerate and verify API contracts**

Run:

```powershell
.venv\Scripts\python.exe contracts/generate.py
Set-Location frontend
npm run generate:api
npm run typecheck
Set-Location ..
```

Expected: OpenAPI and TypeScript `RunDTO` contain `alert_state` and `alert_started_at`; typecheck exits 0.

- [ ] **Step 7: Commit backend state, events, and contract**

```powershell
git add backend/app/modules/agents/contracts.py backend/app/modules/local_execution/service.py backend/app/modules/agents/demo.py tests/backend/test_local_execution.py tests/backend/test_agent_workflow.py contracts/openapi.json frontend/src/shared/api/generated.ts
git commit -m "feat(监测): 持久化缺岗与复岗事件"
```

Stage only files actually changed; do not create an empty demo/workflow test modification.

---

### Task 3: Render persisted alarm state on live video

**Files:**
- Modify: `frontend/src/modules/agents/RunPlayer.vue`
- Modify: `frontend/src/modules/agents/MonitorPanel.vue`
- Modify: `frontend/src/modules/agents/VideoWall.vue`
- Modify: `frontend/src/modules/agents/state.ts`
- Modify: `frontend/src/modules/agents/agents.css`
- Create: `frontend/tests/agent-alert-overlay.test.ts`
- Modify: `frontend/tests/agent-wall.test.ts`

**Interfaces:**
- Consumes: generated `Run.alert_state` from Task 2.
- Produces: `RunPlayer` props `alertActive?: boolean` and `alertLabel?: string`.
- Produces: visual class `.alert-active` and banner `.run-alert-banner` with accessible `role="alert"`.

- [ ] **Step 1: Write failing player and pass-through tests**

Mount `RunPlayer` with a mock playback session and assert alert markup changes without recreating media:

```ts
it('keeps the picture red until persisted run state returns to normal', async () => {
  const wrapper = mount(RunPlayer, {
    props: {
      identity: 'run-1', agentId: 'agent-1',
      load: async () => playback(),
      alertActive: true, alertLabel: '人员缺岗',
    },
  })
  await flushPromises()
  expect(wrapper.get('.run-player-surface').classes()).toContain('alert-active')
  expect(wrapper.get('[role="alert"]').text()).toBe('人员缺岗')
  await wrapper.setProps({ alertActive: false })
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.get('.run-player-surface').classes()).not.toContain('alert-active')
})
```

Extend wall tests with a run whose `alert_state` is `absence` and assert the `RunPlayer` stub receives `alertActive=true`. Add a compact `MonitorPanel` mount asserting the selected single run receives the same prop.

- [ ] **Step 2: Run frontend tests and confirm RED**

Run:

```powershell
Set-Location frontend
npm test -- --run tests/agent-alert-overlay.test.ts tests/agent-wall.test.ts
Set-Location ..
```

Expected: missing props, banner, CSS class, and pass-through assertions fail.

- [ ] **Step 3: Add player alert props and accessible overlay**

Extend `RunPlayer` props:

```ts
const props = withDefaults(defineProps<{
  identity:string
  agentId:string
  load:()=>Promise<Playback>
  mediaKind?:'image'|'video'
  isLive?:boolean
  alertActive?:boolean
  alertLabel?:string
}>(), { mediaKind:'video', isLive:false, alertActive:false, alertLabel:'人员缺岗' })
```

Bind the state without changing `identity`, so an alert transition never restarts video:

```vue
<div ref="surface" class="run-player-surface" :class="{'alert-active':alertActive}">
  <div class="run-frame" :style="{aspectRatio:ratio,'--frame-ratio':ratio}">
    <div v-if="alertActive" class="run-alert-banner" role="alert">{{alertLabel}}</div>
    <svg v-if="session" class="run-overlays" :class="{'alert-active':alertActive}"
         viewBox="0 0 1000 1000" preserveAspectRatio="none"
         aria-label="后端提供的监测区域与目标位置">
      <!-- regions and targets retain geometry; only color changes -->
    </svg>
  </div>
</div>
```

Use CSS to apply a red inset border, red region/target strokes, and a high-contrast top-left banner. Keep pointer events disabled on overlays.

- [ ] **Step 4: Pass one run state to single view and video wall**

In `MonitorPanel.vue`:

```vue
<RunPlayer
  :key="selected.id"
  :identity="`${selected.id}:${selected.state}:${workspace?.runtime_available}`"
  :agent-id="agentId"
  :load="()=>agentApi.playback(agentId,selected!.id)"
  :is-live="selected.source_kind==='camera'&&state(selected)==='running'"
  :alert-active="selected.alert_state==='absence'"
  alert-label="人员缺岗"
/>
```

In `VideoWall.vue`, pass the matching `tile.run.alert_state` identically. Do not include alert state in the player `key` or `identity`; changing alarm state must not recreate the player or restart live video.

Add event labels in `state.ts`:

```ts
person_absence: '人员缺岗',
person_presence_restored: '恢复在岗',
```

Render `label(event.event_type)` in `EventsPanel.vue` if the raw machine value is currently displayed; include that file in the commit when changed.

- [ ] **Step 5: Run focused frontend tests and typecheck**

Run:

```powershell
Set-Location frontend
npm test -- --run tests/agent-alert-overlay.test.ts tests/agent-wall.test.ts tests/agent-realtime.test.ts
npm run typecheck
Set-Location ..
```

Expected: overlay, pass-through, event-stream, and type tests all pass.

- [ ] **Step 6: Commit the visual alarm linkage**

```powershell
git add frontend/src/modules/agents/RunPlayer.vue frontend/src/modules/agents/MonitorPanel.vue frontend/src/modules/agents/VideoWall.vue frontend/src/modules/agents/EventsPanel.vue frontend/src/modules/agents/state.ts frontend/src/modules/agents/agents.css frontend/tests/agent-alert-overlay.test.ts frontend/tests/agent-wall.test.ts
git commit -m "feat(画面): 联动显示缺岗与复岗状态"
```

Stage only files actually changed.

---

### Task 4: Full regression, runtime proof, and restart

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: all committed deliverables from Tasks 1–3.
- Produces: fresh test/build/runtime evidence and a running local application on `http://127.0.0.1:8000`.

- [ ] **Step 1: Run the full backend suite**

```powershell
.venv\Scripts\python.exe -m pytest tests/backend -q
```

Expected: zero failures.

- [ ] **Step 2: Run the full frontend suite and production build**

```powershell
Set-Location frontend
npm test
npm run build
Set-Location ..
```

Expected: zero test failures, successful `vue-tsc`, and successful Vite build. The existing HLS chunk-size warning is informational.

- [ ] **Step 3: Check the committed diff and worktree**

```powershell
git diff --check HEAD~3..HEAD
git status --short
git log -4 --oneline
```

Expected: no whitespace errors, clean worktree, and three implementation commits after the design/plan commits.

- [ ] **Step 4: Restart only the project process tree**

Resolve the current `deploy/scripts/run.py` root process through `Get-CimInstance Win32_Process`, stop that exact process tree, then start:

```powershell
Start-Process -FilePath '.venv\Scripts\python.exe' `
  -ArgumentList '-u','deploy/scripts/run.py' `
  -WorkingDirectory (Get-Location) `
  -WindowStyle Hidden `
  -RedirectStandardOutput 'var\logs\run.log' `
  -RedirectStandardError 'var\logs\run-error.log'
```

Do not stop the separately managed MediaMTX/simulated-camera process tree.

- [ ] **Step 5: Verify readiness and state contract**

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
```

Expected: API, worker, FFmpeg, MediaMTX, and local models report `ready`; GPU may remain `unavailable`. Query an active agent workspace and verify each run includes `alert_state`.

- [ ] **Step 6: Report delivery state**

Report commit IDs, test counts, runtime readiness, and that changes remain local until the user explicitly requests a push. Do not create a PR.
