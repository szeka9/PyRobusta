DEVICE ?= u0

SRC_DIR := src
EXAMPLE_DIR := example/mem_usage_api
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
all: build upload

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
	done

# -----------------------------
# Upload example app
# -----------------------------
.PHONY: upload-example
upload-example:
	@echo "Uploading example files"
	mpremote $(DEVICE) cp $(EXAMPLE_DIR)/app.py :app.py
	mpremote $(DEVICE) cp $(EXAMPLE_DIR)/boot.py :boot.py
	mpremote $(DEVICE) cp $(EXAMPLE_DIR)/mem_usage.py :mem_usage.py
	mpremote $(DEVICE) cp pyrobusta.env :pyrobusta.env

# -----------------------------
# Run example directly
# -----------------------------
.PHONY: run-example
run-example:
	mpremote $(DEVICE) run $(EXAMPLE_DIR)/app.py

# -----------------------------
# Clean local build
# -----------------------------
.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)

# -----------------------------
# Clean package on device
# -----------------------------
.PHONY: clean-device
clean-device:
	mpremote $(DEVICE) run scripts/clean_device.py

# -----------------------------
# Full redeploy
# -----------------------------
.PHONY: redeploy
redeploy: clean build clean-device upload