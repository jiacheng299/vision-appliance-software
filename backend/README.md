# Foundation backend and worker

The API is a FastAPI application factory at `app.main:create_app`. Keep `backend` and repository root on `PYTHONPATH`; run from the repository root. Start the API before its independent Worker on a new database. Parent deployment tooling supplies these commands and same-origin frontend assets.

```powershell
$env:PYTHONPATH = "$PWD/backend;$PWD"
.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
# Another terminal with the same environment:
.venv/Scripts/python.exe -m worker.supervisor
.venv/Scripts/python.exe -m pytest tests/backend -q
.venv/Scripts/python.exe contracts/generate.py
```

All Python dependencies, including development test dependencies, are pinned in `backend/requirements.txt`. The worktree `.venv` is independent of any prior demo environment. Alembic revision `0001_foundation` contains explicit frozen table definitions; API and Worker run migrations at startup. Application DTOs are separate from ORM models. Modules own source management, settings, runtime and realtime transport. Shared services own controlled storage, configuration, encryption, errors and database access.

## Effective environment configuration

| Variable | Default / meaning |
|---|---|
| `VISION_VAR_ROOT` | Repository `var`; SQLite `vision.db`, `uploads`, `media` and `secrets` live here |
| `VISION_FRONTEND_DIST` | Repository `frontend/dist`; static assets and SPA fallback outside `/api` |
| `VISION_FFMPEG` / `VISION_FFPROBE` | `ffmpeg` / `ffprobe` resolved on PATH; absolute executable paths accepted |
| `VISION_MEDIA_TIMEOUT_SECONDS` | 120; bounded duration for each local media command |
| `VISION_WORKER_LEASE_SECONDS` | 180; live Worker renews unexpired leases every 3 seconds |
| `VISION_WORKER_POLL_SECONDS` | 1; queue polling interval |
| `VISION_MAX_CHUNK_BYTES` | 8388608; browser should use chunks of at most 4 MiB |

Settings are persisted, validated and versioned. They do not accept arbitrary host paths. Default camera allowlist is loopback only. The allowed private CIDR ranges are RFC1918 IPv4, IPv6 unique local and loopback. Expanding this policy requires an explicit settings change. Unknown fields and broad/public ranges are rejected.

## Account-free access, storage and media behavior

The application has no user accounts, login, roles, session cookies or CSRF tokens. Business APIs, settings, media and WebSocket are immediately usable. HTTP writes and WebSocket reject unrelated browser origins. Camera credentials remain encrypted and media paths remain controlled. Historical users/sessions tables from the initial migration are retained for compatibility but have no active ORM models or routes.

Camera userinfo is removed from returned addresses. Usernames and passwords are encrypted with Fernet in the database. `var/secrets/camera.key` is generated locally; back up this key together with the database to retain access to camera credentials. Lost/corrupted ciphertext produces `credentials_unavailable`; submitting both username and password can replace it. Omitted credentials preserve their value, explicit empty strings clear them, and separately supplied credentials override embedded URL userinfo. Credentials and FFmpeg stderr are never returned or written to application logs.

Uploads use UUID directories and bounded sequential chunks. Identical retransmission is idempotent, mismatched retransmission and incomplete completion return 409. Completion durably enqueues a media job and returns `probing`; only successful FFprobe, real H264/AAC browser preview transcode and a final output probe produce `ready`. The worker hashes and verifies the original bytes. Same filenames do not overwrite files. Media uses FileResponse with HTTP Range support. Archive revokes media access and cancels pending jobs/uploads. Cancellation and archival retain files in private storage; they do not claim physical erasure.

The Worker claims jobs under a SQLite writer lock. Ownership requires the worker ID and an unexpired lease. Heartbeat cannot resurrect an expired lease. Expired jobs can be reclaimed, and repeated lease expiry eventually becomes a visible failure. Final state updates recheck ownership and cancellation. The global `max_concurrent_jobs` is an upper bound across Worker processes; each supervisor executes one job at a time.

## Explicit boundaries and diagnostics

- Camera connection tests use pinned-IP RTSP DESCRIBE, with Basic and common Digest authentication, total response deadlines, bounded response sizes and no redirect following. This proves only the returned RTSP video session description. A successful diagnostic leaves the source `unverified` with `media_gateway_unavailable`; it never claims decoded video or an online stream. Preview returns actionable 503 until a real media gateway adapter is integrated.
- There is no MediaMTX adapter, model executor, inference engine or GPU collector. Their service states are unavailable. There are no fabricated runs, events, loaded models or GPU percentages.
- Runtime CPU, memory and disk values are measured locally. The API samples every 3 seconds and on requested snapshots. History is bounded in process memory; a process restart begins a new observation history. Realtime source/runtime notifications are retained in SQLite up to the last 500 notifications; stale cursors require a REST resync.
- Retention/export/reconnection preferences are stored and validated for later capability integration. This foundation does not perform retention cleanup, report export, continuous camera decoding or reconnection. Changing the session timeout affects newly created sessions.
- FFmpeg always produces a browser-compatible preview; large/slow media may reach the configured processing timeout. Inputs with no valid video track, damaged media and unsupported demuxers fail explicitly. Local media commands restrict accepted demuxers and protocols, use argument arrays with `shell=False`, and never accept user host paths.
- Health readiness reports all component states while keeping the API usable if media tools, Worker, gateway or models are unavailable.

## Verification evidence

`tests/backend/red-evidence.txt` records the initial missing application. `security-red-evidence.txt`, `rtsp-red-evidence.txt`, `review-red-evidence.txt` and `recovery-red-evidence.txt` capture observed regression failures before fixes. `green-evidence.txt` and other evidence text files describe the earlier account-based revision; rerun the current suite for current results. Current tests cover account-free API/media/WebSocket access, same-origin checks, legacy settings upgrade, exact credential bytes, secrets at rest, database restart, optimistic concurrency, allowlists, upload order/idempotence/size/cancellation, worker leases/concurrency, truthful camera diagnostics, redirect/401/deadline handling, missing tools, corrupt credentials and real video import/Range/thumbnail access.
