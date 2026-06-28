
# Development Guide

This guide describes the development workflow for PyRobusta itself, including building the framework, deploying examples, and running the test suite.

## Prerequisites

### Setup Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```

### Create ```pyrobusta.env```

```bash
# pyrobusta.env
wifi_ssid="<your-wifi-ssid>"
wifi_password="<your-wifi-password>"
tls="true"
socket_max_con=2
http_mem_cap=0.05
...
```
```pyrobusta.env``` contains runtime configuration, deployed to the device. This allows you to override the
default behavior and configure optional settings. All configuration settings are optional. However, ```wifi_ssid```
and ```wifi_password``` must be defined unless the application initializes network connectivity itself.

- Running applications with ```make run-unix``` or ```make run-device``` uses ```pyrobusta.env```
- Functional tests (```make test-unix```, ```make test-device```) ignore ```pyrobusta.env```.

Check the [Configuration](./application_development/configuration.md) guide for all configuration options.


## Build and Run Example Application

### Run on UNIX Port

```bash
make toolchain          # Setup mpy-cross and micropython
make build              # Cross-compile, create build artifacts
make stage-app      # Create runtime directory for UNIX port
make run-unix           # Run example application on the UNIX port of MicroPython
```

### Deploy to a Device

```bash
make toolchain          # Setup mpy-cross and micropython
make build              # Cross-compile, create build artifacts
make deploy             # Upload build artifacts to the device using mpremote
make tls-cert           # Optional: generate self-signed certificate for the device
make deploy-cert        # Optional: upload generated certificate to the device
make deploy-app         # Deploy the selected example application using mpremote
make run-device         # Reset the device and connect through REPL
```

Deploy a specific application by overriding the ```APP_DIR``` variable. For example:

```bash
make APP_DIR=example/demo_app deploy-app
```

Make targets that communicate with a device (```deploy```, ```deploy-cert```, ```deploy-app```, ```run-device```) use the ```DEVICE``
variable, which defaults to ```u0``` (/dev/ttyUSB0).

Override ```DEVICE``` to select a different serial device, for example:

```bash
make DEVICE=a0 run-device
```

which corresponds to ```/dev/ttyACM0```. Refer to ```mpremote --help``` for additional device shortcuts.

### Redeploy

After modifying the source code, run the following rule to redeploy the application to the device.

```bash
make redeploy           # Will run the following rules: clean build clean-device deploy
```

### Code Quality and Testing

```bash
make static-checkers    # Run static checkers (Pylint, Black formatter)
make unit-test          # Run unit tests
make test-unix          # Run functional tests on the UNIX port
make test-device        # Run functional tests on a device
```

#### Performance testing

Performance tests must be run on a physical device. Results are exported to a directory named after the device.

```bash
# Run performance tests and export results to docs/dimensioning/esp32_c3
make DEVICE=a1 DEVICE_IP=192.168.0.100 DEVICE_NAME=ESP32-C3 perf-test-device
```
