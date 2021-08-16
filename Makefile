ORG=asahi
NAME=builder

build: ## Build docker image
	@docker build -t $(ORG)/$(NAME) .

installer: build ## Build asahi installer
	@docker run --init --rm -v $(PWD):/asahi --platform linux/arm64 $(ORG)/$(NAME)