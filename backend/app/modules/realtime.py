import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func
from ..shared.models import Notification, now, uid
from ..shared.security import same_origin_request
from .runtime import runtime_snapshot

router = APIRouter()

def envelope(item):
    return {'schema_version':'1.0','event_id':item.event_id,'sequence':item.sequence,'type':item.type,'occurred_at':item.occurred_at,'aggregate_id':item.aggregate_id,'payload':item.payload}


@router.websocket('/ws')
async def websocket_endpoint(websocket:WebSocket):
    if not same_origin_request(websocket):
        await websocket.close(code=1008,reason='Origin not allowed')
        return
    await websocket.accept()
    topics, cursor = set(), 0
    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(),timeout=2)
                if not isinstance(message,dict) or message.get('type')!='subscribe' or not isinstance(message.get('topics'),list) or any(t not in ('runtime','source','sources') for t in message['topics']):
                    await websocket.close(code=1008,reason='Invalid subscription')
                    return
                topics = {'source' if t=='sources' else t for t in message['topics']}
                with websocket.app.state.sessions() as db:
                    newest = db.scalar(select(func.max(Notification.sequence))) or 0
                    oldest = db.scalar(select(func.min(Notification.sequence))) or 0
                    previous = message.get('last_sequence')
                    if previous is not None and (not isinstance(previous,int) or previous>newest or previous<max(oldest-1,0)):
                        await websocket.send_json({'schema_version':'1.0','event_id':uid(),'sequence':newest,'type':'resync_required','occurred_at':now(),'aggregate_id':None,'payload':{'reason':'REST snapshot required'}})
                        previous = None
                    if previous is None:
                        cursor = newest
                        if 'runtime' in topics:
                            snapshot = runtime_snapshot(websocket.app,db,record=False)
                            await websocket.send_json({'schema_version':'1.0','event_id':uid(),'sequence':cursor,'type':'runtime','occurred_at':snapshot['observed_at'],'aggregate_id':None,'payload':snapshot})
                    else:
                        cursor = previous
            except asyncio.TimeoutError:
                pass
            with websocket.app.state.sessions() as db:
                rows = list(db.scalars(select(Notification).where(Notification.sequence>cursor).order_by(Notification.sequence).limit(200)))
                for row in rows:
                    cursor = row.sequence
                    if row.type in topics:
                        await websocket.send_json(envelope(row))
    except (WebSocketDisconnect,RuntimeError,ValueError,json.JSONDecodeError):
        return
