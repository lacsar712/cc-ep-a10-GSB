# 科学实验溯源工作台（Experiment Provenance Workbench）

CQRS + Event Sourcing 全栈示例：命令追加 `event_store`，查询走投影表；Vue 前端查看 Run、事件时间线与血缘。

## How to Run

```bash
cd projects/03-experiment-provenance
docker compose up --build
```

> 镜像默认走 `docker.m.daocloud.io`（便于国内拉取）；前端 npm 使用 `npmmirror`。若你可直连 Docker Hub，可将 Dockerfile / compose 中的镜像前缀改回官方名。

首次启动会：

1. 拉起 PostgreSQL
2. 启动 FastAPI 后端并建表
3. `seed` 写入 2 条已完成 Run + 1 条进行中 Run
4. 构建并启动前端（nginx）

停止：

```bash
docker compose down
```

本地后端测试（可选，需 Python 3.11+）：

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

## Services / 端口

| 服务 | 地址 |
|------|------|
| Frontend | http://localhost:3173 |
| Backend API | http://localhost:8173 |
| PostgreSQL | localhost:54373 |

容器内：

- `db`：Postgres `provenance/provenance`，库名 `provenance`
- `backend`：Uvicorn `:8000`
- `seed`：一次性灌数后退出
- `frontend`：nginx `:80`，`/api` 反代到 backend

## 账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| researcher | lab123456 | 可发命令（Start/Metric/Artifact/Complete/Abort） |
| auditor | audit123456 | 只读事件与投影，可操作事件回放 |

## Verification

1. 打开 http://localhost:3173 ，使用 `researcher` / `lab123456` 登录
2. 在 Run 列表看到 seed 数据（含进行中与已完成）
3. 点击「新建 Run」，填写 project/name、dataset sha、code commit，启动
4. 在详情页记录指标、挂载产物，再 Complete（或 Abort）
5. 打开「事件时间线」确认 version 递增的原始事件
6. 打开「血缘」确认 code_commit、dataset 指纹、artifacts、metrics
7. 健康检查：`GET http://localhost:8173/api/health`
8. 用 `auditor` 登录：可看列表/事件/血缘，命令按钮不可用
9. 打开侧栏「事件回放」（或 Run 列表/详情里的「回放」），选定一条已完成 Run，从 v1 起点「前进一步」：可看到状态由进行中变为已完成，度量条数、附件件数逐条增加；右侧「正式投影当前值」全程保持最终态不变

终态或 `expected_version` 不匹配时，API 返回 **409**。

## 事件回放（只读演示）

侧栏「事件回放」是一个**只读、按 version 步进**的演示页，不是通用调试器：

- 选定 Run 后从第 1 版开始，只能「上一步 / 前进一步 / 复位到 v1」，不能任意跳转或编辑。
- 每一步展示：本步事件、应用之后的**临时状态**、状态、**度量条数**、**附件件数**。
- 后端 `GET /api/runs/{id}/replay?version=N` 仅从 `event_store` 读取前 N 条事件，在**请求内存**中折叠出临时投影（`replay_projection_at_version`），从不 `add/commit` 到 `run_projections`；响应返回后临时对象即丢弃，正式投影天然不受影响、无需复位。
- 接口走 `get_current_user`，**审计员可操作**；只暴露这一个固定的逐版折叠视图。
- `version` 超过事件总数时钳制到最后一版；`version < 1` 返回 422；未登录返回 401。

## 架构要点

- **命令**：`StartRun` / `RecordMetric` / `AttachArtifact` / `CompleteRun` / `AbortRun`
- **事件**：`RunStarted` / `MetricRecorded` / `ArtifactAttached` / `RunCompleted` / `RunAborted`
- **event_store**：`(aggregate_id, version)` 唯一；冲突 → 409
- **run_projections**：查询侧投影（状态、指标、产物等）
- **只读回放**：`/api/runs/{id}/replay?version=N` 从 event_store 在内存中折叠临时投影，不触碰 run_projections
