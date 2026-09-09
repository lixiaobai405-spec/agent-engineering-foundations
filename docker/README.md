# Phase 2 Docker Sandboxes

Task 17 defines two fixed command profiles in addition to the retained Phase 2C
patch image:

- `agent-foundations-sandbox:phase2` from `docker/agent-sandbox.Dockerfile`
- `agent-foundations-sandbox-python:phase2d`
- `agent-foundations-sandbox-node:phase2d`

The host controller supplies a filtered, read-only snapshot at `/project-ro`.
The fixed entrypoint copies it into the container-only `/workspace` tmpfs before
executing the structured argv with `exec "$@"`. On the Node image, the entrypoint
makes `/workspace/node_modules` a real tmpfs directory and `ln -s` each store
entry from `/opt/sandbox/node_modules` (including `.bin`) into it. The store
itself stays read-only; the whole tree is not copied into tmpfs. The Node
entrypoint also sets `TMPDIR` to a directory on the `/workspace` tmpfs so
Vitest can create ephemeral files under `--read-only` without a `/tmp`
mount. Rebuild the Node image after changing the entrypoint and update only
the Node `final_*` fields in `docker/sandbox-manifest.phase2d.json`. The backend keeps networking
disabled, the root filesystem read-only, all Linux capabilities dropped,
`no-new-privileges`, UID/GID `65532:65532`, and fixed PID, CPU, memory, output,
and timeout limits. There is no host subprocess fallback.

The Python Dockerfile is pinned to the locally inspected immutable
`python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2`
base. The Node Dockerfile is pinned to the inspected immutable
`node@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5`
base. Its build arguments may only be overridden with another independently
inspected immutable RepoDigest, never a mutable tag or fabricated image ID.
Both final image IDs, optional final RepoDigests, and lock fingerprints must be
recorded in `SandboxManifest` before command execution.

The build context is allowlisted by `.dockerignore`; it contains only the three
Dockerfiles, entrypoint, Python lock, and existing npm manifests. It does not
send source, tests, `.env`, Git data, Chat assets, databases, logs, or the dirty
worktree to the daemon.

The Phase 2C controlled Patch image remains independently rebuildable without
using either Task 17 command-profile image. The legacy `agent-foundations-sandbox:phase2`
image now includes `git` so Phase 2D read-only `git_status` / `git_diff` / `git_log`
can run with `mount_mode=read_only`. Those tools still use isolated HOME / XDG /
`GIT_CONFIG_*` inside the container and never inherit the host Git config. This
does not add Git write tools, host Git fallback, or command-profile image changes.

```powershell
docker build --pull=false -f docker/agent-sandbox.Dockerfile -t agent-foundations-sandbox:phase2 .
```

Pull, build, run, smoke testing, and image deletion all require the explicit
authorization described by Task 17. Never use `docker prune`. If Docker or
trusted provenance is unavailable, execution fails closed. `PROJECT_FULL_ACCESS`
still means project-scoped implemented capabilities under hard Policy and
Sandbox limits; it never means unrestricted terminal, network, credentials,
home-directory, or computer access.
