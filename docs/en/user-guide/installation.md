# EasyRemote Installation Guide

## 📋 System Requirements

### Minimum Requirements
- Python 3.9+
- Operating System: Windows, macOS, Linux
- Memory: 512MB
- Network: Stable internet connection

### Recommended Configuration
- Python 3.9+
- Memory: 2GB+
- CPU: Multi-core processor
- Network: Low-latency network environment

## 📦 Installation Methods

### Method 1: Install using pip (Recommended)

```bash
pip install easyremote
```

### Method 2: Install specific version using pip

```bash
# Install latest version
pip install easyremote --upgrade

# Install specific version
pip install easyremote==1.0.0
```

### Method 3: Install from source code

```bash
# Clone repository
git clone https://github.com/Qingbolan/EasyCompute.git
cd EasyCompute

# Install dependencies and package
pip install -e .
```

## Dependency Management

### Core Dependencies
```bash
# EasyRemote core dependencies will be installed automatically
pip install grpcio>=1.50.0
pip install protobuf>=4.21.0
```

### Optional Dependencies
#### Built-in package extras
```bash
# GPU metrics (optional)
pip install "easyremote[gpu]"

# Protobuf/gRPC code generation tools (optional)
pip install "easyremote[build]"
```

#### AI/ML Workloads
```bash
# For AI inference workloads
pip install torch torchvision
pip install tensorflow
pip install numpy pandas
```

#### Advanced Features
```bash
# For monitoring and logging
pip install prometheus-client
pip install structlog

# For encryption and security
pip install cryptography
```

## 🐳 Docker Installation

### Pull official image
```bash
docker pull easyremote/easyremote:latest
```

### Run gateway server
```bash
docker run -p 8080:8080 easyremote/easyremote:latest server
```

### Run compute node
```bash
docker run easyremote/easyremote:latest node --gateway your-gateway:8080
```

## 🏗️ Development Environment Setup

### Recommended workflow (uv, for contributors)

```bash
uv sync
uv run ruff check easyremote tests gallery examples --output-format=full
uv run pytest -q
uv run python gallery/run_smoke_tests.py
```

### Create virtual environment
```bash
# Using venv
python -m venv easyremote-env
source easyremote-env/bin/activate  # Linux/macOS
# easyremote-env\Scripts\activate   # Windows

# Using conda
conda create -n easyremote python=3.9
conda activate easyremote
```

### Install development dependencies
```bash
pip install easyremote[dev]

# If you use uv, install project + default dev/test groups
uv sync

# Add optional feature extras when needed
uv sync --extra gpu --extra build

# Or manually install development tools
pip install pytest
pip install black
pip install flake8
pip install mypy
```

## ✅ Verify Installation

### Check version
```bash
python -c "import easyremote; print(easyremote.__version__)"
```

### Run basic test
```python
# test_installation.py
from easyremote import Server, ComputeNode, Client

print("✅ EasyRemote imported successfully")
print("✅ All core components available")

# Test basic functionality
try:
    server = Server(port=8081)
    print("✅ Server created successfully")
    
    node = ComputeNode("localhost:8081")
    print("✅ ComputeNode created successfully")
    
    client = Client("localhost:8081") 
    print("✅ Client created successfully")
    
    print("🎉 Installation verification complete!")
except Exception as e:
    print(f"❌ Installation verification failed: {e}")
```

## 🔍 Troubleshooting

### Common Issues

#### 1. Import Errors
```bash
# Issue: ModuleNotFoundError: No module named 'easyremote'
# Solution: Confirm correct installation
pip list | grep easyremote
pip install easyremote --force-reinstall
```

#### 2. gRPC Dependency Issues
```bash
# Issue: grpc module related errors
# Solution: Reinstall grpc dependencies
pip uninstall grpcio
pip install grpcio --no-cache-dir

# Install grpcio-tools only if you need proto code generation
pip install "easyremote[build]"
```

#### 3. Network Connection Issues
```bash
# Issue: Cannot connect to gateway server
# Solution: Check network and firewall settings
telnet your-gateway-ip 8080
```

#### 4. Permission Issues
```bash
# Issue: Permission denied
# Solution: Use user installation
pip install --user easyremote
```

### Platform-Specific Issues

#### Windows
```powershell
# If encountering long path issues
git config --system core.longpaths true

# If encountering Visual Studio build tools issues
# Install Microsoft C++ Build Tools
```

#### macOS
```bash
# If encountering SSL certificate issues
/Applications/Python\ 3.x/Install\ Certificates.command

# If encountering permission issues
sudo chown -R $(whoami) /usr/local/lib/python3.x/site-packages
```

#### Linux
```bash
# If encountering compilation issues, install build tools
sudo apt-get install build-essential
sudo apt-get install python3-dev

# CentOS/RHEL
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel
```

## 🎓 Next Steps

After installation, you can:

1. 📖 [Quick Start](quick-start.md) - 5-minute tutorial
2. 🎓 [Basic Tutorial](../tutorials/basic-usage.md) - Detailed learning guide
3. 📚 [API Reference](api-reference.md) - Complete API documentation
4. 💡 [Examples](examples.md) - Practical use cases

## 🆘 Getting Help

If you encounter issues during installation:

- 🐛 [GitHub Issues](https://github.com/Qingbolan/EasyCompute/issues)
- 💬 [Community Discussions](https://github.com/Qingbolan/EasyCompute/discussions)
- 📧 [Email Support](mailto:silan.hu@u.nus.edu)

---

*Language: English | [中文](../../zh/user-guide/installation.md)* 
