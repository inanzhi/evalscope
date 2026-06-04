"""SandboxService: process-level facade for ms_enclave sandbox managers.

Unifies the two historical code paths:

* ``SandboxMixin.EnclaveSandboxBackend`` – one manager per benchmark, pooled.
* ``EnclaveAgentEnvironment`` – one manager per process, per-sample containers.

Both are now thin wrappers around :class:`SandboxService`.  The service
caches managers keyed by ``(engine, manager_config)`` so the same
``base_url`` / Docker daemon is reused across benchmarks and agent
environments within a process.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import threading
from typing import TYPE_CHECKING, Any, Awaitable, Dict, Optional, Tuple, TypeVar

from evalscope.utils.logger import get_logger
from .config_builder import build_sandbox_config
from .engine import SandboxEngine, get_enclave_types, resolve_engine

if TYPE_CHECKING:
    from ms_enclave.sandbox.manager import SandboxManager

logger = get_logger()

T = TypeVar('T')

# ---------------------------------------------------------------------------
# Handles: returned to callers instead of raw SandboxManager to keep the
# lifecycle consistent (pool vs per-sample).
# ---------------------------------------------------------------------------


class PoolHandle:
    """Handle for a pooled sandbox warmed up via ``manager.initialize_pool``.

    ``execute_tool_in_pool`` borrows a free sandbox from the pool, runs the
    tool, and returns it.  The pool itself is stopped when the parent
    :class:`SandboxService` shuts down.

    When ``service`` is provided, the underlying manager coroutine is run on
    the service's dedicated loop (the loop the manager was started on), so the
    pool's loop-bound asyncio primitives (``_pool_lock`` / ``_pool_condition``)
    are always touched from the same loop.  ``service=None`` keeps the handle
    usable standalone (e.g. unit tests with a mock manager).
    """

    def __init__(self, manager: 'SandboxManager', service: Optional['SandboxService'] = None) -> None:
        self._manager = manager
        self._service = service

    @property
    def manager(self) -> 'SandboxManager':
        return self._manager

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        coro = self._manager.execute_tool_in_pool(tool_name, parameters)
        if self._service is not None:
            return await self._service._run_coro(coro)
        return await coro


class SandboxHandle:
    """Handle for a single per-sample container created via ``manager.create_sandbox``.

    ``close()`` calls ``manager.delete_sandbox`` and is idempotent.  As with
    :class:`PoolHandle`, manager coroutines are run on ``service``'s dedicated
    loop when one is provided, keeping create/execute/delete on the same loop.
    """

    def __init__(
        self,
        manager: 'SandboxManager',
        sandbox_id: str,
        service: Optional['SandboxService'] = None,
    ) -> None:
        self._manager = manager
        self._sandbox_id: Optional[str] = sandbox_id
        self._service = service

    @property
    def sandbox_id(self) -> Optional[str]:
        return self._sandbox_id

    async def _on_service_loop(self, coro: Any) -> Any:
        if self._service is not None:
            return await self._service._run_coro(coro)
        return await coro

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        if self._sandbox_id is None:
            raise RuntimeError('SandboxHandle already closed')
        return await self._on_service_loop(self._manager.execute_tool(self._sandbox_id, tool_name, parameters))

    async def close(self) -> None:
        if self._sandbox_id is None:
            return
        try:
            await self._on_service_loop(self._manager.delete_sandbox(self._sandbox_id))
            logger.debug(f'SandboxService: sandbox {self._sandbox_id} deleted.')
        except Exception as exc:
            logger.warning(f'SandboxService: error deleting sandbox {self._sandbox_id}: {exc}')
        finally:
            self._sandbox_id = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _freeze(cfg: Optional[Dict[str, Any]]) -> str:
    """Produce a stable, hashable representation of a manager config dict."""
    try:
        return json.dumps(cfg or {}, sort_keys=True, default=str)
    except Exception:
        return repr(cfg or {})


class SandboxService:
    """Process-level registry of ms_enclave ``SandboxManager`` instances.

    Access via :func:`get_sandbox_service`; the singleton is installed at
    import time and cleaned up through ``atexit``.
    """

    def __init__(self) -> None:
        # (engine, frozen-config) → started SandboxManager
        self._managers: Dict[Tuple[SandboxEngine, str], 'SandboxManager'] = {}
        # threading.Lock guards the cache, per-key startup events, and the
        # lazy loop construction below. We deliberately do NOT use asyncio.Lock:
        # it is acquired from arbitrary worker threads (each sample's
        # AsyncioLoopRunner loop calls in via acquire_pool_sync / _ensure_loop),
        # whereas asyncio.Lock binds to the loop it's first awaited on and would
        # raise "attached to a different event loop" from the second caller on.
        self._thread_lock = threading.Lock()
        # Per-key threading.Event used to coordinate concurrent first-time
        # manager.start() calls without holding the cache lock across await.
        self._manager_starting: Dict[Tuple[SandboxEngine, str], threading.Event] = {}
        # Dedicated, process-lifetime event loop on which *all* manager
        # operations run. ms_enclave managers pin loop-bound state to whatever
        # loop they were started on: the background ``_cleanup_task`` and the
        # pool's ``_pool_lock`` / ``_pool_condition``. The eval driver runs each
        # sample on its own short-lived AsyncioLoopRunner loop, so binding the
        # shared manager to any one sample's loop orphans those primitives the
        # moment that sample finishes (the "Task was destroyed but it is
        # pending" / "Event loop is closed" warnings at shutdown). Routing every
        # manager op through this single loop keeps that state valid for the
        # whole process and lets ``stop()`` cancel the cleanup task on the same
        # loop it lives on. Created lazily on first use.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Dedicated event loop
    # ------------------------------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Return the service's dedicated loop, starting it on first use."""
        loop = self._loop
        if loop is not None:
            return loop
        with self._thread_lock:
            if self._loop is None:
                new_loop = asyncio.new_event_loop()
                thread = threading.Thread(
                    target=new_loop.run_forever,
                    name='SandboxServiceLoop',
                    daemon=True,
                )
                thread.start()
                self._loop = new_loop
                self._loop_thread = thread
        return self._loop

    def _run_coro_sync(self, coro: Awaitable[T], timeout: Optional[float] = None) -> T:
        """Run ``coro`` on the dedicated loop from a sync caller and block."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._ensure_loop())
        try:
            return fut.result(timeout)
        except Exception:
            fut.cancel()
            raise

    async def _run_coro(self, coro: Awaitable[T]) -> T:
        """Run ``coro`` on the dedicated loop from within another loop.

        Bridges the cross-loop result back into the caller's running loop via
        :func:`asyncio.wrap_future` so callers can ``await`` it normally.
        """
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, self._ensure_loop()))

    def _stop_loop(self) -> None:
        """Stop and close the dedicated loop (idempotent)."""
        loop, thread = self._loop, self._loop_thread
        self._loop, self._loop_thread = None, None
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(loop.stop)
        except Exception:
            pass
        if thread is not None:
            thread.join(timeout=5.0)
        try:
            loop.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Manager cache
    # ------------------------------------------------------------------

    async def get_or_create_manager(
        self,
        engine: SandboxEngine,
        manager_config: Optional[Dict[str, Any]] = None,
    ) -> 'SandboxManager':
        """Return a started manager for ``(engine, manager_config)``; create if needed.

        Multi-loop safe: the cache lookup, manager construction, and the
        startup-coordination Event are guarded by ``threading.Lock`` (not
        asyncio.Lock). ``manager.start()`` is awaited *without* holding any
        lock so concurrent loops can't deadlock each other.
        """
        key = (engine, _freeze(manager_config))

        # Fast path: already-cached, ready manager.
        existing = self._managers.get(key)
        if existing is not None:
            return existing

        # Slow path: this thread either becomes the starter or waits for it.
        with self._thread_lock:
            existing = self._managers.get(key)
            if existing is not None:
                return existing

            starting_event = self._manager_starting.get(key)
            if starting_event is not None:
                # Another thread is in the middle of starting this manager.
                is_starter = False
            else:
                starting_event = threading.Event()
                self._manager_starting[key] = starting_event
                is_starter = True
                # Construct the manager object synchronously while the lock is held;
                # this is cheap (no IO) and ensures only one is ever built per key.
                manager = self._construct_manager(engine, manager_config or {})

        if not is_starter:
            # Block (off-loop) until the starter finishes, then read the result.
            await asyncio.to_thread(starting_event.wait)
            cached = self._managers.get(key)
            if cached is None:
                raise RuntimeError(f'SandboxService: peer failed to start manager for {engine.value}')
            return cached

        # Starter path: run the (potentially long) start() outside any lock.
        try:
            await manager.start()
            with self._thread_lock:
                self._managers[key] = manager
            logger.info(
                f'SandboxService: manager started for engine={engine.value} '
                f'(total_managers={len(self._managers)}).'
            )
            return manager
        finally:
            with self._thread_lock:
                self._manager_starting.pop(key, None)
            starting_event.set()

    def _construct_manager(self, engine: SandboxEngine, manager_config: Dict[str, Any]) -> 'SandboxManager':
        _, _, manager_cls, manager_config_cls = get_enclave_types(engine)

        if manager_cls is not None:
            cfg = (
                manager_config_cls.model_validate(manager_config) if manager_config_cls is not None else manager_config
            )
            return manager_cls(config=cfg) if manager_config_cls is not None else manager_cls(**manager_config)

        # Default path: ms_enclave ``SandboxManagerFactory`` (covers docker).
        from ms_enclave.sandbox.manager import SandboxManagerFactory
        return SandboxManagerFactory.create_manager(**manager_config)

    # ------------------------------------------------------------------
    # Public APIs: pooled (SandboxMixin) and per-sample (Agent env)
    # ------------------------------------------------------------------

    def acquire_pool_sync(
        self,
        engine: SandboxEngine,
        pool_size: int,
        sandbox_config: Any,
        manager_config: Optional[Dict[str, Any]] = None,
    ) -> PoolHandle:
        """Sync entrypoint: warm up (if needed) and return a pooled handle.

        Runs on the dedicated service loop so the pool's loop-bound primitives
        outlive the calling worker's short-lived loop.
        """
        return self._run_coro_sync(
            self._acquire_pool(engine, pool_size, sandbox_config, manager_config)
        )

    async def _acquire_pool(
        self,
        engine: SandboxEngine,
        pool_size: int,
        sandbox_config: Any,
        manager_config: Optional[Dict[str, Any]] = None,
    ) -> PoolHandle:
        """Warm up (if needed) and return a pooled handle for ``engine``."""
        manager = await self.get_or_create_manager(engine, manager_config)
        if not getattr(manager, '_pool_initialized', False):
            sandbox_type, _, _, _ = get_enclave_types(engine)
            pool = await manager.initialize_pool(pool_size=pool_size, sandbox_type=sandbox_type, config=sandbox_config)
            logger.info(f'SandboxService: pool initialized with {len(pool)} sandboxes (engine={engine.value}).')
        return PoolHandle(manager, self)

    async def create_sandbox(
        self,
        engine: SandboxEngine,
        sandbox_config: Any,
        manager_config: Optional[Dict[str, Any]] = None,
    ) -> SandboxHandle:
        """Create a single per-sample sandbox and return its handle.

        The manager work runs on the dedicated service loop; the returned
        handle routes its later ``execute_tool`` / ``close`` calls there too.
        """
        return await self._run_coro(self._create_sandbox(engine, sandbox_config, manager_config))

    async def _create_sandbox(
        self,
        engine: SandboxEngine,
        sandbox_config: Any,
        manager_config: Optional[Dict[str, Any]] = None,
    ) -> SandboxHandle:
        manager = await self.get_or_create_manager(engine, manager_config)
        sandbox_type, _, _, _ = get_enclave_types(engine)
        sandbox_id = await manager.create_sandbox(sandbox_type, sandbox_config)
        logger.debug(f'SandboxService: sandbox {sandbox_id} created (engine={engine.value}).')
        return SandboxHandle(manager, sandbox_id, self)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown_all_async(self) -> None:
        managers = list(self._managers.values())
        self._managers.clear()
        for manager in managers:
            try:
                await manager.stop()
                logger.info('SandboxService: manager stopped.')
            except Exception as exc:
                logger.warning(f'SandboxService: error stopping manager: {exc}')

    def shutdown_all(self) -> None:
        """Synchronous shutdown hook (registered via ``atexit``).

        Stops every manager on the dedicated service loop — the loop their
        ``_cleanup_task`` lives on — so the task is cancelled and awaited
        cleanly, then tears the loop down. If the loop was never created, no
        manager was ever started and there is nothing to do.
        """
        if self._loop is None:
            return
        try:
            self._run_coro_sync(self.shutdown_all_async(), timeout=600)
        except Exception as exc:
            logger.warning(f'SandboxService: shutdown_all failed: {exc}')
        finally:
            self._stop_loop()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_SERVICE: Optional[SandboxService] = None
_SERVICE_LOCK = threading.Lock()


def get_sandbox_service() -> SandboxService:
    """Return the process-wide :class:`SandboxService` singleton."""
    global _SERVICE
    if _SERVICE is None:
        with _SERVICE_LOCK:
            if _SERVICE is None:
                _SERVICE = SandboxService()
                atexit.register(_SERVICE.shutdown_all)
    return _SERVICE


# ---------------------------------------------------------------------------
# Convenience helpers used by SandboxMixin / EnclaveAgentEnvironment
# ---------------------------------------------------------------------------


def build_and_acquire_pool_sync(
    engine: SandboxEngine,
    pool_size: int,
    sandbox_config_dict: Optional[Dict[str, Any]],
    manager_config: Optional[Dict[str, Any]] = None,
) -> PoolHandle:
    """Synchronous helper for :class:`SandboxMixin`.

    Combines :func:`build_sandbox_config` and
    :meth:`SandboxService.acquire_pool_sync`, which warms the pool on the
    service's dedicated loop.
    """
    service = get_sandbox_service()
    sandbox_config = build_sandbox_config(engine, sandbox_config_dict)
    return service.acquire_pool_sync(engine, pool_size, sandbox_config, manager_config)


__all__ = [
    'PoolHandle',
    'SandboxHandle',
    'SandboxService',
    'build_and_acquire_pool_sync',
    'get_sandbox_service',
]
