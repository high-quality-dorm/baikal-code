sync:
	uv sync --all-packages

run:
	uv run -m app

certs:
	mkdir -p certs
	openssl req -x509 -newkey rsa:2048 -nodes \
	  -keyout certs/jwt-private-key.pem \
	  -out certs/jwt-cert.pem \
	  -days 365 \
	  -subj "/CN=baikal-dev"

db-up:
	docker compose up -d --wait

db-down:
	docker compose down

db-reset:
	docker compose down -v
	docker compose up -d --wait

seed:
	uv run python scripts/seed.py

format:
	uv run ruff check --select I --fix packages/
	uv run ruff check --fix packages/
	uv run ruff format packages/

check:
	uv run ty check packages/
	uv run ruff check packages/
	uv run ruff format --check packages/
	uv run python scripts/check_docs.py

docs-check:
	uv run python scripts/check_docs.py

test:
	uv run pytest tests/
