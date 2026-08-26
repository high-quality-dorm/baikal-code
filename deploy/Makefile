# Baikal: production deployment.
#
# Usage (из каталога deploy/):
#   make setup       # один раз: .env из шаблона + JWT-ключи + сборка фронтенда
#   nano .env        # заполнить секреты (БД, LLM, CERT_DIR)
#   make up          # docker compose up -d --build
#
# Обновление: git pull && make up (если менялся фронтенд — сначала make frontend).

COMPOSE := docker compose

## --- Одноразовая подготовка ---

.PHONY: setup certs frontend

# .env из шаблона + JWT-ключи (если ещё нет) + сборка фронтенда.
setup: certs frontend
	@test -f .env || cp .env.example .env
	@echo "Setup готов: создан deploy/.env, JWT-ключи, фронтенд. Заполните .env и запустите 'make up'."

# JWT-ключи (RS256) генерируются один раз в ../certs/, если их ещё нет.
# TLS-сертификаты для nginx этой целью НЕ создаются — они ваши (см. CERT_DIR в .env).
certs:
	@test -f ../certs/jwt-private-key.pem -a -f ../certs/jwt-cert.pem \
		|| (mkdir -p ../certs && openssl req -x509 -newkey rsa:2048 -nodes \
			-keyout ../certs/jwt-private-key.pem -out ../certs/jwt-cert.pem \
			-days 365 -subj "/CN=baikal-prod")

# Сборка фронтенда в ../frontend/dist (раздаётся nginx'ом).
frontend:
	cd ../frontend && npm ci && npm run build

## --- Жизненный цикл ---

.PHONY: up down restart ps logs config db-init

# Все compose-команды требуют deploy/.env (в нём живёт CERT_DIR и секреты);
# без него — понятная ошибка вместо cryptic "empty section between colons".
.env:
	@echo "Ошибка: deploy/.env отсутствует. Сначала запустите 'make setup'."; exit 1

up: .env
	$(COMPOSE) up -d --build

down: .env
	$(COMPOSE) down

restart: .env
	$(COMPOSE) restart

ps: .env
	$(COMPOSE) ps

logs: .env
	$(COMPOSE) logs -f

config: .env
	$(COMPOSE) config

# Разовая настройка внешней БД: применяет схему, роли, RLS и вью (db/*.sql).
# Требует DATABASE_URL_OWNER в .env (закомментирован в .env.example).
db-init:
	@OWNER=$$(sed -n 's/^DATABASE_URL_OWNER=//p' .env 2>/dev/null | tail -1); \
	if [ -z "$$OWNER" ]; then \
		echo "Ошибка: DATABASE_URL_OWNER не задан в .env (см. .env.example)."; \
		exit 1; \
	fi; \
	psql "$$OWNER" -f ../db/01_schema.sql && \
	psql "$$OWNER" -f ../db/02_roles.sql && \
	psql "$$OWNER" -f ../db/03_rls.sql && \
	psql "$$OWNER" -f ../db/04_views.sql