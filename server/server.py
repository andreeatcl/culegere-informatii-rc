"""
WMI Distributed System - Server
Coordinates query execution across registered clients.
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.protocol import (
    MSG_REGISTER, MSG_EXECUTION_REQUEST, MSG_DISCONNECT,
    MSG_CLIENT_LIST_UPDATE, MSG_EXECUTION_RESPONSE, MSG_ERROR,
    ALLOWED_COMMANDS, encode, decode
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SERVER] %(levelname)s %(message)s"
)
log = logging.getLogger("server")

HOST = "0.0.0.0"
PORT = 9000
QUERY_TIMEOUT = 5  # seconds per client target


class ClientConnection:
    def __init__(self, client_id: str, hostname: str, ip: str,
                 reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.client_id = client_id
        self.hostname = hostname
        self.ip = ip
        self.reader = reader
        self.writer = writer
        self._pending: Dict[str, asyncio.Future] = {}  # request_id → Future

    def to_dict(self):
        return {"id": self.client_id, "hostname": self.hostname, "ip": self.ip}

    async def send(self, msg: dict):
        try:
            self.writer.write(encode(msg))
            await self.writer.drain()
        except Exception as e:
            log.warning(f"Send error to {self.hostname}: {e}")

    def register_pending(self, request_id: str) -> asyncio.Future:
        fut = asyncio.get_event_loop().create_future()
        self._pending[request_id] = fut
        return fut

    def resolve_pending(self, request_id: str, result: dict):
        fut = self._pending.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(result)


class Server:
    def __init__(self):
        self.clients: Dict[str, ClientConnection] = {}  # client_id → ClientConnection
        self._lock = asyncio.Lock()

    # ── Broadcast ─────────────────────────────────────────────────────────────

    async def broadcast(self, msg: dict, exclude_id: Optional[str] = None):
        for cid, conn in list(self.clients.items()):
            if cid != exclude_id:
                await conn.send(msg)

    # ── Client handler ────────────────────────────────────────────────────────

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info("peername")
        log.info(f"New TCP connection from {addr}")

        conn: Optional[ClientConnection] = None

        try:
            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=300)
                except asyncio.TimeoutError:
                    log.info(f"Idle timeout for {addr}")
                    break

                if not line:
                    break

                try:
                    msg = decode(line.decode("utf-8"))
                except json.JSONDecodeError:
                    log.warning(f"Malformed message from {addr}: {line[:80]}")
                    continue

                msg_type = msg.get("type")

                # ── REGISTER ──────────────────────────────────────────────────
                if msg_type == MSG_REGISTER:
                    hostname = msg.get("hostname", "unknown")
                    ip = msg.get("ip", str(addr[0]))

                    client_id = str(uuid.uuid4())[:8]
                    conn = ClientConnection(client_id, hostname, ip, reader, writer)

                    async with self._lock:
                        # Send current client list to the new client
                        existing = [c.to_dict() for c in self.clients.values()]
                        await conn.send({
                            "type": MSG_CLIENT_LIST_UPDATE,
                            "clients": existing
                        })

                        self.clients[client_id] = conn

                        # Notify existing clients about new joiner
                        await self.broadcast({
                            "type": MSG_CLIENT_LIST_UPDATE,
                            "clients": [c.to_dict() for c in self.clients.values()]
                        }, exclude_id=client_id)

                    log.info(f"Registered client [{client_id}] hostname={hostname} ip={ip} "
                             f"(total: {len(self.clients)})")

                # ── EXECUTION_REQUEST ────────────────────────────────────────
                elif msg_type == MSG_EXECUTION_REQUEST:
                    if conn is None:
                        log.warning(f"EXECUTION_REQUEST before REGISTER from {addr}")
                        continue

                    command = msg.get("command", "").strip()
                    targets = msg.get("targets", [])  # [] = all

                    if not command:
                        await conn.send({
                            "type": MSG_ERROR,
                            "error": "Empty command"
                        })
                        continue

                    if command not in ALLOWED_COMMANDS:
                        await conn.send({
                            "type": MSG_ERROR,
                            "error": f"Unsupported command: '{command}'"
                        })
                        continue

                    asyncio.create_task(
                        self.execute_command(conn, command, targets)
                    )

                # ── EXECUTION_RESPONSE (from a target client) ─────────────────
                elif msg_type == MSG_EXECUTION_RESPONSE:
                    if conn is None:
                        continue
                    request_id = msg.get("request_id", "")
                    conn.resolve_pending(request_id, msg)

                # ── DISCONNECT ────────────────────────────────────────────────
                elif msg_type == MSG_DISCONNECT:
                    log.info(f"Client [{conn.client_id if conn else '?'}] sent DISCONNECT")
                    break

                else:
                    log.warning(f"Unknown message type '{msg_type}' from {addr}")

        except asyncio.IncompleteReadError:
            pass
        except ConnectionResetError:
            pass
        except Exception as e:
            log.error(f"Unexpected error from {addr}: {e}", exc_info=True)
        finally:
            await self.remove_client(conn)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # ── Remove / cleanup ──────────────────────────────────────────────────────

    async def remove_client(self, conn: Optional[ClientConnection]):
        if conn is None or conn.client_id not in self.clients:
            return
        async with self._lock:
            self.clients.pop(conn.client_id, None)

        log.info(f"Client [{conn.client_id}] hostname={conn.hostname} disconnected "
                 f"(remaining: {len(self.clients)})")

        await self.broadcast({
            "type": MSG_CLIENT_LIST_UPDATE,
            "clients": [c.to_dict() for c in self.clients.values()]
        })

    # ── Query execution ───────────────────────────────────────────────────────

    async def execute_command(self, operator: ClientConnection, command: str, targets: list):
        request_id = str(uuid.uuid4())[:8]
        log.info(f"Command [{request_id}] from [{operator.client_id}]: '{command}' "
                 f"targets={targets or 'ALL'}")

        async with self._lock:
            all_clients = dict(self.clients)

        # Resolve target list and include per-target errors for invalid targets
        invalid_results = []
        if not targets:
            target_clients = [c for cid, c in all_clients.items() if cid != operator.client_id]
        else:
            target_clients = []
            for t in targets:
                match = None
                for cid, c in all_clients.items():
                    if cid == t or c.hostname == t or c.ip == t:
                        match = c
                        break
                if match:
                    target_clients.append(match)
                else:
                    log.warning(f"Command [{request_id}]: target '{t}' not found")
                    invalid_results.append({
                        "client_id": t,
                        "hostname": "unknown",
                        "ip": "unknown",
                        "status": "error",
                        "error": "Target not found",
                    })

        if not target_clients:
            if invalid_results:
                await operator.send({
                    "type": MSG_EXECUTION_RESPONSE,
                    "request_id": request_id,
                    "results": invalid_results,
                })
            else:
                await operator.send({
                    "type": MSG_ERROR,
                    "error": "No targets available",
                })
            return

        # Fan-out: send EXECUTION_REQUEST to each target and collect results
        async def query_one(target: ClientConnection):
            sub_id = f"{request_id}_{target.client_id}"
            fut = target.register_pending(sub_id)
            await target.send({
                "type": MSG_EXECUTION_REQUEST,
                "command": command,
                "request_id": sub_id
            })
            try:
                result = await asyncio.wait_for(fut, timeout=QUERY_TIMEOUT)
                return {
                    "client_id": target.client_id,
                    "hostname": target.hostname,
                    "ip": target.ip,
                    "status": result.get("status", "ok"),
                    "data": result.get("data"),
                    "error": result.get("error")
                }
            except asyncio.TimeoutError:
                target._pending.pop(sub_id, None)
                log.warning(f"Timeout waiting for [{target.client_id}] on command [{request_id}]")
                return {
                    "client_id": target.client_id,
                    "hostname": target.hostname,
                    "ip": target.ip,
                    "status": "timeout",
                    "error": f"No response within {QUERY_TIMEOUT}s"
                }

        tasks = [asyncio.create_task(query_one(t)) for t in target_clients]
        results = await asyncio.gather(*tasks)
        results.extend(invalid_results)

        log.info(f"Command [{request_id}] complete: {len(results)} result(s)")
        await operator.send({
            "type": MSG_EXECUTION_RESPONSE,
            "request_id": request_id,
            "results": list(results)
        })

    # ── Start ─────────────────────────────────────────────────────────────────

    async def start(self):
        server = await asyncio.start_server(self.handle_client, HOST, PORT)
        addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
        log.info(f"Server listening on {addrs}")
        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(Server().start())
