# Author: Silan Hu (silan.hu@u.nus.edu)

.PHONY: help server node commander

PORT ?= 8085
GATEWAY ?= 127.0.0.1:$(PORT)
USER_ID ?= demo-user
NODE_ID ?= robot-sandbox-$(USER_ID)
TARGET_USER_ID ?= $(USER_ID)
TARGET_USER_NODE_ID ?=
MISSION_ID ?= mission-robot-inspection
MISSION_STEPS ?= boot,inspect,report
ROBOT_ACTION ?= forward
ROBOT_DISTANCE_M ?= 1.5

help:
	@echo "Targets: server | node | commander"
	@echo "Variables: PORT=$(PORT) GATEWAY=$(GATEWAY)"
	@echo "           USER_ID=$(USER_ID) NODE_ID=$(NODE_ID)"
	@echo "           TARGET_USER_ID=$(TARGET_USER_ID) TARGET_USER_NODE_ID=$(TARGET_USER_NODE_ID)"
	@echo "           MISSION_ID=$(MISSION_ID) MISSION_STEPS=$(MISSION_STEPS)"
	@echo "           ROBOT_ACTION=$(ROBOT_ACTION) ROBOT_DISTANCE_M=$(ROBOT_DISTANCE_M)"

server:
	EASYREMOTE_PORT=$(PORT) uv run python server.py

node:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) USER_ID=$(USER_ID) NODE_ID=$(NODE_ID) uv run python client_sandbox_node.py

commander:
	EASYREMOTE_GATEWAY_ADDRESS=$(GATEWAY) TARGET_USER_ID=$(TARGET_USER_ID) TARGET_USER_NODE_ID=$(TARGET_USER_NODE_ID) MISSION_ID=$(MISSION_ID) MISSION_STEPS=$(MISSION_STEPS) ROBOT_ACTION=$(ROBOT_ACTION) ROBOT_DISTANCE_M=$(ROBOT_DISTANCE_M) uv run python commander_client.py
