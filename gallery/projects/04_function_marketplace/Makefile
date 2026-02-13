# Author: Silan Hu (silan.hu@u.nus.edu)

.PHONY: help server node-finance node-ops client agent-demo

PORT ?= 8082
GATEWAY ?= 127.0.0.1:$(PORT)

help:
	@echo "Targets: server | node-finance | node-ops | client | agent-demo"
	@echo "Variables: PORT=$(PORT) GATEWAY=$(GATEWAY)"

server:
	EASYREMOTE_PORT=$(PORT) uv run python server.py

node-finance:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python node_finance.py

node-ops:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python node_ops.py

client:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) uv run python client.py

agent-demo:
	uv run python agent_catalog_demo.py
