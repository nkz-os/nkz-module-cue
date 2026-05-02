FROM python:3.11-alpine
LABEL org.opencontainers.image.source=https://github.com/nkz-os/nkz-module-cue

WORKDIR /app

RUN apk add --no-cache \
    postgresql-client \
    gcc \
    musl-dev \
    postgresql-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/app/

RUN adduser -D -u 1000 cue && chown -R cue:cue /app
USER cue

EXPOSE 5000

CMD ["python", "-m", "app.cue_api"]
