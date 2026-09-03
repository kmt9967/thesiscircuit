import asyncio

import httpx
import pytest

from backend.app.config import Settings
from backend.app.phase2.engine import run_batch
from backend.app.phase2.policy import Policy
from backend.app.phase2.repository import Phase2Repository
from tests.test_phase2 import position, state


def test_concurrent_dispatchers_have_one_owner():
    async def scenario():
        entered, proceed = asyncio.Event(), asyncio.Event()
        class Repo:
            active=False
            def __init__(self): self.rows={}; self.events=[]
            async def completed(self,key): return key in self.rows
            async def acquire_lease(self,*_):
                if self.active: return False
                self.active=True; self.events.append("START"); return True
            async def history(self): return [],[]
            async def release_lease(self,owner,outcome,cycle=None):
                self.events.append(outcome)
                if cycle: self.rows[str(cycle.id)]=cycle
                self.active=False
        class Provider:
            calls=0
            async def refresh(self,*_):
                self.calls+=1; entered.set(); await proceed.wait()
                return state(positions=[position()])
        repo,provider=Repo(),Provider()
        task=asyncio.create_task(run_batch(provider,repo,Settings(),Policy(),"overlap",count=1))
        await entered.wait()
        with pytest.raises(RuntimeError,match="overlap"):
            await run_batch(provider,repo,Settings(),Policy(),"second",count=1)
        proceed.set(); await task
        await run_batch(provider,repo,Settings(),Policy(),"overlap",count=1)
        assert provider.calls==1 and repo.events==["START","COMPLETED"]
    asyncio.run(scenario())


def test_uncertain_completion_is_reconciled_not_duplicated():
    class Repo:
        def __init__(self): self.rows={}
        calls=0
        async def completed(self,key): return key in self.rows
        async def acquire_lease(self,*_): return True
        async def history(self): return [],[]
        async def release_lease(self,owner,outcome,cycle=None):
            if cycle:
                self.rows[str(cycle.id)]=cycle
                self.calls+=1
                raise httpx.ReadTimeout("Acknowledgment lost")
    class Provider:
        calls=0
        async def refresh(self,*_): self.calls+=1; return state()
    async def scenario():
        repo,provider=Repo(),Provider()
        with pytest.raises(httpx.ReadTimeout):
            await run_batch(provider,repo,Settings(),Policy(),"timeout",count=1)
        await run_batch(provider,repo,Settings(),Policy(),"timeout",count=1)
        assert provider.calls==1 and repo.calls==1
    asyncio.run(scenario())


@pytest.mark.parametrize("reply", [False,None,"true"])
def test_expired_or_malformed_completion_ack_fails_closed(reply):
    async def scenario():
        cfg=Settings(supabase_url="https://example.supabase.co",supabase_service_role_key="test")
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=reply))) as client:
            with pytest.raises((RuntimeError, ValueError)):
                await Phase2Repository(cfg,client).release_lease("owner","FAILED")
    asyncio.run(scenario())
