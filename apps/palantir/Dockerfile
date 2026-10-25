FROM python:3.12-alpine

RUN apk add --no-cache bash curl
WORKDIR /app
COPY server.py /app/server.py
COPY seed-free-movies.sh /app/seed-free-movies.sh
COPY static /app/static

ENV PALANTIR_PORT=8080
EXPOSE 8080

CMD ["python3", "/app/server.py"]
