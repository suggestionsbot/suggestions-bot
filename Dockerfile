FROM python:3.11-alpine

WORKDIR /code
RUN pip install poetry

COPY ./pyproject.toml /code/pyproject.toml
COPY ./poetry.lock /code/poetry.lock

RUN poetry install

COPY . /code

CMD ["poetry", "run", "python", "main.py"]