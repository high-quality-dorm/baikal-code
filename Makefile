
run:
	uv run -m app

format:
	uv run ruff check --select I --fix src/
	uv run ruff check --fix src/
	uv run ruff format src/

check:
	uv run ty check src/
	uv run ruff check src/
	uv run ruff format --check src/
