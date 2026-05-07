# 免费/低成本 Java AI 中转站部署计划

## 目标

先做一个可验证的 MVP：前端用 Vue3，后端用 Spring Boot，数据库和 Redis 用免费托管服务，部署平台优先选择不需要信用卡的免费方案。

这个计划默认走合规路线：使用官方 API 或用户自带 API Key，不获取、共享、转卖或代管 Plus 账号。

## 推荐技术栈

```text
前端：Vue3 + Vite
后端：Spring Boot 单体应用
反向代理：平台域名/CDN 优先，后期再上 Nginx
数据库：Supabase PostgreSQL
Redis：Upstash Redis
部署：Zeabur / Render / Railway 先试，后期迁移 VPS
域名/CDN：Cloudflare
```

## 免费平台选择

| 平台 | 是否需要信用卡 | Java 支持 | 适合程度 | 注意事项 |
|---|---:|---:|---|---|
| Zeabur | 不需要 | 支持 Spring Boot | 首选测试平台 | 免费档会休眠，无 SLA |
| Render | 通常不需要 | 支持 Java/Docker | 适合演示 | 15 分钟无访问会休眠 |
| Railway | 不需要 | 支持 Spring Boot | 可试用 | 试用后不是完全免费，未验证账号可能有网络限制 |
| Back4app Containers | 不需要 | 支持 Docker | 不推荐 Java | 免费内存太小 |
| webapp.io | 不需要 | 可跑容器 | 备选 | 免费限制较多，稳定性未知 |

首选顺序：

```text
1. Zeabur
2. Render
3. Railway
```

## 为什么先不用完整 SpringCloud

SpringCloud 通常需要多个服务一起跑：

```text
gateway
user-service
billing-service
proxy-service
config-service
registry-service
```

免费无卡平台的 CPU、内存、休眠策略都比较紧，完整 SpringCloud 很容易出现：

```text
启动慢
内存不够
冷启动时间长
服务互相掉线
排查成本高
```

MVP 阶段建议先做 Spring Boot 单体，把模块在代码里分清楚：

```text
auth 模块
user 模块
billing 模块
proxy 模块
admin 模块
log 模块
```

等有稳定用户和收入后，再拆成 SpringCloud。

## MVP 架构

```text
用户浏览器
  ↓
Vue3 前端
  ↓
Spring Boot 后端
  ↓
Supabase PostgreSQL
  ↓
Upstash Redis
  ↓
官方 AI API
```

可选域名/CDN：

```text
Cloudflare DNS/CDN
  ↓
前端平台域名
  ↓
后端平台域名
```

## 核心功能优先级

第一阶段必须有：

```text
用户注册/登录
用户余额
API Key 管理
模型列表
聊天接口转发
请求日志
简单限流
后台手动充值
```

第二阶段再做：

```text
在线支付
套餐系统
代理/分销
公告系统
模型成本统计
失败重试
风控规则
```

第三阶段再考虑：

```text
SpringCloud 拆分
多节点部署
Prometheus/Grafana 监控
队列系统
自动扩容
多供应商模型路由
```

## 数据库设计草案

```sql
create table users (
  id uuid primary key,
  email text unique not null,
  password_hash text not null,
  balance numeric default 0,
  status text default 'active',
  created_at timestamptz default now()
);

create table api_keys (
  id bigserial primary key,
  user_id uuid not null,
  key_hash text not null,
  name text,
  status text default 'active',
  created_at timestamptz default now()
);

create table api_logs (
  id bigserial primary key,
  user_id uuid,
  model text,
  prompt_tokens int default 0,
  completion_tokens int default 0,
  cost numeric default 0,
  status text,
  created_at timestamptz default now()
);

create table recharge_orders (
  id bigserial primary key,
  user_id uuid not null,
  amount numeric not null,
  status text default 'pending',
  remark text,
  created_at timestamptz default now()
);
```

## 部署步骤

### 1. 前端部署

```text
注册 Cloudflare Pages 或 Vercel
上传 Vue3 项目
配置构建命令：npm run build
配置输出目录：dist
绑定域名
```

### 2. 后端部署

优先尝试 Zeabur：

```text
注册 Zeabur
导入 GitHub 仓库
选择 Spring Boot 项目
配置环境变量
部署服务
获取后端访问域名
```

后端环境变量示例：

```text
SERVER_PORT=8080
DATABASE_URL=Supabase 连接串
REDIS_URL=Upstash Redis 连接串
AI_API_BASE=https://api.openai.com/v1
AI_API_KEY=你的官方 API Key
JWT_SECRET=随机长密钥
```

### 3. 数据库

```text
注册 Supabase
创建项目
创建数据表
保存数据库连接串
配置 Row Level Security 或只允许后端访问
```

### 4. Redis

```text
注册 Upstash
创建 Redis 数据库
保存 REST URL 或 Redis URL
用于限流、短期 token、验证码缓存
```

### 5. 域名

```text
Cloudflare 托管域名 DNS
前端绑定 app.example.com
后端绑定 api.example.com
开启 HTTPS
配置 CORS 只允许你的前端域名
```

## 安全要求

必须做到：

```text
不要把官方 API Key 放到前端
不要把 Supabase service_role key 放到前端
用户 API Key 只存哈希或加密密文
扣费逻辑只在后端执行
每个用户设置限流
记录调用日志
管理后台加权限
```

建议做到：

```text
接口签名
IP 限流
异常成本报警
余额不足立即阻断
敏感日志脱敏
定期备份数据库
```

## 免费阶段风险

```text
服务会休眠，第一次访问慢
免费额度可能随平台政策变化
Java 后端冷启动比 Node/Go 慢
免费平台可能限制出站网络
没有 SLA，不适合承诺稳定性
用户量上来后必须迁移付费环境
```

## 迁移路线

当出现以下情况时，准备迁移：

```text
每天有稳定付费用户
免费平台开始频繁休眠或限流
后端内存不够
需要 Nginx 自定义反代
需要完整 SpringCloud
需要更稳定的数据库和备份
```

迁移目标：

```text
1 台 2 核 4GB VPS 起步
Nginx + Spring Boot + Redis
数据库继续用 Supabase，或迁移自建 PostgreSQL/MySQL
```

后续规模更大：

```text
前端：Cloudflare Pages
网关：Nginx / Spring Cloud Gateway
后端：多 SpringCloud 服务
数据库：托管 PostgreSQL/MySQL
缓存：托管 Redis
监控：Prometheus + Grafana
日志：Loki / ELK
```

## 当前建议

现在先不要买服务器，也不要完整上 SpringCloud。

最稳的第一版：

```text
Vue3
Spring Boot 单体
Supabase PostgreSQL
Upstash Redis
Zeabur 部署后端
Cloudflare Pages 部署前端
Cloudflare 绑定域名
```

先把注册、登录、余额、转发、日志跑通，再考虑支付和推广。
