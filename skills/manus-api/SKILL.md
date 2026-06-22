---
name: manus-api
description: Manage Manus tasks, projects, and configuration via API, or leverage Manus agents to build automated bots and workflows.
---

# Manus API Integration Guide

This skill provides the trunk knowledge for integrating Manus AI agents into applications or automated workflows. Official API documentation source files are embedded under `docs/` (relative to this file).

**Version policy.** This guide targets **API v2**, the current and recommended version for all new integrations. **API v1 is deprecated** but still operational; if a user is working with a pre-existing v1 integration, the legacy docs are under `docs/v1/` for reference. Never recommend v1 for new projects.

**Where to look for information.**
You can find all API specifications, request schemas, and edge-case parameters in the embedded docs at `docs/v2/*.mdx` (or `docs/v1/` for legacy users). If you suspect the embedded docs are outdated or missing a newly released endpoint, fall back to the online documentation at [https://open.manus.im/docs/v2/introduction](https://open.manus.im/docs/v2/introduction).

**Base URL and response envelope.** All requests go to `https://api.manus.ai` with header `x-manus-api-key: <key>`. Successful responses have the shape `{ "ok": true, "request_id": "...", ...data }`; errors have `{ "ok": false, "request_id": "...", "error": { "code": "...", "message": "..." } }`. Common error codes are `invalid_argument`, `not_found`, `permission_denied`, and `rate_limited`. API keys are created at [https://manus.im/app#settings/integrations/api](https://manus.im/app#settings/integrations/api).

---

## 1. Getting Started Guides Overview

The `docs/v2/` directory contains several conceptual guides in addition to per-endpoint references. Consult these when the user's question is about an integration pattern rather than a specific API call — they contain integration advice and architectural details not repeated in this file.

| Guide | When to read it | File |
| --- | --- | --- |
| **Introduction** | Top-level capability summary; response envelope and error-code catalog. | `docs/v2/introduction.mdx` |
| **Authentication** | API key generation, rotation, storage best practices. Account limit: 50 keys. | `docs/v2/authentication.mdx` |
| **Rate Limits** | Per-user request-per-minute ceilings for every v2 endpoint. Consult before designing polling or batch-creation loops. | `docs/v2/rate-limits.mdx` |
| **Task Lifecycle** | Polling patterns, handling `waiting` status (user confirmation via `task.confirmAction`), and result retrieval. | `docs/v2/task-lifecycle.mdx` |
| **Connectors** | How to authorize third-party apps (Gmail, GitHub, etc.) in the webapp and pass their UUIDs in `message.connectors`. | `docs/v2/connectors.mdx` |
| **Webhooks** | Event types, delivery payload shape, and RSA-SHA256 signature verification — required reading for production bots. | `docs/v2/webhooks-overview.mdx`, `docs/v2/webhooks-security.mdx` |
| **Agents** | Custom IM agents and the `agent-default-main_task` shortcut for interacting with the default IM agent without looking up UUIDs. | `docs/v2/agents-overview.mdx` |
| **Integrations** | Setting up Manus inside external platforms (currently Slack). Distinct from Connectors: Integrations put Manus into a platform; Connectors put a platform into Manus. | `docs/v2/integrations-overview.mdx`, `docs/v2/integrations-slack.mdx` |
| **Data Integrations** | Built-in third-party data sources (e.g., SimilarWeb) invoked implicitly via prompt — no API key management required from the caller. | `docs/v2/data-integrations-overview.mdx`, `docs/v2/data-integrations-similarweb.mdx` |

---

## 2. Endpoint Groups Overview

The Manus API is organized into the following groups (full specs in `docs/v2/*.mdx`):

| Group | Purpose | Key Endpoints |
| --- | --- | --- |
| **Tasks** | The core engine. Create and manage agent execution lifecycles and multi-turn conversations. | `task.create`, `task.sendMessage`, `task.listMessages`, `task.confirmAction`, `task.stop` |
| **Projects** | Group related tasks and automatically inject shared instructions (personas/rules). | `project.create`, `project.list` |
| **Files** | Upload attachments (PDFs, CSVs, images) for agents to process, or download generated artifacts. | `file.upload`, `file.detail`, `file.delete` |
| **Webhooks** | Configure HTTP callbacks for task lifecycle events. | `webhook.create`, `webhook.list`, `webhook.delete`, `webhook.publicKey` |
| **Skills** | List available agent skills to selectively enable or force during a task. | `skill.list` |
| **Connectors** | List installed third-party integrations (e.g., Gmail, GitHub) to attach to tasks. | `connector.list` |
| **Agents** | Manage and configure custom IM agents. | `agent.list`, `agent.get`, `agent.update` |
| **Usage** | Retrieve token and cost consumption for the team. | `usage.list`, `usage.teamStatistic`, `usage.teamLog` |

---

## 3. Integration Architecture & Implicit Knowledge

When building bots or automated triggers (such as email pollers, cron jobs, or platform chatbots), keep these architectural patterns in mind.

- **Task ID Lifecycle.** For multi-turn conversations (like a Slack thread), call `task.create` for the first message and store the `task_id`. For subsequent messages in the same thread, use `task.sendMessage` with that `task_id` [1]. For isolated, one-off automated triggers, always use `task.create` [2].
- **Persona Injection via Projects.** The recommended way to give an agent a persona or system prompt is to create a Project with an `instruction` field (e.g., "Always format output as a Markdown table"), then pass the resulting `project_id` when calling `task.create` [3].
- **Output Format Directives.** If your integration requires a specific output format (e.g., PDF for an email attachment), instruct the agent directly in the prompt ("Generate the final report as a PDF"). Do not parse and convert Markdown yourself unless strictly necessary.
- **Result Retrieval Paths.** Retrieve output via Webhooks (recommended for production bots) [4] or by polling `task.listMessages` (simpler for scripts) [5]. Webhook payloads must be verified using the RSA-SHA256 signature [6].

---

## 4. Core Flow: Concrete API Specs

The following endpoints form the critical path for a closed-loop integration.

### 4.1 Uploading Attachments (Input)

**Endpoint**: `POST /v2/file.upload` [7]
**Request Body**: `{"filename": "dataset.csv"}`
**Response**: Returns an `upload_url` (presigned S3 URL, valid 3 minutes) and a `file` object with an `id`.
**Action Required**: Perform an HTTP `PUT` request with the raw file bytes to the `upload_url`. Then use the `file.id` in `task.create` or `task.sendMessage`.

### 4.2 Creating a Project (Persona Injection)

**Endpoint**: `POST /v2/project.create` [3]

```json
{
  "name": "Financial Analysis Bot",
  "instruction": "You are a senior financial analyst. Always summarize findings in a bulleted list."
}
```

**Response**: Returns a `project` object containing the `id` to be used in tasks.

### 4.3 Creating a Task

**Endpoint**: `POST /v2/task.create` [2]

```json
{
  "message": {
    "content": [
      { "type": "text", "text": "Analyze this dataset." },
      { "type": "file", "file_id": "file-12345" }
    ],
    "connectors": ["connector-uuid-123"]
  },
  "project_id": "project-67890",
  "title": "Q1 Analysis"
}
```

**Response**: Returns a `task_id` and a `task_url` for webapp viewing.

### 4.4 Polling for Results

**Endpoint**: `GET /v2/task.listMessages?task_id=task-67890&limit=50&order=asc` [5]

Look for a `status_update` message whose `agent_status` is `"stopped"` to know the task is done. The final output is in `assistant_message` objects:

```json
{
  "type": "assistant_message",
  "assistant_message": {
    "content": "Here is the summary...",
    "attachments": [
      {
        "type": "file",
        "filename": "report.pdf",
        "url": "https://cdn.manus.im/files/...",
        "content_type": "application/pdf"
      }
    ]
  }
}
```

Download generated artifacts directly from the `url`. Note that `task.listMessages` returns messages in reverse chronological order by default; pass `order=asc` for chronological iteration.

---

## References

Each v2 endpoint has a dedicated reference file named after its method (group.action convention): e.g., `task.create` is documented at `docs/v2/task.create.mdx`, `file.upload` at `docs/v2/file.upload.mdx`, and so on. To read the spec for any endpoint mentioned in this guide, open `docs/v2/<endpoint>.mdx` directly.

[1] task.sendMessage — `docs/v2/task.sendMessage.mdx`
[2] task.create — `docs/v2/task.create.mdx`
[3] project.create — `docs/v2/project.create.mdx`
[4] Webhooks Overview — `docs/v2/webhooks-overview.mdx`
[5] task.listMessages — `docs/v2/task.listMessages.mdx`
[6] Webhook Security — `docs/v2/webhooks-security.mdx`
[7] file.upload — `docs/v2/file.upload.mdx`
