"""
Shared protocol definitions for WMI Distributed System.
All messages are JSON-encoded, newline-delimited over TCP.
"""

import json

# ─── Message Types ───────────────────────────────────────────────────────────

# Client -> Server
MSG_REGISTER = "REGISTER"                   # {type, hostname, ip}
MSG_EXECUTION_REQUEST = "EXECUTION_REQUEST" # {type, command, targets}
MSG_DISCONNECT = "DISCONNECT"               # {type}

# Server -> Client
MSG_CLIENT_LIST_UPDATE = "CLIENT_LIST_UPDATE"  # {type, clients: [{id, hostname, ip}]}
MSG_EXECUTION_RESPONSE = "EXECUTION_RESPONSE"  # {type, request_id, status/data/error/results}
MSG_ERROR = "ERROR"                           # {type, error}

# ─── Simulated Commands ─────────────────────────────────────────────────────

ALLOWED_COMMANDS = {
    "get_os",
    "get_cpu",
    "get_ram",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def encode(msg: dict) -> bytes:
    return (json.dumps(msg) + "\n").encode("utf-8")

def decode(data: str) -> dict:
    return json.loads(data.strip())
