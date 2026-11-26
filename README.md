# status-panel

## 概述

宿舍电量查询、洗衣机状态展示、浴室状态展示。

## 仓库结构

```
status-panel/
├── .github/workflows/  # CI、镜像构建与部署工作流调用
├── server/             # FastAPI 服务、配置与测试
├── miniprogram/        # 微信小程序客户端
├── compose.yaml        # 应用编排定义
├── Dockerfile          # 服务端镜像定义
├── litestream.yml      # Litestream 副本定义
└── README.md
```

## 开发

### 后端

```bash
cd server
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8000
```

校验命令：

```bash
uv run pytest --cov=app --cov-report=term-missing
uv run pyright
uv run ruff check app tests
uv run ruff format --check app tests
```

健康检查端点为 `GET /healthz`。

### 小程序

参见 `miniprogram/README.md`。

## 部署

### 触发

推送 `main` 后，`docker` 工作流构建镜像并调用共享部署工作流；服务器执行 `deploy-app status-panel`。工作流定义位于 `.github/workflows/`，共享工作流位于 `.github` 仓库。

### 运行环境

| 项目 | 值 |
| --- | --- |
| 应用目录 | `/opt/status-panel` |
| 数据目录 | `/opt/status-panel/data`，容器内为 `/data` |
| 备份目录 | `/opt/status-panel/backup`，容器内为 `/backup` |
| 环境文件 | `/opt/status-panel/status-panel.env` |
| 镜像 | 见 `compose.yaml`，标签为 `main` |

容器用户与运行数据属主均为 33:33。

### 手动部署

```bash
deploy-app status-panel
```

## 约束

- 应用以单实例运行；SQLite 写锁与调度器均不支持多副本。
- `data/` 与 `backup/` 为未跟踪的运行数据目录；不得在应用目录执行 `git clean -fdx`。
- `server/config/` 下的静态配置随镜像发布；修改后须重新构建并部署。
