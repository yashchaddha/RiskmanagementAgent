FROM python:3.13.7-slim-trixie

#FROM python:3.13.7-alpine3.21
# alpine is smaller but there are issues with grpcio
# needs g++ linux-headers to compile but ends up being too slow
# and this doesn't work
# RUN apk add --no-cache py3-grpcio

WORKDIR /usr/src/app

COPY backend .
# COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

EXPOSE 8000

CMD [ "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
