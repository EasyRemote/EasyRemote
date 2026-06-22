# 07 Claude Code Robot Commander MCP

## Usage Scenario

Claude Code or a similar developer agent may act as a commander for real device tasks, not only code generation. It can generate plans, deploy runtime capabilities, operate robots or sandbox devices, and read telemetry.

## Concrete Use Case

A developer installs a commander skill in Claude Code. The user asks, "Move demo-user's inspection robot forward by one meter and report status." The commander uses EasyRemote to locate the user node, install a robot runtime skill, execute the action, and pull status and telemetry.

## Current Problem

Robot control usually depends on vendor SDKs, local network access, and device-specific protocols. An agent may generate the right plan but still lacks a safe way to operate user-side devices across networks. Exposing device APIs directly to an agent also lacks authorization boundaries and execution evidence.

## Intent

This project separates the commander's high-level decision from local device execution. Claude Code enters the EasyRemote capability layer through MCP, and the actual device action runs inside the local user-node runtime.

## Target Outcome

The commander skill can deploy tasks and call device capabilities through a common path without directly taking over the device. The user node keeps local permission control and receipt evidence, while robotics platforms package actions as installable, auditable, composable capabilities.
