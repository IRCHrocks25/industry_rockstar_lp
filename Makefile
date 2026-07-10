# Landing Page Platform — dev tasks.
# Windows without make: use `scripts/dev.ps1 <target>` (same targets).

PYTHON ?= python
PORT   ?= 8000
MANAGE  = $(PYTHON) manage.py

.PHONY: setup run worker migrate makemigrations test superuser

setup:            ## Create venv + install deps + copy .env if missing
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements.txt
	@test -f .env || cp .env.example .env

run:              ## Control + publishing planes (PORT=8000; keep .env hosts in sync)
	$(MANAGE) runserver 0.0.0.0:$(PORT)

worker:           ## Django-Q2 cluster (background jobs)
	$(MANAGE) qcluster

migrate:
	$(MANAGE) migrate

makemigrations:
	$(MANAGE) makemigrations

test:
	$(MANAGE) test apps

superuser:
	$(MANAGE) createsuperuser
