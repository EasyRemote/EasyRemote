# 03 A2A Incident Copilot

## Usage Scenario

SRE and platform engineering teams want an incident copilot to help process alerts: collect evidence, call diagnostic scripts, prepare remediation suggestions, and request human approval before risky actions.

## Concrete Use Case

An API latency alert fires. The copilot calls a log node for error summaries, a metrics node for latency distribution, and a deployment node for recent changes. If the risk is low, it prepares a rollback recommendation. If the action writes state, it waits for the on-call engineer to approve.

## Current Problem

Operations knowledge is scattered across runbooks, scripts, dashboards, and personal experience. Agents can read docs and write recommendations, but calling internal scripts safely introduces permission, network, execution evidence, and multi-step state management problems.

## Intent

This project makes operations actions authorized capabilities and lets agents organize them through A2A-style task chains. Diagnosis, judgment, and remediation are no longer agent autobiography; they become executions with call boundaries and receipts.

## Target Outcome

The on-call engineer gets a copilot that can perform low-risk diagnosis, summarize evidence, and preserve human approval points. The system can trace the identity, input, output, and result of each step, so incident review does not depend on chat history and memory.
