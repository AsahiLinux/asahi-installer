# SPDX-License-Identifier: GPL-2.0-or-later
import asyncio, base64, hashlib, mimetypes, os, struct
from urllib.parse import unquote, urlsplit

WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SUBPROTOCOL = "jsonrpc2.0"
MAX_MESSAGE = 1024 * 1024

REASONS = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
           426: "Upgrade Required", 431: "Request Header Fields Too Large"}

class HttpError(Exception):
    def __init__(self, status, headers=None):
        super().__init__(status)
        self.status = status
        self.headers = headers or {}

class WebSocketClosed(Exception):
    def __init__(self, code=1006):
        super().__init__(code)
        self.code = code

class WebSocket:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.send_lock = asyncio.Lock()
        self.closed = False

    async def send(self, text):
        await self.send_frame(0x1, text.encode("utf-8"))

    async def send_frame(self, opcode, payload):
        if self.closed and opcode != 0x8:
            raise WebSocketClosed()
        n = len(payload)
        if n < 126:
            header = bytes([0x80 | opcode, n])
        elif n < 65536:
            header = bytes([0x80 | opcode, 126]) + struct.pack("!H", n)
        else:
            header = bytes([0x80 | opcode, 127]) + struct.pack("!Q", n)
        async with self.send_lock:
            try:
                self.writer.write(header + payload)
                await self.writer.drain()
            except (ConnectionError, OSError):
                self.closed = True
                raise WebSocketClosed()

    async def close(self, code=1000, reason=""):
        if not self.closed:
            payload = struct.pack("!H", code) + reason.encode("utf-8")[:120]
            try:
                await self.send_frame(0x8, payload)
            except WebSocketClosed:
                pass
            self.closed = True
        try:
            self.writer.close()
            await asyncio.wait_for(self.writer.wait_closed(), 2)
        except (ConnectionError, OSError, asyncio.TimeoutError):
            pass

    async def fail(self, code):
        await self.close(code)
        raise WebSocketClosed(code)

    async def read_frame(self):
        try:
            b0, b1 = await self.reader.readexactly(2)
            fin, rsv, opcode = b0 & 0x80, b0 & 0x70, b0 & 0x0f
            masked, length = b1 & 0x80, b1 & 0x7f
            if rsv or not masked:
                await self.fail(1002)
            if length == 126:
                length = struct.unpack("!H", await self.reader.readexactly(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", await self.reader.readexactly(8))[0]
            if opcode >= 0x8 and (length > 125 or not fin):
                await self.fail(1002)
            if length > MAX_MESSAGE:
                await self.fail(1009)
            mask = await self.reader.readexactly(4)
            data = await self.reader.readexactly(length) if length else b""
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            self.closed = True
            raise WebSocketClosed()
        if length:
            key = (mask * (length // 4 + 1))[:length]
            data = (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(length, "big")
        return opcode, bool(fin), data

    async def recv(self):
        message = bytearray()
        started = False
        while True:
            opcode, fin, data = await self.read_frame()
            if opcode == 0x8:
                code = struct.unpack("!H", data[:2])[0] if len(data) >= 2 else 1005
                await self.close(code if 1000 <= code < 5000 and code not in (1005, 1006, 1015) else 1000)
                raise WebSocketClosed(code)
            if opcode == 0x9:
                await self.send_frame(0xA, data)
                continue
            if opcode == 0xA:
                continue
            if opcode in (0x1, 0x2):
                if started or opcode == 0x2:
                    await self.fail(1002 if started else 1003)
                started = True
            elif opcode == 0x0:
                if not started:
                    await self.fail(1002)
            else:
                await self.fail(1002)
            message += data
            if len(message) > MAX_MESSAGE:
                await self.fail(1009)
            if fin:
                try:
                    return message.decode("utf-8")
                except UnicodeDecodeError:
                    await self.fail(1007)

class Request:
    def __init__(self, method, target, headers):
        self.method = method
        self.target = target
        self.headers = headers
        self.path = unquote(urlsplit(target).path)

class Transport:
    def __init__(self, handler, ui_dir=None):
        self.handler = handler
        self.ui_dir = os.path.realpath(ui_dir) if ui_dir else None
        self.servers = []
        self.sockets = set()
        self.port = None
        self.hosts = set()
        self.origins = set()

    def set_port(self, port):
        self.port = port
        self.hosts = {f"localhost:{port}", f"127.0.0.1:{port}", f"[::1]:{port}"}
        self.origins = {f"http://{h}" for h in self.hosts}

    async def start(self):
        server = await asyncio.start_server(self.client, "127.0.0.1", 0, reuse_address=False)
        self.servers.append(server)
        self.set_port(server.sockets[0].getsockname()[1])
        try:
            self.servers.append(await asyncio.start_server(self.client, "::1", self.port, reuse_address=False))
        except OSError:
            pass

    async def stop(self):
        for server in self.servers:
            server.close()
        for ws in list(self.sockets):
            await ws.close(1001)
        self.servers = []

    async def client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            if not peer or peer[0] not in ("127.0.0.1", "::1"):
                return
            req = await self.read_request(reader)
            if req.headers.get("host") not in self.hosts:
                raise HttpError(403)
            if req.path == "/api/ws":
                await self.websocket(req, reader, writer)
            else:
                await self.static(req, writer)
        except HttpError as e:
            await self.respond(writer, e.status, REASONS.get(e.status, "Error").encode(), "text/plain", e.headers)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, OSError):
            pass
        finally:
            try:
                writer.close()
            except OSError:
                pass

    async def read_request(self, reader):
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        except asyncio.LimitOverrunError:
            raise HttpError(431)
        lines = raw.decode("latin-1").split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
            raise HttpError(400)
        headers = {}
        for line in lines[1:]:
            if not line:
                continue
            if ":" not in line:
                raise HttpError(400)
            name, value = line.split(":", 1)
            name = name.strip().lower()
            headers[name] = f"{headers[name]}, {value.strip()}" if name in headers else value.strip()
        return Request(parts[0], parts[1], headers)

    async def websocket(self, req, reader, writer):
        h = req.headers
        if req.method != "GET":
            raise HttpError(405)
        if "origin" in h and h["origin"] not in self.origins:
            raise HttpError(403)
        if "websocket" not in h.get("upgrade", "").lower() or "upgrade" not in h.get("connection", "").lower():
            raise HttpError(400)
        if h.get("sec-websocket-version") != "13":
            raise HttpError(426, {"Sec-WebSocket-Version": "13"})
        key = h.get("sec-websocket-key", "")
        try:
            if len(base64.b64decode(key, validate=True)) != 16:
                raise ValueError
        except ValueError:
            raise HttpError(400)
        if SUBPROTOCOL not in [p.strip() for p in h.get("sec-websocket-protocol", "").split(",")]:
            raise HttpError(400)
        accept = base64.b64encode(hashlib.sha1(key.encode() + WS_GUID).digest()).decode()
        writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {accept}\r\nSec-WebSocket-Protocol: {SUBPROTOCOL}\r\n\r\n").encode())
        await writer.drain()
        ws = WebSocket(reader, writer)
        self.sockets.add(ws)
        try:
            await self.handler(ws)
        except WebSocketClosed:
            pass
        finally:
            self.sockets.discard(ws)
            await ws.close(1000)

    async def static(self, req, writer):
        if req.method not in ("GET", "HEAD"):
            raise HttpError(405)
        if not self.ui_dir:
            raise HttpError(404)
        path = req.path + "index.html" if req.path.endswith("/") else req.path
        full = os.path.realpath(os.path.join(self.ui_dir, path.lstrip("/")))
        if not full.startswith(self.ui_dir + os.sep) or not os.path.isfile(full):
            raise HttpError(404)
        with open(full, "rb") as f:
            body = f.read()
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        await self.respond(writer, 200, body, ctype, head=req.method == "HEAD")

    async def respond(self, writer, status, body, ctype, headers=None, head=False):
        ws_hosts = " ".join(f"ws://{h}" for h in sorted(self.hosts))
        out = {
            "Content-Type": ctype, "Content-Length": str(len(body)), "Connection": "close",
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (f"default-src 'self'; connect-src 'self' {ws_hosts}; img-src 'self' data:; "
                                        "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
        }
        out.update(headers or {})
        head_text = f"HTTP/1.1 {status} {REASONS.get(status, 'Error')}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in out.items()) + "\r\n"
        writer.write(head_text.encode("latin-1") + (b"" if head else body))
        await writer.drain()
