# EasyRemote Node Types & Roles

## 🎭 Simple and Effective Role Model

EasyRemote uses a **simple three-role architecture** that focuses on ease of use and practical functionality rather than complex distributed systems theory.

## 🌟 Core Roles

### 1. ComputeNode (Resource Provider)
> **Primary Function**: Provide computational resources to the network

The ComputeNode is any machine that offers its computational capabilities to the EasyRemote network.

```python
from easyremote import ComputeNode
from easyremote.core.data import ResourceRequirements

# GPU workstation sharing its power
node = ComputeNode(
    gateway_address="gateway.example.com:8080",
    node_id="gpu-workstation-01"
)

@node.register
def train_deep_learning_model(model_config, dataset):
    """Train a model using local GPU"""
    # This runs on the ComputeNode's hardware
    return train_model_on_gpu(model_config, dataset)

@node.register
def process_video_stream(video_data):
    """Process video frames in real-time"""
    for frame in video_data:
        processed_frame = gpu_process_frame(frame)
        yield processed_frame

node.serve()  # Start serving functions
```

**Key Characteristics**:
- **Resource Ownership**: Owns and manages local computational resources
- **Function Provider**: Exposes functions for remote execution
- **Self-Registration**: Automatically registers with VPS Gateway
- **Resource Monitoring**: Tracks local resource usage and health
- **Security**: Ensures only authorized requests are processed

**Types of ComputeNodes**:

#### High-Performance GPU Node
```python
gpu_node = ComputeNode(
    gateway_address="gateway.com:8080",
    node_id="rtx4090-machine"
)

@gpu_node.register(
    resource_requirements=ResourceRequirements(gpu_required=True, min_memory_mb=16384),
    tags={"ai_training", "rendering", "simulation"},
)
def train_large_model(model_architecture, training_data):
    """Train large AI models requiring significant GPU memory"""
    return train_with_cuda(model_architecture, training_data)
```

#### CPU-Optimized Node
```python
cpu_node = ComputeNode(
    gateway_address="gateway.com:8080",
    node_id="cpu-powerhouse"
)

@cpu_node.register(tags={"data_processing", "compilation", "analysis"})
async def parallel_data_processing(large_dataset):
    """Process large datasets using all CPU cores"""
    return await process_with_multiprocessing(large_dataset)
```

#### Edge Computing Node
```python
edge_node = ComputeNode(
    gateway_address="gateway.com:8080",
    node_id="raspberry-pi-sensor"
)

@edge_node.register(tags={"iot_data", "local_inference"})
def capture_sensor_data():
    """Capture real-time sensor data from edge device"""
    return {
        "temperature": get_temperature(),
        "motion": detect_motion(),
        "timestamp": time.time()
    }
```

#### Specialized Service Node
```python
service_node = ComputeNode(
    gateway_address="gateway.com:8080",
    node_id="database-service"
)

@service_node.register(tags={"data_storage", "search", "analytics"})
def query_database(query, params):
    """Execute database queries with proper authentication"""
    return execute_secure_query(query, params)
```

### 2. VPS Gateway (Central Coordinator)
> **Primary Function**: Coordinate communication between clients and compute nodes

The VPS Gateway is the central hub that makes the entire network possible.

```python
from easyremote import Server
from fastapi import FastAPI

# Simple gateway setup
app = FastAPI()
server = Server(port=8080)

# Gateway automatically:
# 1. Accepts ComputeNode registrations
# 2. Creates API endpoints for registered functions
# 3. Routes client requests to appropriate nodes
# 4. Handles load balancing and health monitoring

if __name__ == "__main__":
    server.start()
```

**Core Responsibilities**:

#### Function Registry Management
```python
class FunctionRegistry:
    def __init__(self):
        self.registered_functions = {}
        self.node_capabilities = {}
    
    async def register_function(self, node_id: str, function_info: dict):
        """Register a function from a ComputeNode"""
        function_path = f"{node_id}.{function_info['name']}"
        
        self.registered_functions[function_path] = {
            "node_id": node_id,
            "function_name": function_info['name'],
            "metadata": function_info.get('metadata', {}),
            "requirements": function_info.get('requirements', {}),
            "registered_at": datetime.utcnow(),
            "health_status": "healthy"
        }
        
        # Auto-generate API endpoint
        await self.create_api_endpoint(function_path)
    
    async def create_api_endpoint(self, function_path: str):
        """Automatically create REST API endpoint"""
        @app.post(f"/api/{function_path}")
        async def execute_function(request: dict):
            node_id = self.registered_functions[function_path]["node_id"]
            node = self.get_connected_node(node_id)
            return await node.execute_function(request)
```

#### Load Balancing & Health Monitoring
```python
class GatewayOrchestrator:
    def __init__(self):
        self.node_health = {}
        self.load_balancer = LoadBalancer()
    
    async def route_request(self, function_name: str, request: dict):
        """Route request to best available node"""
        # Find all nodes that provide this function
        available_nodes = self.find_function_providers(function_name)
        
        # Filter by health status
        healthy_nodes = [node for node in available_nodes 
                        if self.node_health[node] == "healthy"]
        
        if not healthy_nodes:
            raise NoHealthyNodesError(f"No healthy nodes for {function_name}")
        
        # Select best node based on load balancing strategy
        selected_node = await self.load_balancer.select_node(
            healthy_nodes, request_requirements=request.get('requirements', {})
        )
        
        return await self.execute_on_node(selected_node, function_name, request)
```

#### API Generation & Documentation
```python
class APIGenerator:
    def __init__(self, app: FastAPI):
        self.app = app
    
    async def auto_generate_api(self, function_info: dict):
        """Automatically generate OpenAPI documentation"""
        function_path = f"{function_info['node_id']}.{function_info['name']}"
        
        # Create endpoint with proper typing
        @self.app.post(
            f"/api/{function_path}",
            summary=function_info.get('description', ''),
            response_model=function_info.get('return_type', dict),
            tags=[function_info['node_id']]
        )
        async def generated_endpoint(request: function_info.get('input_type', dict)):
            return await self.route_to_node(function_path, request)
        
        # Update OpenAPI schema
        self.app.openapi_schema = None  # Force regeneration
```

**Gateway Features**:
- **Automatic API Generation**: REST endpoints for all registered functions
- **OpenAPI Documentation**: Auto-generated API docs
- **Health Monitoring**: Track node health and availability
- **Load Balancing**: Distribute requests optimally
- **Authentication**: Secure access control
- **Monitoring Dashboard**: Real-time network status

### 3. Client (Function Consumer)
> **Primary Function**: Consume remote computational resources

Clients use remote functions as if they were local, with full type safety and IDE support.

```python
from easyremote import remote
from easyremote.core.nodes.client import set_default_gateway

set_default_gateway("gateway.com:8080")

# Method 1: Decorator-based (recommended)
@remote(node_id="gpu-workstation-01")
def train_deep_learning_model(model_config, dataset):
    """This function runs remotely on the GPU workstation"""
    pass  # Implementation is on the remote node

# Method 2: Direct wrapper creation from an existing function object
def _train_stub(model_config, dataset):
    pass

remote_trainer = remote(
    _train_stub,
    node_id="gpu-workstation-01",
    function_name="train_deep_learning_model",
)

# Method 3: Explicit gateway binding per function
@remote(node_id="gpu-workstation-01", gateway_address="gateway.com:8080")
def train_model_anywhere(model_config, dataset):
    pass

# Usage - exactly like local functions!
model_config = {"layers": 10, "learning_rate": 0.001}
dataset = load_training_data()

result = await train_deep_learning_model(model_config, dataset)
print(f"Training completed: {result}")
```

**Client Patterns**:

#### Research Scientist
```python
# Researcher using multiple remote resources
@remote(node_id="hpc-cluster")
def run_simulation(simulation_params):
    pass

@remote(node_id="gpu-farm") 
def train_model(model_config):
    pass

@remote(node_id="data-warehouse")
def query_large_dataset(query):
    pass

# Compose complex workflows
async def research_pipeline(experiment_config):
    # Step 1: Get data
    data = await query_large_dataset(experiment_config.data_query)
    
    # Step 2: Run simulation
    simulation_results = await run_simulation({
        "data": data,
        "parameters": experiment_config.sim_params
    })
    
    # Step 3: Train model
    model = await train_model({
        "architecture": experiment_config.model_arch,
        "training_data": simulation_results
    })
    
    return {"model": model, "results": simulation_results}
```

#### Startup Developer
```python
# Startup using shared GPU resources for development
@remote(node_id="shared-gpu-01", timeout=120)
def fine_tune_model(base_model, custom_data):
    pass

@remote(function_name="serve_model_inference", load_balancing=True)
def serve_model_inference(model_id, input_data):
    pass

# Cost-effective AI development
async def develop_ai_feature(user_data):
    # Fine-tune model for specific use case
    custom_model = await fine_tune_model("gpt-3.5-turbo", user_data)
    
    # Deploy for inference
    inference_endpoint = await serve_model_inference(custom_model.id, test_data)
    
    return inference_endpoint
```

#### Enterprise Application
```python
# Enterprise app using distributed microservices
@remote(node_id="auth-service")
def authenticate_user(credentials):
    pass

@remote(node_id="payment-processor")
def process_payment(payment_info):
    pass

@remote(node_id="recommendation-engine")
def get_recommendations(user_id):
    pass

# Distributed application architecture
async def handle_user_request(user_request):
    # Authenticate
    user = await authenticate_user(user_request.credentials)
    
    if user_request.type == "purchase":
        payment_result = await process_payment(user_request.payment_info)
        return {"status": "purchased", "transaction": payment_result}
    
    elif user_request.type == "browse":
        recommendations = await get_recommendations(user.id)
        return {"recommendations": recommendations}
```

## 🔄 Role Interactions

### Registration Flow
```
ComputeNode                VPS Gateway               Client
     │                          │                     │
     │─── Register Functions ──→│                     │
     │                          │                     │
     │                          │←── Request Function ─│
     │                          │                     │
     │←── Execute Function ──────│                     │
     │                          │                     │
     │─── Return Result ────────→│                     │
     │                          │                     │
     │                          │─── Return Result ──→│
```

### Dynamic Discovery Flow
```
Client                     VPS Gateway               ComputeNodes
  │                           │                         │
  │── Find GPU Nodes ────────→│                         │
  │                           │─── Query Capabilities ─→│
  │                           │←── Return Capabilities ──│
  │←── Available Nodes ───────│                         │
  │                           │                         │
  │── Execute on Best Node ──→│                         │
  │                           │─── Route to Selected ──→│
```

### Load Balancing Example
```python
class SmartLoadBalancer:
    async def select_best_node(self, function_name: str, requirements: dict):
        """Select optimal node based on multiple factors"""
        candidates = await self.find_capable_nodes(function_name, requirements)
        
        scores = {}
        for node in candidates:
            score = await self.calculate_node_score(node, requirements)
            scores[node] = score
        
        # Select highest scoring node
        best_node = max(scores.items(), key=lambda x: x[1])[0]
        return best_node
    
    async def calculate_node_score(self, node: str, requirements: dict) -> float:
        """Calculate suitability score for a node"""
        node_status = await self.get_node_status(node)
        
        # Factors: resource availability, latency, load, capability match
        resource_score = self.score_resources(node_status.resources, requirements)
        latency_score = 1.0 / (node_status.avg_latency + 1)
        load_score = 1.0 - (node_status.current_load / node_status.max_capacity)
        capability_score = self.score_capabilities(node_status.capabilities, requirements)
        
        # Weighted average
        total_score = (
            resource_score * 0.3 +
            latency_score * 0.2 + 
            load_score * 0.3 +
            capability_score * 0.2
        )
        
        return total_score
```

##  Role-Based Use Cases

### GPU Sharing Team
```python
# Team lead sets up shared GPU node
gpu_node = ComputeNode("team-gateway:8080", "team-gpu-01")

@gpu_node.register(max_concurrent=1, tags={"team-shared"})
def train_team_model(user_id, model_config, dataset):
    """Shared GPU training with fair usage quotas"""
    return train_with_quota_management(user_id, model_config, dataset)

# Team members use shared resource
@remote(node_id="team-gpu-01")
def train_team_model(user_id, model_config, dataset):
    pass

# Alice trains her model
alice_result = await train_team_model("alice", alice_config, alice_data)

# Bob trains his model (queued if Alice is using GPU)
bob_result = await train_team_model("bob", bob_config, bob_data)
```

### Academic Research Network
```python
# University contributes HPC cluster
hpc_node = ComputeNode("research-gateway:8080", "stanford-hpc")

@hpc_node.register(timeout_seconds=1800, tags={"academic", "verified"})
def run_climate_simulation(research_proposal_id, params):
    """Run climate simulations for academic research"""
    return submit_to_slurm_cluster(research_proposal_id, params)

# Researchers from other institutions
@remote(node_id="stanford-hpc", timeout=600)
def run_climate_simulation(research_proposal_id, params):
    pass

# MIT researcher uses Stanford's resources
mit_results = await run_climate_simulation("MIT-2024-001", climate_params)
```

### Startup MVP Development
```python
# Startup rents dedicated inference node
inference_node = ComputeNode("startup-gateway:8080", "inference-01")

@inference_node.register(load_balancing=True, max_concurrent=16)
def serve_ai_api(model_version, user_input):
    """Serve AI model with auto-scaling"""
    return model_inference(model_version, user_input)

# Frontend application
@remote(node_id="inference-01")
def serve_ai_api(model_version, user_input):
    pass

# Handle user requests
async def handle_user_query(user_input):
    ai_response = await serve_ai_api("v1.2", user_input)
    return {"response": ai_response, "model": "v1.2"}
```

## 📊 Role Performance Metrics

### ComputeNode Metrics
```python
@dataclass
class ComputeNodeMetrics:
    # Resource utilization
    cpu_usage: float
    memory_usage: float 
    gpu_usage: float
    
    # Function execution
    functions_executed: int
    avg_execution_time: float
    success_rate: float
    
    # Network performance  
    uptime: float
    connection_stability: float
    data_transfer_rate: float
    
    # Business metrics
    revenue_generated: float  # If monetized
    user_satisfaction: float
```

### VPS Gateway Metrics
```python
@dataclass 
class GatewayMetrics:
    # Network coordination
    connected_nodes: int
    active_functions: int
    requests_per_second: float
    
    # Load balancing efficiency
    node_utilization_balance: float
    request_routing_latency: float
    
    # System health
    uptime: float
    error_rate: float
    avg_response_time: float
```

### Client Metrics  
```python
@dataclass
class ClientMetrics:
    # Usage patterns
    functions_called: int
    avg_call_frequency: float
    preferred_node_types: List[str]
    
    # Performance experience
    avg_response_time: float
    success_rate: float
    cost_efficiency: float
    
    # Satisfaction
    retry_rate: float
    feature_adoption: float
```

##  Role Evolution

### Current State
- **Simple**: Three clear roles with distinct responsibilities
- **Practical**: Focused on real-world use cases
- **Accessible**: Easy to understand and implement

### Future Enhancements

#### Specialized Node Types
```python
# Future: Specialized node roles
class QuantumComputeNode(ComputeNode):
    """Specialized node for quantum computing tasks"""
    
    @node.register(tags={"quantum_backend:ibm_q"})
    def run_quantum_circuit(circuit_definition):
        return execute_on_quantum_hardware(circuit_definition)

class MLOpsNode(ComputeNode):
    """Specialized node for ML operations"""
    
    @node.register(tags={"pipeline:automated"})
    def deploy_model(model_artifact, deployment_config):
        return automated_model_deployment(model_artifact, deployment_config)
```

#### Enhanced Gateway Features
```python
# Future: Advanced gateway capabilities
class IntelligentGateway(Server):
    """Gateway with AI-powered optimization"""
    
    async def predictive_scaling(self):
        """Predict resource needs and scale preemptively"""
        demand_forecast = await self.ml_predictor.forecast_demand()
        await self.resource_scheduler.scale_for_demand(demand_forecast)
    
    async def intelligent_caching(self, function_call):
        """AI-driven caching decisions"""
        cache_value = await self.cache_predictor.should_cache(function_call)
        if cache_value > threshold:
            await self.cache_manager.cache_result(function_call)
```

#### Advanced Client Features  
```python
# Future: Smart client capabilities
@remote(load_balancing={"requirements": {"latency": "low"}})
def smart_function(data):
    """Function with automatic optimization"""
    pass

# Client automatically:
# - Chooses best node based on data characteristics
# - Splits large jobs across multiple nodes  
# - Handles retries and failover
# - Optimizes data transfer
result = await smart_function(large_dataset)
```

---

*This simple three-role model makes EasyRemote accessible to developers while providing the flexibility needed for complex distributed computing scenarios.* 
