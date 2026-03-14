# -----------------------------
# Configuration
# -----------------------------
DEVICE ?= u0
SRC_DIR := src
EXAMPLE_DIR := example/mem_usage_api

PY_FILES := $(shell find $(SRC_DIR) -type f -name "*.py" ! -name "__init__.py")
MPY_FILES := $(PY_FILES:.py=.mpy)

# -----------------------------
# Default target
# -----------------------------
.PHONY: all
all: compile upload

# -----------------------------
# Cross compile
# -----------------------------
.PHONY: compile
compile: $(MPY_FILES)

%.mpy: %.py
	@echo "Compiling $< -> $@"
	@mpy-cross $< -o $@

# -----------------------------
# Upload compiled files
# -----------------------------
.PHONY: upload
upload:
	@echo "Uploading compiled files to device $(DEVICE)"
	@find $(SRC_DIR) | grep -v __pycache__ | while read source; do \
		rel=$${source#$(SRC_DIR)/}; \
		if [ -d "$$source" ]; then \
			echo "================================================"; \
			echo "Creating directory: $$rel"; \
			mpremote $(DEVICE) mkdir "$$rel" || true; \
		elif [ -f "$$source" ] && echo "$$source" | grep -q '\.mpy$$'; then \
			echo "================================================"; \
			echo "Uploading: $$rel"; \
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
# Clean compiled artifacts locally
# -----------------------------
.PHONY: clean
clean:
	@echo "Removing local .mpy files"
	find $(SRC_DIR) -type f -name "*.mpy" -delete

# -----------------------------
# Clean device filesystem
# -----------------------------
.PHONY: clean-device
clean-device:
	mpremote $(DEVICE) run scripts/clean_device.py

# -----------------------------
# Full redeploy
# -----------------------------
.PHONY: redeploy
redeploy: clean compile upload
