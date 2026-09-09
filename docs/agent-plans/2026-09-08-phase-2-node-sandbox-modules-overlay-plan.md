# Phase 2 Node Sandbox Modules Overlay Plan

**Date:** 2026-09-08  
**Status:** Task 44 / `phase-2d-task-28` 已于 2026-09-08 用户验收通过（targeted）。本计划无 Task 45。不关闭 Task 25 / Phase 2 用户验收 / Step 10/11；付费 3×3 须另授权，预检须用新 Node pin。  
**Role:** planner 维护；本文件不实现生产代码  
**Parent:** `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md`  
**Does not replace:** Task 25、Step 10/11、3×3 操作合同、Task 42/43、可靠性 follow-on、产品硬化

## 0. 定位

Task 25 Step 10 付费 3×3 **未开跑**。Node 修好副本预检：`typecheck:chat=0`，`test:chat=1`，`build:chat=1`。根因见 `docs/task-evidence/phase-2d-task-9-step-10.md` §5a：entrypoint 把只读 `/opt/sandbox/node_modules` **整目录**链到 `/workspace/node_modules`，容器 `--read-only`，Vite 无法 `mkdir /workspace/node_modules/.vite-temp`。

这是 **harness blocker**，不是模型失败。本计划只有 **一个** Task。

用户可见 **Task 44**；稳定 ID **`phase-2d-task-28`**。Evidence：`docs/task-evidence/phase-2d-task-28.md`。Task 44 / `phase-2d-task-28` 已于 2026-09-08 由用户确认验收通过（targeted）；见 evidence §9。

## 1. 锁定方案（不要再让执行人挑选）

**不要**整包 `cp -a` 进 `/workspace` tmpfs（512 MiB 上限，Chat/Vite 依赖树会撑爆）。  
**不要**把本 Task 做成「只设 `VITE_CACHE_DIR` / 改夹具 cacheDir」（治标，其它工具仍可能往 `node_modules/` 写）。

锁定为 **可写目录 + 包级符号链接**：

1. `/opt/sandbox/node_modules` 留在镜像里，保持只读。
2. `/workspace/node_modules` 必须是 tmpfs 上的**真实目录**，不得是指向 store 的符号链接。
3. 把 store 里的每个条目（含 `.bin` 等点文件）`ln -s` 进该目录。包内容仍只读；Vite 的 `.vite-temp` / `.vite` 作为**新子目录**落在可写父目录上。
4. 项目夹具仍不带 `node_modules`，仍禁止 `npm install`。
5. Docker 运行时标志不变：`--network none`、`--read-only`、`--user 65532:65532`、`--tmpfs /workspace` 512 MiB、`--pull never`。
6. 不放宽 Policy、gate_id、任意 Shell、网络。

entrypoint 仅在 `SANDBOX_NODE_MODULES` 非空时走上述逻辑（Node 镜像）。Python 镜像不设该环境变量，行为与现在一致。本 Task **只重建 Node 镜像**，不重建 Python / Phase 2C patch 镜像。

POSIX 约束（与现有 `test_entrypoint_and_build_context` 一致）：保留 `exec "$@"`；禁止 `eval`、`sh -c`；禁止 `cp -a "$SANDBOX_NODE_MODULES"`。用 `for` + `ln -s` + `basename`，不要解释 argv。

## 2. 重建与 pin

entrypoint 打进 Node 镜像，**必须**本地重建，否则 Chat 仍跑旧入口。

授权范围（仅本 Task，需用户把 executor prompt 贴进新会话后才执行）：

```powershell
docker build --pull=false -f docker/agent-sandbox-node.Dockerfile -t agent-foundations-sandbox-node:phase2d .
```

禁止：`docker pull`、`docker prune`、改 `package.json` / `package-lock.json`、改 Node 基础镜像 digest、改 Dockerfile 里的 `lockfile-sha256` LABEL（仍等于 `package-lock.json` 的 sha256）。

重建后 **只改 pin 的 Node `final_*`**：

1. `docker image inspect agent-foundations-sandbox-node:phase2d --format "{{.Id}}"`
2. `docker image inspect agent-foundations-sandbox-node:phase2d --format "{{index .RepoDigests 0}}"`（若为空，沿用 Task 17 惯例：`agent-foundations-sandbox-node@<Id>`，Id 含 `sha256:` 前缀）
3. 写入 `docker/sandbox-manifest.phase2d.json` 的 `node.final_image_id` 与 `node.final_repo_digest`
4. **不要**改 `node.lockfile_sha256`、`node.base_repo_digest`、整个 `python` 对象
5. 同步 `tests/unit/execution/test_sandbox_manifest.py` 的 `_PINNED_NODE_IMAGE_ID`（该测试写死了旧 `eb349e91…`）
6. 复验：inspect 的 Id **等于**新 pin，且 **不等于**旧 `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21`

Chat 继续 `SandboxManifest.load_pinned`；禁止运行时用 inspect 覆盖 pin。

## 3. Task 44 / `phase-2d-task-28`：Node sandbox 可写 node_modules 父目录

### Goal

在现有 Node 安全边界下，修好的虚构 TypeScript 夹具执行 exact `npm run test:chat` / `typecheck:chat` / `build:chat` 退出码均为 0。镜像依赖保持只读；夹具不带 `node_modules`；禁止 install/网络/Shell。

### TDD

required。

Red 必须在改 `sandbox-entrypoint.sh` **之前**跑，且因「整目录 symlink → 不可写 cache」或「脚本仍是根 symlink」而失败，不是语法/导入错误。

1. **单元 Red（无 Docker）：** 新测试读取 `docker/sandbox-entrypoint.sh`，断言：
   - 不存在把 `"$SANDBOX_NODE_MODULES"` **作为** `/workspace/node_modules` 的整目录 `ln -s`
   - 当 `SANDBOX_NODE_MODULES` 非空时：`mkdir` 真实 `/workspace/node_modules`，并对 store 子项（含点文件/`.bin`）`ln -s`
   - 仍有 `exec "$@"`；无 `eval`；无 `sh -c`；无把 store `cp -a` 进 workspace
2. **Docker 行为 Red（改入口前，对当前已 pin 的旧 Node 镜像）：** 用修好夹具 + 与 3×3 预检相同的 `--read-only` / `--network none` / tmpfs 标志跑 `npm run test:chat`（或 `build:chat`），预期非 0，输出含 `node_modules/.vite-temp` / `ENOENT` / `Read-only file system` 一类。把命令、退出码、关键原文写入本 Task evidence。不要把 `phase-2d-task-9-step-10.md` 的旧输出冒充本 Task 的 Red；必须本会话重跑。

然后改 entrypoint → 只重建 Node 镜像 → 更新 pin → Green。

### Files

允许修改：

- `docker/sandbox-entrypoint.sh`
- `docker/sandbox-manifest.phase2d.json`（仅 `node.final_image_id` / `node.final_repo_digest`）
- `docker/README.md`（一段：Node 用包级 symlink，不整包拷贝；重建 Node 后必须更新 pin）
- `tests/unit/execution/test_sandbox_manifest.py`（`_PINNED_NODE_IMAGE_ID`）
- `tests/unit/execution/test_docker.py`（仅当现有 entrypoint 断言与新脚本冲突时做最小对齐；不得删掉 `exec "$@"` / 禁止 `eval` / `sh -c` / dockerignore 固定列表）
- 允许新增：`tests/unit/execution/test_sandbox_entrypoint.py`
- 允许新增：`tests/fixtures/phase2_node_sandbox_project/`（**修好**的 3×3 Node 夹具：`add` 返回 `left + right`，测试期望 `2`；`package.json` scripts 必须是 exact `test:chat` / `typecheck:chat` / `build:chat`；无 `node_modules`）
- 允许新增：`tests/integration/test_node_sandbox_gates.py`（`@pytest.mark.docker`；skip 除非 `-m docker`）
- `docs/task-evidence/phase-2d-task-28.md`
- 本计划勾选；Phase 2 计划附录指针；3×3 操作合同里 Node pin 的过时硬编码改为「以 pin 文件为准」

禁止：

- `docker/agent-sandbox-node.Dockerfile`（不改基础 digest、LABEL lock、`npm ci`）
- `docker/agent-sandbox-python.Dockerfile`、Python pin、Phase 2C patch 镜像
- `package.json`、`package-lock.json`、`web/chat/**`、Chat 静态包、Task 42/43 代码
- Policy / Approval / `gate_id` / `DockerCommandBuilder` 安全标志（不得去掉 `--read-only` / `--network none`）
- 用环境变量或夹具 `cacheDir` 代替本方案
- 付费 3×3、开 Chat、勾选 Step 10/11、修其它 P3、commit/push

回退：还原本 Task 文件；Node 镜像若已重建，记录新旧 Id，**不要** `docker prune`。保留脏工作区。

### 验证合同

```text
Target tests：
  conda/agent-foundations：
  python -m pytest tests/unit/execution/test_sandbox_entrypoint.py tests/unit/execution/test_docker.py::test_entrypoint_and_build_context tests/unit/execution/test_sandbox_manifest.py -q
Affected regression tests：
  python -m pytest tests/unit/execution/test_docker.py tests/unit/execution/test_sandbox_manifest.py tests/unit/tools/command/test_gate_expand.py tests/unit/tools/command/test_classifier.py -q
Full suite：not-required
Full suite reason：只改 Node entrypoint 与 Node final pin；不扩大 Tool/权限；Python pin 与 Policy 不变。完整基线仍属 Task 25 Step 11。
Additional gates：
  1. 本 Task 授权的 Node docker build（--pull=false）
  2. inspect Id/RepoDigest 写入 pin 后与 pin 一致；旧 eb349e91… 不再匹配
  3. python pin 未改；node.lockfile_sha256 仍等于 package-lock.json sha256
  4. pytest -m docker tests/integration/test_node_sandbox_gates.py
     修好夹具三门 exit 0；node_modules 为目录非根 symlink；.bin 为 symlink；
     touch /opt/sandbox/node_modules/.vite-temp-probe → 只读失败；
     禁止在测试里 npm install 或 --network 非 none
  5. 受影响文件 ruff + mypy strict
  6. git diff --check
```

Windows：`$env:PYTHONIOENCODING='utf-8'`；`D:\anaconda\envs\agent-foundations\python.exe`。不要用会 GBK 崩掉的裸 `conda run` 当主路径。

Docker 集成测试优先走 `DockerBackend` + 生产 pin（snapshot / `--read-only` / tmpfs），超时至少 120s。不要手写一套更松的 `docker run`。

### 完成条件

- [x] 单元测试证明 entrypoint 不再根 symlink store
- [x] 本 Task 的 Docker Red 已保存，随后 Green：修好夹具三门 exit 0
- [x] Node 新 `final_image_id` 已 pin，inspect 复验一致；Python pin 未动
- [x] 镜像 store 仍只读；无整包拷贝；无 npm install；无网络；无放宽 Policy
- [x] evidence 完整；未勾选 Task 25 Step 10/11；未声称 3×3 或 Phase 2 完成
- [x] 未 commit / push

### Steps

- [x] **Step 1:** 从模板创建 `docs/task-evidence/phase-2d-task-28.md`，记录 `git status` 与脏树必须保留
- [x] **Step 2:** 写单元测试并跑 Red（entrypoint 仍是根 symlink）
- [x] **Step 3:** 用当前 pin 的旧 Node 镜像对修好夹具跑 `test:chat` 或 `build:chat`，保存 Docker 行为 Red
- [x] **Step 4:** 改 `docker/sandbox-entrypoint.sh` 为目录 + 包级 symlink
- [x] **Step 5:** 重建 Node 镜像；inspect；只更新 Node `final_*` 与 `_PINNED_NODE_IMAGE_ID`
- [x] **Step 6:** Green：Target 单元测试 + `-m docker` 三门 0 + 只读探针
- [x] **Step 7:** Affected + ruff + mypy + `git diff --check`；完成 evidence；**停止**（不要开 3×3）

**Suggested commit after explicit authorization:** `fix: overlay sandbox node_modules so vite can write caches`

---

本计划无 Task 45。完成后停止。付费 3×3 仍须另授权，走 Task 25 Step 10，并改用**新** Node pin 做预检。

**User acceptance:** 2026-09-08 用户确认 `确认「Task 44 / phase-2d-task-28 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-28.md` §9。范围仅限 Node entrypoint 可写 `/workspace/node_modules` 父目录 + store 条目级 symlink（含 `.bin`）、Node 分支 `TMPDIR=/workspace/.sandbox-tmp`、只重建 Node 镜像并更新 `node.final_*` / `_PINNED_NODE_IMAGE_ID`。未改 Node Dockerfile、Python pin、`package-lock`、Policy、`gate_id`、Docker 安全标志、Chat UI。独立复验为 targeted：Target 20 passed；Affected 86 passed；`pytest -m docker` 4 passed；inspect 与 pin `sha256:12f2470f314aae00f8757a313d78da471472984f7d039bdfdf1c57a553cfc0e7` 一致；python pin `730aea0a…` 未改。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（单元测试读脚本文本；旧 `eb349e91…` 镜像可能仍在本地；`TMPDIR` 占用 workspace tmpfs）不因本次确认要求立即返工。本确认不是计划正文 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。本计划无 Task 45。未授权 commit、push、付费 3×3 或 Phase 3。
