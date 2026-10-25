FROM python:3.12-alpine

WORKDIR /app
COPY server.py /app/server.py
COPY static /app/static

ENV PALANTIR_PORT=8080
EXPOSE 8080

CMD ["python3", "/app/server.py"]
