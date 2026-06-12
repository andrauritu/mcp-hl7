FROM python:3.12-slim

WORKDIR /app

COPY receiver.py cert.pem key.pem ./

EXPOSE 2575

CMD ["python", "receiver.py"]
