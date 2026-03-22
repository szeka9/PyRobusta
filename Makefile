PYROBUSTA_VERSION := 0.1.0
DEVICE ?= u0

SRC_DIR := src
EXAMPLE_DIR := example/mem_usage
BUILD_DIR := build
DIST_DIR := dist
PKG := pyrobusta
TLS_DIR := tls

MICROPY_ROOT := external/micropython
MPY_CROSS := $(MICROPY_ROOT)/mpy-cross/build/mpy-cross
MICROPYTHON := $(MICROPY_ROOT)/ports/unix/build-standard/micropython

RUNTIME_DIR := runtime
TEST_RUNTIME := runtime-test

PY_FILES := $(shell find $(SRC_DIR)/$(PKG) -type f -name "*.py")
NON_INIT_PY := $(filter-out %__init__.py,$(PY_FILES))

MPY_TARGETS = $(patsubst $(SRC_DIR)/%.py,$(BUILD_DIR)/%.mpy,$(NON_INIT_PY))
INIT_TARGETS = $(patsubst $(SRC_DIR)/%.py,$(BUILD_DIR)/%.py,$(filter %__init__.py,$(PY_FILES)))

.PHONY: all
all: clean toolchain pylint unit-test build test-unix deploy

# ================================================
# Build
# ================================================

# -----------------------------
# Toolchain
# -----------------------------

.PHONY: toolchain
toolchain:
	$(MAKE) -C $(MICROPY_ROOT)/mpy-cross
	$(MAKE) -C $(MICROPY_ROOT)/ports/unix

# -----------------------------
# Build package
# -----------------------------
.PHONY: build
build: $(MPY_TARGETS) $(INIT_TARGETS)

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
	@find $(BUILD_DIR)/$(PKG) | while read source; do \
		rel=$${source#$(BUILD_DIR)/}; \
		if [ -d "$$source" ]; then \
			mpremote $(DEVICE) mkdir "$$rel" || true; \
		elif [ -f "$$source" ]; then \
			echo "Uploading $$rel"; \
			mpremote $(DEVICE) rm "$$rel" || true; \
			mpremote $(DEVICE) cp "$$source" ":$$rel"; \
		fi; \
		sleep 1; \
	done

# -----------------------------
# Deploy custom configuration
# -----------------------------
.PHONY: deploy-config
deploy-config:
	@echo "Uploading pyrobusta.env"
	mpremote $(DEVICE) cp pyrobusta.env :pyrobusta.env

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
	@sed -E -i.bak 's/(PYROBUSTA_VERSION[[:space:]]*=[[:space:]]*)"[^"]*"/\1"$(PYROBUSTA_VERSION)"/' \
		$(SRC_DIR)/pyrobusta/utils/config.py \
		&& rm -f $(SRC_DIR)/pyrobusta/utils/config.py.bak
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
	@mkdir -p $(RUNTIME_DIR)

	@echo "Copying built package"
	@cp -r build/pyrobusta $(RUNTIME_DIR)/

	@echo "Copying example files"
	@cp $(EXAMPLE_DIR)/app.py $(RUNTIME_DIR)/
	@cp $(EXAMPLE_DIR)/boot.py $(RUNTIME_DIR)/

	@echo "Copying TLS certificate"
	@cp $(TLS_DIR)/cert.der $(RUNTIME_DIR)/
	@cp $(TLS_DIR)/key.der $(RUNTIME_DIR)/

	@if [ -f pyrobusta.env ]; then cp pyrobusta.env $(RUNTIME_DIR)/; fi

# -----------------------------
# Run example locally with unix micropython
# -----------------------------
.PHONY: run-unix
run-unix: stage-example
	@echo "Running example with unix micropython"
	cd $(RUNTIME_DIR) && ../$(MICROPYTHON) app.py

# -----------------------------
# Deploy example app
# -----------------------------
.PHONY: deploy-example
deploy-example:
	@echo "Uploading boot.py"
	mpremote $(DEVICE) cp $(EXAMPLE_DIR)/boot.py :boot.py

	@echo "Uploading pyrobusta.env"
	mpremote $(DEVICE) cp pyrobusta.env :pyrobusta.env

# -----------------------------
# Run example directly
# -----------------------------
.PHONY: run-device
run-device:
	mpremote $(DEVICE) run $(EXAMPLE_DIR)/app.py


# ================================================
# Unit tests, static checkers
# ================================================

# -----------------------------
# Pylint
# -----------------------------
.PHONY: pylint
pylint:
	@echo "Running Pylint"
	@python3 -m pylint $(SRC_DIR)


# -----------------------------
# Black formatter
# -----------------------------
.PHONY: black
black:
	@echo "Running black formatter"
	@python3 -m black --check $(SRC_DIR)

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
	@mkdir -p $(TEST_RUNTIME)

	@cp -r build/pyrobusta $(TEST_RUNTIME)/
	@cp tests/functional/*.py $(TEST_RUNTIME)/

# -----------------------------
# Run functional tests on unix port
# -----------------------------
.PHONY: test-unix
test-unix: TLS_DIR=$(TEST_RUNTIME)
test-unix: stage-test tls-cert
	@cd $(TEST_RUNTIME); \
	for test in test_*.py; do \
		echo "Running $$test"; \
		../$(MICROPYTHON) $$(basename $$test) || exit 1; \
	done

# -----------------------------
# Run functional tests on device
# -----------------------------
.PHONY: test-device
test-device: #clean-device upload
	@cd $(TEST_RUNTIME); \
	for test in test_*.py; do \
		echo "Running $$test"; \
		mpremote $(DEVICE) run $$(basename $$test) || exit 1; \
	done

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
	@mpremote $(DEVICE) cp $(TLS_DIR)/key.der :key.der
	@mpremote $(DEVICE) cp $(TLS_DIR)/cert.der :cert.der

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
	mpremote $(DEVICE) run scripts/clean_device.py
