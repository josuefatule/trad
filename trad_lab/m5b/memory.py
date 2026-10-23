"""Bounded in-memory ASGI WebSocket harness. Never calls socket/bind/listen."""
import asyncio
import json
from types import SimpleNamespace
from urllib.parse import urlsplit


class MemoryClosed(ConnectionError):
    pass


class MemorySocket:
    def __init__(self, app, path, *, headers=(), query=b'', subprotocols=(), client='127.0.0.1',port=18000):
        self.incoming=asyncio.Queue(maxsize=4);self.outgoing=asyncio.Queue(maxsize=4)
        self.scope={'type':'websocket','asgi':{'version':'3.0'},'scheme':'ws','path':path,'raw_path':path.encode(),
                    'query_string':query,'headers':list(headers),'client':(client,50101),'server':('127.0.0.1',port),
                    'root_path':'','subprotocols':list(subprotocols),'state':{}}
        self.app=app;self.task=None;self.close_code=None

    async def open(self):
        self.task=asyncio.create_task(self.app(self.scope,self.incoming.get,self.outgoing.put))
        await self.incoming.put({'type':'websocket.connect'})
        message=await self._next()
        if message['type']!='websocket.accept':
            await self.task
            raise MemoryClosed('WebSocket rejected '+str(message.get('code')))
        return self

    async def _next(self):
        receiver=asyncio.create_task(self.outgoing.get())
        done,_=await asyncio.wait({receiver,self.task},return_when=asyncio.FIRST_COMPLETED)
        if receiver in done:return receiver.result()
        if not self.outgoing.empty():receiver.cancel();await asyncio.gather(receiver,return_exceptions=True);return self.outgoing.get_nowait()
        receiver.cancel();await asyncio.gather(receiver,return_exceptions=True)
        self.task.result();raise MemoryClosed('ASGI ended without a frame')

    async def recv(self):
        message=await self._next()
        if message['type']=='websocket.close':
            self.close_code=message['code'];raise MemoryClosed('WebSocket closed '+str(self.close_code))
        if message['type']!='websocket.send':raise MemoryClosed('Unexpected ASGI event')
        return message.get('text',message.get('bytes'))

    async def send(self,pcm):
        if self.task.done():raise MemoryClosed('ASGI already closed')
        await self.incoming.put({'type':'websocket.receive','bytes':pcm})

    async def close(self):
        if not self.task:return
        if not self.task.done():
            try:await asyncio.wait_for(self.incoming.put({'type':'websocket.disconnect','code':1000}),1)
            except TimeoutError:self.task.cancel()
        try:await asyncio.wait_for(asyncio.shield(self.task),3)
        except (TimeoutError,asyncio.CancelledError):
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)


def connector(service):
    async def connect(url,**kwargs):
        from urllib.parse import urlsplit
        parts=urlsplit(url)
        headers=[(k.lower().encode(),v.encode()) for k,v in kwargs.get('additional_headers',{}).items()]
        return await MemorySocket(service,parts.path,query=parts.query.encode(),headers=headers).open()
    return connect


class MemoryHTTP:
    def __init__(self,app,base_url='http://127.0.0.1:18010'):self.app=app;self.base=urlsplit(base_url)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def get(self,path,headers=None):return await self.request('GET',path,headers)
    async def post(self,path,headers=None,json=None):return await self.request('POST',path,headers,json)
    async def request(self,method,path,headers=None,data=None):
        body=b'' if data is None else json.dumps(data).encode()
        parts=urlsplit(path)
        values=[(b'host',self.base.netloc.encode()),(b'content-type',b'application/json'),(b'content-length',str(len(body)).encode())]
        values += [(k.lower().encode(),v.encode()) for k,v in (headers or {}).items()]
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':self.base.scheme,
               'path':parts.path,'raw_path':parts.path.encode(),'query_string':parts.query.encode(),'root_path':'',
               'headers':values,'client':('127.0.0.1',50001),'server':(self.base.hostname,self.base.port),'state':{}}
        messages=[];used=False
        async def receive():
            nonlocal used
            if used:await asyncio.Future()
            used=True;return {'type':'http.request','body':body,'more_body':False}
        async def send(message):messages.append(message)
        await self.app(scope,receive,send)
        start=next(m for m in messages if m['type']=='http.response.start')
        content=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
        return SimpleNamespace(status_code=start['status'],json=lambda:json.loads(content),content=content,headers=dict(start['headers']))
