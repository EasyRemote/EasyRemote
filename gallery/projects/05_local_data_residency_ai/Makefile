# Author: Silan Hu (silan.hu@u.nus.edu)

.PHONY: help server node client protocol-demo

PORT ?= 8083
GATEWAY ?= 127.0.0.1:$(PORT)

help:
	@echo "Targets: server | node | client | protocol-demo"
	@echo "Variables: PORT=$(PORT) GATEWAY=$(GATEWAY)"

server:
	EASYREMOTE_PORT=$(PORT) uv run python server.py

node:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python node_local_processor.py

client:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python client.py

protocol-demo:
	uv run python protocol_demo.py
