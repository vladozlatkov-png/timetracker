SHELL := /bin/bash
COMPOSE := docker compose
OPERATON_URL ?= http://localhost:8080/engine-rest

.PHONY: help up down logs deploy migrate psql workers validate clean

help:
	@echo "up        start engine + engine database"
	@echo "workers   start the external-task and mirror workers"
	@echo "migrate   apply sql/*.sql to the Audit OS database (\$$AUDIT_OS_DSN)"
	@echo "deploy    deploy bpmn/*.bpmn to the engine"
	@echo "validate  check the BPMN files parse and DI is complete"
	@echo "logs      tail all container logs"
	@echo "psql      psql shell on the engine database"
	@echo "down      stop everything (volumes preserved)"
	@echo "clean     stop and DELETE the engine database volume"

up:
	$(COMPOSE) up -d engine-db operaton
	@echo "waiting for the engine to answer..."
	@until curl -sf $(OPERATON_URL)/engine >/dev/null 2>&1; do printf '.'; sleep 2; done; echo
	@echo "Cockpit:  http://localhost:8080/operaton/app/cockpit/  (demo/demo)"
	@echo "Tasklist: http://localhost:8080/operaton/app/tasklist/"

workers:
	$(COMPOSE) --profile workers up -d --build external-tasks mirror

migrate:
	@test -n "$$AUDIT_OS_DSN" || { echo "AUDIT_OS_DSN is not set (source your .env)"; exit 1; }
	@for f in sql/*.sql; do echo "applying $$f"; psql "$$AUDIT_OS_DSN" -v ON_ERROR_STOP=1 -f "$$f"; done

deploy:
	OPERATON_URL=$(OPERATON_URL) ./scripts/deploy_bpmn.sh

validate:
	@python3 scripts/validate_bpmn.py

logs:
	$(COMPOSE) --profile workers logs -f --tail=100

psql:
	$(COMPOSE) exec engine-db psql -U $${ENGINE_DB_USER:-operaton} -d $${ENGINE_DB_NAME:-operaton}

down:
	$(COMPOSE) --profile workers down

clean:
	$(COMPOSE) --profile workers down -v
