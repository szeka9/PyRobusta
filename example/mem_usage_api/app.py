import asyncio

import pyrobusta.server.http_server as http_server
from mem_usage import load as demo_app

http_server.main()
demo_app()

try:
    asyncio.get_event_loop().run_forever()
except Exception as e:
    print(f"[asyncio] loop stopped: {e}")
    asyncio.get_event_loop().close()
