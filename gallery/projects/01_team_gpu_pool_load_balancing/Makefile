# Author: Silan Hu (silan.hu@u.nus.edu)

.PHONY: help server node-alpha node-beta client

PORT ?= 8081
GATEWAY ?= 127.0.0.1:$(PORT)

help:
	@echo "Targets: server | node-alpha | node-beta | client"
	@echo "Variables: PORT=$(PORT) GATEWAY=$(GATEWAY)"

server:
	EASYREMOTE_PORT=$(PORT) uv run python server.py

node-alpha:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python node_gpu_alpha.py

node-beta:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python node_gpu_beta.py

client:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python client.py
