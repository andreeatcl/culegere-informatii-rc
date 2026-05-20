FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
COPY server/ ./server/
COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 9000

CMD ["python", "-u", "-m", "server.main"]
