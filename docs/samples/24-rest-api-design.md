# REST API 设计规范

## URL 设计

### 资源命名

- 使用名词复数：`/api/users` 而非 `/api/getUser`
- 层级关系通过路径表示：`/api/users/{id}/orders`
- 筛选和分页用查询参数：`?page=1&limit=20&status=active`
- 动词通过 HTTP 方法体现

| 方法 | 操作 | 幂等 | 示例 |
|------|------|:----:|------|
| GET | 读取 | ✅ | `GET /api/users/42` |
| POST | 创建 | ❌ | `POST /api/users` |
| PUT | 全量替换 | ✅ | `PUT /api/users/42` |
| PATCH | 部分更新 | ❌ | `PATCH /api/users/42` |
| DELETE | 删除 | ✅ | `DELETE /api/users/42` |

## 状态码

- **200 OK**：请求成功
- **201 Created**：资源创建成功（POST）
- **204 No Content**：删除成功，无返回体
- **400 Bad Request**：请求参数错误
- **401 Unauthorized**：未认证
- **403 Forbidden**：无权限
- **404 Not Found**：资源不存在
- **409 Conflict**：资源冲突（如重复创建）
- **422 Unprocessable Entity**：验证失败
- **429 Too Many Requests**：限流
- **500 Internal Server Error**：服务端错误

## 请求与响应

### 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

### 错误响应

```json
{
  "code": 40001,
  "message": "参数校验失败",
  "errors": [{"field": "email", "message": "邮箱格式不正确"}]
}
```

## 安全

- 使用 HTTPS（TLS 1.2+）
- 认证：JWT（Bearer Token）/ OAuth 2.0
- 限流：基于 IP 或 Token，返回 429 + Retry-After 头
- 输入校验：白名单校验，拒绝未预期的字段
