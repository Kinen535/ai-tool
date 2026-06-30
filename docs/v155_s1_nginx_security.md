# V15.5-S1 Nginx Security Gateway

本阶段完成：

1. Gunicorn 改为监听 127.0.0.1:5000
2. Nginx 监听 80 端口并反向代理到 Gunicorn
3. 普通访问限速：120 次/分钟/IP
4. 搜索接口限速：20 次/分钟/IP
5. POST 写入接口限速：10 次/分钟/IP
6. Nginx 访问日志：/var/log/nginx/ai-tool-access.log
7. Nginx 错误日志：/var/log/nginx/ai-tool-error.log
8. Flask 安全日志后台：/security/logs?token=安全token

注意：
公网访问使用 http://服务器IP/
不要再使用 http://服务器IP:5000/
