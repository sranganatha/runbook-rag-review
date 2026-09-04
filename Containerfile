FROM docker.io/library/python:3.12-slim

WORKDIR /app
COPY . .

RUN python -m compileall -q runbook_rag_review tests \
    && python -m runbook_rag_review.validate_fixtures

CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
