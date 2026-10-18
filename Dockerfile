FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv

# manually set cache dir to /tmp to prevent permission issues
ENV RUFF_CACHE_DIR=/tmp/ruff_cache
# use the interpreter of the base image instead of .python-version
ENV UV_PYTHON=/usr/local/bin/python3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

WORKDIR /app

# dependencies first to keep them in a separate layer
COPY pyproject.toml uv.lock /app/
RUN uv sync --locked --no-dev --no-install-project

# the version comes from the git tags via setuptools-scm, so git is needed while installing the project.
# without .git (e.g. built from a tarball) pass the version: --build-arg SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0
ARG SETUPTOOLS_SCM_PRETEND_VERSION
COPY . /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && uv sync --locked --no-dev \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/*

USER 1000

ENTRYPOINT ["/app/.venv/bin/python", "-m", "ili2py.cli"]
