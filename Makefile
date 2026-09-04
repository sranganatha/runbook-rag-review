PYTHON ?= python
IMAGE ?= runbook-rag-review:test

.PHONY: check test test-container

check:
	$(PYTHON) -m compileall -q runbook_rag_review tests
	$(PYTHON) -m runbook_rag_review.validate_fixtures

test:
	$(PYTHON) -m unittest discover -s tests -v

test-container:
	podman build --tag $(IMAGE) .
	podman run --rm --network none $(IMAGE)
