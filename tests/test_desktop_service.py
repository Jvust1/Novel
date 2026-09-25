import asyncio
from desktop_adapter import serve_until_stopped


def test_shutdown_waits_for_full_server_stop(tmp_path):
    events=[]
    class FakeServer:
        async def start(self):events.append('start')
        def stop(self):events.append('stop')
        @property
        def stopped(self):
            async def complete():events.append('stopped')
            return complete()
    stop=tmp_path/'stop';stop.write_text('stop')
    asyncio.run(serve_until_stopped(FakeServer(),stop))
    assert events==['start','stop','stopped']


def test_cancellation_still_closes_server(tmp_path):
    events=[]
    class FakeServer:
        async def start(self):events.append('start')
        def stop(self):events.append('stop')
        @property
        def stopped(self):
            async def complete():events.append('stopped')
            return complete()
    async def exercise():
        task=asyncio.create_task(serve_until_stopped(FakeServer(),tmp_path/'not-yet'))
        await asyncio.sleep(.01);task.cancel()
        try:await task
        except asyncio.CancelledError:pass
    asyncio.run(exercise())
    assert events==['start','stop','stopped']
