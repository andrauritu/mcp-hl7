FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir flask requests

COPY . .

# Ingest ICD + ATC data at build time so the DB is ready
RUN python ingest_icd.py && python ingest_atc.py

EXPOSE 8000

CMD ["flask", "run", "--host", "0.0.0.0", "--port", "8000"]
