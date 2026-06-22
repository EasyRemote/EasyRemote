# 04 Function Marketplace

## Usage Scenario

An organization has many validated business functions, but they are scattered across services, scripts, and repositories. A platform team wants to turn them into a discoverable, reusable, governable capability marketplace.

## Concrete Use Case

The finance team owns `normalize_invoice`, the operations team owns `classify_ticket`, and the data team owns `score_customer_health`. A new project needs all three for customer risk analysis and should not copy the logic into a new codebase.

## Current Problem

Function reuse often stops at "I know another team wrote that." Real use still requires copying code, opening a new API, negotiating permissions, or waiting for another team's backlog. There is no shared catalog, and the function has no clear owner, version, invocation record, or quality signal.

## Intent

This project defines a function marketplace as a marketplace of callable capabilities. It is not a snippet list. The original teams continue to own the functions, while the platform provides common discovery and governance.

## Target Outcome

New projects can search existing capabilities before building new ones. The platform can attach tags, permissions, scores, audits, and version policy to capabilities. Business functions move from team-local implementation to organization-level assets.
