FROM ghcr.io/astral-sh/uv:python3.13-alpine

RUN apk update
RUN apk add git

WORKDIR /code

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

COPY ./pyproject.toml /code/pyproject.toml
COPY ./uv.lock /code/uv.lock

RUN uv sync --frozen --no-dev

COPY . /code

CMD ["uv", "run", "python", "-O", "main.py"]