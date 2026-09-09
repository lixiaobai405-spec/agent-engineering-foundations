# Task Evidence: phase-2d-task-1

## 1. Identity

- Task ID: `phase-2d-task-1`
- Authoritative plan or task spec: Task 17 in `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` plus the user-confirmed executor prompt dated 2026-08-13
- Evidence status: user-accepted / targeted verification and authorized Docker smoke pass
- TDD required: yes
- Started at: 2026-08-13 16:34:11 +08:00 (Asia/Shanghai)
- Dependency: Phase 2C user-accepted; `docs/task-evidence/phase-2c-task-5.md` records `Task 16 验收通过`

## 2. Pre-change Snapshot

- Branch: `codex/phase-2-next`
- Initial `git diff --check`: exit `0`
- Docker read-only availability:
  - `docker version`: exit `0`; Docker Desktop 4.74.0, Engine 29.4.3
  - `docker image inspect python:3.12-slim-bookworm`: exit `0`; RepoDigest `python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2`
  - `docker image inspect agent-foundations-sandbox:phase2`: exit `0`; image ID `sha256:3b692a84c818d01499182604da38379fe36a5ee73792c87ebef60a078effcf42`
- Docker/network mutation authorization at pre-change time: not granted. It was later granted explicitly by the user on 2026-08-26 under the restricted scope recorded in section 8.
- Existing user changes that must be preserved: all Task 15/16 tracked and untracked changes, the retained current Chat build assets, `.agents/`, and `.gate-backup/`.
- Explicitly protected overlap: `src/agent_foundations/execution/container_runner.py` is already modified and must not be edited.
- Task 17 target-path overlap audit:
  - all planned new command/workspace/sandbox-manifest/test files are absent;
  - `src/agent_foundations/execution/models.py`, `src/agent_foundations/execution/docker.py`, `docker/agent-sandbox.Dockerfile`, `docker/README.md`, `.dockerignore`, `pyproject.toml`, and allowed existing tests are present and clean;
  - no unrecognized Task 17 overlap was found.
- Intended modification scope: only the user-listed Task 17 files, this evidence file, and Task 17 Step 1-8 checkboxes when actually satisfied.
- Expected rollback: remove only Task 17-created files and reverse only Task 17 hunks in allowed modified files. Do not use `git reset`, `git restore`, `git checkout --`, or `git clean`; do not touch accepted Task 15/16 changes or Chat hashed assets.
- Worktree decision: remain on the existing non-main branch because accepted prerequisite state exists only in this dirty checkout; a new clean worktree would omit it.

### Complete initial `git status --short --branch`

```text
## codex/phase-2-next
 M docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
 M src/agent_foundations/chat/api.py
 M src/agent_foundations/chat/events.py
 M src/agent_foundations/chat/models.py
 M src/agent_foundations/chat/repository.py
 M src/agent_foundations/chat/runner.py
 M src/agent_foundations/chat/schema.py
 M src/agent_foundations/chat/tool_execution.py
 M src/agent_foundations/cli/main.py
 M src/agent_foundations/execution/container_runner.py
 M src/agent_foundations/runtime/tool_execution.py
 M src/agent_foundations/storage/migrations.py
 D src/agent_foundations/viewer/static/chat/assets/angular-html-Br9IDCc2.js
 D src/agent_foundations/viewer/static/chat/assets/angular-ts-CBiFgP06.js
 D src/agent_foundations/viewer/static/chat/assets/apl-MbI41U1o.js
 D src/agent_foundations/viewer/static/chat/assets/astro-CqTitrHt.js
 D src/agent_foundations/viewer/static/chat/assets/blade-Bjdrv9Mo.js
 D src/agent_foundations/viewer/static/chat/assets/c-CE7AOLh2.js
 D src/agent_foundations/viewer/static/chat/assets/chapel-BLJAosYf.js
 D src/agent_foundations/viewer/static/chat/assets/cobol-auvo_Xn8.js
 D src/agent_foundations/viewer/static/chat/assets/coffee-CixWl31r.js
 D src/agent_foundations/viewer/static/chat/assets/cpp-jRGy5cB4.js
 D src/agent_foundations/viewer/static/chat/assets/crystal-DRBJvzve.js
 D src/agent_foundations/viewer/static/chat/assets/css-DABI0tYP.js
 D src/agent_foundations/viewer/static/chat/assets/dist-T1nCZiDI.js
 D src/agent_foundations/viewer/static/chat/assets/edge-G1HpqmlR.js
 D src/agent_foundations/viewer/static/chat/assets/elixir-Ci1pRWE1.js
 D src/agent_foundations/viewer/static/chat/assets/elm-BEcS-2QS.js
 D src/agent_foundations/viewer/static/chat/assets/erb-CVcTjrey.js
 D src/agent_foundations/viewer/static/chat/assets/git-rebase-CrxUNPrW.js
 D src/agent_foundations/viewer/static/chat/assets/glimmer-js-CMYWrGPd.js
 D src/agent_foundations/viewer/static/chat/assets/glimmer-ts-BwiEgHjR.js
 D src/agent_foundations/viewer/static/chat/assets/glsl-BYth7iN7.js
 D src/agent_foundations/viewer/static/chat/assets/graphql-COrGf1zq.js
 D src/agent_foundations/viewer/static/chat/assets/hack-BK2UJF3D.js
 D src/agent_foundations/viewer/static/chat/assets/haml-ZST33X7G.js
 D src/agent_foundations/viewer/static/chat/assets/handlebars-DnaYoJE3.js
 D src/agent_foundations/viewer/static/chat/assets/html-BvdJQemT.js
 D src/agent_foundations/viewer/static/chat/assets/html-derivative-B0KJsSKd.js
 D src/agent_foundations/viewer/static/chat/assets/http-D_uLoRf9.js
 D src/agent_foundations/viewer/static/chat/assets/hurl-ChUpJhJC.js
 D src/agent_foundations/viewer/static/chat/assets/index-BsLxeqKM.js
 D src/agent_foundations/viewer/static/chat/assets/java-BqlL-K6q.js
 D src/agent_foundations/viewer/static/chat/assets/javascript-BEBSv_Zu.js
 D src/agent_foundations/viewer/static/chat/assets/jinja-CjiB-k_t.js
 D src/agent_foundations/viewer/static/chat/assets/jison-CppSe3Os.js
 D src/agent_foundations/viewer/static/chat/assets/json-Bs8O13pM.js
 D src/agent_foundations/viewer/static/chat/assets/jsx-C9djHW19.js
 D src/agent_foundations/viewer/static/chat/assets/julia-BJmFFGWo.js
 D src/agent_foundations/viewer/static/chat/assets/just-CUC0FeKS.js
 D src/agent_foundations/viewer/static/chat/assets/latex-CyLHBWGd.js
 D src/agent_foundations/viewer/static/chat/assets/liquid-WdIQIGUe.js
 D src/agent_foundations/viewer/static/chat/assets/lua-CwnwSu3U.js
 D src/agent_foundations/viewer/static/chat/assets/marko-CAJ0MAon.js
 D src/agent_foundations/viewer/static/chat/assets/mdc-DVaF0f0u.js
 D src/agent_foundations/viewer/static/chat/assets/nginx-CksSLgO4.js
 D src/agent_foundations/viewer/static/chat/assets/nim-CyEMrrnJ.js
 D src/agent_foundations/viewer/static/chat/assets/org-CIu6kNHi.js
 D src/agent_foundations/viewer/static/chat/assets/perl-Ppy8Vkit.js
 D src/agent_foundations/viewer/static/chat/assets/php-DwoN-K_8.js
 D src/agent_foundations/viewer/static/chat/assets/pug-CFZhbxnR.js
 D src/agent_foundations/viewer/static/chat/assets/qml-Cwcp2WY7.js
 D src/agent_foundations/viewer/static/chat/assets/r-Kcu3-vsT.js
 D src/agent_foundations/viewer/static/chat/assets/razor-Dd6U0Dby.js
 D src/agent_foundations/viewer/static/chat/assets/regexp-BJ5uTFvs.js
 D src/agent_foundations/viewer/static/chat/assets/rst-zJDd_Jph.js
 D src/agent_foundations/viewer/static/chat/assets/ruby-BJidHcND.js
 D src/agent_foundations/viewer/static/chat/assets/sas-ZhLpzvbj.js
 D src/agent_foundations/viewer/static/chat/assets/scss-Cq1YI9D7.js
 D src/agent_foundations/viewer/static/chat/assets/shellscript-Cy3YwgyF.js
 D src/agent_foundations/viewer/static/chat/assets/shellsession-DvBYlWyu.js
 D src/agent_foundations/viewer/static/chat/assets/soy-Gke3uJGT.js
 D src/agent_foundations/viewer/static/chat/assets/sql-Bi0CZRPR.js
 D src/agent_foundations/viewer/static/chat/assets/stata-DaYTtn--.js
 D src/agent_foundations/viewer/static/chat/assets/surrealql-C1I4VpCG.js
 D src/agent_foundations/viewer/static/chat/assets/svelte-0ET6s8oV.js
 D src/agent_foundations/viewer/static/chat/assets/templ-Dpdsh1BB.js
 D src/agent_foundations/viewer/static/chat/assets/tex-CzRMFehr.js
 D src/agent_foundations/viewer/static/chat/assets/ts-tags-_eY3elFp.js
 D src/agent_foundations/viewer/static/chat/assets/tsx-DAcI0J79.js
 D src/agent_foundations/viewer/static/chat/assets/twig-CfJR_zFX.js
 D src/agent_foundations/viewer/static/chat/assets/typescript-B7Bj2GLz.js
 D src/agent_foundations/viewer/static/chat/assets/vue-8LHzWmOV.js
 D src/agent_foundations/viewer/static/chat/assets/vue-html-Bc2_oPo7.js
 D src/agent_foundations/viewer/static/chat/assets/vue-vine-Zp3nHzTE.js
 D src/agent_foundations/viewer/static/chat/assets/xml-COe5uDfI.js
 D src/agent_foundations/viewer/static/chat/assets/xsl-sUzUQRhv.js
 D src/agent_foundations/viewer/static/chat/assets/yaml-D4wLN2eH.js
 M src/agent_foundations/viewer/static/chat/index.html
 M tests/chat/app.test.tsx
 M tests/chat/reducer.test.ts
 M tests/e2e/test_chat_ui.py
 M tests/integration/test_chat_api.py
 M tests/integration/test_chat_approval_flow.py
 M tests/unit/chat/test_repository.py
 M tests/unit/chat/test_tool_execution.py
 M tests/unit/durable/test_effects.py
 M tests/unit/durable/test_repository.py
 M tests/unit/security/test_repository.py
 M tests/unit/storage/test_database.py
 M tests/unit/tools/patch/test_repository.py
 M web/chat/App.tsx
 M web/chat/components/ApprovalCard.tsx
 M web/chat/components/ConversationList.tsx
 M web/chat/state/reducer.ts
 M web/chat/state/types.ts
?? .agents/
?? .gate-backup/
?? docs/task-evidence/phase-2c-task-4.md
?? docs/task-evidence/phase-2c-task-5.md
?? src/agent_foundations/tools/patch/applier.py
?? src/agent_foundations/tools/patch/apply_patch.py
?? src/agent_foundations/viewer/static/chat/assets/angular-html-DX66NJo7.js
?? src/agent_foundations/viewer/static/chat/assets/angular-ts-DTNc-ed2.js
?? src/agent_foundations/viewer/static/chat/assets/apl-hpff1rlF.js
?? src/agent_foundations/viewer/static/chat/assets/astro-Y5P8Bv0U.js
?? src/agent_foundations/viewer/static/chat/assets/blade-DgFv9E3z.js
?? src/agent_foundations/viewer/static/chat/assets/c-BwiyrKZ1.js
?? src/agent_foundations/viewer/static/chat/assets/chapel-DVQAz2vG.js
?? src/agent_foundations/viewer/static/chat/assets/cobol-fLVVOb9Z.js
?? src/agent_foundations/viewer/static/chat/assets/coffee-Dst4G5rk.js
?? src/agent_foundations/viewer/static/chat/assets/cpp-DZypZBB4.js
?? src/agent_foundations/viewer/static/chat/assets/crystal-BYcveLEY.js
?? src/agent_foundations/viewer/static/chat/assets/css-DYlV1atn.js
?? src/agent_foundations/viewer/static/chat/assets/dist-B-P1qZiO.js
?? src/agent_foundations/viewer/static/chat/assets/edge-C-D6nw8R.js
?? src/agent_foundations/viewer/static/chat/assets/elixir-Bjvj1-A-.js
?? src/agent_foundations/viewer/static/chat/assets/elm-BMeJPZxf.js
?? src/agent_foundations/viewer/static/chat/assets/erb-BQ_OL3mf.js
?? src/agent_foundations/viewer/static/chat/assets/git-rebase-CYHGjVWD.js
?? src/agent_foundations/viewer/static/chat/assets/glimmer-js-CqWmZ7C-.js
?? src/agent_foundations/viewer/static/chat/assets/glimmer-ts-BtnV7dTa.js
?? src/agent_foundations/viewer/static/chat/assets/glsl-C1jie91L.js
?? src/agent_foundations/viewer/static/chat/assets/graphql-DxxEZ2NU.js
?? src/agent_foundations/viewer/static/chat/assets/hack-D5j8yVpm.js
?? src/agent_foundations/viewer/static/chat/assets/haml-BqPNoNp8.js
?? src/agent_foundations/viewer/static/chat/assets/handlebars-BRPqLVo2.js
?? src/agent_foundations/viewer/static/chat/assets/html-Db0ojM8h.js
?? src/agent_foundations/viewer/static/chat/assets/html-derivative-Dp5HEBIw.js
?? src/agent_foundations/viewer/static/chat/assets/http-ClI2lKdr.js
?? src/agent_foundations/viewer/static/chat/assets/hurl-D6RYnYK5.js
?? src/agent_foundations/viewer/static/chat/assets/index-BeeIJ38N.js
?? src/agent_foundations/viewer/static/chat/assets/java-DWM_gFzP.js
?? src/agent_foundations/viewer/static/chat/assets/javascript-DvdDbDs0.js
?? src/agent_foundations/viewer/static/chat/assets/jinja-D81tZGwy.js
?? src/agent_foundations/viewer/static/chat/assets/jison-ZfxHLlyR.js
?? src/agent_foundations/viewer/static/chat/assets/json-CkiVNMUh.js
?? src/agent_foundations/viewer/static/chat/assets/jsx-CAtXgjoA.js
?? src/agent_foundations/viewer/static/chat/assets/julia-sXI5BdNn.js
?? src/agent_foundations/viewer/static/chat/assets/just-BpuKaJXF.js
?? src/agent_foundations/viewer/static/chat/assets/latex-Cxl6MNJk.js
?? src/agent_foundations/viewer/static/chat/assets/liquid-B0nBQgLO.js
?? src/agent_foundations/viewer/static/chat/assets/lua-jJ5cdDlB.js
?? src/agent_foundations/viewer/static/chat/assets/marko-ZP8Lyn5t.js
?? src/agent_foundations/viewer/static/chat/assets/mdc-eBGnSaaW.js
?? src/agent_foundations/viewer/static/chat/assets/nginx-myGcHUC7.js
?? src/agent_foundations/viewer/static/chat/assets/nim-Dm0l7Tym.js
?? src/agent_foundations/viewer/static/chat/assets/org-DozJs11C.js
?? src/agent_foundations/viewer/static/chat/assets/perl-9OQ-6rF1.js
?? src/agent_foundations/viewer/static/chat/assets/php-BXV0xfJa.js
?? src/agent_foundations/viewer/static/chat/assets/pug-DErnqTNv.js
?? src/agent_foundations/viewer/static/chat/assets/qml-NEStOoow.js
?? src/agent_foundations/viewer/static/chat/assets/r-DHYo0EN7.js
?? src/agent_foundations/viewer/static/chat/assets/razor-3TBqjQGQ.js
?? src/agent_foundations/viewer/static/chat/assets/regexp-Bfc7aK7v.js
?? src/agent_foundations/viewer/static/chat/assets/rst-DZR07Av7.js
?? src/agent_foundations/viewer/static/chat/assets/ruby-Cg7E9A9j.js
?? src/agent_foundations/viewer/static/chat/assets/sas-B9slQVam.js
?? src/agent_foundations/viewer/static/chat/assets/scss-Bs9dsWFJ.js
?? src/agent_foundations/viewer/static/chat/assets/shellscript-DjZHfken.js
?? src/agent_foundations/viewer/static/chat/assets/shellsession-BrHn-pj1.js
?? src/agent_foundations/viewer/static/chat/assets/soy-NTN8Rw7S.js
?? src/agent_foundations/viewer/static/chat/assets/sql-DYkC7VHC.js
?? src/agent_foundations/viewer/static/chat/assets/stata-CRWslQ7o.js
?? src/agent_foundations/viewer/static/chat/assets/surrealql-be1lms5W.js
?? src/agent_foundations/viewer/static/chat/assets/svelte-nI69MEgH.js
?? src/agent_foundations/viewer/static/chat/assets/templ-WAIFdMIJ.js
?? src/agent_foundations/viewer/static/chat/assets/tex-d7-y5A93.js
?? src/agent_foundations/viewer/static/chat/assets/ts-tags-D3sXTMRZ.js
?? src/agent_foundations/viewer/static/chat/assets/tsx-DU1ioWfL.js
?? src/agent_foundations/viewer/static/chat/assets/twig-aDJ5SS-T.js
?? src/agent_foundations/viewer/static/chat/assets/typescript-CR57bNZN.js
?? src/agent_foundations/viewer/static/chat/assets/vue-C_lXSmWX.js
?? src/agent_foundations/viewer/static/chat/assets/vue-html-D9xQYCv8.js
?? src/agent_foundations/viewer/static/chat/assets/vue-vine-DTIaWE6t.js
?? src/agent_foundations/viewer/static/chat/assets/xml-A3qsBl1e.js
?? src/agent_foundations/viewer/static/chat/assets/xsl-B73jH7Ha.js
?? src/agent_foundations/viewer/static/chat/assets/yaml-L3QH9keI.js
?? tests/chat/patch-preview.test.tsx
?? tests/chat/permission-profile.test.tsx
?? tests/fixtures/evals/phase-2c-permission-profiles-v1.json
?? tests/integration/test_controlled_patch_flow.py
?? tests/integration/test_patch_crash_recovery.py
?? tests/integration/test_phase2c_profile_eval.py
?? tests/integration/test_task16_production_wiring.py
?? tests/unit/tools/patch/test_applier.py
?? tests/unit/tools/patch/test_apply_patch.py
?? web/chat/components/PatchPreviewCard.tsx
?? web/chat/components/PermissionProfileSelect.tsx
```

### Complete initial tracked `git diff --name-status`

```text
M	docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
M	src/agent_foundations/chat/api.py
M	src/agent_foundations/chat/events.py
M	src/agent_foundations/chat/models.py
M	src/agent_foundations/chat/repository.py
M	src/agent_foundations/chat/runner.py
M	src/agent_foundations/chat/schema.py
M	src/agent_foundations/chat/tool_execution.py
M	src/agent_foundations/cli/main.py
M	src/agent_foundations/execution/container_runner.py
M	src/agent_foundations/runtime/tool_execution.py
M	src/agent_foundations/storage/migrations.py
D	src/agent_foundations/viewer/static/chat/assets/angular-html-Br9IDCc2.js
D	src/agent_foundations/viewer/static/chat/assets/angular-ts-CBiFgP06.js
D	src/agent_foundations/viewer/static/chat/assets/apl-MbI41U1o.js
D	src/agent_foundations/viewer/static/chat/assets/astro-CqTitrHt.js
D	src/agent_foundations/viewer/static/chat/assets/blade-Bjdrv9Mo.js
D	src/agent_foundations/viewer/static/chat/assets/c-CE7AOLh2.js
D	src/agent_foundations/viewer/static/chat/assets/chapel-BLJAosYf.js
D	src/agent_foundations/viewer/static/chat/assets/cobol-auvo_Xn8.js
D	src/agent_foundations/viewer/static/chat/assets/coffee-CixWl31r.js
D	src/agent_foundations/viewer/static/chat/assets/cpp-jRGy5cB4.js
D	src/agent_foundations/viewer/static/chat/assets/crystal-DRBJvzve.js
D	src/agent_foundations/viewer/static/chat/assets/css-DABI0tYP.js
D	src/agent_foundations/viewer/static/chat/assets/dist-T1nCZiDI.js
D	src/agent_foundations/viewer/static/chat/assets/edge-G1HpqmlR.js
D	src/agent_foundations/viewer/static/chat/assets/elixir-Ci1pRWE1.js
D	src/agent_foundations/viewer/static/chat/assets/elm-BEcS-2QS.js
D	src/agent_foundations/viewer/static/chat/assets/erb-CVcTjrey.js
D	src/agent_foundations/viewer/static/chat/assets/git-rebase-CrxUNPrW.js
D	src/agent_foundations/viewer/static/chat/assets/glimmer-js-CMYWrGPd.js
D	src/agent_foundations/viewer/static/chat/assets/glimmer-ts-BwiEgHjR.js
D	src/agent_foundations/viewer/static/chat/assets/glsl-BYth7iN7.js
D	src/agent_foundations/viewer/static/chat/assets/graphql-COrGf1zq.js
D	src/agent_foundations/viewer/static/chat/assets/hack-BK2UJF3D.js
D	src/agent_foundations/viewer/static/chat/assets/haml-ZST33X7G.js
D	src/agent_foundations/viewer/static/chat/assets/handlebars-DnaYoJE3.js
D	src/agent_foundations/viewer/static/chat/assets/html-BvdJQemT.js
D	src/agent_foundations/viewer/static/chat/assets/html-derivative-B0KJsSKd.js
D	src/agent_foundations/viewer/static/chat/assets/http-D_uLoRf9.js
D	src/agent_foundations/viewer/static/chat/assets/hurl-ChUpJhJC.js
D	src/agent_foundations/viewer/static/chat/assets/index-BsLxeqKM.js
D	src/agent_foundations/viewer/static/chat/assets/java-BqlL-K6q.js
D	src/agent_foundations/viewer/static/chat/assets/javascript-BEBSv_Zu.js
D	src/agent_foundations/viewer/static/chat/assets/jinja-CjiB-k_t.js
D	src/agent_foundations/viewer/static/chat/assets/jison-CppSe3Os.js
D	src/agent_foundations/viewer/static/chat/assets/json-Bs8O13pM.js
D	src/agent_foundations/viewer/static/chat/assets/jsx-C9djHW19.js
D	src/agent_foundations/viewer/static/chat/assets/julia-BJmFFGWo.js
D	src/agent_foundations/viewer/static/chat/assets/just-CUC0FeKS.js
D	src/agent_foundations/viewer/static/chat/assets/latex-CyLHBWGd.js
D	src/agent_foundations/viewer/static/chat/assets/liquid-WdIQIGUe.js
D	src/agent_foundations/viewer/static/chat/assets/lua-CwnwSu3U.js
D	src/agent_foundations/viewer/static/chat/assets/marko-CAJ0MAon.js
D	src/agent_foundations/viewer/static/chat/assets/mdc-DVaF0f0u.js
D	src/agent_foundations/viewer/static/chat/assets/nginx-CksSLgO4.js
D	src/agent_foundations/viewer/static/chat/assets/nim-CyEMrrnJ.js
D	src/agent_foundations/viewer/static/chat/assets/org-CIu6kNHi.js
D	src/agent_foundations/viewer/static/chat/assets/perl-Ppy8Vkit.js
D	src/agent_foundations/viewer/static/chat/assets/php-DwoN-K_8.js
D	src/agent_foundations/viewer/static/chat/assets/pug-CFZhbxnR.js
D	src/agent_foundations/viewer/static/chat/assets/qml-Cwcp2WY7.js
D	src/agent_foundations/viewer/static/chat/assets/r-Kcu3-vsT.js
D	src/agent_foundations/viewer/static/chat/assets/razor-Dd6U0Dby.js
D	src/agent_foundations/viewer/static/chat/assets/regexp-BJ5uTFvs.js
D	src/agent_foundations/viewer/static/chat/assets/rst-zJDd_Jph.js
D	src/agent_foundations/viewer/static/chat/assets/ruby-BJidHcND.js
D	src/agent_foundations/viewer/static/chat/assets/sas-ZhLpzvbj.js
D	src/agent_foundations/viewer/static/chat/assets/scss-Cq1YI9D7.js
D	src/agent_foundations/viewer/static/chat/assets/shellscript-Cy3YwgyF.js
D	src/agent_foundations/viewer/static/chat/assets/shellsession-DvBYlWyu.js
D	src/agent_foundations/viewer/static/chat/assets/soy-Gke3uJGT.js
D	src/agent_foundations/viewer/static/chat/assets/sql-Bi0CZRPR.js
D	src/agent_foundations/viewer/static/chat/assets/stata-DaYTtn--.js
D	src/agent_foundations/viewer/static/chat/assets/surrealql-C1I4VpCG.js
D	src/agent_foundations/viewer/static/chat/assets/svelte-0ET6s8oV.js
D	src/agent_foundations/viewer/static/chat/assets/templ-Dpdsh1BB.js
D	src/agent_foundations/viewer/static/chat/assets/tex-CzRMFehr.js
D	src/agent_foundations/viewer/static/chat/assets/ts-tags-_eY3elFp.js
D	src/agent_foundations/viewer/static/chat/assets/tsx-DAcI0J79.js
D	src/agent_foundations/viewer/static/chat/assets/twig-CfJR_zFX.js
D	src/agent_foundations/viewer/static/chat/assets/typescript-B7Bj2GLz.js
D	src/agent_foundations/viewer/static/chat/assets/vue-8LHzWmOV.js
D	src/agent_foundations/viewer/static/chat/assets/vue-html-Bc2_oPo7.js
D	src/agent_foundations/viewer/static/chat/assets/vue-vine-Zp3nHzTE.js
D	src/agent_foundations/viewer/static/chat/assets/xml-COe5uDfI.js
D	src/agent_foundations/viewer/static/chat/assets/xsl-sUzUQRhv.js
D	src/agent_foundations/viewer/static/chat/assets/yaml-D4wLN2eH.js
M	src/agent_foundations/viewer/static/chat/index.html
M	tests/chat/app.test.tsx
M	tests/chat/reducer.test.ts
M	tests/e2e/test_chat_ui.py
M	tests/integration/test_chat_api.py
M	tests/integration/test_chat_approval_flow.py
M	tests/unit/chat/test_repository.py
M	tests/unit/chat/test_tool_execution.py
M	tests/unit/durable/test_effects.py
M	tests/unit/durable/test_repository.py
M	tests/unit/security/test_repository.py
M	tests/unit/storage/test_database.py
M	tests/unit/tools/patch/test_repository.py
M	web/chat/App.tsx
M	web/chat/components/ApprovalCard.tsx
M	web/chat/components/ConversationList.tsx
M	web/chat/state/reducer.ts
M	web/chat/state/types.ts
warning: in the working copy of 'docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/chat/api.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/chat/events.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/chat/models.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/chat/repository.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/chat/runner.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/chat/schema.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/chat/tool_execution.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/cli/main.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/execution/container_runner.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/runtime/tool_execution.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/storage/migrations.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/agent_foundations/viewer/static/chat/index.html', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/chat/app.test.tsx', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/chat/reducer.test.ts', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/e2e/test_chat_ui.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/integration/test_chat_api.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/integration/test_chat_approval_flow.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/unit/chat/test_repository.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/unit/chat/test_tool_execution.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/unit/durable/test_effects.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/unit/durable/test_repository.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/unit/security/test_repository.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/unit/storage/test_database.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/unit/tools/patch/test_repository.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'web/chat/App.tsx', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'web/chat/components/ApprovalCard.tsx', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'web/chat/components/ConversationList.tsx', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'web/chat/state/reducer.ts', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'web/chat/state/types.ts', LF will be replaced by CRLF the next time Git touches it
```

## 3. Red A: Command Contract

- Recorded before production-code changes: yes
- Time: 2026-08-13 16:37:01 +08:00
- Test files: `tests/unit/tools/command/test_models.py`, `tests/unit/tools/command/test_classifier.py`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/tools/command -q`
- Exit code: `1`
- Relevant verbatim output:

```text
E AssertionError: Task 17 command models are missing
E assert None is not None
E AssertionError: Task 17 command classifier is missing
E assert None is not None
71 failed in 0.76s
RED_A_EXIT=1
```

- Expected failure category: guarded behavioral feature probe; command models and classifier are absent.
- Why this failure demonstrates the missing behavior: pytest collected both test modules normally and every failure was the explicit contract assertion for the absent Task 17 feature. There was no collection, syntax, import, or environment error.
- Invalid preliminary run: the first probe attempted nested `find_spec` before guarding the absent parent package and produced `ModuleNotFoundError` with `71 failed`. It is retained as an invalid test-harness run and is not claimed as Red A. The probe was corrected before any production-code change.

## 4. Green A: Command Contract

- Completed at: 2026-08-13 16:39:24 +08:00
- Production files changed: `src/agent_foundations/tools/command/__init__.py`, `models.py`, `config.py`, `classifier.py`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/tools/command -q`
- Exit code: `0`
- Relevant verbatim output:

```text
.......................................................................  [100%]
71 passed in 0.23s
GREEN_A_EXIT=0
```

- Intermediate Green attempt: `70 passed, 1 failed`; the classifier treated the legal pytest node separator `::` as ADS syntax. The implementation was minimally corrected to split and validate the path and node ID separately; tests were not weakened.

## 5. Red B: Workspace and Sandbox

- Recorded before production-code changes: yes
- Time: 2026-08-13 16:45:11 +08:00
- Test files: `tests/unit/execution/test_workspace.py`, `tests/unit/execution/test_sandbox_manifest.py`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/execution/test_workspace.py tests/unit/execution/test_sandbox_manifest.py -q --tb=line`
- Exit code: `1`
- Relevant verbatim output:

```text
FFFFFFFFFFFFFFFFFFF                                                      [100%]
AssertionError: Task 17 filtered workspace snapshot is missing
AssertionError: Task 17 SandboxManifest is missing
AssertionError: Task 17 fixed sandbox entrypoint is missing
19 failed in 0.22s
RED_B_EXIT=1
```

- Expected failure category: guarded behavioral feature probes for the absent filtered snapshot, SandboxManifest, and fixed entrypoint contracts.
- Why this failure demonstrates the missing behavior: pytest collected both modules normally and all 19 failures were explicit Task 17 feature assertions. There was no collection, syntax, import, or environment error.
- Invalid preliminary run: the first entrypoint probe read the absent file directly and produced one `FileNotFoundError` among the 19 failures. It is retained as an invalid test-harness run and is not claimed as Red B. The probe was corrected before any Workspace/Sandbox production change.

## 6. Green B: Workspace and Sandbox

- Completed at: 2026-08-13 16:50:56 +08:00
- Production files changed: `src/agent_foundations/execution/workspace.py`, `sandbox_manifest.py`, `models.py`, `docker.py`; fixed Dockerfiles, Python lock, entrypoint, `.dockerignore`, `docker/README.md`, and the Docker marker description in `pyproject.toml`.
- Command: `conda run -n agent-foundations python -m pytest tests/unit/execution/test_workspace.py tests/unit/execution/test_sandbox_manifest.py -q`
- Exit code: `0`
- Relevant verbatim output:

```text
...................                                                      [100%]
19 passed in 0.27s
GREEN_B_EXIT=0
```

- Intermediate Green attempt: `18 passed, 1 failed`; the Windows test incorrectly treated an exact snapshot below `%LOCALAPPDATA%\\Temp` as a mount of the whole home directory merely because the path contained the home prefix. The assertion was narrowed to forbid an exact home-root source while requiring the exact snapshot source; the production security boundary was not weakened.

## 7. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `conda run -n agent-foundations python -m pytest tests/unit/tools/command tests/unit/execution/test_workspace.py tests/unit/execution/test_sandbox_manifest.py -q` | 0 | final reviewer-remediation run: `91 passed in 0.36s` |
| Affected regression tests | `conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/execution tests/integration/test_execution_backend.py -q` | 0 | final reviewer-remediation run: `175 passed, 5 skipped in 1.99s`; all five skips are explicitly marked Docker tests and require `-m docker` |
| Ruff | command from the Task 17 prompt over exact affected files | 0 | `All checks passed!` |
| mypy | `conda run -n agent-foundations python -m mypy src/agent_foundations/tools/command src/agent_foundations/execution tests/unit/tools/command tests/unit/execution tests/integration/test_execution_backend.py` | 0 | `Success: no issues found in 22 source files` |
| Package check | `conda run -n agent-foundations python -m pip check` | 0 | `No broken requirements found.` |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors; existing LF/CRLF notices only |

- Full suite: not-required
- Full suite reason: Task 17 defines contracts, filtered snapshots, and fixed image profiles but does not register a command Tool or expand runtime permissions.
- Authorized Docker build/smoke: completed; both fixed images built and the final Docker smoke passed `5 passed, 17 deselected`.
- Authorized restricted network pull/download: completed only for the exact Node base and locked Python/npm dependencies during image builds.

## 8. Contract Matrices

### Command allow/deny matrix

| Input class | Result |
|---|---|
| fixed pytest/Ruff/mypy targets and finite allowed flags | manifest allow with stable rule, Python profile |
| exact `python -m pip check` | manifest allow, package-check category |
| exact five npm scripts | manifest allow with test/typecheck/build category, Node profile |
| `src_evil`, traversal, absolute/drive/UNC/device/ADS, unknown flags or suffix | stable hard deny |
| PowerShell/Bash/cmd/sh, pipeline/redirection/metacharacters | stable hard deny |
| `python -c`, script paths, install, downloader, Git, network tool | stable hard deny |
| project fingerprint drift | `builtin.command.project-fingerprint-mismatch`, hard deny |
| unknown executable | `builtin.command.unknown`, hard deny |

Classifier is pure: it imports no Policy, Approval, or Capability layer and performs no I/O. `ProjectCommandManifest.sandbox` is a required strict `SandboxManifest`; test fixtures use only synthetic format-valid values, never production provenance.

### Workspace exclusion and race matrix

| Boundary | Result |
|---|---|
| regular, PathPolicy-authorized project file | copied to controller temp snapshot, sorted and SHA-256 hashed |
| `.git`, `.env*`, `.agents`, `.gate-backup`, credentials/private keys | excluded before file content is opened |
| symlink, junction/reparse point, dependency/cache/build/log/db/Artifact | excluded |
| source metadata or parent metadata changes during copy | fail closed and exact snapshot discarded |
| file-count, single-file, total-byte limit exceeded | fail closed; no silent omission |
| controller root inside project | rejected |
| snapshot input | exact bind to `/project-ro,readonly` |
| container write layer | `/workspace` tmpfs; source snapshot and host project remain unchanged |
| cleanup | only the verified per-call temp directory below its exact controller root; no prune or broad cleanup |

### Image provenance

- Python base tag: `python:3.12-slim-bookworm`; locally present.
- Python immutable base RepoDigest: `python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2`.
- Node base tag: `node:22-bookworm-slim`; immutable RepoDigest `node@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5`.
- Python lock SHA-256: `54a48d9fe970cea3b27a5488b123660a0b6c73cd68e8462bdac231737b85c531`.
- `package-lock.json` SHA-256: `06c84831ab91e26c98c7ce32291c0e3aac95c97c0287203e5bb292687dbb8d98`.
- Entrypoint SHA-256: `3d9cd9ef22f77913cdf67536cbe75899c9e4f1d937ef804125b834ae757cab0c`.
- Final image tags: `agent-foundations-sandbox-python:phase2d`, `agent-foundations-sandbox-node:phase2d`.
- Python final image ID: `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41`; local RepoDigest `agent-foundations-sandbox-python@sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41`.
- Node final image ID: `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21`; local RepoDigest `agent-foundations-sandbox-node@sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21`.
- Both image labels match their immutable base RepoDigest and exact lock fingerprint. Runtime selects the trusted final image ID through `SandboxManifest`, not an Agent-supplied image/tag.
- The Node Dockerfile now defaults to the inspected immutable RepoDigest. A TDD regression prevents reintroducing an empty or mutable default while still allowing a trusted build-time digest override.
- `.dockerignore` sends exactly the retained Phase 2C Patch Dockerfile, the two Task 17 profile Dockerfiles, fixed entrypoint, Python lock, `package.json`, and `package-lock.json`; source, tests, `.env`, Git, Chat assets, databases, logs, and dirty changes remain outside the daemon context.

### Docker and network authorization checkpoint

- Authorization A (Docker build/run/smoke): granted by the user on 2026-08-26; limited to Task 17 build, image smoke, and exact necessary cleanup.
- Authorization B (restricted pull/download): granted by the user on 2026-08-26; limited to locked base images, the Python lock dependencies, and `package-lock.json` dependencies.
- Initial executor Docker build diagnostics:
  - Python build attempt 1 failed with pip hash mismatch for the locked `jiter==0.16.0` wheel: expected `46add52f...`, received `9c41be15...`.
  - A minimal immutable-base Docker probe then downloaded the same jiter wheel with the correct `46add52f...` hash.
  - Python build attempt 2 failed with a different hash mismatch for the locked `mypy==1.20.2` wheel: expected `a5da6976...`, received `a50d0499...`; an SSL EOF also occurred during that build.
  - No hash checking was disabled and neither package version nor lock content was changed.
- User-provided supplementary network diagnosis (not independently executed by the executor):
  - user changed the system proxy to `127.0.0.1:7890` and reported Docker host/Linux static-proxy confirmation;
  - user ran three exact ephemeral container downloads of locked `jiter==0.16.0` and `mypy==1.20.2`;
  - all 3/3 attempts succeeded, with stable hashes `46add52f4ad47a08bfb1219f3e673da972191489a33016edefdb5ea55bfa8c48` and `a5da6976f20cae27059ea8d0c86e7cef3de720e04c4bb9ee18e3690fdb792066`, and no SSL EOF;
  - this is recorded as user-submitted evidence supporting an external network-state change, not as executor-generated proof.
- Fresh executor read-only check at 2026-08-26 11:36:32 +08:00: Docker Engine `29.4.3`; Docker Desktop reports internal HTTP/HTTPS proxy `http.docker.internal:3128` (the Docker Desktop bridge for its configured host proxy).
- Restricted network targets after B: Docker Hub registry endpoints for `node:22-bookworm-slim`, PyPI/package file registry for exact Python lock dependencies, and npm registry for the existing `package-lock.json`; Dockerfiles contain no downloader or arbitrary URL.
- Daemon impact after A/B: create/cache layers and add/update only the two final Task 17 tags. The existing `agent-foundations-sandbox:phase2` image is retained.
- Host impact: no host package or dependency installation; no real credential access.

### Authorized Docker execution and TDD remediation

The following actions remained within authorization A/B. No host dependency was installed, no credentials were accessed, no image was deleted, and no broad Docker cleanup was used.

| Action | Exit code | Key result |
|---|---:|---|
| `docker pull node:22-bookworm-slim` | 0 | obtained immutable base `node@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5` |
| first Python build | 1 | fail closed: locked jiter hash mismatch; image not accepted |
| second Python build | 1 | fail closed: locked mypy hash mismatch plus SSL EOF; image not accepted |
| final Python build after user proxy diagnosis | 0 | built `agent-foundations-sandbox-python:phase2d`, image ID `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41` |
| initial Node build | 0 | built successfully; BuildKit warned that the Dockerfile's empty ARG default was not independently reproducible |
| Node digest-pin Red | 1 | one assertion failed because `NODE_BASE_IMAGE` had no immutable default |
| Node digest-pin Green | 0 | one test passed after setting the exact inspected RepoDigest default |
| final Node build | 0 | built without the invalid-default warning; image ID `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21` |
| first explicit Docker smoke | 1 | `2 failed, 1 passed, 17 deselected`; Docker exit `125` exposed invalid `--tmpfs` argument syntax |
| tmpfs syntax Red | 1 | exact Docker argv assertion failed against the invalid mount-style value |
| tmpfs syntax Green | 0 | exact unit test passed after changing to Docker's `path:options` syntax |
| live resource/cleanup probes | 0 | `2 passed in 2.99s`; verified live HostConfig limits, cancellation cleanup, real timeout, and exact container removal |
| final fixed-profile Docker smoke | 0 | `5 passed, 17 deselected in 5.28s` |
| controlled Patch Docker regression | 0 | `7 passed, 5 deselected, 7 warnings in 4.46s` |

Final successful build commands:

```powershell
docker pull node:22-bookworm-slim
docker build --pull=false --network=default -f docker/agent-sandbox-python.Dockerfile -t agent-foundations-sandbox-python:phase2d .
docker build --pull=false --network=default -f docker/agent-sandbox-node.Dockerfile -t agent-foundations-sandbox-node:phase2d .
docker image inspect agent-foundations-sandbox-python:phase2d agent-foundations-sandbox-node:phase2d
conda run -n agent-foundations python -m pytest tests/unit/execution/test_sandbox_manifest.py tests/integration/test_execution_backend.py -m docker -q
conda run -n agent-foundations python -m pytest tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -m docker -q
```

Runtime smoke verified both Python 3.12 and Node 22/npm; non-root UID; `NetworkMode=none`; read-only rootfs and `/project-ro`; ephemeral writable `/workspace`; no host-project writeback; dropped capabilities; `no-new-privileges`; PID/CPU/memory limits; real timeout; no Docker socket, host home, conda, venv, host `node_modules`, `.env`, or credentials; and exact cleanup. `docker ps -a --filter name=af-` reported `AF_RESIDUE=none` after the final run. The legacy `agent-foundations-sandbox:phase2` image remains present with ID `sha256:3b692a84c818d01499182604da38379fe36a5ee73792c87ebef60a078effcf42`.

The Node `npm ci` build output reported one high-severity advisory in the already locked dependency graph. Task 17 neither ran `npm audit fix` nor changed `package-lock.json`, because dependency mutation is outside this Task and would violate the locked reproducibility contract.

## 9. Scope Audit

- Final Task 17 files:
  - `.dockerignore`; `docker/README.md`; retained clean tracked `docker/agent-sandbox.Dockerfile`; new Python/Node profile Dockerfiles, Python lock, and entrypoint.
  - `src/agent_foundations/tools/command/__init__.py`, `models.py`, `config.py`, `classifier.py`.
  - `src/agent_foundations/execution/models.py`, `docker.py`, `workspace.py`, `sandbox_manifest.py`.
  - `tests/unit/tools/command/__init__.py`, `test_models.py`, `test_classifier.py`; `tests/unit/execution/test_workspace.py`, `test_sandbox_manifest.py`; authorized minimum addition to `tests/integration/test_execution_backend.py`.
  - `pyproject.toml` Docker marker text; Task 17 Step 1-6 checkboxes; this evidence.
- Unrelated changes introduced: none identified.
- Existing user changes preserved: yes; protected `container_runner.py`, `.agents/`, `.gate-backup/`, all Task 15/16 changes, and old/new Chat hashed assets were not edited, restored, or cleaned by Task 17.
- Secrets or generated artifacts detected: none; no `.env` or credential content was read or copied. The requirements lock is an intentional Task artifact derived from installed package metadata without installation or network access.
- Product boundary audit: no `run_command` Tool implementation or ToolRegistry registration, no AgentLoop/Chat/API/CLI/UI wiring, no Approval/Capability/Policy path, no migration, no host subprocess fallback, and no Task 18 work.
- Commit, push, deployment, paid API call, or next Task performed: none

## 10. Gaps and Limitations

- Checks not run and reasons: the full suite is explicitly `not-required`; no real model, paid API, host installation, or Task 18 command was run because each is outside scope.
- Environment warnings: existing LF/CRLF notices; existing invalid-distribution warning at `pip check`; SQLite datetime deprecation warnings in the controlled Patch Docker regression; one npm advisory in the unchanged lockfile.
- Process evidence gaps: none for the Task 17-required Red/Green, targeted/affected gates, image provenance, or authorized Docker smoke. Independent reviewer verification and user acceptance are intentionally still pending.
- Remaining risk: images and build cache are local Docker daemon state and were retained as authorized. Their future deletion or registry publication was not authorized.

## 11. Handoff Summary

- Updated at: 2026-08-26 11:49:33 +08:00
- Current verification status: pass for the current implementation; targeted, affected, quality, provenance, Docker profile smoke, live limit/timeout, cleanup, and controlled Patch Docker regression all pass. Full suite was not required.
- TDD process evidence: complete for Red A/Green A, Red B/Green B, immutable Node base default, and Docker tmpfs argv remediation.
- Recommended reviewer commands: rerun the Target, Affected, Ruff, mypy, pip-check, and diff-check commands in section 7; independently inspect both image labels/IDs; then run the two explicit `-m docker` commands in section 8. Reviewer should treat the user's 3/3 download diagnosis as supplementary evidence and rely on current image provenance plus fresh probes for acceptance.
- Acceptance boundary at implementation handoff: executor implementation was complete without claiming independent reviewer approval or user acceptance. The later explicit user acceptance is recorded in section 15 and does not itself authorize starting Task 18.

## 12. Reviewer Remediation: Sensitive Snapshot Configuration

- Reviewer finding received: 2026-08-26; current implementation was correctly classified as `fail` because credential-bearing package/registry configuration could enter a snapshot.
- Red recorded before the remediation production change: yes.
- Time: 2026-08-26 12:31:25 +08:00.
- Command: `conda run -n agent-foundations python -m pytest tests/unit/execution/test_workspace.py::test_snapshot_copies_only_regular_non_sensitive_project_files -q`
- Exit code: `1`.
- Key original output:

```text
path = .../project/.config/pip/pip.conf
E AssertionError: excluded sensitive file was opened
1 failed in 0.37s
RED_SENSITIVE_EXIT=1
```

- Root cause: the Task 17 snapshot-specific exclusion matrix covered several credential directories and generic secret names, but did not cover Docker client configuration, pip configuration locations, or the exact common credential filenames `auth.json` and `token.txt`. `PathPolicy` is still applied, but its public file-access rules are intentionally not a complete snapshot scrubber; the missing protection belongs in the stricter snapshot layer.
- Green time: 2026-08-26 12:31:57 +08:00.
- Minimal fix: exclude the `.docker` directory, the directory-segment prefix `.config/pip`, and exact case-insensitive names `pip.conf`, `pip.ini`, `auth.json`, and `token.txt` before opening file contents.
- Green command/result: the same single test exited `0` with `1 passed in 0.22s`; the complete workspace unit file then exited `0` with `8 passed in 0.25s`.

## 13. Reviewer Remediation: Phase 2C Patch Image Rebuild Entry

- Reviewer finding received: 2026-08-26; current Patch Docker regression passed only because the local daemon retained `agent-foundations-sandbox:phase2`, while the repository build file was deleted by the Task 17 rename.
- Red recorded before restoring the Dockerfile/build-context entry: yes.
- Time: 2026-08-26 12:32:47 +08:00.
- Command: `conda run -n agent-foundations python -m pytest tests/unit/execution/test_sandbox_manifest.py::test_entrypoint_and_build_context_are_fixed_and_non_interpreting -q`
- Exit code: `1`.
- Key original output:

```text
E AssertionError: Phase 2C patch sandbox must retain a repository build entrypoint
1 failed in 0.20s
RED_PATCH_REBUILD_EXIT=1
```

- Root cause: Task 17's literal Dockerfile rename removed an artifact still referenced by the non-snapshot `DockerBackend` path. The rename was not semantically valid while Phase 2C controlled Patch remains supported. The user-directed reviewer remediation authorizes retaining the old Patch Dockerfile alongside the two new fixed command-profile Dockerfiles; it does not create a new runtime capability.
- Green time: 2026-08-26 12:33:21 +08:00.
- Minimal fix: restore the original independent Patch Dockerfile, add only that file to the existing deny-all Docker build-context allowlist, document its exact offline rebuild command, and retain the two Task 17 profile Dockerfiles separately.
- Green command/result: the same single test exited `0` with `1 passed in 0.06s`; the complete sandbox-manifest unit file then exited `0` with `12 passed in 0.19s`.
- Fresh repository rebuild: `docker build --pull=false --network=none -f docker/agent-sandbox.Dockerfile -t agent-foundations-sandbox:phase2 .` exited `0`. The base resolved to the already established `python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2`; the resulting local image ID is `sha256:ae7d37eae541b4ead4f60614b25f3fe9f934298c332b2441f31d2ceec37a9569`.
- Fresh Patch Docker regression after rebuilding from the repository: `7 passed, 5 deselected, 7 warnings in 4.93s`, exit `0`. The warnings are the already recorded SQLite datetime deprecations. No `af-*` container remained.

## 14. Final Verification After Reviewer Remediation

| Check | Exit code | Fresh result |
|---|---:|---|
| Task 17 Docker smoke | 0 | `5 passed, 17 deselected in 4.67s` |
| Target tests | 0 | `91 passed in 0.36s` |
| Affected regression tests | 0 | `175 passed, 5 skipped in 1.99s` |
| Ruff over the exact Task 17 scope | 0 | `All checks passed!` |
| mypy strict over execution/command scope | 0 | `Success: no issues found in 22 source files` |
| `python -m pip check` | 0 | `No broken requirements found.`; existing invalid-distribution warning only |
| `git diff --check` | 0 | no whitespace errors; existing LF/CRLF notices only |

- Final sensitive-path matrix now includes `.docker/**`, `.config/pip/**`, `pip.conf`, `pip.ini`, `auth.json`, and `token.txt`; the regression guard proves their contents are not opened during snapshot construction.
- Final image matrix has three independent repository build entries: retained Phase 2C controlled Patch plus fixed Python and Node command profiles.
- Final Patch image inspect: ID `sha256:ae7d37eae541b4ead4f60614b25f3fe9f934298c332b2441f31d2ceec37a9569`, user `65532:65532`, workdir `/workspace`; `AF_RESIDUE=none`.
- Current submission status: implementation pass after remediation and explicitly user-accepted. Historical TDD ordering remains executor-submitted evidence and is not claimed as independently witnessed.

## 15. User Acceptance

- Confirmed at: 2026-08-26 12:45:34 +08:00.
- Exact user confirmation: `确认 Task 17 验收通过`.
- Result: Task 17 is user-accepted; the `Task 17 accepted` dependency named by Task 18 is satisfied.
- Boundary: this confirmation records acceptance only. Task 18 has not been started and still requires its own explicit single-Task executor authorization.
- Planner acknowledgment: 2026-08-26 planner session recorded the same user confirmation and updated plan §0 / Task 17 user-acceptance note.
