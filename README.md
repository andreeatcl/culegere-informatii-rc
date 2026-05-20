# Culegerea de informatii sistem la distanta

This application simulates a distributed client-server architecture, allowing an operator to execute remote commands across multiple target clients.

## Getting Started

To launch the environment, open a terminal and execute the provided PowerShell script:

```bash
./run-docker.ps1
```

This script will build and run 6 Docker containers:

- 1 Server
- 1 Operator Client
- 4 Target Clients

## Usage

Once all containers are built and running, the script will automatically attach to the operator client container to begin executing commands. Detach anytime with Ctrl+P, then Ctrl+Q.

Upon connecting, you will automatically receive a list of all 5 connected clients, displaying their internal ID, hostname, and IP address.

### Application Commands

You can navigate the application using the following local terminal commands:

- `list` or `ls` - Show all currently connected clients.
- `commands` - Display the list of allowed remote execution commands.
- `run` or `exec` - Send a command to the target(s).
- `help` - Display the help menu.
- `quit` or `q` - Disconnect from the server and exit the application.

### Remote Execution Commands

When using the run / exec function, you can issue the following commands to the targets:

1. **get_cpu**

- Returns processor information, including:
- Request status
- Target name and IP
- Processor name and architecture
- Number of cores
- Load percentage
- Current and maximum clock speed

2. **get_os**

- Returns operating system details, including:
- Request status
- Target name and IP
- OS name, version, and build number
- OS architecture
- Computer System Name (CSName)
- Total visible memory size
- Free physical memory
- Last boot-up time

3. **get_ram**

- Returns memory statistics, including:
- Request status
- Target name and IP
- Total physical memory
- Available memory

### Targeting and Timeouts

**Selecting Targets**: After initiating a command, you will be prompted to select your targets. You can specify a subset of clients by entering their ID or hostname. Leaving the selection blank will send the command to ALL connected clients.

**Timeouts**: If a client becomes unresponsive or inactive, it will eventually time out. The system will automatically notify the operator when a timeout occurs.

## Shutting Down

To safely stop the application and delete all created Docker containers, run the following command in your terminal:

```bash
docker compose down
```
