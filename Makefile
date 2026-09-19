PYTHON ?= python
IMAGE ?= runbook-rag-review:test

.PHONY: check report test test-container

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
