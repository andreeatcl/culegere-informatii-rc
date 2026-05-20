import asyncio

from client.client import Client


if __name__ == "__main__":
    asyncio.run(Client().run())
