# 00 Basic Remote Math

## Usage Scenario

This is the smallest Demo-as-API scenario. A developer already has a local function and wants another person or system to call it remotely without building a full backend first.

## Concrete Use Case

A sales engineer writes `calculate_quote`, a local function that computes pricing from customer size, plan, and discount. The sales team needs to try it tomorrow. Ideally, the engineer registers the function and the demo client calls it directly.

## Current Problem

To let others try one function, teams often build a temporary HTTP API, start a service, configure ports, add authentication, and explain that the demo is not production. Early prototype feedback gets slowed down by deployment work.

## Intent

This project states the minimum EasyRemote value: a function should not need to become a full service before it can be remotely called. The first service boundary should be registering a capability, not building a temporary backend.

## Target Outcome

The user can move from "it runs locally" to "someone else can call it" quickly. The caller gets a stable entrypoint, the provider keeps the local execution environment, and neither side takes on full deployment cost for an early demo.
