# EasyRemote Architecture Design

## 🏛️ System Architecture Overview

EasyRemote adopts a **simple star topology** with a VPS gateway at the center, enabling lightweight distributed computing without complex infrastructure.

```
┌─────────────────────────────────────────────────────────────────┐
│                    EasyRemote Network                           │
├─────────────────────────────────────────────────────────────────┤
│    Client A ──┐                                                 │
│               │                                                 │
│    Client B ──┤     VPS Gateway     ┌──── ComputeNode 1 (GPU)   │
│               │      (Server)       │                           │
│    Client C ──┤                     ├──── ComputeNode 2 (CPU)   │
│               │                     │                           │
│    Client D ──┘                     └──── ComputeNode 3 (Edge)  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 🧬 Core Components

### 1. ComputeNode (Resource Provider)

The ComputeNode is the fundamental unit that provides computational resources to the network.

```python
from easyremote import ComputeNode

class ComputeNode:
    def __init__(self, vps_address: str, node_id: str, **config):
        self.vps_address = vps_address
        self.node_id = node_id
        self.registered_functions = {}
        self.connection_manager = ConnectionManager()
        self.resource_monitor = ResourceMonitor()
    
    def register(self, func=None, **options):
        """Decorator to register functions for remote execution"""
        def decorator(func):
            function_id = f"{self.node_id}.{func.__name__}"
            self.registered_functions[function_id] = {
                "function": func,
                "metadata": self._extract_metadata(func),
                "options": options
            }
            return func
        
        if func is None:
            return decorator
        return decorator(func)
    
    async def serve(self):
        """Start serving registered functions"""
        await self.connection_manager.connect_to_gateway(self.vps_address)
        await self._register_with_gateway()
        await self._start_function_server()
```

#### Key Features:
- **Function Registration**: `@node.register` decorator for exposing functions
- **Automatic Discovery**: Self-registration with VPS gateway
- **Resource Monitoring**: Track CPU, memory, GPU usage
- **Secure Communication**: TLS encryption with gateway
- **Fault Tolerance**: Automatic reconnection and health checks

#### Advanced Registration Options:
```python
@node.register(
    async_func=True,           # Async function support
    stream=True,               # Streaming response support
    timeout=60,                # Execution timeout
    resource_requirements={    # Resource requirements
        "gpu": True,
        "memory": "8GB"
    },
    auth_required=True,        # Authentication required
    public=False              # Public API exposure
)
async def advanced_function(data):
    """Advanced function with all features"""
    async for result in process_streaming_data(data):
        yield result
```

### 2. VPS Gateway (Central Coordinator)

The VPS Gateway serves as the central coordination point for the entire network.

```python
from easyremote import Server
from fastapi import FastAPI

class EasyRemoteServer:
    def __init__(self, port: int = 8080):
        self.port = port
        self.app = FastAPI()
        self.node_registry = NodeRegistry()
        self.function_registry = FunctionRegistry()
        self.load_balancer = LoadBalancer()
        self.api_generator = APIGenerator()
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes for remote function calls"""
        
        @self.app.post("/api/{function_path:path}")
        async def execute_remote_function(function_path: str, request: dict):
            # Find suitable node for function
            node = await self.load_balancer.select_node(function_path)
            
            # Execute function on selected node
            result = await node.execute_function(function_path, request)
            
            return result
        
        @self.app.websocket("/nodes/{node_id}")
        async def node_connection(websocket: WebSocket, node_id: str):
            # Handle ComputeNode connections
            await self.node_registry.register_node(node_id, websocket)
            await self._handle_node_communication(websocket, node_id)
```

#### Core Responsibilities:
- **Node Management**: Register and monitor ComputeNodes
- **Function Discovery**: Maintain registry of available functions
- **Load Balancing**: Distribute requests across nodes
- **API Generation**: Automatically create REST/WebSocket APIs
- **Authentication**: Handle security and access control
- **Monitoring**: Track system health and performance

#### Function Registry System:
```python
class FunctionRegistry:
    def __init__(self):
        self.functions = {}  # function_id -> node_info
        self.capabilities = {}  # node_id -> capabilities
        
    async def register_function(self, node_id: str, function_info: dict):
        """Register a function from a ComputeNode"""
        function_id = f"{node_id}.{function_info['name']}"
        self.functions[function_id] = {
            "node_id": node_id,
            "function_info": function_info,
            "registered_at": datetime.utcnow(),
            "health_status": "healthy"
        }
        
        # Update node capabilities
        await self._update_node_capabilities(node_id, function_info)
    
    async def find_function_providers(self, function_name: str) -> List[str]:
        """Find all nodes that provide a specific function"""
        providers = []
        for func_id, info in self.functions.items():
            if info["function_info"]["name"] == function_name:
                providers.append(info["node_id"])
        return providers
```

### 3. Client (Function Consumer)

Clients consume remote functions using the `@remote` decorator or direct API calls.

```python
from easyremote import remote

class RemoteFunction:
    def __init__(self, node_id: str, function_name: str, gateway_url: str):
        self.node_id = node_id
        self.function_name = function_name
        self.gateway_url = gateway_url
        self.http_client = HTTPClient()
    
    async def __call__(self, *args, **kwargs):
        """Execute remote function call"""
        request_data = {
            "args": args,
            "kwargs": kwargs,
            "metadata": {
                "call_id": generate_call_id(),
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        function_path = f"{self.node_id}.{self.function_name}"
        response = await self.http_client.post(
            f"{self.gateway_url}/api/{function_path}",
            json=request_data
        )
        
        return response.json()

# Decorator for creating remote function proxies
def remote(node_id: str, function_name: str = None, **options):
    def decorator(func):
        func_name = function_name or func.__name__
        remote_func = RemoteFunction(node_id, func_name, gateway_url)
        
        # Copy function signature for better IDE support
        remote_func.__name__ = func.__name__
        remote_func.__doc__ = func.__doc__
        remote_func.__annotations__ = func.__annotations__
        
        return remote_func
    return decorator
```

#### Usage Patterns:
```python
# Method 1: Decorator-based
@remote(node_id="gpu-workstation")
def train_model(model_config, dataset_path):
    """Train ML model on remote GPU"""
    pass  # Implementation is remote

result = await train_model(config, "data/train.csv")

# Method 2: Direct API calls
import requests
response = requests.post(
    "https://your-vps.com/api/gpu-workstation.train_model",
    json={
        "args": [config, "data/train.csv"],
        "kwargs": {}
    }
)

# Method 3: Dynamic function creation
remote_train = remote("gpu-workstation", "train_model")
result = await remote_train(config, "data/train.csv")
```

## 🌐 Network Communication

### Connection Management

```python
class ConnectionManager:
    def __init__(self):
        self.gateway_connection = None
        self.reconnect_policy = ExponentialBackoff()
        self.heartbeat_interval = 30  # seconds
        
    async def connect_to_gateway(self, gateway_url: str):
        """Establish persistent connection to VPS gateway"""
        while True:
            try:
                self.gateway_connection = await websockets.connect(
                    f"ws://{gateway_url}/nodes/{self.node_id}",
                    extra_headers=self._get_auth_headers()
                )
                
                # Start heartbeat
                asyncio.create_task(self._heartbeat_loop())
                
                # Handle incoming messages
                await self._message_handler()
                
            except ConnectionError as e:
                wait_time = self.reconnect_policy.next_wait_time()
                await asyncio.sleep(wait_time)
```

### Message Protocol

```python
@dataclass
class Message:
    type: str
    payload: dict
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

# Message types
class MessageType:
    FUNCTION_CALL = "function_call"
    FUNCTION_RESPONSE = "function_response"
    REGISTER_FUNCTION = "register_function"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    STREAM_DATA = "stream_data"

# Function call message
function_call_msg = Message(
    type=MessageType.FUNCTION_CALL,
    payload={
        "function_id": "gpu-node.train_model",
        "args": [model_config],
        "kwargs": {"epochs": 10},
        "call_id": "call_123",
        "stream": False
    }
)
```

### Data Serialization

```python
class DataSerializer:
    def __init__(self):
        self.serializers = {
            "json": JSONSerializer(),
            "pickle": PickleSerializer(),
            "msgpack": MessagePackSerializer(),
            "protobuf": ProtobufSerializer()
        }
        
    def serialize(self, data: Any, format: str = "json") -> bytes:
        """Serialize data for network transmission"""
        serializer = self.serializers[format]
        
        # Handle large data with compression
        serialized = serializer.serialize(data)
        
        if len(serialized) > 1024 * 1024:  # 1MB threshold
            return gzip.compress(serialized)
        
        return serialized
    
    def deserialize(self, data: bytes, format: str = "json") -> Any:
        """Deserialize data from network"""
        # Auto-detect compression
        if data.startswith(b'\x1f\x8b'):  # gzip magic number
            data = gzip.decompress(data)
            
        serializer = self.serializers[format]
        return serializer.deserialize(data)
```

## 🛡️ Security Architecture

### Authentication System

```python
class AuthenticationManager:
    def __init__(self, auth_config: dict):
        self.auth_config = auth_config
        self.token_manager = TokenManager()
        self.node_authenticator = NodeAuthenticator()
        
    async def authenticate_node(self, node_id: str, credentials: dict) -> AuthResult:
        """Authenticate ComputeNode connection"""
        
        # Method 1: API Key authentication
        if "api_key" in credentials:
            return await self._authenticate_api_key(node_id, credentials["api_key"])
        
        # Method 2: Certificate-based authentication
        if "certificate" in credentials:
            return await self._authenticate_certificate(node_id, credentials["certificate"])
        
        # Method 3: Token-based authentication
        if "token" in credentials:
            return await self._authenticate_token(node_id, credentials["token"])
        
        return AuthResult(success=False, error="No valid credentials provided")
    
    async def authenticate_client_request(self, request: dict) -> bool:
        """Authenticate client function call"""
        auth_header = request.get("authorization")
        
        if not auth_header:
            return self.auth_config.get("allow_anonymous", False)
        
        return await self.token_manager.validate_token(auth_header)
```

### Data Security

```python
class SecurityLayer:
    def __init__(self):
        self.encryption = AESEncryption()
        self.signing = DigitalSigning()
        
    async def secure_message(self, message: Message, recipient: str) -> bytes:
        """Encrypt and sign message for secure transmission"""
        
        # Serialize message
        serialized = message.to_bytes()
        
        # Encrypt with recipient's public key
        encrypted = await self.encryption.encrypt(serialized, recipient)
        
        # Sign with our private key
        signed = await self.signing.sign(encrypted)
        
        return signed
    
    async def verify_and_decrypt(self, data: bytes, sender: str) -> Message:
        """Verify signature and decrypt message"""
        
        # Verify signature
        verified_data = await self.signing.verify(data, sender)
        
        # Decrypt message
        decrypted = await self.encryption.decrypt(verified_data)
        
        # Deserialize to message
        return Message.from_bytes(decrypted)
```

## 📊 Performance & Scalability

### Load Balancing

```python
class LoadBalancer:
    def __init__(self):
        self.strategies = {
            "round_robin": RoundRobinStrategy(),
            "least_connections": LeastConnectionsStrategy(),
            "resource_based": ResourceBasedStrategy(),
            "latency_based": LatencyBasedStrategy()
        }
        
    async def select_node(self, function_id: str, strategy: str = "resource_based") -> str:
        """Select optimal node for function execution"""
        
        available_nodes = await self.get_available_nodes(function_id)
        
        if not available_nodes:
            raise NoAvailableNodesError(f"No nodes available for {function_id}")
        
        balancer = self.strategies[strategy]
        selected_node = await balancer.select(available_nodes)
        
        return selected_node

class ResourceBasedStrategy:
    async def select(self, nodes: List[NodeInfo]) -> str:
        """Select node based on resource availability"""
        best_node = None
        best_score = 0
        
        for node in nodes:
            # Calculate resource score
            cpu_score = (100 - node.cpu_usage) / 100
            memory_score = (100 - node.memory_usage) / 100
            
            # Weight by node capabilities
            capability_score = self._calculate_capability_score(node)
            
            total_score = (cpu_score + memory_score + capability_score) / 3
            
            if total_score > best_score:
                best_score = total_score
                best_node = node
        
        return best_node.node_id
```

### Performance Monitoring

```python
class PerformanceMonitor:
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.performance_analyzer = PerformanceAnalyzer()
        
    async def track_function_call(self, call_info: dict):
        """Track function call performance"""
        start_time = time.time()
        
        try:
            # Execute function call
            result = await self._execute_function_call(call_info)
            
            # Record success metrics
            execution_time = time.time() - start_time
            await self.metrics_collector.record_success(
                function_id=call_info["function_id"],
                execution_time=execution_time,
                data_size=len(result)
            )
            
            return result
            
        except Exception as e:
            # Record failure metrics
            await self.metrics_collector.record_failure(
                function_id=call_info["function_id"],
                error_type=type(e).__name__,
                execution_time=time.time() - start_time
            )
            raise
    
    async def get_performance_report(self) -> dict:
        """Generate comprehensive performance report"""
        return await self.performance_analyzer.generate_report()
```

### Caching System

```python
class DistributedCache:
    def __init__(self):
        self.local_cache = LRUCache(maxsize=1000)
        self.redis_cache = RedisCache()
        
    async def get_cached_result(self, call_signature: str) -> Optional[Any]:
        """Get cached function result"""
        
        # Check local cache first
        result = self.local_cache.get(call_signature)
        if result is not None:
            return result
        
        # Check distributed cache
        result = await self.redis_cache.get(call_signature)
        if result is not None:
            # Store in local cache for faster access
            self.local_cache[call_signature] = result
            return result
        
        return None
    
    async def cache_result(self, call_signature: str, result: Any, ttl: int = 3600):
        """Cache function result"""
        
        # Store in both local and distributed cache
        self.local_cache[call_signature] = result
        await self.redis_cache.set(call_signature, result, ttl=ttl)

def cacheable(ttl: int = 3600):
    """Decorator for caching function results"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = generate_cache_key(func.__name__, args, kwargs)
            
            # Check cache
            cached_result = await cache.get_cached_result(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            await cache.cache_result(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator
```

## Configuration & Management

### Node Configuration

```python
@dataclass
class NodeConfig:
    node_id: str
    vps_address: str
    
    # Resource limits
    max_concurrent_functions: int = 10
    max_memory_usage: float = 0.8  # 80% of available memory
    max_cpu_usage: float = 0.9     # 90% of available CPU
    
    # Security settings
    auth_required: bool = True
    api_key: Optional[str] = None
    certificate_path: Optional[str] = None
    
    # Performance settings
    reconnect_interval: int = 5
    heartbeat_interval: int = 30
    request_timeout: int = 60
    
    # Feature flags
    enable_streaming: bool = True
    enable_caching: bool = True
    enable_compression: bool = True

# Usage
config = NodeConfig(
    node_id="my-gpu-workstation",
    vps_address="your-vps.com:8080",
    max_concurrent_functions=5,
    auth_required=True,
    api_key="your-secret-key"
)

node = ComputeNode(config)
```

### Gateway Configuration

```python
@dataclass
class GatewayConfig:
    port: int = 8080
    host: str = "0.0.0.0"
    
    # Security
    enable_https: bool = True
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    
    # Performance
    max_connections: int = 1000
    connection_timeout: int = 30
    
    # Features
    enable_api_docs: bool = True
    enable_metrics: bool = True
    enable_web_ui: bool = True
    
    # Load balancing
    default_strategy: str = "resource_based"
    health_check_interval: int = 10

# Usage
config = GatewayConfig(
    port=8080,
    enable_https=True,
    ssl_cert_path="/path/to/cert.pem",
    ssl_key_path="/path/to/key.pem"
)

server = EasyRemoteServer(config)
```

##  Future Architecture Enhancements

### Planned Improvements

1. **Go Backend**: Rewrite core components in Go using Kitex framework for better performance
2. **Multi-Gateway Support**: Support multiple VPS gateways for redundancy and geographic distribution
3. **Advanced Scheduling**: More sophisticated task scheduling and resource allocation
4. **Plugin System**: Extensible architecture for custom functionality

### Extensibility Framework

```python
class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.hooks = defaultdict(list)
    
    def register_plugin(self, plugin: Plugin):
        """Register a new plugin"""
        self.plugins[plugin.name] = plugin
        
        # Register plugin hooks
        for hook_name, handler in plugin.get_hooks().items():
            self.hooks[hook_name].append(handler)
    
    async def execute_hook(self, hook_name: str, *args, **kwargs):
        """Execute all handlers for a hook"""
        results = []
        for handler in self.hooks[hook_name]:
            result = await handler(*args, **kwargs)
            results.append(result)
        return results

# Example plugin
class MonitoringPlugin(Plugin):
    name = "monitoring"
    
    def get_hooks(self):
        return {
            "before_function_call": self.log_function_call,
            "after_function_call": self.record_metrics
        }
    
    async def log_function_call(self, function_id: str, args: list, kwargs: dict):
        print(f"Calling function {function_id} with args {args}")
    
    async def record_metrics(self, function_id: str, result: Any, execution_time: float):
        await self.metrics_db.record(function_id, execution_time)
```

---

*This architecture is designed to be simple, scalable, and maintainable while providing the flexibility needed for diverse distributed computing use cases.* 