FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tests ./tests
# Unit tests run at build time: a broken legal rule fails the build.
RUN python -m pytest -q tests
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
