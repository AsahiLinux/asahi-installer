# SPDX-License-Identifier: GPL-2.0-or-later
import asyncio, collections, hmac, json, logging, subprocess, threading, time

from core.exceptions import FirmwareTooOldError, InstallCancelled
from core.installer import STEP2_DIRECT, STEP2_RECOVERY
from core.util import SUCCESS, user_log
from server.backend import PlanError
from server.messages import msg
from server.transport import WebSocketClosed

HELLO_TIMEOUT = 5
LOG_LIMIT = 10000
CANCEL_TIMEOUT = 20

NAMES = {
    -32700: "Parse error", -32600: "Invalid request", -32601: "Method not found", -32602: "Invalid params",
    -32603: "Internal error", -32001: "Not authenticated", -32002: "Invalid session token",
    -32003: "Already authenticated", -32010: "Invalid phase", -32011: "Not cancellable", -32012: "Not retryable",
    -32013: "Authentication attempts expended", -32020: "Invalid plan", -32030: "Invalid credentials",
    -32031: "Auth attempts exceeded", -32032: "Privileged op failed", -32040: "Cancellation failed",
}

class RpcError(Exception):
    def __init__(self, code, data=None):
        super().__init__(code)
        self.code = code
        self.data = data

class AuthLockout(Exception):
    pass

class PrivilegedFailure(Exception):
    pass

def bad_params(name):
    return RpcError(-32602, msg("error.invalid_params", name))

class LogHandler(logging.Handler):
    def __init__(self, session):
        super().__init__(logging.DEBUG)
        self.session = session

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            level = "error"
        elif record.levelno >= logging.WARNING:
            level = "warning"
        elif record.levelno == SUCCESS:
            level = "success"
        elif record.levelno >= logging.INFO:
            level = "info"
        else:
            level = "debug"
        self.session.post(self.session.ui_log, level, record.getMessage(),
                          getattr(record, "op", None), getattr(record, "op_vars", None))

class Connection:
    def __init__(self, ws):
        self.ws = ws
        self.authed = False
        self.outbox = asyncio.Queue()
        self.tasks = set()
        self.writer = asyncio.ensure_future(self.write_loop())

    async def write_loop(self):
        while True:
            item = await self.outbox.get()
            if item is None:
                return
            try:
                await self.ws.send(item)
            except WebSocketClosed:
                return

    def send(self, obj):
        self.outbox.put_nowait(json.dumps(obj, separators=(",", ":")))

    def stop(self):
        self.outbox.put_nowait(None)

    async def close(self, code=1000):
        self.outbox.put_nowait(None)
        try:
            await asyncio.wait_for(self.writer, 5)
        except (asyncio.TimeoutError, Exception):
            pass
        await self.ws.close(code)

class Session:
    def __init__(self, backend, token, loop, max_auth_attempts=5):
        self.backend = backend
        self.token = token
        self.loop = loop
        self.auth_remaining = max_auth_attempts
        self.auth_lock = threading.Lock()
        self.logs = collections.deque(maxlen=LOG_LIMIT)
        self.seq = 0
        self.conn = None
        self.done = asyncio.Event()
        self.exit_action = None
        self.last_progress = 0
        self.last_flush = 0
        self.clear()
        backend.progress_cb = self.progress_from_worker
        self.log_handler = LogHandler(self)
        user_log.addHandler(self.log_handler)
        user_log.setLevel(logging.DEBUG)

    def close(self):
        user_log.removeHandler(self.log_handler)

    def clear(self):
        self.phase = "blocked" if self.backend.blockers else "ready"
        self.stage = None
        self.step = 0
        self.total = 0
        self.operation = None
        self.failure = None
        self.failure_retryable = False
        self.result = None
        self.plan = None
        self.creds = None
        self.worker = None
        self.cancel_fut = None
        self.auth_users = []
        self.auth_req = None
        self.auth_event = threading.Event()
        self.state_timer = None

    def post(self, fn, *args):
        try:
            self.loop.call_soon_threadsafe(fn, *args)
        except RuntimeError:
            pass

    # notifications

    def snapshot(self):
        active = self.phase in ("running", "awaiting_auth")
        return dict(
            phase=self.phase, stage=self.stage, step=self.step, total=self.total, operation=self.operation,
            cancellable=(self.phase == "running" and self.stage == "preparing" and self.cancel_fut is None) if active else None,
            retryable=self.failure_retryable if self.phase == "failed" else None,
            authUsers=self.auth_users if self.phase == "awaiting_auth" else [],
            authAttemptsRemaining=self.auth_remaining, failure=self.failure, result=self.result)

    def notify(self, method, params):
        if self.conn is not None and self.conn.authed:
            self.conn.send({"jsonrpc": "2.0", "method": method, "params": params})

    def state_changed(self, immediate=True):
        if immediate:
            self.flush_state()
            return
        wait = self.last_flush + 0.1 - time.monotonic()
        if wait <= 0:
            self.flush_state()
        elif self.state_timer is None:
            self.state_timer = self.loop.call_later(wait, self.flush_state)

    def flush_state(self):
        self.last_flush = time.monotonic()
        if self.state_timer is not None:
            self.state_timer.cancel()
            self.state_timer = None
        self.notify("state", self.snapshot())

    # thread-to-loop callbacks

    def ui_log(self, level, line, op, op_vars):
        self.seq += 1
        entry = {"seq": self.seq, "level": level, "line": line}
        self.logs.append(entry)
        self.notify("log", entry)
        if op:
            self.operation = {"key": op, "vars": [str(v) for v in (op_vars or [])], "percent": None}
            self.state_changed(False)

    def ui_op(self, key):
        self.operation = {"key": key, "vars": [], "percent": None}
        self.state_changed(False)

    def ui_percent(self, fraction):
        if self.operation is not None:
            self.operation = dict(self.operation, percent=None if fraction is None else round(min(max(fraction, 0), 1) * 100, 1))
            self.state_changed(False)

    def ui_stage(self, stage):
        self.stage = stage
        self.step = self.stages.index(stage) + 1
        self.operation = None
        if stage != "preparing" and self.cancel_fut is not None and not self.cancel_fut.done():
            self.backend.core.cancel_requested = False
            self.cancel_fut.set_result(False)
        self.state_changed()

    def ui_awaiting(self, users):
        self.phase = "awaiting_auth"
        self.auth_users = users
        self.state_changed()

    def ui_failed(self, message, disk_state, retryable):
        self.phase = "failed"
        self.operation = None
        self.failure = dict(message, diskState=disk_state)
        self.failure_retryable = retryable
        if not retryable:
            self.creds = None
        if self.cancel_fut is not None and not self.cancel_fut.done():
            self.cancel_fut.set_result(message["key"] == "fail.cancelled")
        self.state_changed()

    def ui_complete(self, result):
        self.phase = "complete"
        self.stage = None
        self.operation = None
        self.result = result
        self.creds = None
        self.state_changed()

    def set_future(self, fut, result, error):
        if fut is not None and not fut.done():
            if error is not None:
                fut.set_exception(error)
            else:
                fut.set_result(result)

    def resolve(self, fut, result=None, error=None):
        self.post(self.set_future, fut, result, error)

    def progress_from_worker(self, fraction, rate):
        now = time.monotonic()
        if fraction is not None and fraction < 1.0 and now - self.last_progress < 0.05:
            return
        self.last_progress = now
        self.post(self.ui_percent, fraction)

    # worker thread

    def take_attempt(self):
        with self.auth_lock:
            self.auth_remaining = max(0, self.auth_remaining - 1)
            return self.auth_remaining

    def start_worker(self):
        self.backend.core.cancel_requested = False
        self.stages = ["preparing"] + (["resizing"] if self.plan.kind == "apfs" else []) + ["installing", "finalising"]
        self.failure = None
        self.phase = "running"
        self.stage = "preparing"
        self.step = 1
        self.total = len(self.stages)
        self.operation = None
        self.state_changed()
        self.worker = threading.Thread(target=self.work, daemon=True)
        self.worker.start()

    def enter(self, stage):
        self.backend.core.stage = stage
        self.post(self.ui_stage, stage)

    def work(self):
        plan, be = self.plan, self.backend
        try:
            self.enter("preparing")
            be.prepare(plan)
            if plan.kind == "apfs":
                self.enter("resizing")
                self.post(self.ui_op, "op.resize")
                be.resize(plan)
            self.enter("installing")
            be.install(plan)
            self.enter("finalising")
            result = self.finalise(plan)
        except InstallCancelled:
            user_log.warning("Installation cancelled")
            self.post(self.ui_failed, msg("fail.cancelled"), "unchanged", True)
        except AuthLockout:
            self.post(self.ui_failed, msg("fail.auth_locked"), "partial_install", False)
        except PrivilegedFailure:
            self.post(self.ui_failed, msg("fail.privileged_op"), "partial_install", False)
        except FirmwareTooOldError as e:
            user_log.error(f"Installation failed: firmware too old (needs macOS {e.min_version})")
            self.post(self.ui_failed, msg("fail.firmware_too_old", e.min_version), be.disk_state(plan), False)
        except Exception as e:
            logging.exception("Installation failed")
            user_log.error(f"Installation failed: {e}")
            stage = be.core.stage
            key = {"preparing": "fail.download", "resizing": "fail.resize", "installing": "fail.install",
                   "finalising": "fail.finalise"}.get(stage, "fail.internal")
            state = be.disk_state(plan)
            self.post(self.ui_failed, msg(key), state, state == "unchanged")
        else:
            user_log.log(SUCCESS, "Installation complete")
            self.post(self.ui_complete, result)

    def finalise(self, plan):
        be = self.backend
        mode = be.step2_mode()
        if mode == STEP2_DIRECT:
            self.post(self.ui_op, "op.run_step2")
            be.run_step2_script()
        if mode == STEP2_RECOVERY:
            self.privileged("op.reduced_security", be.set_reduced_security)
        self.privileged("op.bless", be.bless)
        self.post(self.ui_op, "op.finalise")
        return be.finalise(plan)

    def wait_for_auth(self):
        self.auth_event.clear()
        self.post(self.ui_awaiting, self.backend.auth_users())
        self.auth_event.wait()
        req, self.auth_req = self.auth_req, None
        return req

    def privileged(self, op, fn):
        while True:
            fut = None
            if self.creds is None:
                user, password, fut = self.wait_for_auth()
                prompted = True
            else:
                (user, password), prompted = self.creds, False
            self.post(self.ui_op, op)
            checked = self.backend.check_credentials(user, password) if prompted else True
            failed = checked is False
            if not failed:
                try:
                    fn(user, password)
                except subprocess.CalledProcessError:
                    if not prompted:
                        self.creds = None
                        continue
                    if checked is True:
                        self.resolve(fut, error=RpcError(-32032, msg("error.privileged_op_failed")))
                        raise PrivilegedFailure
                    failed = True
                except Exception:
                    self.resolve(fut, error=RpcError(-32032, msg("error.privileged_op_failed")))
                    raise
            if failed:
                if self.take_attempt() <= 0:
                    self.resolve(fut, error=RpcError(-32031, msg("error.auth_attempts_exceeded")))
                    raise AuthLockout
                self.resolve(fut, error=RpcError(-32030, msg("error.invalid_credentials")))
                self.creds = None
                continue
            self.creds = (user, password)
            self.resolve(fut, {"authenticated": True})
            return

    # connections

    async def handle_connection(self, ws):
        conn = Connection(ws)
        deadline = time.monotonic() + HELLO_TIMEOUT
        try:
            while True:
                try:
                    if conn.authed:
                        raw = await ws.recv()
                    else:
                        raw = await asyncio.wait_for(ws.recv(), max(0.01, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    await conn.close(4003)
                    return
                if not await self.dispatch(conn, raw):
                    return
        except WebSocketClosed:
            pass
        finally:
            conn.stop()
            if self.conn is conn:
                self.conn = None

    def respond(self, conn, rid, result=None, error=None):
        if rid is None and error is None:
            return
        obj = {"jsonrpc": "2.0", "id": rid}
        if error is not None:
            obj["error"] = error
        else:
            obj["result"] = result
        conn.send(obj)

    @staticmethod
    def error_obj(code, data=None):
        err = {"code": code, "message": NAMES.get(code, "Error")}
        if data is not None:
            err["data"] = data
        return err

    async def dispatch(self, conn, raw):
        try:
            req = json.loads(raw)
        except ValueError:
            self.respond(conn, None, error=self.error_obj(-32700))
            return True
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"), str) \
                or not isinstance(req.get("params", {}), dict) or isinstance(req.get("id"), (dict, list, bool)):
            self.respond(conn, None, error=self.error_obj(-32600))
            return True
        rid, method, params = req.get("id"), req["method"], req.get("params", {})
        has_id = "id" in req
        if not conn.authed:
            if method != "hello":
                conn.send({"jsonrpc": "2.0", "id": rid, "error": self.error_obj(-32001)})
                await conn.close(4004)
                return False
            return await self.hello(conn, rid, params)
        if method == "hello":
            self.respond(conn, rid, error=self.error_obj(-32003))
            return True
        handler = getattr(self, "rpc_" + method, None) if method.isidentifier() else None
        if handler is None:
            if has_id:
                self.respond(conn, rid, error=self.error_obj(-32601))
            return True
        task = asyncio.ensure_future(self.run(conn, rid if has_id else None, handler, params))
        conn.tasks.add(task)
        task.add_done_callback(conn.tasks.discard)
        return True

    async def run(self, conn, rid, handler, params):
        try:
            result = await handler(params)
            self.respond(conn, rid, result)
        except RpcError as e:
            self.respond(conn, rid, error=self.error_obj(e.code, e.data))
        except Exception:
            logging.exception("RPC handler failed")
            self.respond(conn, rid, error=self.error_obj(-32603, msg("error.internal")))

    async def hello(self, conn, rid, params):
        token = params.get("token")
        if not isinstance(token, str) or not hmac.compare_digest(token.encode(), self.token.encode()):
            conn.send({"jsonrpc": "2.0", "id": rid, "error": self.error_obj(-32002)})
            await conn.close(4002)
            return False
        old = self.conn
        self.conn = conn
        conn.authed = True
        if old is not None and old is not conn:
            await old.close(4001)
        self.respond(conn, rid, {"apiVersion": 1, "serverVersion": self.backend.version.lstrip("v")})
        self.flush_state()
        return True

    # helpers

    def require_phase(self, *phases):
        if self.phase not in phases:
            raise RpcError(-32010, msg("error.invalid_phase", self.phase))

    @staticmethod
    def get(params, name, kind, required=True):
        if name not in params or params[name] is None:
            if required:
                raise bad_params(name)
            return None
        v = params[name]
        if isinstance(v, bool) or not isinstance(v, kind):
            raise bad_params(name)
        return v

    async def blocking(self, fn, *args):
        return await self.loop.run_in_executor(None, fn, *args)

    # RPC methods

    async def rpc_get_system(self, params):
        return self.backend.system()

    async def rpc_list_editions(self, params):
        return {"editions": self.backend.editions()}

    async def rpc_get_disk(self, params):
        self.require_phase("ready")
        return self.backend.disk()

    async def rpc_plan_install(self, params):
        self.require_phase("ready")
        edition = self.get(params, "edition", str)
        target = self.get(params, "target", str)
        size = self.get(params, "sizeMB", int, False)
        try:
            result, _ = self.backend.plan(edition, target, size, self.auth_remaining <= 0)
        except PlanError as e:
            raise RpcError(-32020, e.message)
        return result

    async def rpc_start_install(self, params):
        self.require_phase("ready")
        edition = self.get(params, "edition", str)
        target = self.get(params, "target", str)
        size = self.get(params, "sizeMB", int)
        name = self.get(params, "volumeName", str)
        user = self.get(params, "username", str, False) or ""
        password = self.get(params, "password", str, False) or ""
        if bool(user) != bool(password):
            raise bad_params("password" if user else "username")
        if self.auth_remaining <= 0:
            raise RpcError(-32013, msg("error.auth_attempts_expended"))
        try:
            result, plan = self.backend.plan(edition, target, size)
        except PlanError as e:
            raise RpcError(-32020, e.message)
        if result["problems"]:
            raise RpcError(-32020, result["problems"][0])
        if not self.backend.volume_name_valid(name):
            raise RpcError(-32020, msg("plan.volume_name_invalid"))
        if user:
            if user not in self.backend.auth_users():
                raise RpcError(-32030, msg("error.invalid_credentials"))
            if await self.blocking(self.backend.check_credentials, user, password) is False:
                self.take_attempt()
                self.state_changed()
                raise RpcError(-32030, msg("error.invalid_credentials"))
            self.creds = (user, password)
        plan.volume_name = name
        self.plan = plan
        self.start_worker()
        return {"accepted": True}

    async def rpc_authenticate(self, params):
        self.require_phase("awaiting_auth")
        user = self.get(params, "username", str)
        password = self.get(params, "password", str)
        if self.auth_remaining <= 0:
            raise RpcError(-32013, msg("error.auth_attempts_expended"))
        if user not in self.auth_users:
            raise RpcError(-32030, msg("error.invalid_credentials"))
        fut = self.loop.create_future()
        self.auth_req = (user, password, fut)
        self.phase = "running"
        self.auth_users = []
        self.state_changed()
        self.auth_event.set()
        return await fut

    async def rpc_get_logs(self, params):
        after = self.get(params, "after", int, False) or 0
        entries = [e for e in self.logs if e["seq"] > after]
        return {"nextSeq": self.seq + 1, "entries": entries}

    async def rpc_get_telemetry(self, params):
        self.require_phase("complete")
        enabled, payload, _ = self.backend.telemetry()
        return {"enabled": enabled, "payload": payload}

    async def rpc_finish(self, params):
        self.require_phase("complete")
        share = params.get("shareAnonymousStatistics")
        if not isinstance(share, bool):
            raise bad_params("shareAnonymousStatistics")
        action = self.get(params, "action", str)
        if action not in ("shutdown", "reboot", "none") or (action == "reboot" and self.result["nextStep"] != "direct"):
            raise bad_params("action")
        enabled, payload, url = self.backend.telemetry()
        if share and enabled:
            try:
                await self.blocking(self.backend.send_telemetry, url, payload)
            except Exception:
                logging.exception("Telemetry upload failed")
        self.exit_action = action
        self.loop.call_later(0.05, self.begin_exit)
        return {"accepted": True}

    def begin_exit(self):
        conn = self.conn
        if conn is None:
            self.done.set()
            return
        asyncio.ensure_future(self.finish_exit(conn))

    async def finish_exit(self, conn):
        await conn.close(1000)
        self.done.set()

    async def rpc_cancel(self, params):
        self.require_phase("running", "awaiting_auth")
        if not self.snapshot()["cancellable"]:
            raise RpcError(-32011, msg("error.not_cancellable"))
        self.cancel_fut = self.loop.create_future()
        self.state_changed()
        self.backend.request_cancel()
        try:
            ok = await asyncio.wait_for(asyncio.shield(self.cancel_fut), CANCEL_TIMEOUT)
        except asyncio.TimeoutError:
            ok = False
        self.cancel_fut = None
        if not ok:
            self.state_changed()
            raise RpcError(-32040, msg("error.cancel_failed"))
        return {"cancelled": True}

    async def rpc_retry(self, params):
        self.require_phase("failed")
        if not self.failure_retryable or self.plan is None:
            raise RpcError(-32012, msg("error.not_retryable"))
        self.start_worker()
        return {"success": True}

    async def rpc_reset(self, params):
        self.require_phase("ready", "complete", "failed")
        if self.phase == "failed" and self.failure["diskState"] != "unchanged":
            raise RpcError(-32010, msg("error.reset_unsafe"))
        await self.blocking(self.backend.collect)
        self.clear()
        self.state_changed()
        return {"success": True}
