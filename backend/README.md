# SubLedger（订阅本）后端 API 文档

本文档是当前代码实际提供的后端技术说明与 HTTP API 权威文档，覆盖数据格式、认证方式、Schema、接口、错误码和业务语义。当在线 OpenAPI、其他需求材料与本文档存在差异时，应以当前路由、Schema 和服务实现为准。安装、部署和首次使用请参阅 [项目安装与部署](../README.md#安装与部署)。

- 应用版本：`0.1.6`
- API 前缀：`/api/v1`
- 默认本地地址：`http://127.0.0.1:8000`
- Docker 容器内部地址：`http://127.0.0.1:8000`
- 数据格式：JSON；日志下载接口除外
- 认证方式：服务端 Session + Cookie

## 目录

- [后端技术说明](#后端技术说明)
- [文档入口](#文档入口)
- [通用约定](#通用约定)
- [数据模型](#数据模型)
- [API 总表](#api-总表)
- [认证 API](#认证-api)
- [当前用户 API](#当前用户-api)
- [管理员用户 API](#管理员用户-api)
- [账单规则 API](#账单规则-api)
- [账单实例 API](#账单实例-api)
- [账单周期与实例生成规则](#账单周期与实例生成规则)
- [统计 API](#统计-api)
- [通知 API](#通知-api)
- [日志 API](#日志-api)
- [健康检查](#健康检查)
- [错误码索引](#错误码索引)
- [curl 示例](#curl-示例)
- [当前限制与集成注意事项](#当前限制与集成注意事项)

## 后端技术说明

### 技术栈

- Python `>=3.10,<3.13`，FastAPI 和 Uvicorn。
- SQLAlchemy 2 同步模式、PyMySQL 和 MySQL 8.0/8.4。
- Pydantic 2 请求/响应校验，Alembic 数据库迁移。
- APScheduler 3 进程内调度，Argon2 密码哈希，Fernet 敏感字段加密。
- Python 标准库发送 SMTP 邮件和 HTTPS 飞书 Webhook，JSON Lines 保存本地日志。

### 模块边界

- `app/api/` 负责 HTTP 路由、请求参数、认证依赖、资源权限和响应模型。
- `app/services/` 负责认证、用户、账单日期与实例、统计、通知发送和日志文件操作。
- `app/models.py` 定义 MySQL ORM 模型，`app/schemas.py` 定义 Pydantic 请求/响应模型。
- `app/database.py` 创建同步 SQLAlchemy 连接池和会话，并在应用启动阶段执行 Alembic 迁移。
- `app/security.py` 负责 Argon2 密码哈希、Cookie Session、Fernet 敏感字段加密和登录限流。
- `app/scheduler.py` 在同一个 Web 进程中运行 APScheduler 作业。

### 启动与调度约束

应用启动时会连接数据库、执行迁移、初始化固定 `id=0` 的管理员和默认通知配置，然后按配置启动调度器。调度器包含账单补全、通知检查、日志清理和过期会话清理四类作业；作业异常写入系统日志，不直接终止 Web 服务。

必须使用单个 Uvicorn worker。调度器、登录限流和 JSON Lines 文件日志都位于进程内，多个 worker 或多个后端副本会造成重复调度、限流状态分裂或日志竞争。Docker 容器内部使用端口 `8000`；宿主机端口映射和部署操作见 [项目安装与部署](../README.md#安装与部署)。

### 后端安全与测试边界

密码只保存 Argon2 哈希，Session Token 只通过 `HttpOnly` Cookie 传输，SMTP 密码、飞书 Webhook 和签名密钥使用 Fernet 加密。Fernet 主密钥必须持久化且权限为 `0600`，并与数据库一起备份。日志按敏感键脱敏，但仍应限制日志文件和下载接口访问。

后端单元测试位于 `backend/tests/unit`，覆盖通知出站限制、TLS、失败隔离、周期边界和日志故障等回归。外部发送使用替身或本机临时 SMTP/socket 接收器，不连接公网 SMTP 或飞书。

`backend/tests/integration/test_mysql_billing.py` 使用真实 MySQL 验证 `REPEATABLE READ` 下的双事务交错操作，涵盖手动作废、规则启停、账单补齐、金额修改和通知去重。默认跳过；在独立测试服务器上设置 `SUBLEDGER_TEST_MYSQL_URL` 后执行：

```bash
# 在 backend/ 目录及已安装测试依赖的 Python 环境中运行。
# URL 通过环境变量提供，指向独立测试 MySQL；账号需具备创建、删除测试数据库的权限。
SUBLEDGER_CONFIG=/tmp/subledger-test-no-config.toml python -m pytest
```

每项集成测试创建唯一的 `subledger_test_<随机值>` 数据库，并在结束后删除该测试库，不使用 URL 中指定的已有数据库。Docker 启动和真实 SMTP/飞书发送仍需在部署环境验证。

## 文档入口

服务启动后可访问：

| 地址 | 用途 |
|---|---|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | FastAPI 自动生成的 OpenAPI Schema |
| `/health` | 数据库和调度器健康检查 |

当前 OpenAPI 可以展示路径、基础字段和部分约束，但不会完整表达 Cookie 认证、管理员权限、业务错误码、登录限流、`X-Request-ID`、日志下载媒体类型及部分业务副作用。集成时应同时参考本文档。

## 通用约定

### 请求与响应

- JSON 请求应使用 `Content-Type: application/json`。
- `200 OK` 返回查询或操作结果。
- `201 Created` 返回新建资源。
- `204 No Content` 不返回响应体。
- 账单实例、管理员用户列表和个人通知记录均返回分页结构；规则和日志列表返回数组。
- 账单实例列表使用 `page`、`page_size`，返回 `{items, page, page_size, total}`。
- FastAPI 未匹配路由、方法不允许等框架错误可能仍使用 `{"detail": ...}`，不保证采用业务错误信封。

### Request ID

客户端可以发送：

```http
X-Request-ID: client-generated-id
```

未提供时，服务端生成 32 位十六进制字符串。正常完成的响应及已处理错误响应会携带 `X-Request-ID`；业务错误体中的 `request_id` 与当前请求关联。客户端应保存该值，以便排查日志。

### Cookie Session

登录成功后服务端设置 Session Cookie。Cookie 名由 `[security].cookie_name` 配置，示例配置使用 `subledger_session`。

| 属性 | 当前行为 |
|---|---|
| `HttpOnly` | `true` |
| `SameSite` | `Lax` |
| `Secure` | 由 `[security].cookie_secure` 决定 |
| `Path` | `/` |
| `Max-Age` | `[app].session_expire_days × 86400` |
| `Domain` | 未设置，属于当前主机 |

原始 Session Token 仅发送到 Cookie，数据库只保存 SHA-256 哈希。Session 不是 JWT，不支持 `Authorization: Bearer`，也不会随请求滑动续期。

受保护接口可能返回：

| HTTP 状态 | `code` | 条件 |
|---:|---|---|
| 401 | `AUTH_REQUIRED` | 未提供 Session Cookie |
| 401 | `AUTH_SESSION_INVALID` | Session 不存在、已撤销、已过期，或关联用户不存在/已停用 |

下列操作会撤销 Session：

- 退出登录：只撤销当前 Session。
- 当前用户修改密码：撤销该用户全部 Session，包括当前 Session。
- 管理员重置密码、停用用户：撤销目标用户全部 Session。
- 管理员修改用户并传入 `revoke_sessions=true`：撤销目标用户全部 Session。

### 权限等级

| 等级 | 说明 |
|---|---|
| 公开 | 不要求登录 |
| 当前用户 | 要求有效 Session，只能访问当前用户数据 |
| 管理员 | 当前用户必须同时满足 `role = "admin"` 和 `id = 0` |

管理员接口权限不足时返回 `403 PERMISSION_DENIED`。账单规则和账单实例会同时按资源 ID 与当前用户 ID 查询；不存在和属于其他用户均返回对应的 404，不泄露资源归属。

### 登录限流

登录失败限流保存在当前 Python 进程内存中：

| 维度 | 窗口 | 允许失败次数 |
|---|---:|---:|
| 来源地址 `request.client.host` | 300 秒 | 5 |
| 小写用户名 | 300 秒 | 20 |

达到阈值后返回 `429 AUTH_RATE_LIMITED`，当前不返回 `Retry-After`。成功登录会清空本次来源和账号的计数；应用重启会清空全部计数。多进程之间不会共享限流状态，这也是当前部署要求单 worker 的原因之一。

### 日期、时间、时区和金额

- `date` 使用 ISO 8601 日期：`YYYY-MM-DD`。
- 通知时间使用 JSON time 格式，通常为 `HH:MM:SS`。
- 账单的“今天”、`upcoming`、`passed`、统计范围和通知时间均依据当前用户的 IANA 时区计算。
- `upcoming` 包含用户当地今天，即 `due_date >= today`；`passed` 为 `due_date < today`。
- 数据库中的业务时间戳语义为 UTC，使用不带时区偏移的 `DATETIME` 存储。
- 金额输入按十进制数解析，必须大于 0，最多 14 位有效数字和 2 位小数。
- 金额响应使用固定两位小数的字符串，例如 `"12.30"`，不是 JSON number。
- `currency_code` 只作为用户属性保存并转为大写；当前不校验 ISO 4217，也不进行汇率换算。

### 统一错误响应

业务错误、请求校验错误和未处理异常使用：

```json
{
  "code": "ERROR_CODE",
  "message": "错误描述",
  "request_id": "9c5ac919e0064a6f9d722194486c2a71"
}
```

所有具有 Path、Query 或 Body 参数的接口都可能因格式不合法返回：

```http
HTTP/1.1 422 Unprocessable Entity
```

```json
{
  "code": "INVALID_REQUEST",
  "message": "请求参数格式错误",
  "request_id": "9c5ac919e0064a6f9d722194486c2a71",
  "errors": [
    {"field": "cycle_days", "message": "Input should be greater than 0"}
  ]
}
```

422 的 `errors` 只包含去掉 `body`、`query`、`path` 前缀后的字段路径和安全消息，不返回输入值或内部校验上下文。未捕获异常返回 `500 INTERNAL_ERROR`。接口章节只列出特有业务错误；受保护接口还应结合认证与权限公共错误。

## 数据模型

表格中的“可选”表示请求中可以省略。部分更新请求中，省略字段表示保留原值。

### 用户与认证模型

#### `LoginRequest`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `username` | string | 是 | 1–64 字符 |
| `password` | string | 是 | 1–255 字符 |

#### `UserResponse`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | 管理员固定为 `0` |
| `username` | string | 用户名 |
| `role` | `admin` \| `user` | 角色 |
| `is_active` | boolean | 是否启用 |
| `timezone` | string | IANA 时区 |
| `currency_code` | string | 大写币种代码或自定义代码 |
| `created_at` | string | UTC 创建时间，ISO 8601 `Z` 格式 |
| `updated_at` | string | UTC 更新时间，ISO 8601 `Z` 格式 |

#### `UserProfilePatch`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `username` | string | 否 | 1–64 字符 |
| `timezone` | string | 否 | 1–64 字符，必须是有效 IANA 时区 |
| `currency_code` | string | 否 | 3–8 字符，保存时转大写 |

出现的字段不能为 `null`；空对象 `{}` 可以提交。

#### `PasswordChange`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `current_password` | string | 是 | 1–255 字符 |
| `new_password` | string | 是 | 8–255 字符 |

#### `AdminUserCreate`

| 字段 | 类型 | 必填 | 默认值/约束 |
|---|---|---:|---|
| `username` | string | 是 | 1–64 字符 |
| `password` | string | 是 | 8–255 字符 |
| `timezone` | string | 否 | `UTC`；必须是有效 IANA 时区 |
| `currency_code` | string | 否 | `CNY`；3–8 字符，保存时转大写 |

#### `AdminUserPatch`

| 字段 | 类型 | 必填 | 默认值/说明 |
|---|---|---:|---|
| `username` | string | 否 | 1–64 字符 |
| `timezone` | string | 否 | 有效 IANA 时区 |
| `currency_code` | string | 否 | 3–8 字符，保存时转大写 |
| `revoke_sessions` | boolean | 否 | `false`；为 `true` 时撤销目标用户全部 Session |

出现的字段不能为 `null`。`revoke_sessions` 是操作参数，不是用户资源字段。

#### `AdminPasswordReset`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `password` | string | 是 | 8–255 字符 |

### 账单规则模型

`cycle_type` 支持：

| 值 | 含义 |
|---|---|
| `once` | 单次 |
| `monthly` | 每月 |
| `quarterly` | 每季度 |
| `yearly` | 每年 |
| `custom_days` | 每隔指定天数 |

#### `BillPlanCreate`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `name` | string | 是 | 1–128 字符 |
| `amount` | decimal | 是 | `> 0`，最多 14 位有效数字、2 位小数 |
| `first_due_date` | date | 是 | 首次到期日 |
| `cycle_type` | enum | 是 | 上述五种周期之一 |
| `cycle_days` | integer \| null | 条件必填 | 1–36500；仅 `custom_days` 允许且要求提供 |
| `note` | string \| null | 否 | 备注；当前没有显式长度上限 |

#### `BillPlanPatch`

字段与创建模型一致，且都可以省略。补充规则：

- `name`、`amount`、`first_due_date`、`cycle_type` 出现时不能为 `null`。
- `note: null` 用于清空备注。
- 最终周期为 `custom_days` 时必须具有 1–36500 的 `cycle_days`；请求字段越界返回 422，合并已有字段后不合法返回 `BILL_INVALID_CYCLE`。
- 非 `custom_days` 最终会清空 `cycle_days`；为非自定义周期显式提交非空 `cycle_days` 会返回错误。
- 空对象 `{}` 可以提交，不会重建未来账单。

#### `BillPlanResponse`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | 规则 ID |
| `future_bills_rebuilt` | boolean | 本次修改是否重建今日及未来账单；非修改接口通常为 `false` |
| `name` | string | 规则名称 |
| `amount` | string | 两位小数字符串 |
| `first_due_date` | date | 首次到期日 |
| `cycle_type` | string | 周期类型 |
| `cycle_days` | integer \| null | 自定义周期天数 |
| `is_enabled` | boolean | 是否启用 |
| `note` | string \| null | 备注 |
| `created_at` | string | UTC 创建时间，ISO 8601 `Z` 格式 |
| `updated_at` | string | UTC 更新时间，ISO 8601 `Z` 格式 |

### 账单实例模型

#### `BillOccurrenceResponse`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | 账单实例 ID |
| `plan_id` | integer | 所属规则 ID |
| `plan_name` | string | 当前规则名称 |
| `due_date` | date | 到期日 |
| `amount` | string | 账单实例金额快照 |
| `is_valid` | boolean | 是否计入统计和通知 |
| `time_status` | `upcoming` \| `passed` | 按用户当地今天计算 |
| `cycle_type` | string | 所属规则周期类型 |
| `cycle_days` | integer \| null | 自定义周期天数；删除规则后仍从内部历史关联返回 |

#### `ValidityPatch`

```json
{
  "is_valid": false
}
```

### 通知配置模型

#### `NotificationSettingsPatch`

虽然接口使用 `PUT`，当前实现通过 `exclude_unset` 执行局部更新；未提交的字段保留原值。

| 字段 | 类型 | 可选 | 默认值/约束 |
|---|---|---:|---|
| `email_enabled` | boolean | 是 | Schema 默认 `false` |
| `smtp_host` | string \| null | 是 | SMTP 主机 |
| `smtp_port` | integer \| null | 是 | 1–65535 |
| `smtp_security` | `none` \| `starttls` \| `ssl` \| null | 是 | SMTP 安全方式 |
| `smtp_username` | string \| null | 是 | SMTP 用户名 |
| `smtp_password` | string \| null | 是 | 只写字段 |
| `sender_email` | string \| null | 是 | 发件地址；当前只按字符串处理 |
| `sender_name` | string \| null | 是 | 发件人名称 |
| `recipient_email` | string \| null | 是 | 收件地址；当前只按字符串处理 |
| `feishu_enabled` | boolean | 是 | Schema 默认 `false` |
| `feishu_webhook` | string \| null | 是 | 只写字段 |
| `feishu_secret` | string \| null | 是 | 只写字段，可选签名密钥 |
| `advance_enabled` | boolean | 是 | Schema 默认 `false` |
| `advance_days` | integer | 是 | 默认 `3`，0–365 |
| `advance_time` | time | 是 | 默认 `09:00:00`，用户当地时间 |
| `same_day_enabled` | boolean | 是 | Schema 默认 `false` |
| `same_day_time` | time | 是 | 默认 `08:30:00`，用户当地时间 |

敏感字段 `smtp_password`、`feishu_webhook`、`feishu_secret`：

- 省略或传 `null` 会保留已有密文，不会清除。
- 传入非 `null` 值会使用 Fernet 加密后保存。
- 当前没有专门的清除敏感字段接口。
- 响应不会回显明文或密文。

启用邮件时必须具有 `smtp_host`、`smtp_port`、`smtp_security`、`sender_email` 和 `recipient_email`。启用飞书时必须已经配置 Webhook。

飞书仅接受 `https://open.feishu.cn/open-apis/bot/v2/hook/<token>` 或 `https://open.larksuite.com/open-apis/bot/v2/hook/<token>`，不允许自定义端口（443 除外）、URL 用户名密码、查询参数和片段。发送时检查 DNS 地址，只连接已验证的公网地址，不使用环境代理或跟随重定向。

SMTP 默认只允许公网地址；部署者可通过 `[security].smtp_allowed_hosts` 限制精确主机名/IP，并通过 `smtp_allow_private_hosts` 显式允许内网 SMTP。连接直接使用已验证的 DNS 结果，SSL/STARTTLS 仍按原主机名验证服务器证书。配置示例见 [通知出站限制](../README.md#通知出站限制)。

#### `NotificationSettingsResponse`

| 字段 | 类型 |
|---|---|
| `email_enabled` | boolean |
| `smtp_host` | string \| null |
| `smtp_port` | integer \| null |
| `smtp_security` | string \| null |
| `smtp_username` | string \| null |
| `smtp_password_configured` | boolean |
| `sender_email` | string \| null |
| `sender_name` | string \| null |
| `recipient_email` | string \| null |
| `feishu_enabled` | boolean |
| `feishu_webhook_configured` | boolean |
| `feishu_secret_configured` | boolean |
| `advance_enabled` | boolean |
| `advance_days` | integer |
| `advance_time` | time |
| `same_day_enabled` | boolean |
| `same_day_time` | time |

### 统计模型

`StatisticsResponse`：

```json
{
  "date": "2026-07-20",
  "today": {
    "amount": "19.90",
    "count": 1
  },
  "current_month": {
    "amount": "59.70",
    "count": 3
  },
  "averages": {
    "monthly": "42.50",
    "daily": "1.40"
  },
  "current_year": {
    "amount": "716.40",
    "count": 36
  },
  "next_bill": {
    "bill_id": 101,
    "name": "示例订阅",
    "amount": "19.90",
    "due_date": "2026-07-20",
    "days_remaining": 0
  }
}
```

`next_bill` 没有可用账单时为 `null`。`averages` 当前固定包含 `monthly` 和 `daily`。

### 日志文件模型

`LogFileResponse`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `date` | string | 从日志文件名取得的 UTC 日期 |
| `filename` | string | 文件名，例如 `2026-07-20.log` |
| `size` | integer | 文件字节数 |
| `modified_at` | string | UTC 最后修改时间，ISO 8601 `Z` 格式 |

## API 总表

| # | 方法 | 路径 | 权限 | 成功状态 |
|---:|---|---|---|---:|
| 1 | POST | `/api/v1/auth/login` | 公开 | 200 |
| 2 | POST | `/api/v1/auth/logout` | 当前用户 | 204 |
| 3 | GET | `/api/v1/auth/me` | 当前用户 | 200 |
| 4 | PATCH | `/api/v1/me/profile` | 当前用户 | 200 |
| 5 | PUT | `/api/v1/me/password` | 当前用户 | 204 |
| 6 | GET | `/api/v1/admin/summary` | 管理员 | 200 |
| 7 | GET | `/api/v1/admin/users` | 管理员 | 200 |
| 8 | POST | `/api/v1/admin/users` | 管理员 | 201 |
| 9 | GET | `/api/v1/admin/users/{user_id}` | 管理员 | 200 |
| 10 | PATCH | `/api/v1/admin/users/{user_id}` | 管理员 | 200 |
| 11 | PUT | `/api/v1/admin/users/{user_id}/password` | 管理员 | 204 |
| 12 | POST | `/api/v1/admin/users/{user_id}/disable` | 管理员 | 204 |
| 13 | POST | `/api/v1/admin/users/{user_id}/enable` | 管理员 | 200 |
| 14 | POST | `/api/v1/plans` | 当前用户 | 201 |
| 15 | GET | `/api/v1/plans` | 当前用户 | 200 |
| 16 | GET | `/api/v1/plans/{plan_id}` | 当前用户 | 200 |
| 17 | PATCH | `/api/v1/plans/{plan_id}` | 当前用户 | 200 |
| 18 | DELETE | `/api/v1/plans/{plan_id}` | 当前用户 | 204 |
| 19 | POST | `/api/v1/plans/{plan_id}/disable` | 当前用户 | 204 |
| 20 | POST | `/api/v1/plans/{plan_id}/enable` | 当前用户 | 200 |
| 21 | GET | `/api/v1/bills` | 当前用户 | 200 |
| 22 | GET | `/api/v1/bills/{bill_id}` | 当前用户 | 200 |
| 23 | PATCH | `/api/v1/bills/{bill_id}/validity` | 当前用户 | 200 |
| 24 | GET | `/api/v1/statistics/summary` | 当前用户 | 200 |
| 25 | GET | `/api/v1/me/notification-settings` | 当前用户 | 200 |
| 26 | PUT | `/api/v1/me/notification-settings` | 当前用户 | 200 |
| 27 | POST | `/api/v1/me/notification-settings/test-email` | 当前用户 | 204 |
| 28 | POST | `/api/v1/me/notification-settings/test-feishu` | 当前用户 | 204 |
| 29 | GET | `/api/v1/me/logs` | 当前用户 | 200 |
| 30 | GET | `/api/v1/me/logs/download` | 当前用户 | 200 |
| 31 | GET | `/api/v1/admin/users/{user_id}/logs` | 管理员 | 200 |
| 32 | GET | `/api/v1/admin/users/{user_id}/logs/download` | 管理员 | 200 |
| 33 | GET | `/api/v1/admin/system-logs` | 管理员 | 200 |
| 34 | GET | `/api/v1/admin/system-logs/download` | 管理员 | 200 |
| 35 | GET | `/health` | 公开 | 200 或 503 |
| 36 | GET | `/api/v1/admin/runtime` | 管理员 | 200 |
| 37 | GET | `/api/v1/me/notification-records` | 当前用户 | 200 |

## 认证 API

### `POST /api/v1/auth/login`

登录并创建新的服务端 Session。

- 权限：公开
- 请求体：`LoginRequest`
- 成功：`200 UserResponse`
- 响应头：设置 Session Cookie
- 副作用：创建新的 Session；不会撤销其他设备的已有 Session

特有错误：

| 状态 | `code` | 条件 |
|---:|---|---|
| 401 | `AUTH_INVALID_CREDENTIALS` | 用户不存在、已停用或密码错误 |
| 429 | `AUTH_RATE_LIMITED` | 来源或账号达到登录失败阈值 |

用户不存在、停用和密码错误使用相同错误，避免直接泄露账号状态。

### `POST /api/v1/auth/logout`

- 权限：当前用户
- 请求参数/请求体：无
- 成功：`204 No Content`
- 副作用：撤销当前 Session，并删除当前路径下的 Session Cookie

如果 Cookie 已经无效，认证依赖会先返回 `AUTH_SESSION_INVALID`。

### `GET /api/v1/auth/me`

- 权限：当前用户
- 请求参数/请求体：无
- 成功：`200 UserResponse`

## 当前用户 API

### `PATCH /api/v1/me/profile`

- 权限：当前用户
- 请求体：`UserProfilePatch`
- 成功：`200 UserResponse`
- 行为：仅更新请求中出现的字段；`currency_code` 转为大写

| 状态 | `code` | 条件 |
|---:|---|---|
| 409 | `USER_USERNAME_CONFLICT` | 用户名已被其他用户占用 |

### `PUT /api/v1/me/password`

- 权限：当前用户
- 请求体：`PasswordChange`
- 成功：`204 No Content`
- 副作用：更新 Argon2 密码哈希并撤销该用户全部 Session，包括当前 Session

| 状态 | `code` | 条件 |
|---:|---|---|
| 400 | `AUTH_INVALID_PASSWORD` | 当前密码错误 |

浏览器中的 Cookie 不会在该接口中主动删除，但后续请求会因服务器端 Session 已撤销而返回 `AUTH_SESSION_INVALID`。

## 管理员用户 API

`GET /api/v1/admin/summary` 返回 `total_users`（含管理员）、`active_users` 和 `inactive_users`（仅普通用户）。0.1.4 起移除配额及剩余名额字段；旧配置 `app.max_users` 会被忽略。

### `GET /api/v1/admin/users`

- 权限：管理员
- Query：`q`（用户名包含搜索，忽略大小写，最多 64 字符）、`is_active`（可选布尔值）、`page`（默认 1）、`page_size`（默认 20，范围 1–100）
- 成功：`200 {items: list[UserResponse], page, page_size, total}`
- 行为：返回管理员和普通用户，按 `id` 升序；查询条件取交集，搜索中的 `%`、`_` 按普通字符处理
- 兼容变化：0.1.4 起使用分页对象，旧客户端需要调整

### `POST /api/v1/admin/users`

- 权限：管理员
- 请求体：`AdminUserCreate`
- 成功：`201 UserResponse`
- 行为：创建启用的普通用户及默认通知配置；不限制账户数量；用户 ID 使用当前最大 ID 加 1，在管理员行锁下使用当前读，防止并发创建分配重复 ID

| 状态 | `code` | 条件 |
|---:|---|---|
| 409 | `USER_USERNAME_CONFLICT` | 用户名已存在 |
| 409 | `NOTIFICATION_SETTINGS_CHANGED` | DNS 校验期间通知配置被其他请求修改，需重新加载 |

### `GET /api/v1/admin/users/{user_id}`

- 权限：管理员
- Path：`user_id`，integer
- 成功：`200 UserResponse`
- 说明：允许读取 `user_id=0` 的管理员

| 状态 | `code` | 条件 |
|---:|---|---|
| 404 | `USER_NOT_FOUND` | 用户不存在 |

### `PATCH /api/v1/admin/users/{user_id}`

- 权限：管理员
- Path：`user_id`，integer
- 请求体：`AdminUserPatch`
- 成功：`200 UserResponse`
- 行为：部分更新普通用户；`revoke_sessions=true` 时撤销目标用户全部 Session

| 状态 | `code` | 条件 |
|---:|---|---|
| 404 | `USER_NOT_FOUND` | 普通用户不存在，或 `user_id=0` |
| 409 | `USER_USERNAME_CONFLICT` | 用户名已存在 |
| 409 | `NOTIFICATION_SETTINGS_CHANGED` | DNS 校验期间通知配置被其他请求修改，需重新加载 |

### `PUT /api/v1/admin/users/{user_id}/password`

- 权限：管理员
- Path：`user_id`，integer
- 请求体：`AdminPasswordReset`
- 成功：`204 No Content`
- 副作用：重置密码并撤销目标用户全部 Session

| 状态 | `code` | 条件 |
|---:|---|---|
| 404 | `USER_NOT_FOUND` | 普通用户不存在，或 `user_id=0` |

### `POST /api/v1/admin/users/{user_id}/disable`

- 权限：管理员
- Path：`user_id`，integer
- 请求体：无
- 成功：`204 No Content`
- 副作用：停用普通用户并撤销其全部 Session

| 状态 | `code` | 条件 |
|---:|---|---|
| 404 | `USER_NOT_FOUND` | 普通用户不存在，或 `user_id=0` |

### `POST /api/v1/admin/users/{user_id}/enable`

- 权限：管理员
- Path：`user_id`，integer
- 请求体：无
- 成功：`200 UserResponse`
- 副作用：启用普通用户，并按该用户时区为其所有启用规则补齐账单实例

| 状态 | `code` | 条件 |
|---:|---|---|
| 404 | `USER_NOT_FOUND` | 普通用户不存在，或 `user_id=0` |

## 账单规则 API

所有规则接口只访问当前用户资源。规则不存在或属于其他用户时统一返回 `404 BILL_PLAN_NOT_FOUND`。

### `POST /api/v1/plans`

- 权限：当前用户
- 请求体：`BillPlanCreate`
- 成功：`201 BillPlanResponse`
- 行为：新规则默认为启用；生成所需账单实例

重复规则的首次日期早于今天时，只补建当前用户当地自然年 1 月 1 日至昨天范围内应有的历史实例，再保证当前及未来至少存在两笔实例；不会补建更早年份。单次规则只创建其唯一日期对应的实例。

### `GET /api/v1/plans`

- 权限：当前用户
- 请求参数/请求体：无
- 成功：`200 list[BillPlanResponse]`
- 行为：包含启用和停用规则，按规则 ID 降序；不分页

### `GET /api/v1/plans/{plan_id}`

- 权限：当前用户
- Path：`plan_id`，integer
- 成功：`200 BillPlanResponse`

| 状态 | `code` | 条件 |
|---:|---|---|
| 404 | `BILL_PLAN_NOT_FOUND` | 规则不存在或不属于当前用户 |

### `PATCH /api/v1/plans/{plan_id}`

- 权限：当前用户
- Path：`plan_id`，integer
- 请求体：`BillPlanPatch`
- 成功：`200 BillPlanResponse`

副作用：

- 修改 `first_due_date`、`cycle_type` 或最终 `cycle_days` 时，删除该规则今日及未来的通知记录和账单实例，然后按新排期重建；响应 `future_bills_rebuilt=true`。
- 只修改金额时，更新今日及未来实例的金额快照；历史金额保持原值。
- 修改名称不会保存名称快照，因此历史账单响应也会显示当前规则名称。
- 只修改名称、备注或不改变排期时，`future_bills_rebuilt=false`。

| 状态 | `code` | 条件 |
|---:|---|---|
| 400 | `BILL_INVALID_CYCLE` | 最终周期和 `cycle_days` 组合不合法 |
| 404 | `BILL_PLAN_NOT_FOUND` | 规则不存在或不属于当前用户 |

### `DELETE /api/v1/plans/{plan_id}`

- 权限：当前用户
- Path：`plan_id`，integer
- 请求体：无
- 成功：`204 No Content`
- 副作用：按当前用户时区将规则永久删除；保留 `due_date < today` 的已过账单和历史提醒记录，删除 `due_date >= today` 的账单及提醒记录。今天属于未过账单范围。

删除后规则不会再出现在规则列表或详情中，不能编辑、启用、停用或恢复，也不会再参与补账、未来统计推算和提醒。数据库只保留内部规则墓碑，以维持已过账单的 `plan_id`、规则名称和周期关联；该内部记录不属于可恢复资源。提醒记录先于未过账单删除，全部变化在同一数据库事务中提交。

| 状态 | `code` | 条件 |
|---:|---|---|
| 404 | `BILL_PLAN_NOT_FOUND` | 规则不存在、不属于当前用户或已经删除 |

### `POST /api/v1/plans/{plan_id}/disable`

- 权限：当前用户
- Path：`plan_id`，integer
- 请求体：无
- 成功：`204 No Content`
- 副作用：停用规则，并将今日及未来实例设为无效；历史实例不变

服务端会记录哪些实例原本有效且因规则停用而失效，以便后续有选择地恢复。

### `POST /api/v1/plans/{plan_id}/enable`

- 权限：当前用户
- Path：`plan_id`，integer
- 请求体：无
- 成功：`200 BillPlanResponse`
- 副作用：启用规则，只恢复此前因规则停用而失效的今日及未来实例；用户手动设为无效的实例不会恢复；随后补齐未来实例

## 账单实例 API

### `GET /api/v1/bills`

- 权限：当前用户
- 成功：`200 BillOccurrencePage`
- 所有筛选条件使用 AND 组合

| Query 参数 | 类型 | 默认值 | 约束/说明 |
|---|---|---|---|
| `start_date` | date \| null | `null` | `due_date >= start_date`，闭区间 |
| `end_date` | date \| null | `null` | `due_date <= end_date`，闭区间 |
| `time_status` | string \| null | `null` | `upcoming` 或 `passed` |
| `is_valid` | boolean \| null | `null` | 有效性筛选 |
| `plan_id` | integer \| null | `null` | 规则 ID；其他用户的规则只会得到空结果 |
| `q` | string \| null | `null` | 名称包含搜索，忽略大小写，最多 128 字符；通配符按普通字符处理 |
| `sort` | string | `asc` | `asc` / `desc`，日期与 ID 同向排序 |
| `page` | integer | `1` | `>= 1` |
| `page_size` | integer | `20` | 1–200 |

结果按 `due_date`、`id` 同向排序，响应为 `{items, page, page_size, total}`。`sort` 默认为 `asc`，可设为 `desc`。`start_date > end_date` 返回 `400 INVALID_DATE_RANGE`。

页面默认传入 `time_status=upcoming&sort=asc`；接口不传参数仍查询全部账单并升序排列。名称搜索关联规则当前名称，包含已删除规则保留的历史账单，仍严格限定当前用户。

### `GET /api/v1/bills/{bill_id}`

- 权限：当前用户
- Path：`bill_id`，integer
- 成功：`200 BillOccurrenceResponse`

| 状态 | `code` | 条件 |
|---:|---|---|
| 404 | `BILL_OCCURRENCE_NOT_FOUND` | 实例不存在或不属于当前用户 |

### `PATCH /api/v1/bills/{bill_id}/validity`

- 权限：当前用户
- Path：`bill_id`，integer
- 请求体：`ValidityPatch`
- 成功：`200 BillOccurrenceResponse`
- 行为：手动设置实例有效性，并清除“因规则停用而失效”标记

| 状态 | `code` | 条件 |
|---:|---|---|
| 400 | `BILL_PLAN_DISABLED` | 尝试恢复停用规则下今日或未来实例 |
| 404 | `BILL_OCCURRENCE_NOT_FOUND` | 实例不存在或不属于当前用户 |

停用规则下的历史实例可以恢复有效；限制只适用于用户当地今天及未来。

## 账单周期与实例生成规则

- `once` 只有 `first_due_date` 一笔实例。
- `custom_days` 从首次日期起，每隔 `cycle_days` 天生成。
- `monthly`、`quarterly`、`yearly` 始终基于首次日期计算目标月份。
- 目标月份没有首次日期对应日号时，使用该月最后一天。例如 1 月 31 日的月周期在 2 月落到 28/29 日，3 月仍回到 31 日。
- 启用的重复规则会在实例少于两笔时补足至少两笔 `due_date >= 用户当地今天` 的实例；该逻辑不会主动删除异常存在的多余未来实例。
- 账单实例保存金额快照，不保存名称快照。
- 无效实例仍属于账单数据，但不计入统计，不触发通知。
- 日期达到可表示上界时停止生成；遗留的超大正周期不会使日期迭代溢出。
- 账单修改先锁定规则，再锁定并刷新参与修改的账单，避免 MySQL 事务旧快照覆盖并发变更。

## 统计 API

### `GET /api/v1/statistics/summary`

- 权限：当前用户
- 请求参数/请求体：无
- 成功：`200 StatisticsResponse`

统计口径：

- `date` 是用户当地今天。
- `today`、`current_month`、`current_year` 只统计有效账单实例。
- 对今天及未来尚未持久化的启用重复规则，服务会按规则推算金额和笔数；停用规则和 `once` 不参与推算。
- 历史缺失实例不会通过规则反向推算。
- `averages` 只使用启用中的非单次规则，并固定按 365 天换算，不按闰年调整。
- `next_bill` 只从已持久化、有效且未过期的实例中查询，不即时推算未落库实例。

## 通知 API

### `GET /api/v1/me/notification-settings`

- 权限：当前用户
- 请求参数/请求体：无
- 成功：`200 NotificationSettingsResponse`

| 状态 | `code` | 条件 |
|---:|---|---|
| 404 | `NOTIFICATION_SETTINGS_NOT_FOUND` | 用户通知配置记录不存在 |

### `PUT /api/v1/me/notification-settings`

- 权限：当前用户
- 请求体：`NotificationSettingsPatch`
- 成功：`200 NotificationSettingsResponse`
- 行为：局部更新；敏感字段加密保存，响应只返回是否已配置

| 状态 | `code` | 条件 |
|---:|---|---|
| 400 | `EMAIL_SETTINGS_INCOMPLETE` | 启用邮件但必要配置不完整 |
| 400 | `FEISHU_SETTINGS_INCOMPLETE` | 启用飞书但未配置 Webhook |
| 400 | `SMTP_TARGET_NOT_ALLOWED` | SMTP 目标不满足服务器出站限制或 DNS 解析失败 |
| 400 | `FEISHU_WEBHOOK_NOT_ALLOWED` | Webhook 不是允许的官方 HTTPS 机器人地址 |
| 404 | `NOTIFICATION_SETTINGS_NOT_FOUND` | 通知配置记录不存在 |

### `POST /api/v1/me/notification-settings/test-email`

- 权限：当前用户
- 请求参数/请求体：无
- 成功：`204 No Content`
- 行为：使用已保存配置实际连接 SMTP 并发送测试邮件，DNS 与网络发送使用可配置的独立预算，默认 DNS 5 秒、发送阶段总计 30 秒

| 状态 | `code` | 条件 |
|---:|---|---|
| 400 | `EMAIL_SETTINGS_INCOMPLETE` | 当前启用的邮件配置不完整 |
| 400 | `FEISHU_SETTINGS_INCOMPLETE` | 当前启用的飞书配置不完整；测试前会检查所有启用渠道 |
| 400 | `NETWORK_TIMEOUT` / `NETWORK_ERROR` / `SMTP_REJECTED` 等 | 测试发送失败，详见发送与重试语义 |
| 404 | `NOTIFICATION_SETTINGS_NOT_FOUND` | 通知配置记录不存在 |

测试接口不要求 `email_enabled=true`，但必须具有可用于实际发送的保存配置。

### `POST /api/v1/me/notification-settings/test-feishu`

- 权限：当前用户
- 请求参数/请求体：无
- 成功：`204 No Content`
- 行为：使用已保存 Webhook 实际发送飞书测试消息，DNS 与网络发送使用可配置的独立预算，默认 DNS 5 秒、发送阶段总计 30 秒

| 状态 | `code` | 条件 |
|---:|---|---|
| 400 | `EMAIL_SETTINGS_INCOMPLETE` | 当前启用的邮件配置不完整；测试前会检查所有启用渠道 |
| 400 | `FEISHU_SETTINGS_INCOMPLETE` | 当前启用的飞书配置不完整 |
| 400 | `WEBHOOK_HTTP_ERROR` / `WEBHOOK_REJECTED` / `DELIVERY_UNKNOWN` 等 | 测试失败或结果待核实 |
| 404 | `NOTIFICATION_SETTINGS_NOT_FOUND` | 通知配置记录不存在 |

### 自动通知语义

- 支持 SMTP 邮件和飞书机器人两个独立渠道。
- 支持提前提醒和到期日当天提醒；时间按用户时区解释。
- 调度任务到达或超过配置时间后尝试发送，不要求精确命中某一分钟。
- 通知以 `plan_id + due_date + channel + reminder_type` 防重。
- DNS 校验后按用户、通知设置、规则、账单、通知记录的顺序锁定并读取最新状态，避免旧事务快照重复发送已成功的记录。
- 已成功、结果未知、明确配置错误或已尝试 3 次的记录不再自动发送；临时故障按 60/300 秒间隔重试，且不跨提醒日期。
- SMTP 已接受邮件后的连接关闭异常不会改判发送失败；其余异常按是否明确拒绝、可重试或提交后结果未知分类。
- 单个用户或规则检查异常会回滚相应事务并记录错误，继续处理其他规则和用户。
- 尚未生成账单实例时可以依据启用规则推算提醒；如果实例已存在且无效，则跳过。
- 外部服务可能已收到消息但数据库状态尚未提交，因此系统不保证严格的 exactly-once。

## 日志 API

日志文件是 NDJSON/JSON Lines，每行包含：

```json
{
  "timestamp": "2026-07-20T12:00:00.000000Z",
  "level": "INFO",
  "module": "http",
  "event": "request_completed",
  "request_id": "9c5ac919e0064a6f9d722194486c2a71",
  "user_id": null,
  "result": "success",
  "message": "HTTP request completed",
  "data": {}
}
```

日志按 UTC 日期写入系统目录或用户目录。`password`、`token`、`cookie`、`webhook`、`secret`、`authorization` 等敏感键的值会递归替换为 `[REDACTED]`；脱敏依据键名，不扫描普通字符串内容。

目录创建或文件写入发生 I/O/编码异常时，脱敏后的日志转写标准错误并附带 `log_write_error` 异常类型，不改变已经成功提交的业务响应。标准错误也不可写时放弃该条日志，避免进一步影响服务；日志查询和下载仍会如实报告文件读取失败。

### `GET /api/v1/me/logs`

- 权限：当前用户
- 成功：`200 list[LogFileResponse]`
- 行为：只列出当前用户日志，文件名倒序；不分页

### `GET /api/v1/me/logs/download`

- 权限：当前用户
- Query：`filename`，可选 string
- 成功：文件响应

| 调用方式 | 响应 |
|---|---|
| 提供 `filename` | 单个日志，`application/x-ndjson` |
| 省略 `filename` | 当前用户全部保留日志的 ZIP，`application/zip` |

`filename` 必须是不含目录的 basename、以 `.log` 结尾且实际存在，否则返回 `404 LOG_NOT_FOUND`。

### `GET /api/v1/admin/users/{user_id}/logs`

- 权限：管理员
- Path：`user_id`，integer
- 成功：`200 list[LogFileResponse]`
- 说明：按目录列出指定用户日志，不验证用户数据库记录是否存在；无日志时返回 `[]`

### `GET /api/v1/admin/users/{user_id}/logs/download`

- 权限：管理员
- Path：`user_id`，integer
- Query：`filename`，可选 string
- 成功：单个 NDJSON 或全部 ZIP
- 错误：`404 LOG_NOT_FOUND`

### `GET /api/v1/admin/system-logs`

- 权限：管理员
- 成功：`200 list[LogFileResponse]`
- 行为：列出系统日志，文件名倒序；不分页

### `GET /api/v1/admin/system-logs/download`

- 权限：管理员
- Query：`filename`，可选 string
- 成功：单个 NDJSON 或全部 ZIP
- 错误：`404 LOG_NOT_FOUND`

## 健康检查

### `GET /health`

- 权限：公开
- 请求参数/请求体：无
- 成功或降级响应：

```json
{
  "status": "ok",
  "application": "ok",
  "database": "ok",
  "scheduler": "ok"
}
```

数据库异常、调度器未运行或任务异常达到健康阈值时返回 HTTP 503 和 `status: "degraded"`；调度器关闭时 `scheduler` 为 `"disabled"`，服务仍可健康。

| HTTP 状态 | 条件 |
|---:|---|
| 200 | 数据库可连接，并且调度器已禁用或运行且任务健康 |
| 503 | 数据库不可连接、调度器已启用但未运行，或任务持续失败/逾期/超时 |

调度器配置为禁用时，`scheduler` 为 `"disabled"`，但只要数据库正常，`status` 仍为 `ok`。

## 错误码索引

账单查询新增 `400 INVALID_DATE_RANGE`：开始日期晚于结束日期。

| HTTP 状态 | `code` | 含义 |
|---:|---|---|
| 400 | `AUTH_INVALID_PASSWORD` | 当前密码错误 |
| 400 | `BILL_INVALID_CYCLE` | 周期与周期天数组合不合法 |
| 400 | `BILL_PLAN_DISABLED` | 不能恢复停用规则下当前或未来账单 |
| 400 | `EMAIL_SETTINGS_INCOMPLETE` | 已启用的邮件配置不完整 |
| 400 | `FEISHU_SETTINGS_INCOMPLETE` | 已启用的飞书配置不完整 |
| 400 | `NETWORK_TIMEOUT` / `NETWORK_ERROR` / `SMTP_REJECTED` 等 | 测试发送失败，详见发送与重试语义 |
| 400 | `WEBHOOK_HTTP_ERROR` / `WEBHOOK_REJECTED` / `DELIVERY_UNKNOWN` 等 | 测试失败或结果待核实 |
| 400 | `SMTP_TARGET_NOT_ALLOWED` | SMTP 目标不满足服务器出站限制或无法解析 |
| 400 | `FEISHU_WEBHOOK_NOT_ALLOWED` | 非允许的官方 HTTPS 机器人 Webhook |
| 401 | `AUTH_REQUIRED` | 缺少 Session Cookie |
| 401 | `AUTH_SESSION_INVALID` | Session 已失效或用户不可用 |
| 401 | `AUTH_INVALID_CREDENTIALS` | 用户名或密码错误 |
| 403 | `PERMISSION_DENIED` | 需要 `id=0` 管理员权限 |
| 404 | `USER_NOT_FOUND` | 用户或可操作普通用户不存在 |
| 404 | `BILL_PLAN_NOT_FOUND` | 账单规则不存在或不属于当前用户 |
| 404 | `BILL_OCCURRENCE_NOT_FOUND` | 账单实例不存在或不属于当前用户 |
| 404 | `NOTIFICATION_SETTINGS_NOT_FOUND` | 通知配置不存在 |
| 404 | `LOG_NOT_FOUND` | 日志文件不存在或文件名不合法 |
| 409 | `USER_USERNAME_CONFLICT` | 用户名已存在 |
| 409 | `NOTIFICATION_SETTINGS_CHANGED` | DNS 校验期间通知配置被其他请求修改，需重新加载 |
| 422 | `INVALID_REQUEST` | Path、Query 或 Body 格式/字段校验失败 |
| 429 | `AUTH_RATE_LIMITED` | 登录失败尝试达到限流阈值 |
| 500 | `INTERNAL_ERROR` | 未处理的服务端错误 |

## curl 示例

以下示例仅使用占位账号和本地地址。先设置：

```bash
BASE_URL=http://127.0.0.1:8000
COOKIE_JAR=/tmp/subledger-cookie.txt
```

### 登录并保存 Cookie

```bash
curl -i \
  -c "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"replace-with-your-password"}' \
  "$BASE_URL/api/v1/auth/login"
```

### 获取当前用户

```bash
curl -b "$COOKIE_JAR" "$BASE_URL/api/v1/auth/me"
```

### 创建月周期规则

```bash
curl -b "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"示例订阅",
    "amount":"19.90",
    "first_due_date":"2026-07-20",
    "cycle_type":"monthly",
    "note":"API 文档示例"
  }' \
  "$BASE_URL/api/v1/plans"
```

### 筛选并分页查询账单

```bash
curl -b "$COOKIE_JAR" \
  "$BASE_URL/api/v1/bills?start_date=2026-07-01&end_date=2026-12-31&time_status=upcoming&is_valid=true&page=1&page_size=50"
```

### 管理员创建普通用户

```bash
curl -b "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  -d '{
    "username":"example-user",
    "password":"replace-with-a-strong-password",
    "timezone":"Asia/Shanghai",
    "currency_code":"CNY"
  }' \
  "$BASE_URL/api/v1/admin/users"
```

### 查看并下载日志

```bash
curl -b "$COOKIE_JAR" "$BASE_URL/api/v1/me/logs"

curl -b "$COOKIE_JAR" \
  -OJ "$BASE_URL/api/v1/me/logs/download?filename=2026-07-20.log"

curl -b "$COOKIE_JAR" \
  -OJ "$BASE_URL/api/v1/me/logs/download"
```

### 健康检查

```bash
curl -i "$BASE_URL/health"
```

## 当前限制与集成注意事项

- 必须使用单 Uvicorn worker。APScheduler、登录限流和文件日志都位于 Web 应用进程内。
- 当前不提供公开注册、用户物理删除或单独删除账单实例接口；账单规则删除使用不可恢复的应用级删除，并为已过账单保留内部历史关联。
- 当前没有显式 CSRF Token 或 Origin 校验，也没有配置 CORS 中间件；Cookie 认证应优先配合同源前端，并由部署环境控制外部访问边界。
- 生产构建将前端 `dist/` 复制到后端镜像；FastAPI 托管静态文件并对不含扩展名的前端 GET/HEAD 路径回退 `index.html`。`/api/*`、`/health`、文档路由和缺失静态资源不会回退。
- `/docs`、`/redoc`、`/openapi.json` 默认公开；是否允许外部访问由部署环境决定。
- 普通用户配置的通知地址受服务器出站限制；内网 SMTP 需要部署者显式允许，飞书仅使用官方 HTTPS 机器人地址。
- 在线 OpenAPI 未完整标注 Cookie security scheme、业务错误、`X-Request-ID`、日志文件响应和 `/health` 的 503；不要只依赖自动文档生成客户端安全策略。
- 普通 Docker Compose 的默认入口为 `127.0.0.1:8081`，直接运行的默认入口为 `127.0.0.1:8000`；1Panel 专用编排不映射宿主机端口。具体启动和维护步骤见 [项目安装与部署](../README.md#安装与部署)。

## 0.1.5 实现与兼容性

- 认证会话创建前以 `User FOR UPDATE` 当前读再次核对账户状态和已验证的密码哈希。密码修改、管理员重置、停用和撤销会话统一采用用户 → 会话的锁顺序；重置先完成则拒绝旧凭据，登录先完成则其会话随后被撤销。
- 通知尝试按用户 → 通知设置 → 规则 → 账单 → 提醒记录顺序锁定并重新校验。账单写入也先获取用户共享锁，再锁规则，避免外键检查产生相反锁顺序。网络发送保留在事务中，由外层检查循环统一提交或回滚，保持去重和用户间故障隔离；不承诺跨外部发送与数据库提交的恰好一次投递。
- 统计加载一次规则和全年账单，复用当天/月/年计算，另查询下一笔账单，共 3 次查询。保留金额快照、无效账单、已删除规则历史和未来推算口径；补全周期规则只读取今天及以后账单，一次性规则只检查首次日期。
- 通知配置的 SMTP 主机/用户名、发件/收件邮箱最大 255 字符，发件人名称最大 128 字符，超限返回标准 422 验证响应。
- TOML 布尔、整数、字符串类型严格校验；弃用的 `app.host`、`app.port` 被忽略并警告。`logging.level` 支持 DEBUG、INFO、WARNING、ERROR、CRITICAL，实际过滤低等级记录；失败事件可显式指定 `result="failure"`。归档跳过已轮转删除的文件，其他异常清理临时 ZIP。
- 运行依赖移除 `python-multipart`，`httpx` 移入 `[test]`。开发测试使用 `pip install -e './backend[test]'`。无需数据库迁移或接口响应适配。

## 0.1.6 运行状态与通知记录

### 管理员任务状态

`GET /api/v1/admin/runtime` 仅管理员（ID 0）可访问。返回 `{status, tasks}`，整体状态为 `ok / error / disabled`。每个任务包括 `id`、`name`、`status`、`running`、`next_run_at`、`last_started_at`、`last_finished_at`、`last_success_at`、`duration_seconds`、`consecutive_failures`、`last_error` 与 `counts`；时间为 UTC，尚无数据时为 null。状态包括 `waiting / running / ok / warning / error / disabled`。

`/health` 保留原响应字段，调度器状态纳入任务判断：连续执行失败 3 次、未执行且超过预定时间宽限，或运行超过 `scheduler.task_timeout_seconds`（默认 900 秒）时返回 503。通知任务宽限为两倍检查间隔且至少 120 秒，日任务宽限 600 秒；正在执行且未超时的任务不按未执行逾期处理。首次执行未到时间、关闭调度均不误报。渠道失败汇总为 `counts.failed/unknown` 并显示 warning，业务检查/数据库异常计入 `counts.errors` 与连续失败。状态仅保存在本次进程内，历史执行结果写系统日志。

新增过期会话任务在应用时区 `session_cleanup_hour`（默认 2）执行；按 `expires_at <= UTC 当前时间` 使用到期索引选取，每批 500 条、每轮最多 10000 条。使用短事务和跳过已锁定记录，下一轮继续清理剩余数据，保留未过期会话。

### 个人通知记录

`GET /api/v1/me/notification-records` 返回 `{items, page, page_size, total}`，只查询当前用户记录。参数：

| 参数 | 说明 |
| --- | --- |
| `channel` | `email / feishu`；省略表示全部 |
| `status` | `pending / retry_wait / sent / failed / unknown / expired` |
| `start_date`、`end_date` | 按账户时区的计划提醒日期筛选，包含两端；倒置返回 `400 INVALID_DATE_RANGE` |
| `page`、`page_size` | 默认 1、20；每页 1–100 条 |

按 `scheduled_at DESC, id DESC` 稳定排序。每条记录包含 `id`、`plan_id`、`plan_name`、`due_date`、`channel`、`reminder_type`、`status`、`scheduled_at`、`sent_at`、`attempt_count`、`last_attempt_at`、`next_retry_at`、`error_code`、`error_message`。错误消息为安全映射，不返回原始异常、服务器响应或凭据。过去日期中仍待处理/待重试的记录展示为 `expired`，不补发。历史记录的尝试时间未知时保留 null。

每个业务键只保存一条最新结果，测试发送不写账单提醒记录。删除规则仍按原语义清理今天及未来关联通知记录，记录查询不改变这项规则。

### 发送与重试语义

DNS 在获取数据库行锁前完成，结果限制为允许的地址并绑定连接 IP，TLS 仍验证原域名；获取锁后重新核对配置版本、用户状态、提醒窗口及规则。配置在解析期间改变时跳过本次候选，下轮重新检查。配置保存也先完成出站校验，再加锁复核版本；并发修改返回 `409 NOTIFICATION_SETTINGS_CHANGED`，客户端应重新加载。

`[notifications]` 支持 `dns_timeout_seconds = 5`、`connect_timeout_seconds = 5`、`send_timeout_seconds = 30`。DNS 等待范围 1–30 秒，连接与发送范围为 `1 <= connect <= send <= 120`。DNS 最多 4 个后台解析线程、无等待队列，超时后只有解析继续，不能发送消息。发送始终在事务所在调用线程执行，网络预算耗尽时关闭所有关联套接字，使 TLS、慢速响应正文和多地址尝试受同一截止时间控制；数据库锁等待不属于网络预算。

最多 3 次尝试。可重试的网络连接故障、SMTP 4xx 和 Webhook HTTP 429/5xx，在上次失败后 60/300 秒具备重试资格，下一轮检查才执行；明确拒绝或配置错误停止自动重试。消息提交后连接中断或响应不可确认则标记 `unknown` 并停止自动重发；明确的 SMTP/HTTP 拒绝仍按错误类别处理。第三次失败或下一次重试跨越原提醒日期后停止自动重试。成功记录永不重发，SMTP 已接受消息后关闭连接失败不会改判失败。进程崩溃、数据库提交失败与外部渠道无法原子提交，不能提供严格只送达一次的保证。

测试发送成功仍返回 204，失败返回 400，使用与记录相同的脱敏错误码；结果未知使用 `DELIVERY_UNKNOWN`，提示先核实是否收到消息。

### 升级验证

迁移 `0003_notification_attempts` 增加四个字段，并按旧 `retry_count` 推导尝试次数；已发送不变，未耗尽的失败转为待重试，旧发送中转为结果未知，缺失的历史尝试时间不伪造。回滚需恢复升级前备份。

本版本的回归覆盖任务状态与权限、分批清理、DNS/发送超时、重试间隔及上限、配置变更、结果未知、查询隔离；MySQL 测试验证实际迁移、重复升级、DNS 阶段无用户锁、超时后释放锁与清理/登录并发。
