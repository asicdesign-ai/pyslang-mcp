# Remote Secure Deployment Plan

This document describes how to evolve `pyslang-mcp` from a local `stdio`
analysis server into a remotely connectable MCP service that feels similar to
well-known hosted MCP integrations such as GitHub or Google Sheets, while still
preserving the repo's actual product definition: compiler-backed, read-only HDL
project analysis.

## Product Boundary

`pyslang-mcp` is not a SaaS data connector in the same sense as GitHub or
Google Sheets. Those systems already host the source of truth. This server is
different:

- it analyzes files on disk
- it needs an explicit project root
- it must not silently read arbitrary host paths

Implication:

- a hosted version must provide controlled workspace access, not just expose the
  existing local process over the network

## Goal

Provide a remotely connectable MCP endpoint that:

- supports authenticated users and agents
- can analyze private HDL repositories safely
- preserves strict read-only semantics
- isolates users, repositories, and workspaces
- returns the same compact JSON tool outputs as the local server

## Non-Goals

- shared host-path access across tenants
- arbitrary filesystem browsing
- remote code execution
- simulation, synthesis, or waveform support
- mutable repository actions

## Deployment Model

The recommended model is workspace-scoped remote MCP.

High-level flow:

1. User authenticates to the hosted service.
2. User selects or provisions a workspace.
3. The workspace is populated from a repo clone, uploaded archive, mounted
   volume, or pre-synced project source.
4. The MCP server only analyzes files inside that workspace root.
5. Tool calls include a logical workspace identifier plus project-relative
   inputs.

## Recommended Architecture

### 1. Control Plane

Responsibilities:

- authentication
- user and organization management
- workspace lifecycle
- repo connection management
- audit logging
- rate limiting and quotas

Suggested components:

- API gateway
- auth service
- workspace metadata store
- job queue for workspace sync and prewarming

### 2. Data / Workspace Plane

Responsibilities:

- repository checkout or upload storage
- per-workspace file access
- cached analysis state
- file mtime tracking

Suggested units:

- one isolated workspace per user/repo/revision combination
- ephemeral or semi-persistent storage
- object storage for uploaded bundles
- workspace metadata pointing to exact commit or snapshot

### 3. MCP Execution Plane

Responsibilities:

- serve MCP over HTTP transport
- authorize every request against a workspace
- instantiate analysis only inside the workspace root
- enforce output limits and timeouts

Suggested units:

- stateless HTTP frontend
- worker pool or per-workspace execution service
- shared read-only analysis library reused from the current repo

## Security Model

### Authentication

Use authenticated HTTP access from day one.

Recommended options:

- OAuth/OIDC for human users
- bearer tokens or service tokens for automation
- short-lived access tokens for MCP clients

Avoid:

- anonymous hosted access
- long-lived broad-scope static tokens as the only auth model

### Authorization

Authorization must be workspace-scoped.

Every MCP request should resolve:

- who is calling
- which workspace they can access
- which repo snapshot that workspace maps to

Required checks:

- user can access the workspace
- requested project root is inside the provisioned workspace root
- requested files and filelists remain inside the workspace boundary

### Isolation

This is the critical difference between a safe hosted service and a dangerous
"remote shell with parsing."

Minimum acceptable isolation:

- one workspace root per tenant context
- no access outside that root
- no shared mutable checkout directory across users

Preferred isolation:

- one container or sandbox per workspace
- read-only mounted project files for MCP workers
- scratch directories separated from source directories

### Transport Security

- HTTPS only
- TLS termination at the edge
- secure cookies only if browser-based auth is used
- token redaction in logs

### Auditability

Log:

- authenticated principal
- workspace ID
- tool name
- request timestamps
- response size and truncation
- high-level error categories

Do not log:

- full source contents by default
- raw credentials
- secrets found in user repos

## Workspace Provisioning Modes

Support these in order:

### Mode 1. Single-Tenant Self-Hosted

Best first remote target.

Pattern:

- one company or team deploys the service in its own environment
- the service analyzes repos already available in that network

Why first:

- simpler auth
- fewer multi-tenant risks
- easier enterprise adoption

### Mode 2. Managed Repo Sync

Pattern:

- hosted control plane connects to GitHub/GitLab/Bitbucket
- user authorizes repo access
- service clones selected repos into isolated workspaces

Requirements:

- app installation or OAuth integration
- commit pinning
- branch / revision selection
- background sync jobs

### Mode 3. Upload-Based Workspace

Pattern:

- user uploads a zip or tarball snapshot
- service expands it into an isolated workspace

Use case:

- private code without direct VCS integration

## MCP API Shape For Hosted Use

Keep the semantic tool names the same when possible.

But the transport-facing inputs will likely need one of these patterns:

### Option A. Keep `project_root`

Requests still pass:

- `project_root`
- `files` or `filelist`

The server maps `project_root` inside a workspace root.

Good:

- local and remote parity

Risk:

- more path-handling complexity for clients

### Option B. Introduce `workspace_id`

Requests pass:

- `workspace_id`
- optional relative `project_root`
- `files` or `filelist`

Good:

- cleaner hosted identity boundary
- easier auth and audit

Recommended:

- use `workspace_id` for hosted mode
- preserve current `project_root` shape for local mode

## Codebase Changes Needed

The current repo already has the right core split:

- `project_loader.py`
- `analysis.py`
- `serializers.py`
- `cache.py`
- `server.py`

To support secure remote deployment, add:

- `auth.py`
  - token validation
  - principal extraction
- `workspace_manager.py`
  - workspace resolution
  - repo snapshot selection
  - local path mapping
- `policy.py`
  - authorization checks
  - per-tool limits
- `audit.py`
  - structured logs
  - security events
- `transport_http.py`
  - production HTTP MCP startup path

## Caching Strategy

Local cache logic should be reused, but hosted deployment needs stronger cache
keys:

- workspace ID
- repo snapshot / commit SHA
- project config hash
- tracked file mtimes or immutable snapshot metadata

For remote service operation:

- prefer immutable workspace snapshots keyed by commit
- avoid cross-tenant cache reuse without explicit hard partitioning

## Operational Controls

Required controls:

- per-request timeout
- per-tool response-size limit
- concurrency limit per workspace
- rate limiting per user / org / token
- storage quota per workspace
- background cleanup of old workspaces

Nice to have:

- prewarmed analysis caches for active repos
- tracing around analysis latency
- metrics for tool popularity and truncation frequency

## Rollout Plan

### Phase 0. Keep Local `stdio` First

Done in the current repo.

### Phase 1. Production-Grade Self-Hosted HTTP Mode

Deliverables:

- authenticated HTTP transport
- single-tenant deployment guide
- workspace-scoped path enforcement
- audit logs

Goal:

- make remote use viable inside one company's own infrastructure

### Phase 2. Repo-Connected Hosted Workspaces

Deliverables:

- GitHub/GitLab repo connectors
- workspace provisioning and sync
- commit-pinned analysis
- background indexing / prewarming

Goal:

- comparable usability to well-known hosted MCPs, but for HDL repos

### Phase 3. Multi-Tenant Managed Service

Deliverables:

- tenant isolation hardening
- quotas and billing hooks
- SSO
- org-level admin controls
- security review and penetration testing

Goal:

- public hosted product surface

## Recommendation

If the objective is "make this connectable like famous MCPs," the clean path is:

1. keep the current repo's semantic analysis core unchanged
2. add a secure hosted HTTP transport as a new deployment mode
3. introduce explicit workspace identity for hosted use
4. ship single-tenant self-hosted first
5. only then consider public multi-tenant hosting

That preserves the technical honesty of the current project while still moving
toward a connectable hosted MCP product.
