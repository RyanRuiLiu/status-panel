# deploy — 部署资产

服务器运行配置的唯一事实来源。**改这里，再同步到服务器**，不要直接改服务器。

## 文件

| 文件 | 服务器位置 | 生效方式 |
|---|---|---|
| 根目录 `compose.yaml` | `/opt/status-panel/compose.yaml` | `STATUS_PANEL_TAG=<tag> docker compose -f /opt/status-panel/compose.yaml up -d` |
| 根目录 `Dockerfile` | 不上服务器 | CI 构建（见 `.github/workflows/docker.yml`，tag：`sha-<短哈希>` 与 `v*` 双轨） |
| `litestream.yml` | `/etc/status-panel/litestream.yml` | `docker compose restart litestream` |
| `nginx/status-panel.iseekdream.com.conf` | `/etc/nginx/sites-available/status-panel.iseekdream.com.conf`（enabled 为软链） | `nginx -t && systemctl reload nginx` |
| `.env`（生产密钥） | `/etc/status-panel/status-panel.env`（600） | **不入仓库**；加密副本在 infra `secrets/`（SOPS+age） |

## 部署（标准 compose 命令，无自建脚本）

```bash
# 1. 同步配置
scp compose.yaml <deploy-user>@<deploy-host>:/opt/status-panel/compose.yaml
scp deploy/litestream.yml <deploy-user>@<deploy-host>:/etc/status-panel/litestream.yml

# 2. 按 CI 产出的 sha tag 部署（tag 在 GitHub Actions 的 docker job 里看）
ssh <deploy-user>@<deploy-host> "cd /opt/status-panel && STATUS_PANEL_TAG=sha-<短哈希> docker compose up -d"

# 3. 验证
ssh <deploy-user>@<deploy-host> "docker compose -f /opt/status-panel/compose.yaml ps && curl -s http://127.0.0.1:8120/healthz"
```

## 备份与恢复（LiteStream，litestream.io v0.3）

应用持续写 WAL，sidecar `litestream` 容器实时复制到副本。**没有定时导出脚本**。

```bash
# 查看副本状态
ssh <deploy-user>@<deploy-host> "docker exec status-panel-litestream litestream replicas -config /etc/status-panel/litestream.yml"

# 恢复（覆盖前先把现库挪走；恢复到最新副本）
ssh <deploy-user>@<deploy-host> "docker run --rm -v /var/lib/status-panel:/var/lib/status-panel -v /var/backups/status-panel/litestream:/var/backups/status-panel/litestream litestream/litestream:0.3 restore -o /var/lib/status-panel/status-panel.db file:///var/backups/status-panel/litestream"
```

## 要点（改配置前先读）

- 镜像 tag 由 `STATUS_PANEL_TAG` 注入，**禁止写死 latest**；回滚 = 重新 `up -d` 指向上一个 sha tag。
- 首次部署或换 `Dockerfile` 后：数据目录属主须为 UID/GID 33（`chown -R 33:33 /var/lib/status-panel`）。
- nginx `limit_req_zone` 的 zone 名 `status-panel` 与其它站点共用 http 上下文，**不得与其它站点的 zone 重名**。
- 应用配置全部来自环境变量（`server/.env.example` 为键清单）；`config/laundry.json`、`config/notify.json` 打进镜像，改动走 PR + 发版。
