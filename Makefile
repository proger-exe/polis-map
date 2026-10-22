.PHONY: setup dev-api dev-web dev-bot test

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	cd frontend && npm install

dev-api:
	.venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

dev-web:
	cd frontend && npm run dev -- --host 127.0.0.1

dev-bot:
	.venv/bin/python -m bot.main

test:
	PYTHONPATH=. .venv/bin/pytest -q
