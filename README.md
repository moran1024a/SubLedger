# SubLedger · 订阅本

轻量的个人与小团队订阅账单管理工具：记录周期性订阅，自动生成账单，统计支出，并在到期前通过邮件或飞书提醒。

**当前版本：0.1.9** · Vue 3 + TypeScript · FastAPI + SQLAlchemy · MySQL · MIT License

## 功能

- **订阅规则**：单次，或每 N 天 / 周 / 月 / 年；月末与闰日按首次日期对齐，自动生成未来账单。
- **账单记录**：按未过 / 已过筛选，支持名称搜索、日期范围、规则与有效性筛选和分页；查询条件保存在 URL，可刷新或分享。
- **支出概览**：今日、本月、全年支出，折算月均 / 日均，以及下一笔账单。
- **到期提醒**：SMTP 邮件和飞书 / Lark Webhook，支持提前提醒与当日提醒，渠道配置需测试通过后才能保存，提供通知记录查询。
- **多用户**：管理员创建和管理账号；每个用户独立设置时区、币种、密码和通知渠道。
- **运维**：用户与系统日志、任务运行状态、健康检查，数据库迁移在启动时自动执行。

界面适配桌面与手机，中文界面。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia、Vue Router、Vitest |
| 后端 | Python 3.10–3.12、FastAPI、SQLAlchemy 2、Alembic、APScheduler、Pydantic v2 |
| 数据库 | 外部 MySQL 8.0 / 8.4 |
| 部署 | Docker Compose、1Panel 或直接运行；前端构建产物由 FastAPI 同源托管 |

应用为单实例、单 Uvicorn worker 设计，面向 10–20 人规模，不依赖 Redis 或 Celery。

## 快速开始

需要 Docker Engine、Compose v2 和一个可访问的 MySQL。

1. 在 MySQL 中创建数据库与账号（把 `APP_SOURCE_HOST` 换成应用的来源地址）：

   ```sql
   CREATE DATABASE subledger CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'subledger'@'APP_SOURCE_HOST' IDENTIFIED BY 'replace-with-a-strong-password';
   GRANT ALL PRIVILEGES ON subledger.* TO 'subledger'@'APP_SOURCE_HOST';
   FLUSH PRIVILEGES;
   ```

2. 复制配置模板，填写 `[database]` 连接参数和 `[bootstrap_admin]` 初始管理员：

   ```bash
   cp backend/config/config.example.toml backend/config/config.toml
   chmod 600 backend/config/config.toml
   ```

3. 构建并启动：

   ```bash
   docker compose up -d --build
   curl -i http://127.0.0.1:8081/health
   ```

打开 <http://127.0.0.1:8081>，使用配置中的管理员账号登录。域名、HTTPS 和反向代理由部署者自行配置；启用 HTTPS 时将 `[security].cookie_secure` 设为 `true`。

## 其他部署方式

**直接运行**（Python 3.10、Node.js ≥ 20.19、pnpm 10.12.4）：

```bash
python3.10 -m venv .venv && . .venv/bin/activate
python -m pip install ./backend
corepack enable && corepack pnpm --dir frontend install --frozen-lockfile
corepack pnpm --dir frontend build

cd backend
SUBLEDGER_STATIC_DIR="$(realpath ../frontend/dist)" \
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

配置、密钥和日志的相对路径以 `backend/` 为工作目录；配置不在默认位置时通过 `SUBLEDGER_CONFIG` 指定。

**1Panel**：使用 `docker-compose.1panel.yml`，要求已存在 `1panel-network`；服务只在容器网络内暴露 `8000`，由 1Panel 的反向代理接入。

## 配置

配置文件为 TOML，完整字段和默认值见 [`backend/config/config.example.toml`](backend/config/config.example.toml)。

| 配置段 / 变量 | 用途 |
| --- | --- |
| `[database]` | MySQL 连接与连接池 |
| `[bootstrap_admin]` | 首次启动创建的管理员（ID 为 0），之后修改不影响已有账号 |
| `[app]` | 默认时区、会话有效期 |
| `[scheduler]` | 账单生成、通知检查、日志与会话清理的时间 |
| `[notifications]` | 发送超时 |
| `[logging]` | 日志目录、保留天数、级别 |
| `[security]` | 主密钥路径、Cookie、SMTP 出站白名单 |
| `SUBLEDGER_CONFIG` | 配置文件路径 |
| `SUBLEDGER_STATIC_DIR` | 前端构建目录 |

注意事项：

- 通知凭据使用 `secret_key_file` 指向的 Fernet 主密钥加密。**数据库与主密钥必须配套备份和恢复**；Docker 部署中密钥位于 `subledger-data` 卷，不要执行 `docker compose down -v`。
- 飞书只接受 `open.feishu.cn` / `open.larksuite.com` 的官方机器人 Webhook。SMTP 默认只允许公网地址并验证证书；内网 SMTP 需在 `[security]` 中通过 `smtp_allowed_hosts` 和 `smtp_allow_private_hosts` 放行。
- 配置修改后重启后端生效。

## 首次使用

1. 使用 `[bootstrap_admin]` 中的账号登录，修改管理员密码。
2. 创建普通用户，并为其设置时区和币种。管理员账号只用于管理，不记录订阅；需要记账请使用普通用户。
3. 以普通用户登录，创建订阅规则，核对生成的账单。
4. 在“通知设置”填写邮件或飞书渠道，点击测试并收到消息后保存。

常用路径：`/` 前端，`/api/v1` API，`/docs` 在线 API 文档，`/health` 健康检查。

## 开发

```bash
# 后端（需先准备开发用 MySQL 和 config.toml）
python -m pip install -e './backend[test]'
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1

# 前端，Vite 会把 /api 和 /health 代理到 8000
corepack pnpm --dir frontend dev

# 检查与测试
cd backend && python -m pytest
corepack pnpm --dir frontend typecheck
corepack pnpm --dir frontend lint
corepack pnpm --dir frontend test:unit
```

后端 MySQL 集成测试默认跳过，设置 `SUBLEDGER_TEST_MYSQL_URL` 后启用。

项目结构：

```text
backend/
  app/            FastAPI 应用：api/ 路由，services/ 业务逻辑，models.py，scheduler.py
  alembic/        数据库迁移
  config/         配置模板
  tests/          后端测试
frontend/
  src/            views/ 页面，components/ 组件，stores/ 状态，api/ 客户端，utils/ 工具
  tests/          前端测试
docker-compose.yml / docker-compose.1panel.yml
scripts/build-release.sh   生成源码发布包
```

更多细节：[后端与 API 文档](backend/README.md) · [前端实现说明](frontend/README.md)。

## 发布

```bash
bash scripts/build-release.sh 0.1.9
```

生成 `dist/subledger-0.1.9.tar.gz` 及 `.sha256`，脚本会校验后端、前端与应用声明的版本一致。发布包为源码包，部署时仍需准备配置和 MySQL。

## 升级

备份数据库与主密钥，停止旧服务，用新源码重新构建前端或镜像后启动；数据库迁移自动执行且不支持降级，回滚需恢复升级前的备份。

## 使用边界

- 单实例、单 worker，不支持多副本。
- 不提供自助注册、找回密码、用户物理删除、汇率换算或支付功能。
- 域名、HTTPS、访问控制和数据库运维由部署者负责。

## 开源协议

[MIT License](LICENSE)
