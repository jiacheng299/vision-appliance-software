"""Run with: PYTHONPATH=backend python -m worker.supervisor.

A SQLite lease owns each durable job. A separate heartbeat renews leases while FFmpeg runs.
Multiple supervisor processes may share a database; claims are serialized by BEGIN IMMEDIATE.
"""
import hashlib
import os
import signal
import threading
import time
from cryptography.fernet import InvalidToken
from sqlalchemy import select, update, text
from app.shared.config import Config
from app.shared.db import make_engine, migrate, session_factory
from app.shared.models import Job, Source, Upload, Worker, Log, now, uid
from app.shared.security import Vault
from app.shared.storage import controlled_path
from app.shared.media_gateway import MediaGateway
from app.shared.errors import Error
from app.modules.settings import values_for
from app.modules.sources import notify_source
from .media import probe, transcode, MediaFailure
from .camera import describe

class Supervisor:
    def __init__(self, config=None):
        self.config = config or Config()
        self.config.prepare()
        self.engine = make_engine(self.config)
        migrate(self.engine)
        self.sessions = session_factory(self.engine)
        self.id = uid()
        self.vault = Vault(self.config)
        self.stop = threading.Event()

    def heartbeat(self):
        with self.sessions() as db:
            worker = db.get(Worker,self.id)
            if not worker:
                db.add(Worker(id=self.id,pid=os.getpid(),heartbeat_at=time.time()))
            else:
                worker.heartbeat_at = time.time()
            observed = time.time()
            db.execute(update(Job).where(Job.lease_owner==self.id,Job.state=='running',Job.lease_until>observed).values(lease_until=observed+self.config.worker_lease_seconds))
            db.commit()

    def _heartbeat_loop(self):
        while not self.stop.wait(3):
            try:
                self.heartbeat()
            except Exception:
                # Do not keep a worker falsely online if the DB becomes inaccessible.
                continue

    def claim(self):
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            expired = list(db.scalars(select(Job).where(Job.state=='running',Job.lease_until<time.time())))
            for job in expired:
                if job.attempts>=3:
                    job.state,job.error_code,job.message = 'failed','worker_lease_expired','作业租约多次过期，请检查 Worker 与媒体工具后重新导入。'
                    source = db.get(Source,job.source_id)
                    if source and not source.archived:
                        source.status,source.error_code,source.error_message = 'failed',job.error_code,job.message
                        source.row_version += 1
                        source.updated_at,source.observed_at = now(),now()
                        notify_source(db,source)
                    if job.upload_id:
                        upload = db.get(Upload,job.upload_id)
                        upload.state,upload.error_code,upload.error_message = 'failed',job.error_code,job.message
                else:
                    job.state = 'queued'
                job.lease_owner,job.lease_until = None,None
            db.flush()
            running = len(list(db.scalars(select(Job.id).where(Job.state=='running'))))
            if running >= values_for(db,'resources')['max_concurrent_jobs']:
                db.commit()
                return None
            job = db.scalar(select(Job).where(Job.state=='queued').order_by(Job.created_at,Job.id).limit(1))
            if not job:
                db.commit()
                return None
            job.state,job.lease_owner = 'running',self.id
            job.lease_until = time.time()+self.config.worker_lease_seconds
            job.attempts += 1
            job_id = job.id
            db.commit()
            return job_id

    def owned(self,db,job_id):
        job = db.get(Job,job_id)
        return job if job and job.state=='running' and job.lease_owner==self.id and job.lease_until>time.time() else None

    def process_media(self,job_id):
        with self.sessions() as db:
            job = self.owned(db,job_id)
            if not job:
                return
            upload = db.get(Upload,job.upload_id)
            upload_id,source_id,chunks = upload.id,job.source_id,dict(upload.chunks)
            source = db.get(Source,source_id)
            if source.archived or upload.state=='canceled':
                return
        folder = controlled_path(self.config,'uploads',upload_id)
        original = folder / 'original.media'
        pending = folder / f'{self.id}.assembling'
        sha = hashlib.sha256()
        total = 0
        with pending.open('wb') as output:
            for number in range(len(chunks)):
                path = folder / f'{number}.chunk'
                chunk_sha = hashlib.sha256()
                size = 0
                with path.open('rb') as input_file:
                    while block := input_file.read(1024*1024):
                        output.write(block)
                        sha.update(block)
                        chunk_sha.update(block)
                        size += len(block)
                if chunk_sha.hexdigest()!=chunks[str(number)]['sha256'] or size!=chunks[str(number)]['size']:
                    raise MediaFailure('upload_integrity_error','上传分块校验失败，请重新导入。')
                total += size
        pending.replace(original)
        metadata = probe(self.config,original)
        with self.sessions() as db:
            job = self.owned(db,job_id)
            if not job:
                return
            source,upload = db.get(Source,source_id),db.get(Upload,upload_id)
            if source.archived or upload.state=='canceled':
                return
            for field,value in metadata.items():
                setattr(source,field,value)
            source.sha256,source.size_bytes = sha.hexdigest(),total
            source.status,upload.state = 'transcoding','transcoding'
            source.updated_at,source.observed_at = now(),now()
            source.row_version += 1
            notify_source(db,source)
            db.commit()
        destination = controlled_path(self.config,'media',source_id)
        destination.mkdir(exist_ok=True)
        target,thumbnail = destination / f'{self.id}.mp4',destination / f'{self.id}.jpg'
        thumbnail_ready = transcode(self.config,original,target,thumbnail)
        # Probe the final browser preview before making it visible.
        probe(self.config,target)
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            job = self.owned(db,job_id)
            if not job:
                return
            source,upload = db.get(Source,source_id),db.get(Upload,upload_id)
            if source.archived or upload.state=='canceled':
                return
            source.media_key = f'{source_id}/{self.id}.mp4'
            source.thumbnail_key = f'{source_id}/{self.id}.jpg' if thumbnail_ready else None
            source.status,upload.state,job.state = 'ready','ready','completed'
            source.error_code=source.error_message=None
            source.updated_at,source.observed_at = now(),now()
            source.row_version += 1
            job.lease_owner=job.lease_until=None
            notify_source(db,source)
            db.add(Log(level='INFO',module='worker',message='文件探测与浏览器预览转码完成。'))
            db.commit()

    def process_camera(self,job_id):
        with self.sessions() as db:
            job = self.owned(db,job_id)
            if not job:
                return
            source = db.get(Source,job.source_id)
            if source.archived:
                return
            try:
                address,credentials = source.address,self.vault.decrypt(source.credentials)
            except InvalidToken:
                raise MediaFailure('credentials_unavailable','摄像头凭据无法解密，请恢复对应密钥备份或重新保存凭据。')
            expected_credentials = source.credentials
            networks = values_for(db,'security')['camera_allowed_networks']
            timeout = values_for(db,'resources')['connection_timeout_seconds']
        describe(address,credentials,networks,timeout)
        gateway = MediaGateway(self.config)
        try:
            gateway.ensure_published(source,networks)
            published = True
        except Error:
            published = False
        finally:
            gateway.close()
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            job = self.owned(db,job_id)
            if not job:
                return
            source = db.get(Source,job.source_id)
            if source.archived or source.address!=address or source.credentials!=expected_credentials:
                job.state='canceled'
            else:
                source.status,source.observed_at,source.updated_at = 'unverified',now(),now()
                source.row_version += 1
                source.error_code=None if published else 'media_gateway_unavailable'
                source.error_message=None if published else 'RTSP 视频会话描述可达；尚未在媒体网关确认该路视频，浏览器直播暂不可用。'
                job.state='completed'
                job.message='RTSP 视频会话描述可达，媒体网关已连接；请打开预览检查实际画面。' if published else source.error_message
                notify_source(db,source)
            job.lease_owner=job.lease_until=None
            db.commit()

    def fail(self,job_id,failure):
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            job = self.owned(db,job_id)
            if not job:
                return
            source = db.get(Source,job.source_id)
            if source and not source.archived and source.status!='canceled':
                source.status,source.error_code,source.error_message='failed',failure.code,failure.message
                source.updated_at,source.observed_at=now(),now()
                source.row_version += 1
                notify_source(db,source)
            if job.upload_id:
                upload = db.get(Upload,job.upload_id)
                if upload.state!='canceled':
                    upload.state,upload.error_code,upload.error_message='failed',failure.code,failure.message
            job.state,job.error_code,job.message='failed',failure.code,failure.message
            job.lease_owner=job.lease_until=None
            db.add(Log(level='ERROR',module='worker',message=failure.message))
            db.commit()

    def run_once(self):
        self.heartbeat()
        job_id = self.claim()
        if not job_id:
            return False
        heartbeat = threading.Thread(target=self._heartbeat_loop,daemon=True)
        heartbeat.start()
        try:
            with self.sessions() as db:
                kind = db.get(Job,job_id).kind
            if kind=='media_probe':
                self.process_media(job_id)
            elif kind=='camera_test':
                self.process_camera(job_id)
            else:
                raise MediaFailure('unknown_job','无法识别作业类型。')
        except MediaFailure as failure:
            self.fail(job_id,failure)
        except (OSError,ValueError,KeyError):
            self.fail(job_id,MediaFailure('storage_error','媒体文件读写或校验失败，请检查存储空间并重新导入。'))
        finally:
            self.stop.set()
            heartbeat.join(timeout=5)
            self.stop.clear()
        return True

    def run(self):
        shutdown = threading.Event()
        def stop(*_):
            shutdown.set()
        signal.signal(signal.SIGINT,stop)
        signal.signal(signal.SIGTERM,stop)
        try:
            while not shutdown.is_set():
                if not self.run_once():
                    shutdown.wait(self.config.worker_poll_seconds)
        finally:
            with self.sessions() as db:
                worker = db.get(Worker,self.id)
                if worker:
                    db.delete(worker)
                    db.commit()
            self.engine.dispose()

if __name__=='__main__':
    Supervisor().run()
