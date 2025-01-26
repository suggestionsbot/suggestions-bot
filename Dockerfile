FROM python:3.11-alpine

WORKDIR /code
RUN pip install poetry

COPY ./pyproject.toml /bot/pyproject.toml
COPY ./poetry.lock /bot/poetry.lock

RUN poetry install

COPY . /code


CMD ["poetry", "run", "python", "main.py"]