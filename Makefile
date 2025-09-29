.PHONY: dev test emu seed

VENV ?= .venv
PYTHON ?= python3

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -e apps/companion

seed:
	$(PYTHON) -m apps.companion.dashmaster.scripts.seed_registry

emu:
	$(PYTHON) apps/companion/dashmaster/tests/device_emulator.py

test:
	$(PYTHON) -m pytest apps/companion/dashmaster/tests

dev:
	@echo "Launch services in separate terminals:"
	@echo "  $(PYTHON) -m uvicorn dashmaster.main:app --reload --app-dir apps/companion/dashmaster --port 5055"
	@echo "  npm --prefix apps/web install && npm --prefix apps/web run dev"
	@echo "  $(PYTHON) apps/proxy/python-portmap/portmap.py"
