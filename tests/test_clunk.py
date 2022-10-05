import asyncio

from suggestions.clunk import Clunk, ClunkLock


async def test_pre_queue(clunk_lock: ClunkLock):
    data = []

    async def append(number):
        data.append(number)

    clunk_lock.enqueue(append(1))
    clunk_lock.enqueue(append(2))
    clunk_lock.enqueue(append(3))

    await clunk_lock.run()
    await clunk_lock.wait()

    assert data == [1, 3]

    await clunk_lock.kill()


async def test_post_queue_instant(clunk_lock: ClunkLock):
    data = []

    async def append(number):
        data.append(number)

    await clunk_lock.run()

    clunk_lock.enqueue(append(1))
    clunk_lock.enqueue(append(2))
    clunk_lock.enqueue(append(3))

    await clunk_lock.wait()
    assert data == [1, 3]
    await clunk_lock.kill()


async def test_post_queue_with_sleep(clunk_lock: ClunkLock):
    data = []

    async def append(number):
        data.append(number)
        await asyncio.sleep(0.01)

    await clunk_lock.run()

    clunk_lock.enqueue(append(1))
    clunk_lock.enqueue(append(2))
    clunk_lock.enqueue(append(3))

    await clunk_lock.wait()
    assert data == [1, 3]
    await clunk_lock.kill()


async def test_clunk_acquisition_eviction(clunk: Clunk):
    # These should be different due to non-lazy cache eviction
    r_1 = clunk.acquire("test")
    r_2 = clunk.acquire("test")
    assert r_1 is not r_2


async def test_clunk_acquisition_different_keys(clunk: Clunk):
    r_1 = clunk.acquire("test")
    r_2 = clunk.acquire("test", is_up_vote=False)
    assert r_1 is not r_2


async def test_clunk_acquisition_same(clunk: Clunk):
    data = []

    async def task(number):
        data.append(number)
        await asyncio.sleep(0.05)

    r_1: ClunkLock = clunk.acquire("test")
    r_1.enqueue(task(1))
    await r_1.run()

    r_2: ClunkLock = clunk.acquire("test")
    assert r_2.is_currently_running is True
    assert r_2 is r_1

    r_2.enqueue(task(1))
    await r_1.wait()
    assert data == [1, 1]

    await r_2.kill()
    await asyncio.sleep(0.01)  # Let the loop propagate
    assert r_1.is_currently_running is False
