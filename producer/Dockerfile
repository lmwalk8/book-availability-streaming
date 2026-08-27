FROM python:3.12-slim

WORKDIR /app

COPY producer/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY producer/ .

ENV PYTHONUNBUFFERED=1

CMD ["python", "poll_loop.py"]
