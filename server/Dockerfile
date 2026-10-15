FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
# FastMCP 가 OAuth 관련 파일을 쓸 수 있도록 쓰기 가능한 홈 경로를 지정
ENV FASTMCP_HOME=/tmp/fastmcp
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
