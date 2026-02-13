# Author: Silan Hu (silan.hu@u.nus.edu)

.PHONY: help server node client

PORT ?= 8080
GATEWAY ?= 127.0.0.1:$(PORT)

help:
	@echo "Targets: server | node | client"
	@echo "Variables: PORT=$(PORT) GATEWAY=$(GATEWAY)"

server:
	EASYREMOTE_PORT=$(PORT) uv run python server.py

node:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python compute_node.py

client:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python client.py
