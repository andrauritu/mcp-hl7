FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir flask "web3>=7.0.0"

COPY . .

EXPOSE 8001

CMD ["flask", "run", "--host", "0.0.0.0", "--port", "8001"]
