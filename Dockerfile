FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY hermes_prime/ hermes_prime/
COPY infrastructure/ infrastructure/
COPY miners/ miners/
COPY core/ core/
COPY hermes/ hermes/

RUN pip install --upgrade pip && \
    pip install build && \
    python -m build --wheel

FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        opa \
        ripgrep \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /hermes

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

COPY infrastructure/ infrastructure/
COPY hermes/ hermes/

RUN useradd -m -s /bin/bash hermes && \
    chown -R hermes:hermes /hermes

USER hermes
ENV HERMES_WORKSPACE=/hermes

ENTRYPOINT ["hermes-prime"]
CMD ["--help"]
