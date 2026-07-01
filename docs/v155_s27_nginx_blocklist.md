# V15.5-S2.7 Nginx IP Blocklist Sync

本阶段完成：

1. Flask 封禁名单同步到 Nginx deny 配置
2. 同步脚本：scripts/sync_nginx_blocklist.py
3. 输出文件：/etc/nginx/snippets/ai-tool-ip-blocklist.conf
4. Nginx 配置接入 include

生效流程：

cd /home/admin/ai-tool
python3 scripts/sync_nginx_blocklist.py
nginx -t
systemctl reload nginx

注意：

- 127.0.0.1、内网 IP、保留测试 IP、白名单 IP 不会写入 Nginx deny。
- 数据库里解除封禁后，需要重新执行同步脚本并 reload Nginx。
- 当前是手动同步，后续可以做成后台按钮或定时任务。
- 本机 curl 携带 X-Forwarded-For 通常不能验证 Nginx deny，因为 Nginx 默认看真实连接 IP，不看伪造请求头。
- 203.0.113.0/24 属于保留测试网段，会被同步脚本过滤，这是正常保护。
