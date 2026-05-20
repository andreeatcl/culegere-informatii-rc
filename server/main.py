import asyncio

from server.server import Server


if __name__ == "__main__":
    asyncio.run(Server().start())
