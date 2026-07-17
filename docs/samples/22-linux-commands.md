# Linux 命令与运维

## 文件操作

```bash
ls -la          # 列出文件详情
find . -name "*.py"  # 查找文件
grep -r "error" /var/log/  # 递归搜索文本
tar -czf archive.tar.gz /path  # 压缩打包
chmod 755 script.sh  # 修改权限
chown user:group file  # 修改所有者
```

## 进程管理

```bash
ps aux            # 查看进程
top / htop        # 实时监控
kill -9 PID       # 强制终止
nohup cmd &       # 后台不挂断运行
systemctl start/stop/status nginx  # systemd 服务管理
```

## 网络

```bash
curl -I https://example.com  # 查看 HTTP 响应头
ss -tlnp            # 查看监听端口
tcpdump -i eth0 port 80  # 抓包分析
ping / traceroute   # 网络连通性
iptables -L         # 防火墙规则
```

## 磁盘与内存

```bash
df -h             # 磁盘空间
du -sh /path      # 目录大小
free -h           # 内存使用
iostat / vmstat   # IO/系统负载
```

## Docker 常用命令

```bash
docker ps                  # 列出容器
docker images              # 列出镜像
docker compose up -d       # 启动服务
docker logs -f container   # 查看日志
docker exec -it container bash  # 进入容器
```

### 日志排查最佳实践

1. 先查 `journalctl -xe`（systemd 日志）
2. 再查 `/var/log/`（应用日志）
3. `dmesg -T | tail` 看内核消息（硬件/OOM）
4. 关键应用日志常去：`/var/log/nginx/`, `/var/log/mysql/`
