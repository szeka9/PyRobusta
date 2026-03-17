# PyRobusta

Lightweight micropython framework for application-layer protocols.

## HTTP server
- low memory requirement (~30KB)
- routing decorators
- zero-copy memory footprint
- fixed-size request/response buffers
- optional multipart request/response handling


# Prerequisites

## Create pyrobusta.env in the project root

```bash
# pyrobusta.env
wifi_ssid="<your-wifi-ssid>"
wifi_password="<your-wifi-password>"
socket_max_con=2
http_multipart="false"
http_mem_cap=0.05
```

## Setup virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```


# Build and run example application

## Run on unix port

```bash
make toolchain          # Setup mpy-cross and micropython
make build              # Cross-compile, create build artifacts
make stage-example      # Create runtime directory for unix port
make run-unix           # Run example application on the unix port of micropython
```

## Deploy to a device

```bash
make toolchain          # Setup mpy-cross and micropython
make build              # Cross-compile, create build artifacts
make upload             # Upload build artifacts to device using mpremote
make upload-example     # Upload example application using mpremote
make run-device         # Run application on the device using mpremote run
```
```upload-example``` and ```run-device``` uses the DEVICE argument
set to ```u0``` (/dev/ttyUSB0) by default, passed to mpremote.

Override the DEVICE argument to select a different device, e.g.
```make DEVICE=a0 run-device``` for /dev/ttyACM0. Check mpremote --help
for additional shortcuts.

## Redeploy

When changing the source code, run the below rule for uploading.

```bash
make redeploy           # Will run the following rules: clean build clean-device upload
```

## Unit tests, pylint, functional tests

```bash
make pylint             # Run pylint
make unit-test          # Run unit tests
make test-unix          # Run functional tests on the unix port
make test-device        # Run functional tests on a device
```
