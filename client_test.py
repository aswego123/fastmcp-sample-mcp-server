import asyncio
from fastmcp import Client

async def main():
    async with Client("http://localhost:8000/sse") as c:
        print("Tools:", [t.name for t in await c.list_tools()])
        print(await c.call_tool("password_generate", {"length": 32, "use_symbols": True}))
        print(await c.call_tool("weather", {"latitude": 28.6139, "longitude": 77.2090}))
        print(await c.call_tool("hash_text", {"text": "hello", "algorithm": "sha256"}))

asyncio.run(main())