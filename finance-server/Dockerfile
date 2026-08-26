FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server_app ./server_app
COPY ../app ./app
ENV FINANCE_SERVER_PASSWORD=finance-v4
EXPOSE 8766
CMD ["uvicorn", "server_app.main:app", "--host", "0.0.0.0", "--port", "8766"]
