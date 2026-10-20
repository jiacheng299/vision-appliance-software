import asyncio
from collections import deque, defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
import threading
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException
from sqlalchemy import select, delete
from .shared.config import Config
from .shared.db import make_engine, migrate, session_factory
from .shared.errors import Error, handle_error, error_response
from .shared.security import Vault
from .shared.models import Notification
from .schemas import ErrorDTO
from .modules import auth, sources, settings, runtime, realtime
from .modules.agents import routes as agents

class LoginGuard:
    def __init__(self):
        self.attempts = defaultdict(deque)
        self.lock = threading.Lock()
    def check(self, identity):
        with self.lock:
            queue = self.attempts[identity]
            while queue and queue[0]<time.monotonic()-60:
                queue.popleft()
            if len(queue)>=15:
                raise Error(429,'login_rate_limited','登录尝试过于频繁，请稍后重试。',retryable=True)
            queue.append(time.monotonic())
            if len(self.attempts)>10000:
                self.attempts = defaultdict(deque,{identity:queue})

async def sample_runtime(app):
    while True:
        await asyncio.sleep(3)
        with app.state.sessions() as db:
            payload = runtime.runtime_snapshot(app,db)
            payload['history'] = []
            notification = Notification(type='runtime',aggregate_id=None,payload=payload)
            db.add(notification)
            db.flush()
            cutoff = notification.sequence-500
            if cutoff>0:
                db.execute(delete(Notification).where(Notification.sequence<cutoff))
            db.commit()

def create_app(var_root=None,testing=False):
    config = Config(**({'var_root':var_root} if var_root is not None else {}))
    config.prepare()
    engine = make_engine(config)
    migrate(engine)
    sessions = session_factory(engine)
    with sessions() as db:
        settings.initialize(db)
    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(sample_runtime(app))
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        engine.dispose()
    app = FastAPI(title='Vision Appliance Foundation API',version=config.version,lifespan=lifespan,docs_url='/api/docs',openapi_url='/api/openapi.json',redoc_url=None)
    app.state.config, app.state.engine, app.state.sessions = config, engine, sessions
    app.state.vault = Vault(config)
    app.state.login_guard = LoginGuard()
    app.state.runtime_history = deque(maxlen=120)
    @app.middleware('http')
    async def request_context(request:Request,call_next):
        request.state.request_id = str(uuid.uuid4())
        try:
            response = await call_next(request)
        except Exception:
            response = error_response(request,500,'internal_error','服务器内部错误，请通过请求编号联系维护人员。')
        response.headers['X-Request-ID'] = request.state.request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response
    app.add_exception_handler(Error,handle_error)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        return error_response(request,422,'validation_error','请求字段或值不符合要求。',[{'field':'.'.join(map(str,e['loc'])),'type':e['type']} for e in exc.errors()])
    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        return error_response(request,exc.status_code,'not_found' if exc.status_code==404 else 'http_error','请求资源不存在。' if exc.status_code==404 else '请求无法完成。')
    for module in (auth,sources,settings,runtime,realtime,agents):
        app.include_router(module.router,prefix='/api/v1',responses={code:{'model':ErrorDTO} for code in (400,401,403,404,409,413,422,429,500,503)})
    @app.get('/{path:path}',include_in_schema=False)
    def frontend(path:str):
        if path=='api' or path.startswith('api/'):
            raise Error(404,'not_found','API 路径不存在。')
        root = config.frontend_dist.resolve()
        candidate = (root / path).resolve()
        if root not in candidate.parents and candidate!=root:
            raise Error(404,'not_found','请求资源不存在。')
        if candidate.is_file():
            return FileResponse(candidate)
        if (root / 'index.html').is_file() and ('.' not in Path(path).name):
            return FileResponse(root / 'index.html')
        raise Error(404,'frontend_unavailable','前端尚未构建，请先完成前端构建。')
    return app
