FROM python:3.12

ARG MEM0_REF=main

WORKDIR /tmp
ADD https://github.com/mem0ai/mem0/archive/refs/heads/${MEM0_REF}.tar.gz /tmp/mem0.tar.gz

RUN mkdir -p /src/mem0 \
  && tar -xzf /tmp/mem0.tar.gz -C /src/mem0 --strip-components=1

WORKDIR /app
RUN pip install --no-cache-dir -r /src/mem0/server/requirements.txt

WORKDIR /app/packages
RUN cp /src/mem0/pyproject.toml /src/mem0/poetry.lock /src/mem0/README.md ./ \
  && cp -r /src/mem0/mem0 ./mem0 \
  && pip install --no-cache-dir -e .[graph]

WORKDIR /app
RUN cp -r /src/mem0/server/. /app/

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH=

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
