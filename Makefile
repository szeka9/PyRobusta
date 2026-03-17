DEVICE ?= u0

SRC_DIR := src
EXAMPLE_DIR := example/mem_usage
BUILD_DIR := build
PKG := pyrobusta

MICROPY_ROOT := external/micropython
MPY_CROSS := $(MICROPY_ROOT)/mpy-cross/build/mpy-cross
MICROPYTHON := $(MICROPY_ROOT)/ports/unix/build-standard/micropython

RUNTIME_DIR := runtime
TEST_RUNTIME := runtime-test

PY_FILES := $(shell find $(SRC_DIR)/$(PKG) -type f -name "*.py")
NON_INIT_PY := $(filter-out %__init__.py,$(PY_FILES))

MPY_TARGETS := $(patsubst $(SRC_DIR)/%.py,$(BUILD_DIR)/%.mpy,$(NON_INIT_PY))
INIT_TARGETS := $(patsubst $(SRC_DIR)/%.py,$(BUILD_DIR)/%.py,$(filter %__init__.py,$(PY_FILES)))

.PHONY: all
all: clean toolchain pylint unit-test build test-unix upload

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
# Upload build output
# -----------------------------
.PHONY: upload
upload:
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
# Full redeploy
# -----------------------------
.PHONY: redeploy
redeploy: clean build clean-device upload


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

	@if [ -f pyrobusta.env ]; then cp pyrobusta.env $(RUNTIME_DIR)/; fi

# -----------------------------
# Run example locally with unix micropython
# -----------------------------
.PHONY: run-unix
run-unix: stage-example
	@echo "Running example with unix micropython"
	cd $(RUNTIME_DIR) && ../$(MICROPYTHON) app.py

# -----------------------------
# Upload example app
# -----------------------------
.PHONY: upload-example
upload-example:
	@echo "Uploading example files"
	mpremote $(DEVICE) cp $(EXAMPLE_DIR)/boot.py :boot.py
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
	@python3 -m pylint $(SRC_DIR)

# -----------------------------
# Run unit tests
# -----------------------------
.PHONY: unit-test
unit-test:
	@python3 -m unittest

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
test-unix: stage-test
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
