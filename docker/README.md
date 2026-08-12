# Phase 2 Docker Sandbox

This image is the fixed `agent-foundations-sandbox:phase2` execution boundary. The backend always uses no network, a read-only root filesystem, dropped Linux capabilities, `no-new-privileges`, UID/GID `65532:65532`, and fixed process, memory, and CPU limits. It exposes exactly one `/workspace` bind mount; only the request's already-authorized mount mode controls whether that mount is read-only or project-writable.

Build and smoke testing require explicit authorization because they modify Docker daemon state and may pull the fixed base image:

```powershell
docker build -f docker/agent-sandbox.Dockerfile -t agent-foundations-sandbox:phase2 .
conda run -n agent-foundations python -m pytest tests/integration/test_execution_backend.py -m docker -q
```

Inspect the exact artifacts with `docker image inspect agent-foundations-sandbox:phase2` and `docker ps -a --filter name=af-`. Test containers use `--rm`. The image is intentionally retained unless the user explicitly authorizes removal; cleanup must target the exact tag or image ID, for example `docker image rm agent-foundations-sandbox:phase2`. Never use `docker prune`.

If Docker is unavailable, execution fails closed. There is no host subprocess fallback. `PROJECT_FULL_ACCESS` still means only project-scoped implemented capabilities under hard Policy and Sandbox limits; it never means unrestricted terminal, network, credential, home-directory, or computer access.
