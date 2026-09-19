import asyncio
from datetime import datetime, timezone

from aiohttp import web

from app.ha import HAWebSocket


def test_websocket_monotonic_ids_and_hourly_forecast():
    async def scenario():
        commands = []

        async def serve(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({'type':'auth_required'})
            await ws.receive_json()
            await ws.send_json({'type':'auth_ok'})
            async for msg in ws:
                command = msg.json()
                assert not commands or command['id'] > commands[-1]['id']
                commands.append(command)
                result = [] if command['type']=='get_states' else None
                await ws.send_json({'id':command['id'], 'type':'result', 'success':True, 'result':result})
                if command['type']=='weather/subscribe_forecast':
                    await ws.send_json({'id':command['id'],'type':'event','event':{'forecast':[]}})
            return ws

        app = web.Application(); app.router.add_get('/api/websocket', serve)
        runner = web.AppRunner(app); await runner.setup()
        site = web.TCPSite(runner,'127.0.0.1',0); await site.start()
        port = site._server.sockets[0].getsockname()[1]
        client=HAWebSocket(f'ws://127.0.0.1:{port}/api/websocket','test',{'weather.home'})
        stream=client.stream()
        try:
            kind,_=await asyncio.wait_for(anext(stream),2)
            assert kind=='initial'
            kind,_=await asyncio.wait_for(anext(stream),2)
            assert kind=='forecast'
        finally:
            await stream.aclose(); await runner.cleanup()
        assert commands[0]['type']=='subscribe_trigger'

    asyncio.run(scenario())
