import asyncio

from server.socket_server import SocketServer
from mem_usage import load as demo_app

s = SocketServer()
asyncio.run(s.run_server())

demo_app()
print('Successully started app.py')

try:
    asyncio.get_event_loop().run_forever()
except Exception as e:
    print(f"[asyncio] loop stopped: {e}")
    asyncio.get_event_loop().close()

#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()
