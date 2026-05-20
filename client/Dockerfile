FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
COPY client/ ./client/
COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

ENV SERVER_HOST=server
ENV SERVER_PORT=9000
ENV SIMULATE_FREEZE=0

CMD ["python", "-u", "-m", "client.main"]
