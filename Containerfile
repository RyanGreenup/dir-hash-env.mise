FROM alpine:3.22

ARG MISE_VERSION=v2026.7.18

RUN apk add --no-cache ca-certificates coreutils curl git python3

ENV MISE_INSTALL_PATH=/usr/local/bin/mise
RUN curl --fail --location --silent --show-error \
    --output /tmp/install-mise.sh https://mise.run \
    && sh /tmp/install-mise.sh \
    && rm /tmp/install-mise.sh

WORKDIR /workspace
COPY . .

CMD ["python3", "tests/test.py"]
