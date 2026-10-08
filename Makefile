PYTHON ?= python
IMAGE ?= runbook-rag-review:test
MODEL_COMPOSE ?= compose.model.yaml

.PHONY: check report test test-container verify-model

check:
	$(PYTHON) -m compileall -q runbook_rag_review tests
	$(PYTHON) -m runbook_rag_review.validate_fixtures

test:
	$(PYTHON) -m unittest discover -s tests -v

report:
	$(PYTHON) -m runbook_rag_review.cli evaluate --output-dir artifacts

test-container:
	podman build --tag $(IMAGE) .
	podman run --rm --network none $(IMAGE)

verify-model:
	podman compose -f $(MODEL_COMPOSE) up -d ollama
	podman compose -f $(MODEL_COMPOSE) run --rm pull-model
	podman compose -f $(MODEL_COMPOSE) build verify
	podman compose -f $(MODEL_COMPOSE) run --rm --no-deps verify
	podman compose -f $(MODEL_COMPOSE) down
