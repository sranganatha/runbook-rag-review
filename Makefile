PYTHON ?= python
IMAGE ?= runbook-rag-review:test
MODEL_COMPOSE ?= compose.model.yaml
BEDROCK_IMAGE ?= runbook-rag-review:bedrock
AWS_DIR ?= $(if $(USERPROFILE),$(USERPROFILE)/.aws,$(HOME)/.aws)
AWS_REGION ?= us-east-1

.PHONY: check report test test-container verify-bedrock verify-model

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

verify-bedrock:
	podman build --file Containerfile.bedrock --tag $(BEDROCK_IMAGE) .
	podman run --rm -e AWS_REGION=$(AWS_REGION) -e AWS_EC2_METADATA_DISABLED=true -v "$(AWS_DIR):/root/.aws:ro" -v "$(CURDIR)/artifacts:/app/artifacts" $(BEDROCK_IMAGE)
