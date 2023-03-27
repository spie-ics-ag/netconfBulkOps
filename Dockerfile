FROM python:3.9.16-alpine

WORKDIR /ncbo

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .