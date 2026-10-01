# SubLedger · 订阅本

轻量的个人与小团队订阅账单管理工具，把周期账单、支出统计和到期提醒放在一起。

SubLedger 按 10–20 人的小规模使用场景设计，不设账号数量配额。前端与 API 同源部署，支持直接运行、Docker Compose 和 1Panel，数据存储在部署者管理的外部 MySQL 中。

**当前版本：0.1.7** · Vue 3 + TypeScript · FastAPI + SQLAlchemy · MySQL

[快速开始](#快速开始) · [安装与部署](#安装与部署) · [开发指南](#开发指南) · [后端与 API](backend/README.md) · [前端实现](frontend/README.md)

## 功能

- **订阅与周期账单**：支持单次，或每 N 天、周、月、年；包括每 2 年、3 年，月末与闰日按首次日期对齐。
- **账单管理**：默认查看未过账单，支持历史倒序、名称搜索、日期快捷筛选和分页；查询条件保存在 URL，可刷新或分享；支持详情抽屉、筛选摘要和手机卡片。
- **支出概览**：查看今日、本月、本年支出、平均支出及下一笔账单。
- **到期提醒**：支持 SMTP 邮件和飞书/Lark Webhook，提供提前提醒、当日提醒和通知记录查询；渠道配置须先测试通过再保存。
- **多用户管理**：管理员创建和管理账号；用户独立设置时区、币种、密码与通知渠道。
- **运行维护**：提供用户与系统日志、过期会话清理、任务运行状态、数据库迁移和健康检查。

删除订阅规则时，以用户时区的“今天”为界：保留今天以前的账单，删除今天及未来账单和对应提醒。规则保留删除标记，当前不提供恢复入口。

## 目录

- [快速开始](#快速开始)
- [安装与部署](#安装与部署)
  - [部署前准备](#部署前准备)
  - [Docker Compose 部署](#docker-compose-部署)
  - [直接部署](#直接部署)
  - [1Panel 部署](#1panel-部署)
- [配置说明](#配置说明)
  - [通知出站限制](#通知出站限制)
- [首次使用](#首次使用)
- [维护与升级](#维护与升级)
- [开发指南](#开发指南)
- [项目结构](#项目结构)
- [源码发布包](#源码发布包)
- [使用边界](#使用边界)
- [开源协议](#开源协议)

## 快速开始

已具备 Docker Engine、Compose v2 和外部 MySQL 时，可以使用默认 Compose 部署。先将源码放到固定目录，以下命令在项目根目录执行。

1. 按[部署前准备](#部署前准备)创建 MySQL 数据库与账号。
2. 首次安装时复制配置模板，并编辑数据库连接和初始管理员凭据：

   ```bash
   cp backend/config/config.example.toml backend/config/config.toml
   chmod 600 backend/config/config.toml
   ```

3. 保存配置后构建、启动并检查服务：

   ```bash
   docker compose up -d --build
   docker compose ps
   curl -i http://127.0.0.1:8081/health
   ```

在服务器本机打开 <http://127.0.0.1:8081>，使用配置中的管理员账号登录。远程访问所需的域名、HTTPS 和入口转发由部署者配置。

> 应用仅支持 **单实例、单个 Uvicorn worker**。调度器、登录限流和文件日志位于进程内，不支持通过增加 worker 或副本扩容。

## 安装与部署

目标部署环境为 Ubuntu 22.04 单机服务器。应用不创建、初始化、停止或备份 MySQL 服务；三种部署方式均连接外部 MySQL 8.0/8.4。

| 方式 | 环境要求 | 默认入口 |
| --- | --- | --- |
| Docker Compose | Docker Engine、Compose v2 | 宿主机 `127.0.0.1:8081` → 容器 `8000` |
| 直接部署 | Python 3.10、Node.js ≥ 20.19.0、Corepack / pnpm 10.12.4 | `127.0.0.1:8000` |
| 1Panel | 已安装 1Panel、Docker/Compose，已有 `1panel-network` | 仅容器网络内 `8000`，不映射宿主机端口 |

构建需要访问依赖源。容器部署不要求宿主机安装 Python 或 Node.js；生产环境由 FastAPI 托管前端构建产物，不运行 Vite 开发服务器。

### 部署前准备

**获取源码。** 将项目放到固定目录，例如 `/opt/subledger`。如使用打包文件，先按[源码发布包](#源码发布包)校验，再解压到空目录。项目、密钥和日志目录需要相应的读写权限。

**准备数据库。** 在 MySQL 中创建专用数据库与账号。将示例中的 `APP_SOURCE_HOST` 替换为实际连接来源主机或网段，并设置随机密码：

```sql
CREATE DATABASE subledger CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'subledger'@'APP_SOURCE_HOST' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT ALL PRIVILEGES ON subledger.* TO 'subledger'@'APP_SOURCE_HOST';
FLUSH PRIVILEGES;
```

MySQL 来源授权、监听地址、防火墙、DNS 和端口必须允许应用访问。Docker 中的 `127.0.0.1` 指向 backend 容器自身；请填写容器可访问的数据库地址，不要将它当作宿主机地址。编排文件不提供名为 `mysql` 的服务。

**创建配置。** 首次安装时复制模板；已有配置请直接编辑，不要覆盖：

```bash
cp backend/config/config.example.toml backend/config/config.toml
chmod 600 backend/config/config.toml
```

至少修改 `[database]` 中的连接参数和 `[bootstrap_admin]` 中的用户名、密码。完整字段见[配置模板](backend/config/config.example.toml)，通知渠道的网络限制见[通知出站限制](#通知出站限制)。

### Docker Compose 部署

确认 `backend/config/config.toml` 已存在且是普通文件，再从项目根目录运行：

```bash
docker compose build backend
docker compose up -d
docker compose ps
docker compose logs --tail=100 backend
curl -i http://127.0.0.1:8081/health
```

配置文件以只读方式挂载。若挂载前文件不存在，Docker 可能创建同名目录，导致启动失败。

启动时会检查数据库、执行 Alembic 迁移、初始化管理员并启动调度器。数据库连接在启动重试后仍失败时，容器可按 `unless-stopped` 策略重启；运行中的容器仅变为 `unhealthy` 不会自动触发该策略。

### 直接部署

在项目根目录安装后端依赖并构建前端：

```bash
python3.10 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ./backend

corepack enable
corepack pnpm --dir frontend install --frozen-lockfile
corepack pnpm --dir frontend build
```

从 `backend/` 目录启动，配置、数据和日志的相对路径均以工作目录为基准：

```bash
cd backend
. ../.venv/bin/activate
SUBLEDGER_STATIC_DIR="$(realpath ../frontend/dist)" \
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

如配置不在默认位置，可在同一启动命令中增加 `SUBLEDGER_CONFIG=/absolute/path/config.toml`，同时保留 `SUBLEDGER_STATIC_DIR`。在另一个终端验证：

```bash
curl -i http://127.0.0.1:8000/health
curl -I http://127.0.0.1:8000/
```

长期运行时由部署者配置进程托管，保持工作目录、配置路径和单 worker 设置一致。

### 1Panel 部署

专用文件 [docker-compose.1panel.yml](docker-compose.1panel.yml) 复用已有的 `1panel-network`，不会创建网络，也不映射宿主机端口。

1. 确认网络存在：`docker network inspect 1panel-network`。
2. 准备容器可访问的外部 MySQL，完成数据库、账号和连接来源授权。
3. 将源码放到固定目录，创建并编辑实际配置文件。
4. 在 1Panel 中使用专用编排文件构建、启动；升级现有实例时保持原编排项目名，以复用原数据卷。
5. 检查容器状态、启动日志和容器内健康接口，再配置访问入口。

命令行检查示例：先将项目名设为 1Panel 中的实际值，然后执行。以下检查不会创建新的编排项目。

```bash
COMPOSE_PROJECT='replace-with-your-1panel-project-name'
docker compose -p "$COMPOSE_PROJECT" -f docker-compose.1panel.yml ps
docker compose -p "$COMPOSE_PROJECT" -f docker-compose.1panel.yml logs --tail=100 backend
docker compose -p "$COMPOSE_PROJECT" -f docker-compose.1panel.yml exec -T backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read().decode())"
```

## 配置说明

| 配置段 / 环境变量 | 用途 |
| --- | --- |
| `[database]` | 外部 MySQL 连接与连接池 |
| `[bootstrap_admin]` | 首次启动时创建管理员；修改此处不会重置已有账号 |
| `[app]` | 时区、会话有效期等 |
| `[scheduler]` | 账单检查、通知检查与日志清理时间 |
| `[notifications]` | DNS、连接和发送超时，省略时使用默认值 |
| `[logging]` | 日志目录、保留天数与级别 |
| `[security]` | 主密钥路径、Cookie 配置与 SMTP 出站限制 |
| `SUBLEDGER_CONFIG` | 指定实际 TOML 配置文件路径 |
| `SUBLEDGER_STATIC_DIR` | 指定需要托管的前端构建目录 |

启用 HTTPS 访问时应设置 `[security].cookie_secure = true`。配置变更后重启后端。不要将实际配置、密码、主密钥或运行日志提交到仓库。

### 持久化数据

| 内容 | 直接部署（从 `backend/` 启动） | Docker / 1Panel |
| --- | --- | --- |
| 实际配置 | `backend/config/config.toml` | 只读挂载至 `/app/config/config.toml` |
| Fernet 主密钥 | `backend/data/secret.key` | `subledger-data` 卷中的 `/app/data/secret.key` |
| 日志 | `backend/logs/` | `subledger-logs` 卷中的 `/app/logs/` |
| 业务数据 | 外部 MySQL | 外部 MySQL，不在应用数据卷中 |

相对日志与密钥路径取决于进程工作目录。主密钥不存在时自动创建，权限为 `0600`；已有密钥也必须保持 `0600`。数据库中的通知凭据依赖此密钥解密，**数据库与密钥必须配套备份、恢复**。

Compose 的卷名通常带项目名前缀。更换目录或编排项目名可能挂载新卷；升级时应明确复用原项目名和卷。

### 通知出站限制

飞书/Lark 仅支持以下官方 Webhook：

- `https://open.feishu.cn/open-apis/bot/v2/hook/<token>`
- `https://open.larksuite.com/open-apis/bot/v2/hook/<token>`

不支持转发域名、443 以外的端口、查询参数或重定向；Webhook 连接不使用环境中的 HTTP/HTTPS 代理。

SMTP 默认只允许公网地址，拒绝内网、回环与链路本地地址；SSL/STARTTLS 验证服务器证书和主机名。使用企业内网 SMTP 时，修改现有 `[security]` 段中的字段，不要重复添加该段：

```toml
# 非空时只允许这些精确主机名或 IP，不支持通配符。
smtp_allowed_hosts = ["smtp.example.com", "smtp.corp.example"]
# 仅为受信任的 SMTP 主机允许非公网地址。
smtp_allow_private_hosts = ["smtp.corp.example"]
```

两项均可省略，默认为 `[]`。`smtp_allowed_hosts` 为空时允许任意公网主机；`smtp_allow_private_hosts` 为空时没有内网例外。如两项都配置，内网主机必须同时列入两项。修改后重启后端。

升级后，非官方飞书地址、未放行的内网 SMTP、自签名或主机名不匹配的邮件证书将无法使用。请调整通知地址、配置可信主机例外，或使用受运行环境信任且匹配主机名的证书。

## 首次使用

1. 打开部署入口，使用 `[bootstrap_admin]` 中的账号登录；初始化管理员 ID 为 `0`。
2. 修改管理员密码，再按需创建普通用户。
3. 设置用户时区和币种，创建订阅规则并核对账单日期。
4. 填写邮件或飞书草稿，点击测试，收到通过结果后保存。测试会实际发送消息，但不会覆盖已保存配置。
5. 检查支出概览、日志和健康状态。

| 路径 | 说明 |
| --- | --- |
| `/` | 前端页面 |
| `/api/v1` | API 路径前缀 |
| `/docs`、`/redoc`、`/openapi.json` | 在线 API 文档与 Schema |
| `/health` | 数据库与调度器健康状态 |

## 维护与升级

### 健康检查与故障定位

`GET /health` 在数据库可访问且调度器及任务正常（或已在配置中关闭调度）时返回 `200`，否则返回 `503`。管理员首页可查看本次启动后的任务执行情况。任务连续失败 3 次、未执行且超过宽限期，或运行超过配置的时间上限时降级；单个通知渠道失败只标记为需关注。首次任务尚未到执行时间不会误报。

| 现象 | 优先检查 |
| --- | --- |
| 配置加载失败 | 实际配置是否为普通文件；`SUBLEDGER_CONFIG` 路径是否正确 |
| 数据库连接失败 | 容器可达地址、DNS、端口、密码与 MySQL 来源授权 |
| 1Panel 网络不存在 | 名称是否严格为 `1panel-network`，是否已预先创建 |
| 页面空白或刷新返回 404 | 是否构建 `frontend/dist/`，静态目录是否配置正确 |
| 健康检查返回 503 | 数据库连接、调度器配置与启动日志 |
| 通知发送失败 | 渠道凭据、DNS、出站限制与 TLS 证书；执行实际测试发送 |
| 标准错误出现 `log_write_error` | 日志目录权限与磁盘空间；文件日志失败时错误会回退到标准错误输出 |

### 数据备份

备份应包含外部 MySQL、配套 Fernet 主密钥、实际配置文件，以及需要保留的日志。数据库备份使用数据库服务或托管平台提供的工具，并验证能够恢复。配置和密钥含敏感信息，应限制访问权限。

> `docker compose down -v` 或清理应用卷会丢失主密钥，即使外部数据库仍在，也无法解密原通知配置。普通重启和升级不要删除数据卷。

### 升级、重启与停止

升级前记录当前版本、配置路径、Compose 项目名和卷名。停止旧 backend 以冻结写入，备份数据库与配套密钥，将新源码解压到新空目录，再恢复实际配置和持久化数据。不要携带旧的虚拟环境、`node_modules` 或前端构建产物。

普通 Compose 升级时，在新目录中显式指定原项目名。以下脚本会先检查原应用卷；如使用了自定义卷名，应按实际名称核对：

```bash
COMPOSE_PROJECT='replace-with-existing-compose-project-name'
if [ "$COMPOSE_PROJECT" = 'replace-with-existing-compose-project-name' ]; then
  printf '请先填写原 Compose 项目名。\n' >&2
else
  (
    set -e
    docker volume inspect "${COMPOSE_PROJECT}_subledger-data" "${COMPOSE_PROJECT}_subledger-logs"
    docker compose -p "$COMPOSE_PROJECT" up -d --build
    docker compose -p "$COMPOSE_PROJECT" ps
    docker compose -p "$COMPOSE_PROJECT" logs --tail=100 backend
    curl -f http://127.0.0.1:8081/health
  )
fi
```

1Panel 升级应在原编排项目中操作；命令行操作需保留原 `-p` 项目名，并为所有 Compose 命令添加 `-f docker-compose.1panel.yml`。使用容器内健康检查，不能套用宿主机 `8081` 入口。

直接部署应停止旧进程，在新目录安装后端依赖、重新构建前端，恢复配置与数据路径，然后按[直接部署](#直接部署)启动。数据库迁移在应用启动时自动执行。

升级后验证健康接口、登录、规则、账单、统计和通知配置解密。回滚必须考虑数据库变化；不要仅替换旧代码后继续使用已经迁移或产生新业务状态的数据库。

日常维护使用 `docker compose restart backend`、`stop backend`、`start backend`，并保持正确项目名及编排文件。`down` 保留命名卷，`down -v` 会删除它们。

### 从 0.1.6 升级到 0.1.7

先停止写入、备份数据库与主密钥，再按上面的升级步骤启动新版。启动时自动执行 `0004_general_cycles`；旧月/季/年/自定义天数规则转换为 `month × 1/3`、`year × 1`、`day × N`，已有账单、金额快照、手动作废状态及通知记录保持不变。回滚需恢复升级前备份，不能只切回旧程序。

- **通用周期**：选择“单次”或“每 N 天/周/月/年”，金额是每次扣费总额。整数上限分别为 36500 天、5214 周、1200 月、100 年。每 2 年 240 元折算月均为 10 元；单次规则不参与月均和日均。短月取月末，后续恢复首次日号；2 月 29 日遇非闰年取 28 日，遇闰年恢复 29 日。
- **首页与查询**：首页展示今日、本月预计、全年预计和最多 10 笔真实近期账单。预计金额包含未来推算，可能与已生成明细合计不同；月均、日均展示折算口径。账单高级筛选可折叠，输入与已生效条件分开；详情抽屉、关联规则和返回操作保留 URL 查询上下文。
- **表单与手机**：原有六个用户菜单和视觉风格保留；新增规则摘要、未保存离开确认、持久错误反馈、手机卡片及全宽详情。写入超时或服务错误应先重新查询核实，客户端不会自动重发。
- **先测试再保存**：SMTP 或飞书配置首次填写、修改或重新启用均须测试，后端也会验证。凭证有效 10 分钟，与用户、会话、渠道、配置内容和已保存版本绑定；修改渠道字段、保存、退出重登或服务重启后需重新测试。仅关闭渠道或仅调整提醒时间不需要测试。旧有配置可以继续使用，测试期间仍使用已保存配置。
- **测试边界**：每用户每渠道至少间隔 30 秒，全局最多同时 4 个测试；测试会实际发送一条消息。成功代表服务接受发送，不保证最终投递到收件箱；失败或结果未知不能用于保存。结果未知时先检查是否收到，避免重复发送。飞书与邮件各自测试，均修改时需各有有效凭证。

API 输出的周期统一为新类型并增加 `cycle_interval`；旧类型请求仍可转换接收，但旧客户端需适配新响应和通知保存校验。部署仍使用单 worker；没有引入新的业务依赖或配置项。

### 从 0.1.5 升级到 0.1.6

升级前停止旧服务，备份数据库与配套主密钥，然后按上面的升级步骤安装、构建并启动。启动自动执行 `0003_notification_attempts` 迁移，增加通知尝试次数、最近尝试、下次重试和安全错误码。已发送记录保持已发送；旧失败记录保留次数，只有尚未耗尽次数且仍在当日提醒窗口内的记录可继续尝试；旧的发送中记录标记为结果未知。

- **任务状态**：管理员首页展示最近成功时间、耗时、连续失败和下次执行时间。状态保存在进程内，重启后重新统计；系统日志保留执行历史。
- **会话清理**：默认每天应用时区 02:00 清理已过期会话，每批 500 条、每轮最多 10000 条。关闭调度器也会关闭此任务。
- **通知控制**：默认 DNS 等待 5 秒、单地址连接最多 5 秒，锁内网络发送共享 30 秒预算。DNS 在持锁前完成，发送前重新核对配置。超时终止连接；数据库锁等待不包含在网络预算内。
- **重试与查询**：最多尝试 3 次，临时故障在 60 秒、300 秒后具备重试资格，由下一轮通知检查执行；明确配置错误停止自动重试。提交后无法确认送达的结果标记为未知并停止自动重发，应先检查是否已收到消息。不会跨原提醒日期补发。
- **前端体验**：查询、写入/测试发送、下载默认超时分别为 15、45、60 秒，包含读取响应正文。页面离开或切换查询时取消失效查询；写入超时应重新查询或刷新核实，避免重复提交。组件与样式按需加载。

新增配置均可省略，旧配置继续可用；不要用示例文件覆盖实际配置。`[scheduler].session_cleanup_hour` 默认为 `2`，`task_timeout_seconds` 默认为 `900`（健康判定阈值，不强行中止任务）；`[notifications]` 三个超时字段见配置模板。网络与服务端提交无法组成同一事务，仍不能保证消息严格只送达一次。通知记录只保存每条业务提醒的最新结果，测试发送另记用户日志。

回滚需恢复升级前配套备份，不能将旧代码直接连接到使用了新重试状态的数据库。

### 从 0.1.4 升级到 0.1.5

本次无需数据库迁移，API 响应结构不变。重新安装依赖、构建前端并重启服务即可；保留数据库、主密钥和日志。

- 登录与密码修改、管理员重置/停用使用统一锁顺序，阻止旧密码验证结果在重置后创建有效会话。
- 规则与用户详情随 URL 更新，丢弃旧请求和旧确认框的结果；认证初始化失败可重试，并发初始化共享请求。
- 每次通知发送前重新校验账户、渠道和提醒设置，由检查循环统一提交事务。已在发送中的通知会先完成，关闭操作提交后不再按旧配置继续发送。
- 统计复用规则与全年账单，查询由 8 次减少到 3 次；未来账单补全只读取所需日期范围。历史漏账仍不补处理。
- TOML 配置严格检查类型，例如 `enabled = false` 不可写成字符串；`app.host`、`app.port` 已废弃，保留时警告并忽略，监听地址由 Uvicorn/部署入口设置。`logging.level` 现在实际过滤日志。
- 通知输入长度与数据库一致：SMTP 主机、用户名、发件/收件邮箱最多 255 字符，发件人名称最多 128 字符，超限返回 422。
- 合并重复日志和资料处理，移除未使用组件、参数和直接依赖；`httpx` 仅在后端测试依赖中保留。

### 从 0.1.3 升级到 0.1.4

本次无需数据库迁移。账户数量配额已移除，旧配置中的 `app.max_users` 不再生效，可保留或删除；性能设计目标为 10–20 人使用，仍须单实例、单 worker。

前后端需要配套升级：`GET /api/v1/admin/users` 从数组改为 `{items, page, page_size, total}`，支持用户名搜索和状态筛选；管理员概览不再返回 `max_users`、`remaining_users`。自行集成 API 的客户端需同步调整。

账单页默认查询未过账单（包含用户当地今天），按日期升序；已过和全部默认降序。标签切换清除日期范围，其他条件通过查询按钮或回车提交；翻页、重试和有效性操作使用已提交条件。接口不传筛选和排序参数时仍保持全部账单、日期升序，新增 `q`、`sort`，日期倒置返回 `400 INVALID_DATE_RANGE`。

### 旧版本迁移

<details>
<summary>0.1.0：从内置 MySQL 迁移到外部 MySQL</summary>

0.1.0 的编排包含 MySQL 容器和 `mysql-data` 卷，0.1.1 起不再提供。删除服务声明不会自动迁移数据库。

1. 保存旧编排文件和项目名，备份数据库卷、主密钥、配置及日志。
2. 创建外部数据库与账号，使用旧编排停止 backend，暂时保持旧 MySQL 运行。
3. 导出完整数据库并导入外部 MySQL，核对关键表、行数、`alembic_version` 和 `utf8mb4` 字符集。
4. 使用旧编排执行不带 `-v` 的 `down`，保留所有卷。
5. 切换到新源码，修改数据库配置，复用原项目名及主密钥卷启动。
6. 验证健康、登录、业务数据与通知配置解密。

回滚窗口内保留旧 `mysql-data`，不要执行 `docker volume prune`。升级到更新版本时还需遵循下面的迁移说明。

</details>

<details>
<summary>0.1.1 → 0.1.2：账单规则删除标记</summary>

迁移从 `0001_initial_schema` 升至 `0002_add_bill_plan_deleted_at`，只增加可空的 `bill_plans.deleted_at` 字段，不回填或删除现有业务数据。只有用户主动删除规则时才执行相应账单清理。

按上述升级流程停止写入、备份、切换新目录并复用原卷。应用先完成迁移，再启动调度器。使用测试规则验证删除行为，不要删除唯一的生产数据。

删除标记不能安全地通过 Alembic downgrade 转回 0.1.1；回退需恢复升级前同批次数据库和主密钥，再启动旧版本。仅回退代码可能重新显示已删除规则。

</details>

<details>
<summary>0.1.2 → 0.1.3：1Panel 专用编排</summary>

0.1.3 新增 `docker-compose.1panel.yml`，不增加数据库迁移。普通 Compose 可继续使用原编排。

1Panel 实例切换前备份数据、主密钥和配置，记录原项目名并检查原应用卷，确认 `1panel-network` 已存在。将新源码解压到空目录并恢复配置，在原编排项目中改用专用文件重新构建启动。核对容器网络、健康状态和通知配置解密；专用编排不映射宿主机端口，访问入口需相应调整。

</details>

## 开发指南

后端声明支持 Python `>=3.10,<3.13`，部署示例使用 Python 3.10；前端声明 Node.js `>=20.19.0`，包管理器为 pnpm `10.12.4`。Docker 构建使用 Node.js 22 和 Python 3.10。

先准备独立的开发数据库与配置，并安装依赖。启动会执行迁移和调度任务，开发环境应使用独立的通知配置。

后端终端：

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

前端终端，在项目根目录执行：

```bash
corepack pnpm --dir frontend dev
```

Vite 将 `/api` 和 `/health` 代理到本地 `8000` 端口。

### 检查与测试

在项目根目录安装后端测试依赖并运行测试：

```bash
python -m pip install './backend[test]'
cd backend
python -m pytest
```

前端检查在项目根目录执行：

```bash
corepack pnpm --dir frontend typecheck
corepack pnpm --dir frontend lint
corepack pnpm --dir frontend test:unit
corepack pnpm --dir frontend build
```

前端单元测试使用 jsdom 与模拟 API，不代替真实浏览器和通知渠道验证。后端 MySQL 集成测试默认跳过，设置 `SUBLEDGER_TEST_MYSQL_URL` 后启用；测试账号需有创建和删除独立测试数据库的权限。具体范围见[后端安全与测试边界](backend/README.md#后端安全与测试边界)。

## 项目结构

```text
SubLedger/
├── README.md                    # 项目介绍、部署与维护入口
├── docker-compose.yml           # 普通 Docker Compose
├── docker-compose.1panel.yml     # 1Panel 专用编排
├── scripts/build-release.sh     # 源码发布打包
├── backend/
│   ├── README.md                # 后端设计与 HTTP API
│   ├── pyproject.toml           # Python 依赖与测试配置
│   ├── Dockerfile               # 前端构建与后端运行镜像
│   ├── config/config.example.toml
│   ├── alembic/                 # 数据库迁移
│   ├── app/
│   │   ├── main.py              # 应用入口与生命周期
│   │   ├── api/                 # HTTP 路由
│   │   ├── services/            # 账单、通知、日志等业务逻辑
│   │   ├── models.py            # 数据模型
│   │   ├── schemas.py           # 请求与响应结构
│   │   └── scheduler.py         # 定时任务
│   └── tests/                   # 单元与集成测试
└── frontend/
    ├── README.md                # 前端结构与交互约定
    ├── package.json
    ├── pnpm-lock.yaml
    ├── src/
    │   ├── api/                 # API 客户端
    │   ├── views/               # 业务页面
    │   ├── components/          # 可复用组件
    │   ├── stores/              # Pinia 状态
    │   ├── router/              # 路由与权限
    │   └── utils/               # 格式化与校验
    └── tests/                   # 前端单元测试
```

请求经过 FastAPI 路由和业务服务访问 MySQL；APScheduler 在同一后端进程中执行账单、通知和日志清理任务，无需 Redis 或 Celery。

| 修改内容 | 前端入口（`frontend/src/`） | 后端入口（`backend/app/`） |
| --- | --- | --- |
| 登录与会话 | `stores/auth.ts`、`api/client.ts` | `api/auth.py`、`security.py` |
| 订阅与账单 | `views/plans/`、`views/bills/`、`components/billing/` | `api/plans.py`、`api/bills.py`、`services/billing.py` |
| 支出统计 | `views/HomeView.vue` | `api/statistics.py`、`services/statistics.py` |
| 通知设置 | `views/settings/NotificationsView.vue` | `api/notifications.py`、`services/notifications.py`、`services/outbound.py` |
| 用户管理与日志 | `views/admin/` | `api/users.py`、`api/logs.py`、`services/logging.py` |

## 源码发布包

从项目根目录生成发布包，版本号必须与后端、前端及 FastAPI 声明一致：

```bash
bash scripts/build-release.sh 0.1.7
```

输出为 `dist/subledger-0.1.7.tar.gz` 和对应的 `.sha256`。脚本按固定文件清单打包源码、文档及部署文件，排除实际配置、密钥、日志、依赖目录和构建产物；它不安装依赖或构建镜像，也不会覆盖已有的同名发布包。

下载或复制两个文件到同一目录后校验：

```bash
sha256sum -c subledger-0.1.7.tar.gz.sha256
tar -tzf subledger-0.1.7.tar.gz
```

校验成功后解压到新的空目录。以下示例在目标目录非空时停止：

```bash
(
  set -e
  sudo install -d -o "$USER" -g "$USER" /opt/subledger
  if [ -n "$(find /opt/subledger -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    printf '目标目录非空，请使用新的空目录。\n' >&2
    exit 1
  fi
  tar -xzf subledger-0.1.7.tar.gz --strip-components=1 -C /opt/subledger
)
```

发布包是源码包，不是离线安装包或预构建镜像。解压后仍需创建实际配置、准备外部 MySQL，再按所选部署方式安装依赖或构建镜像。

## 使用边界

- 面向小规模、持续运行的单实例服务；不提供多副本协调或停机期间历史漏账补偿。
- 不提供自主注册、找回密码、用户物理删除或独立删除账单的 API。
- 不提供汇率换算、支付执行、数据库备份 API 或主密钥轮换工具。
- 域名、HTTPS、访问控制入口和外部数据库运维由部署者管理。

接口字段、状态码和业务语义见[后端文档](backend/README.md)；页面职责、交互约定及前端实现见[前端文档](frontend/README.md)。

## 开源协议

本项目采用 [MIT License](LICENSE)。
