# 06 Runtime Device Capability Injection

## Usage Scenario

Consumer agent apps and edge platforms need user devices to perform actions such as taking photos, recording video, sampling audio, or reading sensors. They should not preinstall every future capability into the client.

## Concrete Use Case

A user authorizes a home assistant agent to take a phone photo of a device label. The client initially exposes only a safe installation entrypoint. The agent sends a camera runtime skill, the user device registers `take_photo` locally, and the agent calls that capability to receive the photo result.

## Current Problem

Preinstalling all device capabilities expands attack surface, increases permission requests, and complicates the client. Waiting for a release to add every new capability slows agent product iteration. More importantly, the platform must control actions by user, device, and authorization scope rather than turning the device into a generic remote-control endpoint.

## Intent

This project treats device actions as runtime capabilities installed on demand. The server initiates the capability transfer, but registration and execution happen locally on the user device. Authorization, source, action scope, and receipts must become part of the capability chain.

## Target Outcome

Agents can extend user-device capabilities when a task requires them, while the user side keeps authorization and execution boundaries. The platform does not need frequent client releases to introduce new device actions, and each capability can be targeted and audited by user node.
