# 数字人智能体客户运营后台部署说明

这个目录用于把授权后台迁移到另一台 Linux 服务器。模板文件不包含真实密码、Token、数据库连接串、服务器 IP 或客户数据。

## 包含能力

- 管理员登录与后台页面：`/admin`
- 客户管理：创建、查询、更新、删除客户
- 授权管理：生成授权码、停用、续期、重置设备绑定
- 积分系统：试用版 1300 积分，高级会员月付 36000 积分，钻石会员月付 200000 积分
- 订单系统：客户自助下单、上传付款凭证、人工确认收款后自动发货或充值积分
- 客户端接口：激活、心跳、积分预占、积分确认扣除、积分明细
- 版本更新：上传新版本安装包，客户端检查更新
- 审计与日志：记录后台操作、客户日志、积分流水

## 推荐目录

```bash
/opt/aivo-commercial
  app/
  storage/
  venv/
/etc/aivo-commercial/aivo-commercial.env
```

## 部署步骤

1. 创建系统用户和目录。

   ```bash
   sudo useradd --system --home /opt/aivo-commercial --shell /usr/sbin/nologin aivo || true
   sudo mkdir -p /opt/aivo-commercial /etc/aivo-commercial
   sudo chown -R aivo:aivo /opt/aivo-commercial
   ```

2. 从 GitHub 私有仓库拉取代码，把 `resources/app` 复制到 `/opt/aivo-commercial/app` 所在的项目根目录。

   推荐结构是让 `/opt/aivo-commercial` 下直接存在 `app` 目录：

   ```bash
   cd /opt/aivo-commercial
   # 示例：从仓库复制 resources/app 到当前目录的 app
   # rsync -a /path/to/repo/resources/app/ ./app/
   ```

3. 创建 Python 虚拟环境并安装授权后台依赖。

   ```bash
   cd /opt/aivo-commercial
   python3 -m venv venv
   ./venv/bin/pip install --upgrade pip
   ./venv/bin/pip install -r app/requirements-commercial.txt
   ```

4. 复制环境变量模板并填写真实配置。

   ```bash
   sudo cp app/deploy/commercial/aivo-commercial.env.example /etc/aivo-commercial/aivo-commercial.env
   sudo nano /etc/aivo-commercial/aivo-commercial.env
   ```

   必填项：

   - `STORAGE_DIR`
   - `COMMERCIAL_REPOSITORY_BACKEND`
   - `COMMERCIAL_DATABASE_URL`，如果使用 PostgreSQL
   - `COMMERCIAL_ADMIN_USERNAME`
   - `COMMERCIAL_ADMIN_PASSWORD_HASH`
   - `COMMERCIAL_ADMIN_SESSION_SECRET`
   - `COMMERCIAL_API_BASE_URL`
   - `COMMERCIAL_RELEASE_PUBLIC_BASE_URL`

5. 生成管理员密码哈希。

   ```bash
   cd /opt/aivo-commercial
   ./venv/bin/python -m app.scripts.hash_admin_password
   ```

   把输出的哈希写入 `COMMERCIAL_ADMIN_PASSWORD_HASH`。

6. 配置 systemd。

   ```bash
   sudo cp app/deploy/commercial/aivo-commercial.service.template /etc/systemd/system/aivo-commercial.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now aivo-commercial
   sudo systemctl status aivo-commercial --no-pager
   ```

7. 配置 Nginx 和 HTTPS。

   ```bash
   sudo cp app/deploy/commercial/nginx_api_digitalhumanagent.conf.template /etc/nginx/conf.d/api.digitalhumanagent.example.com.conf
   sudo nginx -t
   sudo systemctl reload nginx
   ```

8. 验证服务。

   ```bash
   curl -fsS https://api.digitalhumanagent.example.com/health
   curl -fsS https://api.digitalhumanagent.example.com/updates/latest
   ```

## PostgreSQL 与文件存储选择

小规模测试可以使用文件存储：

```env
COMMERCIAL_REPOSITORY_BACKEND=file
STORAGE_DIR=/opt/aivo-commercial/storage
```

正式商用建议使用 PostgreSQL：

```env
COMMERCIAL_REPOSITORY_BACKEND=postgres
COMMERCIAL_DATABASE_URL=postgresql://aivo_user:CHANGE_ME@127.0.0.1:5432/aivo_commercial
```

## 迁移已有 JSON 数据

先 dry-run：

```bash
cd /opt/aivo-commercial
./venv/bin/python -m app.scripts.migrate_commercial_json_to_postgres --storage-dir /opt/aivo-commercial/storage --dry-run
```

确认后真实迁移：

```bash
./venv/bin/python -m app.scripts.migrate_commercial_json_to_postgres --storage-dir /opt/aivo-commercial/storage --database-url "$COMMERCIAL_DATABASE_URL"
```

## 备份

`commercial_backup.sh` 用于备份 PostgreSQL 和发布包目录。建议用 cron 或 systemd timer 每天执行一次，并至少保留 14 天。

## 安全要求

- GitHub 仓库必须保持 Private。
- 不要提交真实 `.env`、数据库备份、客户数据、支付凭证、API Key、Token、OSS 签名链接。
- 后台必须走 HTTPS。
- 管理员密码哈希和 `COMMERCIAL_ADMIN_SESSION_SECRET` 每套服务器单独生成。
- 生产环境保持 `COMMERCIAL_ENABLE_DOCS` 为空，不开放 `/docs`。
