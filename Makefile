PYROBUSTA_VERSION := v0.7.0
DEVICE ?= u0

SRC_DIR := src
TEST_DIR := tests
EXAMPLE_DIR := example/demo_app
BUILD_DIR := build
DIST_DIR := dist
TLS_DIR := tls
ASSETS_DIR := assets

PKG := pyrobusta

MICROPY_ROOT := external/micropython
MPY_CROSS := $(MICROPY_ROOT)/mpy-cross/build/mpy-cross
MICROPYTHON := $(MICROPY_ROOT)/ports/unix/build-standard/micropython

RUNTIME_DIR := runtime
TEST_RUNTIME := runtime-test

PY_FILES := $(shell find $(SRC_DIR)/$(PKG) -type f -name "*.py")
NON_INIT_PY := $(filter-out %__init__.py,$(PY_FILES))

MPY_TARGETS = $(patsubst $(SRC_DIR)/%.py,$(BUILD_DIR)/%.mpy,$(NON_INIT_PY))
INIT_TARGETS = $(patsubst $(SRC_DIR)/%.py,$(BUILD_DIR)/%.py,$(filter %__init__.py,$(PY_FILES)))

# Performance testing properties
DEVICE_IP := # e.g. 192.168.1.100
DEVICE_NAME := # e.g. ESP32-C3, will be used for report generation
PT_DIR := tests/system

.PHONY: all
all: clean toolchain static-checkers unit-test build test-unix deploy deploy-config tls-cert deploy-cert deploy-example

# ================================================
# Build
# ================================================

# -----------------------------
# Toolchain
# -----------------------------

.PHONY: toolchain
toolchain:
	git submodule update --init
	git -C $(MICROPY_ROOT) submodule update --init
	$(MAKE) -C $(MICROPY_ROOT)/mpy-cross clean
	$(MAKE) -C $(MICROPY_ROOT)/ports/unix clean
	$(MAKE) -C $(MICROPY_ROOT)/mpy-cross
	$(MAKE) -C $(MICROPY_ROOT)/ports/unix

# -----------------------------
# Build package
# -----------------------------
.PHONY: build
build: $(MPY_TARGETS) $(INIT_TARGETS)
	@mkdir -p $(BUILD_DIR)
	@if [ -d assets ]; then \
		echo "Copying assets/ -> $(BUILD_DIR)"; \
		cp -r assets $(BUILD_DIR)/${PKG}/; \
	fi

# Compile .py -> .mpy
$(BUILD_DIR)/%.mpy: $(SRC_DIR)/%.py
	@mkdir -p $(dir $@)
	@echo "Compiling $< -> $@"
	@$(MPY_CROSS) $< -o $@

# Copy __init__.py
$(BUILD_DIR)/%.py: $(SRC_DIR)/%.py
	@mkdir -p $(dir $@)
	@echo "Copying $< -> $@"
	@cp $< $@

# -----------------------------
# Deploy build output to device
# -----------------------------
.PHONY: deploy
deploy:
	@echo "Uploading build/$(PKG) to device $(DEVICE)"
	@mpremote $(DEVICE) soft-reset
	@mpremote $(DEVICE) mkdir :/lib  || true
	@find $(BUILD_DIR)/$(PKG) | while read source; do \
		rel=$${source#$(BUILD_DIR)/}; \
		remote="/lib/$${rel}"; \
		if [ -d "$$source" ]; then \
			mpremote $(DEVICE) mkdir "$$remote" || true; \
		elif [ -f "$$source" ]; then \
			echo "Uploading $$remote"; \
			mpremote $(DEVICE) rm ":$$remote" || true; \
			mpremote $(DEVICE) cp "$$source" ":$$remote"; \
		fi; \
		sleep 1; \
	done
	@mpremote $(DEVICE) reset

# -----------------------------
# Deploy custom configuration
# -----------------------------
.PHONY: deploy-config
deploy-config:
	@echo "Uploading pyrobusta.env"
	@mpremote $(DEVICE) soft-reset
	@if [ -f pyrobusta.env ]; then mpremote $(DEVICE) cp pyrobusta.env :pyrobusta.env; fi
	@mpremote $(DEVICE) reset


# -----------------------------
# Deploy index page
# -----------------------------
.PHONY: deploy-www
deploy-www:
	@echo "Deploying /www"
	@mpremote $(DEVICE) soft-reset
	@mpremote $(DEVICE) run scripts/install_www.py
	@mpremote $(DEVICE) reset

# -----------------------------
# Full redeploy
# -----------------------------
.PHONY: redeploy
redeploy: clean build clean-device deploy


# ================================================
# Rules for release
# ================================================

# -----------------------------
# Prepare distribution
# -----------------------------
.PHONY: publish
publish:
	test -n "$(DIST_DIR)" && rm -rf "$(PWD)/$(DIST_DIR)"
	mkdir -p "$(PWD)/$(DIST_DIR)"
	@sed -E -i.bak 's/(PYROBUSTA_VERSION[[:space:]]*=[[:space:]]*)"[^"]*"/\1"$(PYROBUSTA_VERSION)"/' \
		$(SRC_DIR)/pyrobusta/utils/config.py \
		&& rm -f $(SRC_DIR)/pyrobusta/utils/config.py.bak
	@sed -E -i.bak 's/(PyRobusta[[:space:]]).+([[:space:]]Web Server)/\1$(PYROBUSTA_VERSION)\2/' \
		$(ASSETS_DIR)/www/*.html \
		&& rm -f $(ASSETS_DIR)/www/*.html.bak
	$(MAKE) clean
	$(MAKE) build BUILD_DIR=$(DIST_DIR)
	scripts/update_package.bash $(DIST_DIR) package.json $(PYROBUSTA_VERSION)


# ================================================
# Example apps
# ================================================

# -----------------------------
# Prepare unix example runtime
# -----------------------------
.PHONY: stage-example
stage-example:
	@echo "Preparing unix runtime in $(RUNTIME_DIR)"
	@rm -rf $(RUNTIME_DIR)
	@mkdir -p $(RUNTIME_DIR)/lib

	@echo "Copying built package"
	@cp -r build/pyrobusta $(RUNTIME_DIR)/lib
	@cp -r build/pyrobusta/assets/www $(RUNTIME_DIR)/

	@echo "Copying example app"
	@cp $(EXAMPLE_DIR)/app.py $(RUNTIME_DIR)/
	@cp $(EXAMPLE_DIR)/boot.py $(RUNTIME_DIR)/

	@echo "Copying TLS certificate"
	@cp $(TLS_DIR)/cert.der $(RUNTIME_DIR)/
	@cp $(TLS_DIR)/key.der $(RUNTIME_DIR)/

	@if [ -f pyrobusta.env ]; then cp pyrobusta.env $(RUNTIME_DIR)/; fi
	@echo "http_port=8080" >> $(RUNTIME_DIR)/pyrobusta.env
	@echo "https_port=4443" >> $(RUNTIME_DIR)/pyrobusta.env

# -----------------------------
# Run example locally with unix micropython
# -----------------------------
.PHONY: run-unix
run-unix: stage-example
	@echo "Running example with unix micropython"
	cd $(RUNTIME_DIR) && MICROPYPATH=":.frozen:lib" ../$(MICROPYTHON) app.py

# -----------------------------
# Deploy example app
# -----------------------------
.PHONY: deploy-example
deploy-example:
	@echo "Uploading boot.py, app.py"
	@mpremote $(DEVICE) soft-reset
	mpremote $(DEVICE) cp $(EXAMPLE_DIR)/boot.py :boot.py
	mpremote $(DEVICE) cp $(EXAMPLE_DIR)/app.py :app.py

	@echo "Uploading pyrobusta.env"
	@if [ -f pyrobusta.env ]; then mpremote $(DEVICE) cp pyrobusta.env :pyrobusta.env; fi
	@mpremote $(DEVICE) reset
	@echo "\e[32m$(EXAMPLE_DIR) example is successfully deployed, \n"\
	"run 'make DEVICE=$(DEVICE) run-device' to restart the device and check the output.\e[0m"

# -----------------------------
# Connect to device through REPL
# -----------------------------
.PHONY: run-device
run-device:
	@mpremote $(DEVICE) reset repl


# ================================================
# Unit tests, static checkers
# ================================================

# -----------------------------
# Pylint
# -----------------------------
.PHONY: pylint
pylint:
	@echo "Running Pylint in $(SRC_DIR)/"
	@python3 -m pylint $(SRC_DIR)
	@echo "Running Pylint in $(TEST_DIR)/"
	@python3 -m pylint --rc-file=$(TEST_DIR)/.pylintrc $(TEST_DIR)


# -----------------------------
# Black formatter
# -----------------------------
.PHONY: black
black:
	@echo "Running black formatter"
	@python3 -m black --check $(SRC_DIR) $(TEST_DIR)

# -----------------------------
# Run unit tests
# -----------------------------
.PHONY: unit-test
unit-test:
	@echo "Running unit tests"
	@python3 -m unittest -v

# -----------------------------
# Run all static checkers
# -----------------------------
.PHONY: static-checkers
static-checkers: pylint black


# ================================================
# Functional tests
# ================================================

# -----------------------------
# Prepare functional tests
# -----------------------------
.PHONY: stage-test
stage-test:
	@rm -rf $(TEST_RUNTIME)
	@mkdir -p $(TEST_RUNTIME)/lib

	@cp -r build/pyrobusta $(TEST_RUNTIME)/lib
	@cp tests/functional/*.py $(TEST_RUNTIME)/

# -----------------------------
# Run functional tests on unix port
# -----------------------------
.PHONY: test-unix
test-unix: TLS_DIR=$(TEST_RUNTIME)
test-unix: stage-test tls-cert
	@cd $(TEST_RUNTIME); \
	for test in test_*.py; do \
		echo "\n==================================="; \
		echo "Running $$test"; \
		echo "==================================="; \
		MICROPYPATH=":.frozen:lib" ../$(MICROPYTHON) $$(basename $$test) || exit 1; \
	done

# -----------------------------
# Run functional tests on device
# -----------------------------
.PHONY: test-device
test-device: stage-test #clean-device upload
	@mpremote $(DEVICE) soft-reset
	@cd $(TEST_RUNTIME); \
	for test in test_*.py; do \
		echo "\n==================================="; \
		echo "Running $$test"; \
		echo "==================================="; \
		mpremote $(DEVICE) run $$(basename $$test) || exit 1; \
	done
	@mpremote $(DEVICE) reset

# ================================================
# Performance testing
# ================================================

# -----------------------------
# Run HTTP dimensioning tests
# -----------------------------
.PHONY: perf-test-http-dimensioning
perf-test-http-dimensioning:
	@mpremote $(DEVICE) soft-reset
	mpremote $(DEVICE) cp $(PT_DIR)/http_dimensioning/app_base.py :app_base.py
	mpremote $(DEVICE) cp $(PT_DIR)/http_dimensioning/app_multipart.py :app_multipart.py
	mpremote $(DEVICE) cp $(PT_DIR)/http_dimensioning/boot.py :boot.py
	@mpremote $(DEVICE) reset
	$(PT_DIR)/http_dimensioning/test.py "$(DEVICE)" "$(DEVICE_IP)" "$(DEVICE_NAME)"

# -----------------------------
# Run all performance tests
# -----------------------------
.PHONY: perf-test-device
perf-test-device: perf-test-http-dimensioning

# ================================================
# Utilities for TLS
# ================================================

# -----------------------------
# Generate certificate
# -----------------------------
.PHONY: tls-cert
tls-cert:
	@rm -f $(TLS_DIR)/cert.der $(TLS_DIR)/key.der; \
	mkdir -p $(TLS_DIR);

	@openssl genpkey \
    -algorithm RSA \
    -out $(TLS_DIR)/key.der \
    -outform DER \
    -pkeyopt rsa_keygen_bits:2048 2>/dev/null
	
	@openssl req -new -x509 \
    -key $(TLS_DIR)/key.der \
    -keyform DER \
    -out $(TLS_DIR)/cert.der \
    -outform DER \
    -days 365 \
    -subj "/CN=localhost"

# -----------------------------
# Deploy certificate
# -----------------------------
.PHONY: deploy-cert
deploy-cert:
	@mpremote $(DEVICE) soft-reset
	@mpremote $(DEVICE) cp $(TLS_DIR)/key.der :key.der
	@mpremote $(DEVICE) cp $(TLS_DIR)/cert.der :cert.der
	@mpremote $(DEVICE) reset

# ================================================
# Cleanup
# ================================================

# -----------------------------
# Clean local build
# -----------------------------
.PHONY: clean-build
clean-build:
	rm -rf $(BUILD_DIR)

# -----------------------------
# Clean staging
# -----------------------------

.PHONY: clean-runtime
clean-runtime:
	rm -rf $(RUNTIME_DIR) $(TEST_RUNTIME)

# -----------------------------
# Clean all
# -----------------------------
.PHONY: clean
clean: clean-build clean-runtime

# -----------------------------
# Clean package on device
# -----------------------------
.PHONY: clean-device
clean-device:
	@mpremote $(DEVICE) soft-reset
	mpremote $(DEVICE) run scripts/clean_device.py
	@mpremote $(DEVICE) reset
