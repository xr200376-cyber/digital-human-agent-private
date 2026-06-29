# 雄图IP智能体客户运营后台部署加固

这个目录只放生产部署模板，不包含真实密码、Token、数据库连接串或服务器地址。

## 上线顺序

1. 创建 PostgreSQL 数据库和专用用户。
2. 按 `aivo-commercial.env.example` 创建 systemd 环境变量文件。
3. 运行 JSON 迁移 dry-run：

   ```bash
   python -m app.scripts.migrate_commercial_json_to_postgres --storage-dir /opt/aivo-commercial/storage --dry-run
   ```

4. 确认数据量后执行真实迁移：

   ```bash
   python -m app.scripts.migrate_commercial_json_to_postgres --storage-dir /opt/aivo-commercial/storage --database-url "$COMMERCIAL_DATABASE_URL"
   ```

5. 启动服务并加载 Nginx 配置。
6. 验证：

   ```bash
   curl -fsS https://api.xiongtuai.cc/health
   curl -fsS https://api.xiongtuai.cc/updates/latest
   ```

## 备份

`commercial_backup.sh` 用于每日 cron/systemd timer 备份 PostgreSQL 和发布包目录。保留策略：14 天日备份，8 周周备份。
