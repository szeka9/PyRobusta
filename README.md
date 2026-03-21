# PyRobusta

Lightweight micropython framework for application-layer protocols.

## HTTP server
- low memory requirement (~30KB)
- routing decorators
- zero-copy memory footprint
- fixed-size request/response buffers
- optional multipart request/response handling


# Prerequisites

## Create pyrobusta.env in the project root (uploaded to device)

```bash
# pyrobusta.env
wifi_ssid="<your-wifi-ssid>"
wifi_password="<your-wifi-password>"
tls="true"
socket_max_con=2
http_mem_cap=0.05
...
```
Settings stored in pyrobusta.env affect example application run with ```make run-unix``` or ```make run-device```, allowing
to experiment with different settings. These settings are ignored when running functional tests (```make test-unix```, ```make test-device```).
Check [configuration.md](https://github.com/szeka9/PyRobusta/blob/main/docs/configuration.md) for further configuration options.

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
make deploy             # Upload build artifacts to device using mpremote
make tls-cert           # Optional: generate self-signed certificate for the device
make deploy-cert        # Optional: upload generated certificate to the device
make deploy-example     # Upload example application using mpremote
make run-device         # Run application on the device using mpremote run
```
```deploy-example``` and ```run-device``` uses the DEVICE argument
set to ```u0``` (/dev/ttyUSB0) by default, passed to mpremote.

Override the DEVICE argument to select a different device, e.g.
```make DEVICE=a0 run-device``` for /dev/ttyACM0. Check mpremote --help
for additional shortcuts.

## Redeploy

When changing the source code, run the below rule for uploading.

```bash
make redeploy           # Will run the following rules: clean build clean-device deploy
```

## Unit tests, pylint, functional tests

```bash
make pylint             # Run pylint
make unit-test          # Run unit tests
make test-unix          # Run functional tests on the unix port
make test-device        # Run functional tests on a device
```
