# status-panel

南通大学宿舍生活服务：宿舍电量查询、洗衣机状态、微信身份兑换（供 ntu-shower 作 `X-Identity`）。

## 目录结构

```
status-panel/
├── server/        # FastAPI 后端（uv 管理，含契约测试）
├── miniprogram/   # 微信小程序（原生 TypeScript）
└── deploy/        # 部署说明与 Litestream 配置
```

## 后端开发

```bash
cd server
uv sync                # 安装依赖
cp .env.example .env   # 本地开发值；生产值不入库（密文在 infra secrets/）
uv run uvicorn app.main:app --reload --port 8120
uv run pytest          # 契约测试
uv run pyright         # 严格类型检查
uv run ruff check app tests
```

健康检查：`GET /healthz`

## 小程序开发

1. 微信开发者工具 → 导入项目 → 目录选 `miniprogram/`（AppID 已配置）
2. 详情 → 本地设置 → 勾选「不校验合法域名」（开发期连本地后端）
3. `config.ts` 的 `BASE_URL` 当前为生产域名；本地联调改为 `http://127.0.0.1:8120`（不提交）

## 部署与发布

- 服务端：推送 `main` 后由 CI 构建并部署，说明见 [`deploy/README.md`](deploy/README.md)
- 小程序：真机回归（电量三卡 + 洗衣机）→ 微信开发者工具上传 → 提审

约束：单实例（SQLite 写锁 + 调度器不可重复注册），禁止扩容副本。

## 工程守则（红线）

- **禁止兜底、防御式编程、兼容层**：单一直线路径；异常只在真实失败模式上抛出；
  不写"以防万一"的分支、备用数据源、格式兼容、静默吞错
- **禁止推断**：外部系统的事实必须来自实测验证（探测/真实响应/源码逆向），
  每条标注验证方式；未验证的假设不得写进代码与文档
- **依赖与版本一律实测查询**（npm registry / 官方文档），不凭记忆
- **注释规范**：自包含（不引用文档编号，防漂移）；只写 why 不写 what；
  行为契约由契约测试承载（测试名即文档）；验证过程叙事只进 FACTS.md 不进代码
- 外部系统对接改版：先重验事实再改代码
