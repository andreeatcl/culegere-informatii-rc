"""
WMI Distributed System - Client
Connects to server, registers, and provides an interactive operator UI.
Can also act as a passive target (responds to EXECUTION_REQUEST from server).
"""

import asyncio
import json
import logging
import os
import platform
import socket
import sys

from rich import box
from rich.console import Console
from rich.table import Table

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.protocol import (
    MSG_REGISTER, MSG_EXECUTION_REQUEST, MSG_DISCONNECT,
    MSG_CLIENT_LIST_UPDATE, MSG_EXECUTION_RESPONSE, MSG_ERROR,
    ALLOWED_COMMANDS, encode, decode
)
from client.wmi_sim import execute_command

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [CLIENT] %(levelname)s %(message)s"
)
log = logging.getLogger("client")

console = Console()

SERVER_HOST = os.environ.get("SERVER_HOST", "localhost")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "9000"))
SIMULATE_FREEZE = os.environ.get("SIMULATE_FREEZE", "0") == "1"


class Client:
    def __init__(self):
        self.hostname = platform.node()
        self.ip = self._get_local_ip()
        self.known_clients = {}  # id -> {id, hostname, ip}
        self.reader = None
        self.writer = None
        self._running = True

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    # -- Network ---------------------------------------------------------------

    async def connect(self):
        console.print(f"\nConnecting to {SERVER_HOST}:{SERVER_PORT} ...")
        self.reader, self.writer = await asyncio.open_connection(SERVER_HOST, SERVER_PORT)
        console.print(f"Connected as hostname='{self.hostname}' ip={self.ip}")
        if SIMULATE_FREEZE:
            console.print("FREEZE MODE: client will not respond to commands")

    async def register(self):
        await self._send({
            "type": MSG_REGISTER,
            "hostname": self.hostname,
            "ip": self.ip
        })

    async def _send(self, msg: dict):
        self.writer.write(encode(msg))
        await self.writer.drain()

    # -- Incoming message handler --------------------------------------------

    async def _recv_loop(self):
        try:
            while self._running:
                line = await self.reader.readline()
                if not line:
                    console.print("\nServer closed connection.")
                    self._running = False
                    break
                try:
                    msg = decode(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                await self._handle(msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self._running:
                console.print(f"\nConnection error: {e}")
            self._running = False

    async def _handle(self, msg: dict):
        t = msg.get("type")

        if t == MSG_CLIENT_LIST_UPDATE:
            self.known_clients = {c["id"]: c for c in msg.get("clients", [])}
            console.print(f"\nClient list updated ({len(self.known_clients)} clients)")
            _print_clients(self.known_clients)

        elif t == MSG_EXECUTION_REQUEST:
            request_id = msg.get("request_id", "")
            command = msg.get("command", "")
            console.print(f"\nExecuting command: '{command}'")

            if SIMULATE_FREEZE:
                console.print("FREEZE MODE: ignoring command (simulated timeout)")
                return

            result = execute_command(command)
            result["type"] = MSG_EXECUTION_RESPONSE
            result["request_id"] = request_id
            await self._send(result)
            console.print(f"Result sent (status={result['status']})")

        elif t == MSG_EXECUTION_RESPONSE:
            request_id = msg.get("request_id", "")
            results = msg.get("results", [])

            console.print("\n" + "-" * 60)
            console.print(f"AGGREGATED RESULTS [request_id={request_id}]")
            console.print("-" * 60)

            for r in results:
                status_tag = "OK" if r.get("status") == "ok" else "ERR"
                console.print(
                    f"\n{status_tag} [{r.get('client_id')}] {r.get('hostname')} ({r.get('ip')})"
                    f" status={r.get('status')}"
                )
                if r.get("error"):
                    console.print(f"  Error: {r.get('error')}")
                elif r.get("data"):
                    _pretty_data(r.get("data"), indent=2)

            console.print("-" * 60)

        elif t == MSG_ERROR:
            console.print(f"\nERROR: {msg.get('error', 'Unknown error')}")

    # -- Operator CLI ----------------------------------------------------------

    async def _cli_loop(self):
        await asyncio.sleep(0.3)
        _print_help()

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, KeyboardInterrupt):
                break

            if not self._running:
                break

            cmd = line.strip()
            if not cmd:
                _prompt()
                continue

            parts = cmd.split(None, 1)
            verb = parts[0].lower()

            if verb in ("quit", "exit", "q"):
                console.print("Disconnecting...")
                self._running = False
                await self._send({"type": MSG_DISCONNECT})
                break

            if verb in ("list", "ls", "l"):
                if self.known_clients:
                    _print_clients(self.known_clients)
                else:
                    console.print("No other clients connected.")

            elif verb in ("help", "h"):
                _print_help()

            elif verb in ("commands", "cmds"):
                console.print("Allowed commands:")
                for i, q in enumerate(sorted(ALLOWED_COMMANDS), 1):
                    console.print(f"  {i}. {q}")

            elif verb in ("run", "exec"):
                await self._interactive_command()

            else:
                console.print(f"Unknown command '{verb}'. Type 'help' for options.")

            _prompt()

    async def _interactive_command(self):
        allowed = sorted(ALLOWED_COMMANDS)
        console.print("\nSelect command:")
        for i, q in enumerate(allowed, 1):
            console.print(f"  {i}. {q}")
        console.print("Enter number or type command directly:")
        _prompt()

        loop = asyncio.get_event_loop()
        raw = (await loop.run_in_executor(None, sys.stdin.readline)).strip()

        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(allowed):
                command = allowed[idx]
            else:
                console.print("Invalid selection.")
                return
        else:
            command = raw

        if not command:
            console.print("Empty command - cancelled.")
            return

        if command not in ALLOWED_COMMANDS:
            console.print(f"Unsupported command: '{command}'")
            return

        console.print("\nSelect targets (blank = ALL clients):")
        console.print("Enter comma-separated IDs/hostnames, or press Enter for all:")
        _print_clients(self.known_clients)
        _prompt()

        raw_targets = (await loop.run_in_executor(None, sys.stdin.readline)).strip()
        targets = [t.strip() for t in raw_targets.split(",") if t.strip()] if raw_targets else []

        console.print(f"\nSending command to {'ALL' if not targets else targets}...")
        await self._send({
            "type": MSG_EXECUTION_REQUEST,
            "command": command,
            "targets": targets
        })

    # -- Run ------------------------------------------------------------------

    async def run(self):
        await self.connect()
        await self.register()

        recv_task = asyncio.create_task(self._recv_loop())
        cli_task = asyncio.create_task(self._cli_loop())

        done, pending = await asyncio.wait(
            [recv_task, cli_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
        try:
            await asyncio.gather(*pending, return_exceptions=True)
        except Exception:
            pass

        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
        console.print("\nGoodbye.")


# -- Utilities ---------------------------------------------------------------

def _print_help():
    console.print(
        "\nCommands:\n"
        "  list / ls     - show connected clients\n"
        "  commands      - show allowed commands\n"
        "  run / exec    - send a command\n"
        "  help          - this help\n"
        "  quit / q      - disconnect and exit\n"
    )


def _print_clients(clients: dict):
    if not clients:
        console.print("(none)")
        return
    table = Table(title="Clients", box=box.ASCII)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("HOSTNAME")
    table.add_column("IP")
    for c in clients.values():
        table.add_row(str(c.get("id")), str(c.get("hostname")), str(c.get("ip")))
    console.print(table)


def _pretty_data(data, indent=2):
    pad = " " * indent
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for k, v in item.items():
                    console.print(f"{pad}{k}: {v}")
                console.print("")
            else:
                console.print(f"{pad}{item}")
    elif isinstance(data, dict):
        for k, v in data.items():
            console.print(f"{pad}{k}: {v}")
    else:
        console.print(f"{pad}{data}")


def _prompt():
    console.print("  > ", end="", soft_wrap=True)


if __name__ == "__main__":
    try:
        asyncio.run(Client().run())
    except KeyboardInterrupt:
        console.print("\nInterrupted.")
