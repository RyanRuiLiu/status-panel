# deploy — 部署资产

服务器运行配置的事实来源。修改本目录后推送 `main`，由 CI 构建镜像并触发服务器部署。

## 服务器布局

| 路径 | 内容 |
|---|---|
| `/opt/status-panel` | `compose.yaml`、`status-panel.env`、`deploy/litestream.yml`；Git 工作副本 |
| `/var/lib/status-panel` | SQLite 数据库与 `-wal`、`-shm`，属主 33:33 |
| `/var/backups/status-panel/litestream` | Litestream 文件副本，属主 33:33 |

## 镜像

- 服务端：`crpi-5rhaq5x8z5ec9tig-vpc.cn-hangzhou.personal.cr.aliyuncs.com/ryanruiliu/status-panel:main`
- Litestream：`crpi-5rhaq5x8z5ec9tig-vpc.cn-hangzhou.personal.cr.aliyuncs.com/ryanruiliu/litestream:main`

ACR 只保留 `main` 单一 tag，不产生版本与 sha tag。回滚需检出旧提交、重新构建并部署。

## 部署

CI：推送 `main` 后由 `docker` 工作流构建镜像，`deploy` 工作流调用 `/hooks/deploy-status-panel`，服务器执行 `deploy-app status-panel`。

服务器手动部署：

```bash
deploy-app status-panel
```

`deploy-app` 依次执行：获取 `/opt/status-panel` 的 `origin/main`、校验 Compose、拉取镜像、`docker compose up -d`、轮询容器状态直至健康。健康检查失败时输出容器状态与日志并返回非零，不自动回滚。

## 环境变量

- 运行值：`/opt/status-panel/status-panel.env`，权限 600。
- 加密副本：infra 仓库 `secrets/status-panel.env.enc`。
- 修改流程：在 infra 仓库执行 `scripts/set-app-env.ps1`，由脚本上传、加密回写并重启应用；随后提交并推送密文。
- 键清单：`server/.env.example`。

## 备份与恢复

应用持续写 WAL，`litestream` sidecar 依据 `deploy/litestream.yml` 复制到文件副本。文件副本与数据库位于同一磁盘，不提供磁盘故障保护。

恢复步骤（先停止写入）：

```bash
cd /opt/status-panel
TAG=main docker compose stop status-panel
mv /var/lib/status-panel/status-panel.db /var/lib/status-panel/status-panel.db.bak
rm -f /var/lib/status-panel/status-panel.db-wal /var/lib/status-panel/status-panel.db-shm
docker run --rm \
  -v /var/lib/status-panel:/var/lib/status-panel \
  -v /var/backups/status-panel/litestream:/var/backups/status-panel/litestream \
  crpi-5rhaq5x8z5ec9tig-vpc.cn-hangzhou.personal.cr.aliyuncs.com/ryanruiliu/litestream:main \
  restore -o /var/lib/status-panel/status-panel.db file:///var/backups/status-panel/litestream
chown 33:33 /var/lib/status-panel/status-panel.db
TAG=main docker compose up -d
```

## 要点

- 单实例：SQLite 写锁与调度器均不支持多副本。
- `config/laundry.json`、`config/notify.json` 打进镜像，改动需推送并发版。
- 首次部署与换镜像后，`/var/lib/status-panel` 与 `/var/backups/status-panel/litestream` 的属主须为 33:33。
