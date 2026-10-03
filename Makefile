run:
	cd backend && uvicorn app.main:app --reload --port 8000
test:
	cd backend && python -m pytest -q
data:
	python scripts/fetch_market_data.py
