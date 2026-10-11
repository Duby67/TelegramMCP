# TelegramMCP

A planned MCP service that lets AI agents access a user's Telegram account through a defined set of tools. This README records the intended architecture; the Docker service and API are not yet implemented.

## Deployment and connection model

The project will provide a single Docker image and a shared API. Users will deploy the service themselves and choose the connection method that suits their client.

| Deployment | Intended clients | Connection |
| --- | --- | --- |
| Local Docker service | AI agents running on the user's computer | The agent connects to the container's local MCP endpoint. |
| Docker service on a server | Browser-based plugins and cloud clients | The plugin connects to the service through an authenticated HTTPS MCP endpoint. |

Both deployments will use the same container, API, and Telegram tools. Server deployment will add external connectivity and authentication rather than require a separate application. The project will not require a centrally hosted service operated by its maintainer.

## Account access and secrets

Users will authorize their Telegram account in their own deployment. Telegram credentials and account sessions will remain in persistent storage controlled by that user and will not be included in tool responses sent to the model. The model will receive the tools' results, including the messages requested for analysis.

## Initial use case

An agent will read new posts from selected Telegram channels, filter them by topic, and produce a daily digest with links to the source messages. Scheduling will be handled by the connected client or a separate scheduler; MCP will provide access to Telegram. The Docker service must be running and reachable whenever a task executes.
