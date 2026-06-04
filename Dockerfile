FROM golang:1.23-bookworm AS build

WORKDIR /app

COPY go.mod go.sum* ./
RUN go mod download

COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/trader-api ./cmd/trader-api

FROM debian:bookworm-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /out/trader-api /usr/local/bin/trader-api

EXPOSE 8000

CMD ["trader-api"]
