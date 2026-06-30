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

## S1.3 源码泄露防护

本阶段增加 Nginx 敏感路径封锁：

1. 禁止访问 /.git、/.env 等隐藏敏感目录
2. 禁止访问 .py、.db、.sqlite、.sql、.bak、.zip、.tar、.gz 等敏感文件
3. 禁止访问 /data/、/services/、/templates/、/docs/、/venv/
4. 敏感路径统一返回 404
5. 用 curl 验证 /app.py、/.git/config、/data/snapshots.db 均不能被访问
