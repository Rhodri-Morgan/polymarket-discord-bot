IMAGE_NAME := polymarket-bot
CONTAINER_NAME := polymarket-bot
DOCKER_RUN := docker run --rm \
	--name $(CONTAINER_NAME) \
	--env-file .env \
	-v $(HOME)/.aws:/root/.aws:ro \
	-v $(PWD)/data:/app/data \
	-e AWS_PROFILE=rtm


.PHONY: install
install:
	uv sync

.PHONY: install-dev
install-dev:
	uv sync --dev

.PHONY: install-git-hooks
install-git-hooks:
	uv run pre-commit install

.PHONY: format
format:
	uv run black .

.PHONY: lint
lint:
	uv run ruff check .

.PHONY: run
run:
	uv run python -m polymarket_bot

.PHONY: seed
seed:
	uv run python scripts/seed_dev_data.py --data-dir ./data

.PHONY: dev
dev: seed
	DATA_DIR=./data uv run python -m polymarket_bot

.PHONY: test
test:
	uv run pytest

.PHONY: docker-stop
docker-stop:
	@docker stop $(CONTAINER_NAME) 2>/dev/null || true

.PHONY: docker-build
docker-build:
	docker build -t $(IMAGE_NAME) .

.PHONY: docker-run
docker-run: docker-stop docker-build
	$(DOCKER_RUN) $(IMAGE_NAME)

.PHONY: docker-seed
docker-seed: docker-build
	mkdir -p data
	$(DOCKER_RUN) $(IMAGE_NAME) uv run python scripts/seed_dev_data.py --data-dir /app/data

.PHONY: docker-dev
docker-dev: docker-stop docker-seed
	$(DOCKER_RUN) $(IMAGE_NAME)

.PHONY: docker-test
docker-test: docker-build
	$(DOCKER_RUN) $(IMAGE_NAME) uv run pytest

.PHONY: docker-shell
docker-shell: docker-build
	$(DOCKER_RUN) -it $(IMAGE_NAME) /bin/bash

.PHONY: clean
clean:
	rm -rf .venv __pycache__ .pytest_cache .mypy_cache data/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.PHONY: docker-clean
docker-clean:
	docker rmi $(IMAGE_NAME) 2>/dev/null || true

.PHONY: tag-and-push
tag-and-push:
	@gh api 'repos/Rhodri-Morgan/github-workflows/contents/scripts/tag-and-push.sh?ref=v2' --jq '.content' | base64 -d > /tmp/tag-and-push.sh
	@sh /tmp/tag-and-push.sh
