FROM nats:2.10.9-alpine

# Install curl for healthcheck
RUN apk add --no-cache curl 
RUN curl -sf https://binaries.nats.dev/nats-io/natscli/nats@latest | sh
