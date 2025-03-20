FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN apt update && apt install -y procps && rm -rf /var/lib/apt/lists/*

CMD ["python", "-u", "main.py"]