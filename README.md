# PyRobusta

A lightweight HTTP server library for MicroPython designed for constrained embedded systems.

## HTTP features
- Routing decorators
- Fixed-size, configurable request/response buffers
- Multipart request and response handling
- Chunked transfer decoding for streamed request bodies
- Bounded-copy memory footprint
- Finite-state-machine parser with linear sliding buffer
- Robust byte-stream handling
- Query parameter parsing with percent encoding support
- TLS support

# Installation

Install PyRobusta on your MicroPython-enabled device using the mip package manager.

A minimum of 40 KB free heap is required. However, for better usability and stability,\
devices with more SRAM are strongly recommended. The ESP32-C3 SuperMini is a good\
entry-level option, providing a comfortable amount of free memory after installation.

If you haven’t already set up your environment, follow the [setup guide](./docs/setup.md) to install\
mpremote and connect your device to Wi-Fi.


```python
# Install the latest version of PyRobusta
import mip
mip.install("github:szeka9/PyRobusta")

# Install required assets
from pyrobusta.utils.assets import install_www
install_www()

# Start the HTTP server
import asyncio
from pyrobusta.server.http_server import HttpServer

async def main():
    server = HttpServer()
    asyncio.create_task(server.start_socket_server())
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
```

# Access the Application

Open a web browser and enter your device’s IP address in the address bar.\
You should see the default homepage. Refer to the included documentation\
for details on supported use cases and advanced features.

![image info](./docs/img/home_page.png)


# Configuration and Optimization

To fine-tune heap usage and optimize performance, see:
- [dimensioning guide](./docs/dimensioning/http_dimensioning.md)
- [configuration settings](./docs/configuration.md)

# Development

Check the provided development guide to create and deploy custom builds\
to your device: [development guide](./docs/development.md)
