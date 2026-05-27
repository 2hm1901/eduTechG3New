.PHONY: install run test clean

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt
	@echo ""
	@echo "Done. Next:  source .venv/bin/activate && cp .env.example .env && make run"

run:
	uvicorn src.app:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -v tests/

clean:
	rm -rf _data __pycache__ .pytest_cache src/__pycache__ src/adapters/__pycache__ tests/__pycache__
