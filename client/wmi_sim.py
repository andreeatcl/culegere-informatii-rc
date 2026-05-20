"""
Simulated command execution using psutil + platform.
Returns real system information for simple commands.
"""

import platform
import os

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


ALLOWED_COMMANDS = {
    "get_os",
    "get_cpu",
    "get_ram",
}


def execute_command(command: str) -> dict:
    """
    Execute a simulated command. Returns {"status": "ok", "data": ...}
    or {"status": "error", "error": "..."}.
    """
    cmd = command.strip()

    if cmd not in ALLOWED_COMMANDS:
        return {
            "status": "error",
            "error": f"Command not supported: '{cmd}'. Allowed: {sorted(ALLOWED_COMMANDS)}",
        }

    try:
        data = _dispatch(cmd)
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _dispatch(command: str):
    if command == "get_os":
        return _os_info()
    if command == "get_cpu":
        return _cpu_info()
    if command == "get_ram":
        return _ram_info()
    raise ValueError(f"Unknown command: {command}")


def _os_info():
    info = {
        "Caption": platform.system(),
        "Version": platform.version(),
        "BuildNumber": platform.release(),
        "OSArchitecture": platform.machine(),
        "CSName": platform.node(),
    }
    if PSUTIL_AVAILABLE:
        vm = psutil.virtual_memory()
        info["TotalVisibleMemorySize_KB"] = vm.total // 1024
        info["FreePhysicalMemory_KB"] = vm.available // 1024
        info["LastBootUpTime"] = str(psutil.boot_time())
    return info


def _cpu_info():
    info = {
        "Name": platform.processor() or "Unknown Processor",
        "Architecture": platform.machine(),
        "NumberOfCores": os.cpu_count() or 1,
    }
    if PSUTIL_AVAILABLE:
        info["LoadPercentage"] = psutil.cpu_percent(interval=0.5)
        freq = psutil.cpu_freq()
        if freq:
            info["MaxClockSpeed_MHz"] = round(freq.max, 1)
            info["CurrentClockSpeed_MHz"] = round(freq.current, 1)
    return info


def _ram_info():
    info = {
        "TotalPhysicalMemory_GB": None,
        "AvailableMemory_GB": None,
    }
    if PSUTIL_AVAILABLE:
        vm = psutil.virtual_memory()
        info["TotalPhysicalMemory_GB"] = round(vm.total / 1e9, 2)
        info["AvailableMemory_GB"] = round(vm.available / 1e9, 2)
    return info
