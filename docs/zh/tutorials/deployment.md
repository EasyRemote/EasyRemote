# EasyRemote 部署指南

##  部署目标

本指南将帮助您在不同环境中部署EasyRemote分布式计算系统：
- 本地开发环境部署
- VPS生产环境部署
- Docker容器化部署
- 云平台部署
- 高可用集群部署

## 📋 部署前准备

### 系统要求

#### 最低要求
- **操作系统**: Linux/Windows/macOS
- **Python版本**: 3.8+
- **内存**: 2GB RAM
- **存储**: 5GB 可用空间
- **网络**: 稳定的互联网连接

#### 推荐配置
- **操作系统**: Ubuntu 20.04+ / CentOS 8+
- **Python版本**: 3.9+
- **内存**: 8GB+ RAM
- **CPU**: 4核心+
- **存储**: 20GB+ SSD
- **网络**: 低延迟网络

### 网络端口

| 组件 | 默认端口 | 协议 | 说明 |
|------|----------|------|------|
| Gateway Server | 8080 | TCP | 主要服务端口 |
| Monitoring | 9090 | HTTP | 监控指标端口 |
| Dashboard | 3000 | HTTP | Web管理界面 |

## 🏠 本地开发环境部署

### 1. 快速单机部署

创建部署脚本 `deploy_local.py`：

```python
#!/usr/bin/env python3
import subprocess
import time
import threading
import signal
import sys
import os

class LocalDeployment:
    def __init__(self):
        self.processes = []
        self.running = True
        
    def start_server(self):
        """启动网关服务器"""
        print(" 启动网关服务器...")
        
        server_code = '''
from easyremote import Server
import logging

logging.basicConfig(level=logging.INFO)
server = Server(host="127.0.0.1", port=8080)
print("✅ 网关服务器启动成功")
server.start()
'''
        
        with open('temp_server.py', 'w') as f:
            f.write(server_code)
            
        process = subprocess.Popen([sys.executable, 'temp_server.py'])
        self.processes.append(('server', process))
        time.sleep(2)  # 等待服务器启动
        
    def start_compute_node(self, node_id=1):
        """启动计算节点"""
        print(f"💻 启动计算节点 {node_id}...")
        
        node_code = f'''
from easyremote import ComputeNode
import time
import random
import logging

logging.basicConfig(level=logging.INFO)
node = ComputeNode("127.0.0.1:8080")

@node.register
def add_numbers(a, b):
    """加法计算"""
    return a + b

@node.register
def multiply_numbers(a, b):
    """乘法计算"""
    return a * b

@node.register
def process_data(data_list):
    """数据处理"""
    return {{
        "count": len(data_list),
        "sum": sum(data_list),
        "average": sum(data_list) / len(data_list),
        "max": max(data_list),
        "min": min(data_list)
    }}

@node.register
def simulate_ai_inference(text):
    """模拟AI推理"""
    time.sleep(0.5)  # 模拟处理时间
    return {{
        "input": text,
        "sentiment": random.choice(["positive", "negative", "neutral"]),
        "confidence": random.uniform(0.7, 0.95),
        "node_id": {node_id}
    }}

print(f"✅ 计算节点 {node_id} 启动成功")
node.serve()
'''
        
        with open(f'temp_node_{node_id}.py', 'w') as f:
            f.write(node_code)
            
        process = subprocess.Popen([sys.executable, f'temp_node_{node_id}.py'])
        self.processes.append((f'node_{node_id}', process))
        time.sleep(1)
        
    def start_client_test(self):
        """启动客户端测试"""
        print("🧪 启动客户端测试...")
        
        client_code = '''
from easyremote import Client
import time
import random

def run_tests():
    client = Client("127.0.0.1:8080")
    
    print("🔄 开始功能测试...")
    
    # 测试基本数学运算
    result1 = client.execute("add_numbers", 10, 20)
    print(f"➕ 10 + 20 = {result1}")
    
    result2 = client.execute("multiply_numbers", 6, 7)
    print(f"✖️ 6 × 7 = {result2}")
    
    # 测试数据处理
    test_data = [random.randint(1, 100) for _ in range(10)]
    result3 = client.execute("process_data", test_data)
    print(f"📊 数据处理结果: {result3}")
    
    # 测试AI推理
    result4 = client.execute("simulate_ai_inference", "This is a test message")
    print(f"🤖 AI推理结果: {result4}")
    
    print("✅ 所有测试完成")

if __name__ == "__main__":
    run_tests()
'''
        
        with open('temp_client.py', 'w') as f:
            f.write(client_code)
            
        # 等待节点就绪
        time.sleep(3)
        subprocess.run([sys.executable, 'temp_client.py'])
        
    def cleanup_temp_files(self):
        """清理临时文件"""
        temp_files = [
            'temp_server.py',
            'temp_client.py'
        ]
        
        # 添加节点文件
        for i in range(1, 4):
            temp_files.append(f'temp_node_{i}.py')
            
        for file in temp_files:
            try:
                if os.path.exists(file):
                    os.remove(file)
            except Exception:
                pass
                
    def signal_handler(self, signum, frame):
        """信号处理器"""
        print("\n🛑 收到停止信号，正在清理...")
        self.running = False
        self.cleanup()
        
    def cleanup(self):
        """清理所有进程"""
        for name, process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"✅ 已停止: {name}")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"🔪 强制停止: {name}")
            except Exception as e:
                print(f"❌ 停止失败 {name}: {e}")
        
        self.cleanup_temp_files()
        print("🧹 清理完成")
        
    def deploy(self):
        """执行部署"""
        # 注册信号处理器
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
            print(" 开始本地部署...")
            print("=" * 50)
            
            # 启动组件
            self.start_server()
            self.start_compute_node(1)
            self.start_compute_node(2)
            self.start_compute_node(3)
            
            print("\n📊 系统组件状态:")
            for name, process in self.processes:
                status = "运行中" if process.poll() is None else "已停止"
                print(f"  {name}: {status}")
            
            print(f"\n🌐 系统地址: http://127.0.0.1:8080")
            print("🧪 运行测试客户端...")
            
            # 运行测试
            self.start_client_test()
            
            print("\n🎉 本地部署完成！")
            print("按 Ctrl+C 停止系统...")
            
            # 保持运行
            while self.running:
                time.sleep(1)
                
        except Exception as e:
            print(f"❌ 部署失败: {e}")
            self.cleanup()

if __name__ == "__main__":
    deployment = LocalDeployment()
    deployment.deploy()
```

**运行部署：**
```bash
python deploy_local.py
```

### 2. 开发环境配置

创建开发配置文件 `dev_config.py`：

```python
# 开发环境配置
DEV_CONFIG = {
    "server": {
        "host": "127.0.0.1",
        "port": 8080,
        "debug": True,
        "log_level": "DEBUG"
    },
    "nodes": [
        {"type": "general", "count": 2},
        {"type": "test", "count": 1}
    ],
    "monitoring": {
        "enabled": True,
        "port": 9090
    }
}

def setup_dev_environment():
    """设置开发环境"""
    import logging
    import os
    
    # 设置日志
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 设置环境变量
    os.environ['EASYREMOTE_ENV'] = 'development'
    os.environ['EASYREMOTE_DEBUG'] = 'true'
    
    print("✅ 开发环境配置完成")
    return DEV_CONFIG
```

## 🌐 VPS生产环境部署

### 1. VPS准备工作

#### 系统初始化脚本 `setup_vps.sh`：

```bash
#!/bin/bash

# VPS环境初始化脚本
set -e

echo " 开始VPS环境初始化..."

# 更新系统
echo "📦 更新系统包..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get upgrade -y
    sudo apt-get install -y python3 python3-pip python3-venv git curl wget
elif command -v yum &> /dev/null; then
    sudo yum update -y
    sudo yum install -y python3 python3-pip git curl wget
fi

# 安装Python依赖
echo "🐍 设置Python环境..."
python3 -m pip install --upgrade pip
python3 -m pip install virtualenv

# 创建项目目录
echo "📁 创建项目目录..."
sudo mkdir -p /opt/easyremote
sudo chown $(whoami):$(whoami) /opt/easyremote
cd /opt/easyremote

# 创建虚拟环境
echo "🌐 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate

# 安装EasyRemote
echo "📦 安装EasyRemote..."
pip install easyremote

# 配置防火墙
echo "🔥 配置防火墙..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 8080/tcp
    sudo ufw allow 22/tcp
    sudo ufw --force enable
elif command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --permanent --add-port=8080/tcp
    sudo firewall-cmd --permanent --add-port=22/tcp
    sudo firewall-cmd --reload
fi

echo "✅ VPS环境初始化完成"
echo "📂 项目目录: /opt/easyremote"
echo "🌐 请确保端口8080已开放"
```

#### 运行初始化：
```bash
curl -sSL https://your-domain.com/setup_vps.sh | bash
```

### 2. 生产环境部署脚本

创建 `production_deploy.py`：

```python
#!/usr/bin/env python3
import os
import sys
import subprocess
import json
import time
from pathlib import Path

class ProductionDeployer:
    def __init__(self, config_file="production_config.json"):
        self.config = self._load_config(config_file)
        self.project_dir = Path("/opt/easyremote")
        self.venv_dir = self.project_dir / "venv"
        self.logs_dir = self.project_dir / "logs"
        self.services_dir = self.project_dir / "services"
        
        # 创建必要目录
        self.logs_dir.mkdir(exist_ok=True)
        self.services_dir.mkdir(exist_ok=True)
        
    def _load_config(self, config_file):
        """加载生产配置"""
        default_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 8080,
                "workers": 4,
                "log_level": "INFO"
            },
            "security": {
                "enable_tls": False,
                "cert_file": None,
                "key_file": None
            },
            "monitoring": {
                "enabled": True,
                "port": 9090,
                "metrics_interval": 30
            },
            "backup": {
                "enabled": True,
                "interval": "daily",
                "retention_days": 7
            }
        }
        
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            config = default_config
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
        
        return config
    
    def create_systemd_service(self):
        """创建systemd服务"""
        service_content = f"""[Unit]
Description=EasyRemote Gateway Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory={self.project_dir}
Environment=PATH={self.venv_dir}/bin
ExecStart={self.venv_dir}/bin/python -c "from easyremote import Server; Server(host='{self.config['server']['host']}', port={self.config['server']['port']}).start()"
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=easyremote

[Install]
WantedBy=multi-user.target
"""
        
        service_file = "/etc/systemd/system/easyremote.service"
        with open(service_file, 'w') as f:
            f.write(service_content)
        
        # 重新加载systemd
        subprocess.run(["sudo", "systemctl", "daemon-reload"])
        subprocess.run(["sudo", "systemctl", "enable", "easyremote"])
        
        print("✅ Systemd服务创建完成")
    
    def create_nginx_config(self):
        """创建Nginx反向代理配置"""
        nginx_config = f"""
server {{
    listen 80;
    server_name your-domain.com;  # 替换为您的域名
    
    location / {{
        proxy_pass http://127.0.0.1:{self.config['server']['port']};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 支持长连接
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }}
    
    # 健康检查端点
    location /health {{
        proxy_pass http://127.0.0.1:{self.config['server']['port']}/health;
        access_log off;
    }}
    
    # 监控指标（如果启用）
    location /metrics {{
        proxy_pass http://127.0.0.1:{self.config['monitoring']['port']}/metrics;
        allow 127.0.0.1;
        deny all;
    }}
}}
"""
        
        nginx_file = f"{self.project_dir}/nginx_easyremote.conf"
        with open(nginx_file, 'w') as f:
            f.write(nginx_config)
        
        print(f"✅ Nginx配置已创建: {nginx_file}")
        print("📝 请手动将配置复制到Nginx sites-available目录")
    
    def create_monitoring_script(self):
        """创建监控脚本"""
        monitoring_script = f"""#!/usr/bin/env python3
import time
import requests
import logging
import json
from datetime import datetime

# 配置日志
logging.basicConfig(
    filename='{self.logs_dir}/monitoring.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def check_health():
    \"\"\"检查服务健康状态\"\"\"
    try:
        response = requests.get(
            'http://127.0.0.1:{self.config['server']['port']}/health',
            timeout=5
        )
        
        if response.status_code == 200:
            logging.info("服务健康检查通过")
            return True
        else:
            logging.warning(f"服务健康检查失败: {{response.status_code}}")
            return False
            
    except Exception as e:
        logging.error(f"健康检查异常: {{e}}")
        return False

def collect_metrics():
    \"\"\"收集系统指标\"\"\"
    try:
        # 这里可以添加自定义指标收集逻辑
        metrics = {{
            "timestamp": datetime.now().isoformat(),
            "health": check_health(),
            "server_status": "running"
        }}
        
        with open('{self.logs_dir}/metrics.json', 'a') as f:
            f.write(json.dumps(metrics) + '\\n')
            
    except Exception as e:
        logging.error(f"指标收集异常: {{e}}")

def main():
    \"\"\"主监控循环\"\"\"
    while True:
        collect_metrics()
        time.sleep({self.config['monitoring']['metrics_interval']})

if __name__ == "__main__":
    main()
"""
        
        monitoring_file = self.services_dir / "monitoring.py"
        with open(monitoring_file, 'w') as f:
            f.write(monitoring_script)
        
        # 使脚本可执行
        os.chmod(monitoring_file, 0o755)
        
        print(f"✅ 监控脚本已创建: {monitoring_file}")
    
    def create_backup_script(self):
        """创建备份脚本"""
        backup_script = f"""#!/bin/bash
set -e

BACKUP_DIR="{self.project_dir}/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/easyremote_backup_$DATE.tar.gz"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 创建备份
echo "🗃️ 开始备份..."
tar -czf $BACKUP_FILE \\
    --exclude='{self.project_dir}/venv' \\
    --exclude='{self.project_dir}/backups' \\
    --exclude='{self.project_dir}/__pycache__' \\
    {self.project_dir}

echo "✅ 备份完成: $BACKUP_FILE"

# 清理旧备份
find $BACKUP_DIR -name "easyremote_backup_*.tar.gz" -mtime +{self.config['backup']['retention_days']} -delete

echo "🧹 清理旧备份完成"
"""
        
        backup_file = self.services_dir / "backup.sh"
        with open(backup_file, 'w') as f:
            f.write(backup_script)
        
        # 使脚本可执行
        os.chmod(backup_file, 0o755)
        
        # 添加到crontab
        if self.config['backup']['enabled']:
            cron_schedule = "0 2 * * *"  # 每天凌晨2点
            if self.config['backup']['interval'] == "hourly":
                cron_schedule = "0 * * * *"
            elif self.config['backup']['interval'] == "weekly":
                cron_schedule = "0 2 * * 0"
            
            print(f"📅 建议添加到crontab: {cron_schedule} {backup_file}")
        
        print(f"✅ 备份脚本已创建: {backup_file}")
    
    def setup_ssl(self):
        """设置SSL证书"""
        if not self.config['security']['enable_tls']:
            print("ℹ️ TLS未启用，跳过SSL设置")
            return
        
        cert_file = self.config['security']['cert_file']
        key_file = self.config['security']['key_file']
        
        if not cert_file or not key_file:
            print("🔒 设置自签名证书...")
            
            # 生成自签名证书
            cert_file = f"{self.project_dir}/server.crt"
            key_file = f"{self.project_dir}/server.key"
            
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:4096",
                "-keyout", key_file, "-out", cert_file,
                "-days", "365", "-nodes",
                "-subj", "/C=US/ST=State/L=City/O=Organization/CN=localhost"
            ])
            
            print(f"✅ 自签名证书已生成:")
            print(f"  证书: {cert_file}")
            print(f"  密钥: {key_file}")
        else:
            print(f"✅ 使用提供的证书: {cert_file}")
    
    def create_health_check(self):
        """创建健康检查端点"""
        health_check_code = f"""
from easyremote import Server
import json
import time

class HealthCheckServer(Server):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_time = time.time()
        
    def register_health_endpoints(self):
        @self.register_endpoint("/health")
        def health_check():
            return {{
                "status": "healthy",
                "uptime": time.time() - self.start_time,
                "timestamp": time.time()
            }}
        
        @self.register_endpoint("/metrics")
        def metrics():
            return {{
                "uptime": time.time() - self.start_time,
                "requests_total": getattr(self, 'request_count', 0),
                "timestamp": time.time()
            }}

# 使用示例
if __name__ == "__main__":
    server = HealthCheckServer(
        host="{self.config['server']['host']}", 
        port={self.config['server']['port']}
    )
    server.register_health_endpoints()
    server.start()
"""
        
        health_file = self.services_dir / "health_server.py"
        with open(health_file, 'w') as f:
            f.write(health_check_code)
        
        print(f"✅ 健康检查服务已创建: {health_file}")
    
    def deploy(self):
        """执行生产部署"""
        print(" 开始生产环境部署...")
        print("=" * 60)
        
        try:
            # 创建各种服务和配置
            print("1. 创建systemd服务...")
            self.create_systemd_service()
            
            print("2. 创建Nginx配置...")
            self.create_nginx_config()
            
            print("3. 设置SSL证书...")
            self.setup_ssl()
            
            print("4. 创建监控脚本...")
            self.create_monitoring_script()
            
            print("5. 创建备份脚本...")
            self.create_backup_script()
            
            print("6. 创建健康检查...")
            self.create_health_check()
            
            # 启动服务
            print("7. 启动EasyRemote服务...")
            subprocess.run(["sudo", "systemctl", "start", "easyremote"])
            subprocess.run(["sudo", "systemctl", "status", "easyremote", "--no-pager"])
            
            print("\n" + "=" * 60)
            print("🎉 生产环境部署完成！")
            print(f"🌐 服务地址: http://your-server-ip:{self.config['server']['port']}")
            print("📋 后续步骤:")
            print("  1. 配置域名DNS解析")
            print("  2. 安装和配置Nginx")
            print("  3. 设置SSL证书")
            print("  4. 配置监控告警")
            print("  5. 测试服务功能")
            
        except Exception as e:
            print(f"❌ 部署失败: {e}")
            raise

if __name__ == "__main__":
    deployer = ProductionDeployer()
    deployer.deploy()
```

### 3. 生产环境运行

```bash
# 切换到项目目录
cd /opt/easyremote

# 激活虚拟环境
source venv/bin/activate

# 运行部署脚本
python production_deploy.py

# 检查服务状态
sudo systemctl status easyremote

# 查看服务日志
sudo journalctl -u easyremote -f
```

## 🐳 Docker容器化部署

### 1. Dockerfile

创建 `Dockerfile`：

```dockerfile
# 多阶段构建
FROM python:3.9-slim as builder

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --user -r requirements.txt

# 生产镜像
FROM python:3.9-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/root/.local/bin:${PATH}"

# 创建非root用户
RUN groupadd -r easyremote && useradd -r -g easyremote easyremote

# 设置工作目录
WORKDIR /app

# 从builder阶段复制依赖
COPY --from=builder /root/.local /root/.local

# 复制应用代码
COPY . .

# 创建必要目录
RUN mkdir -p /app/logs /app/data && \
    chown -R easyremote:easyremote /app

# 切换到非root用户
USER easyremote

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# 启动命令
CMD ["python", "-c", "from easyremote import Server; Server(host='0.0.0.0', port=8080).start()"]
```

### 2. Docker Compose配置

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  # 网关服务器
  easyremote-gateway:
    build: .
    container_name: easyremote-gateway
    ports:
      - "8080:8080"
    environment:
      - EASYREMOTE_ENV=production
      - EASYREMOTE_LOG_LEVEL=INFO
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    restart: unless-stopped
    networks:
      - easyremote-network
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8080/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # 计算节点1
  easyremote-node1:
    build: 
      context: .
      dockerfile: Dockerfile.node
    container_name: easyremote-node1
    environment:
      - EASYREMOTE_GATEWAY=easyremote-gateway:8080
      - EASYREMOTE_NODE_TYPE=general
      - EASYREMOTE_NODE_ID=node1
    depends_on:
      easyremote-gateway:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - easyremote-network

  # 计算节点2
  easyremote-node2:
    build: 
      context: .
      dockerfile: Dockerfile.node
    container_name: easyremote-node2
    environment:
      - EASYREMOTE_GATEWAY=easyremote-gateway:8080
      - EASYREMOTE_NODE_TYPE=ai
      - EASYREMOTE_NODE_ID=node2
    depends_on:
      easyremote-gateway:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - easyremote-network

  # 监控服务
  prometheus:
    image: prom/prometheus:latest
    container_name: easyremote-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
    restart: unless-stopped
    networks:
      - easyremote-network

  # Grafana仪表板
  grafana:
    image: grafana/grafana:latest
    container_name: easyremote-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    restart: unless-stopped
    networks:
      - easyremote-network

  # Nginx反向代理
  nginx:
    image: nginx:alpine
    container_name: easyremote-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - easyremote-gateway
    restart: unless-stopped
    networks:
      - easyremote-network

networks:
  easyremote-network:
    driver: bridge

volumes:
  prometheus_data:
  grafana_data:
```

### 3. 计算节点Dockerfile

创建 `Dockerfile.node`：

```dockerfile
FROM python:3.9-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制节点代码
COPY compute_node.py .

# 暴露端口（如果需要）
EXPOSE 8081

# 启动命令
CMD ["python", "compute_node.py"]
```

### 4. 计算节点代码

创建 `compute_node.py`：

```python
import os
import time
import random
from easyremote import ComputeNode

def main():
    # 从环境变量获取配置
    gateway_address = os.getenv('EASYREMOTE_GATEWAY', 'localhost:8080')
    node_type = os.getenv('EASYREMOTE_NODE_TYPE', 'general')
    node_id = os.getenv('EASYREMOTE_NODE_ID', f'node_{random.randint(1000, 9999)}')
    
    print(f" 启动计算节点: {node_id} (类型: {node_type})")
    print(f"🔗 连接到网关: {gateway_address}")
    
    # 创建计算节点
    node = ComputeNode(gateway_address)
    
    # 注册通用函数
    @node.register
    def add_numbers(a, b):
        """基础加法运算"""
        return a + b
    
    @node.register
    def multiply_numbers(a, b):
        """基础乘法运算"""
        return a * b
    
    @node.register
    def process_data_list(data_list):
        """处理数据列表"""
        if not data_list:
            return {"error": "空数据列表"}
        
        return {
            "count": len(data_list),
            "sum": sum(data_list),
            "average": sum(data_list) / len(data_list),
            "max": max(data_list),
            "min": min(data_list),
            "node_id": node_id
        }
    
    # 根据节点类型注册特定函数
    if node_type == 'ai':
        @node.register
        def ai_text_analysis(text):
            """AI文本分析（模拟）"""
            time.sleep(0.5)  # 模拟AI处理时间
            return {
                "text": text,
                "length": len(text),
                "word_count": len(text.split()),
                "sentiment": random.choice(["positive", "negative", "neutral"]),
                "confidence": random.uniform(0.7, 0.95),
                "node_id": node_id,
                "processed_by": "ai_node"
            }
        
        @node.register
        def ai_image_classification(image_data):
            """AI图像分类（模拟）"""
            time.sleep(1.0)  # 模拟图像处理时间
            classes = ["cat", "dog", "bird", "car", "house"]
            return {
                "predicted_class": random.choice(classes),
                "confidence": random.uniform(0.8, 0.99),
                "processing_time": 1.0,
                "node_id": node_id,
                "processed_by": "ai_node"
            }
    
    elif node_type == 'compute':
        @node.register
        def heavy_computation(n):
            """CPU密集型计算"""
            start_time = time.time()
            
            # 模拟重计算（计算斐波那契数列）
            def fibonacci(n):
                if n <= 1:
                    return n
                return fibonacci(n-1) + fibonacci(n-2)
            
            if n > 35:  # 防止计算过长
                n = 35
            
            result = fibonacci(n)
            processing_time = time.time() - start_time
            
            return {
                "input": n,
                "result": result,
                "processing_time": processing_time,
                "node_id": node_id,
                "processed_by": "compute_node"
            }
    
    # 注册健康检查函数
    @node.register
    def health_check():
        """节点健康检查"""
        return {
            "status": "healthy",
            "node_id": node_id,
            "node_type": node_type,
            "timestamp": time.time()
        }
    
    print(f"✅ 节点 {node_id} 准备就绪")
    print(f"📋 已注册函数类型: {node_type}")
    
    # 开始服务
    try:
        node.serve()
    except KeyboardInterrupt:
        print(f"\n🛑 节点 {node_id} 停止")
    except Exception as e:
        print(f"❌ 节点 {node_id} 运行错误: {e}")

if __name__ == "__main__":
    main()
```

### 5. Docker部署命令

```bash
# 构建镜像
docker-compose build

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f easyremote-gateway

# 扩展计算节点
docker-compose up -d --scale easyremote-node1=3

# 停止服务
docker-compose down

# 完全清理
docker-compose down -v --rmi all
```

## ☁️ 云平台部署

### 1. AWS ECS部署

创建 `aws-ecs-task-definition.json`：

```json
{
  "family": "easyremote-gateway",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "easyremote-gateway",
      "image": "your-account.dkr.ecr.region.amazonaws.com/easyremote:latest",
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "EASYREMOTE_ENV",
          "value": "production"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/easyremote",
          "awslogs-region": "us-west-2",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "python -c 'import requests; requests.get(\"http://localhost:8080/health\")'"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

### 2. Kubernetes部署

创建 `k8s-deployment.yaml`：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: easyremote-gateway
  labels:
    app: easyremote-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: easyremote-gateway
  template:
    metadata:
      labels:
        app: easyremote-gateway
    spec:
      containers:
      - name: easyremote-gateway
        image: easyremote:latest
        ports:
        - containerPort: 8080
        env:
        - name: EASYREMOTE_ENV
          value: "production"
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: easyremote-gateway-service
spec:
  selector:
    app: easyremote-gateway
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8080
  type: LoadBalancer

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: easyremote-compute-nodes
  labels:
    app: easyremote-compute-nodes
spec:
  replicas: 5
  selector:
    matchLabels:
      app: easyremote-compute-nodes
  template:
    metadata:
      labels:
        app: easyremote-compute-nodes
    spec:
      containers:
      - name: easyremote-node
        image: easyremote-node:latest
        env:
        - name: EASYREMOTE_GATEWAY
          value: "easyremote-gateway-service:80"
        - name: EASYREMOTE_NODE_TYPE
          value: "general"
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
```

部署到Kubernetes：
```bash
kubectl apply -f k8s-deployment.yaml
kubectl get pods
kubectl get services
```

## 部署后验证

### 1. 功能测试脚本

创建 `test_deployment.py`：

```python
#!/usr/bin/env python3
import requests
import time
import json
from easyremote import Client

def test_health_check(base_url):
    """测试健康检查"""
    print("🔍 测试健康检查...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ 健康检查通过")
            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False

def test_basic_functions(server_address):
    """测试基本功能"""
    print("🧪 测试基本功能...")
    try:
        client = Client(server_address)
        
        # 测试加法
        result = client.execute("add_numbers", 10, 20)
        assert result == 30, f"加法测试失败: {result}"
        print("✅ 加法测试通过")
        
        # 测试数据处理
        test_data = [1, 2, 3, 4, 5]
        result = client.execute("process_data_list", test_data)
        assert result["sum"] == 15, f"数据处理测试失败: {result}"
        print("✅ 数据处理测试通过")
        
        return True
        
    except Exception as e:
        print(f"❌ 功能测试失败: {e}")
        return False

def test_load_balancing(server_address, num_requests=10):
    """测试负载均衡"""
    print(f"⚖️ 测试负载均衡 ({num_requests} 请求)...")
    
    client = Client(server_address)
    node_ids = set()
    
    try:
        for i in range(num_requests):
            result = client.execute("health_check")
            if "node_id" in result:
                node_ids.add(result["node_id"])
        
        print(f"✅ 负载均衡测试通过，涉及 {len(node_ids)} 个节点")
        return True
        
    except Exception as e:
        print(f"❌ 负载均衡测试失败: {e}")
        return False

def test_performance(server_address, num_requests=50):
    """测试性能"""
    print(f"📊 测试性能 ({num_requests} 请求)...")
    
    client = Client(server_address)
    start_time = time.time()
    successful_requests = 0
    
    try:
        for i in range(num_requests):
            try:
                result = client.execute("add_numbers", i, i+1)
                successful_requests += 1
            except Exception:
                pass
        
        end_time = time.time()
        total_time = end_time - start_time
        rps = successful_requests / total_time
        
        print(f"✅ 性能测试完成:")
        print(f"  总请求: {num_requests}")
        print(f"  成功请求: {successful_requests}")
        print(f"  总耗时: {total_time:.2f}秒")
        print(f"  RPS: {rps:.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print(" 开始部署验证...")
    print("=" * 50)
    
    # 配置测试目标
    base_url = "http://localhost:8080"  # 根据实际部署调整
    server_address = "localhost:8080"
    
    tests = [
        ("健康检查", lambda: test_health_check(base_url)),
        ("基本功能", lambda: test_basic_functions(server_address)),
        ("负载均衡", lambda: test_load_balancing(server_address)),
        ("性能测试", lambda: test_performance(server_address))
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 执行测试: {test_name}")
        if test_func():
            passed += 1
        else:
            print(f"❌ 测试失败: {test_name}")
    
    print("\n" + "=" * 50)
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过，部署验证成功！")
        return True
    else:
        print("❌ 部分测试失败，请检查部署配置")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
```

### 2. 监控检查

```bash
# 检查系统资源
htop

# 检查网络连接
netstat -tulpn | grep 8080

# 检查日志
tail -f /opt/easyremote/logs/easyremote.log

# 检查Docker容器（如果使用Docker）
docker ps
docker logs easyremote-gateway

# 检查Kubernetes Pod（如果使用K8s）
kubectl get pods
kubectl logs deployment/easyremote-gateway
```

## 🚨 故障排除

### 常见问题

1. **端口被占用**
```bash
# 查看端口占用
lsof -i :8080
# 杀死占用进程
kill -9 PID
```

2. **权限问题**
```bash
# 检查文件权限
ls -la /opt/easyremote/
# 修改权限
sudo chown -R $(whoami):$(whoami) /opt/easyremote/
```

3. **网络连接问题**
```bash
# 检查防火墙
sudo ufw status
# 开放端口
sudo ufw allow 8080
```

4. **内存不足**
```bash
# 检查内存使用
free -h
# 检查交换空间
swapon --show
```

## 📚 相关资源

- 📖 [基础使用教程](basic-usage.md)
-  [高级场景教程](advanced-scenarios.md)
- 📚 [API参考文档](../user-guide/api-reference.md)
- 🏗️ [架构设计文档](../architecture/overview.md)

## 💬 获取帮助

- 🐛 [GitHub Issues](https://github.com/Qingbolan/EasyCompute/issues)
- 💬 [社区讨论](https://github.com/Qingbolan/EasyCompute/discussions)
- 📧 [邮件支持](mailto:silan.hu@u.nus.edu) 