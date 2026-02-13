# EasyRemote Load Balancing Design

##  Overview

EasyRemote supports **多节点负载均衡**，允许多个ComputeNode提供相同的函数，系统自动根据负载、性能和可用性分配请求。这确保了高可用性、可扩展性和最优的资源利用率。

## 🏗️ 负载均衡架构

### 核心概念

```
Client Request ──→ VPS Gateway ──→ Load Balancer ──→ Best Available Node
                        │                │
                        └─ Function Registry    └─ Node Health Monitor
                        │  - train_model         │  - gpu-node-1: 45% load
                        │    ├─ gpu-node-1       │  - gpu-node-2: 78% load  
                        │    ├─ gpu-node-2       │  - gpu-node-3: 23% load
                        │    └─ gpu-node-3       │
```

### 多节点函数提供

```python
# 多个节点可以提供相同的函数
# Node 1 - 高端工作站
@gpu_node_1.register(load_balancing=True)
def train_model(data):
    return train_on_rtx4090(data)

# Node 2 - 游戏PC
@gpu_node_2.register(load_balancing=True) 
def train_model(data):  # 相同函数名！
    return train_on_rtx3080(data)

# Node 3 - 云实例
@gpu_node_3.register(load_balancing=True)
def train_model(data):  # 相同函数名！
    return train_on_a100(data)
```

## 🎛️ 负载均衡策略

### 1. Round Robin (轮询)
```python
class RoundRobinBalancer:
    def __init__(self):
        self.current_index = 0
    
    async def select_node(self, available_nodes):
        """轮询选择节点"""
        if not available_nodes:
            raise NoAvailableNodesError()
        
        selected_node = available_nodes[self.current_index % len(available_nodes)]
        self.current_index += 1
        return selected_node

# 配置轮询负载均衡
@remote(function_name="train_model", load_balancing="round_robin")
def train_model(data):
    pass
```

### 2. Resource-Aware (资源感知)
```python
class ResourceAwareBalancer:
    async def select_node(self, available_nodes, request_requirements=None):
        """基于资源利用率选择最优节点"""
        best_node = None
        best_score = -1
        
        for node in available_nodes:
            node_stats = await self.get_node_stats(node.id)
            
            # 计算节点得分
            cpu_score = (100 - node_stats.cpu_usage) / 100
            memory_score = (100 - node_stats.memory_usage) / 100
            gpu_score = (100 - node_stats.gpu_usage) / 100 if node_stats.has_gpu else 0.5
            
            # 检查资源需求匹配
            requirement_score = self.check_requirements_match(
                node_stats.capabilities, 
                request_requirements or {}
            )
            
            # 综合得分
            total_score = (cpu_score + memory_score + gpu_score + requirement_score) / 4
            
            if total_score > best_score:
                best_score = total_score
                best_node = node
        
        return best_node

# 配置资源感知负载均衡
@remote(
    function_name="train_model",
    load_balancing={
        "strategy": "resource_aware",
        "requirements": {"gpu_memory": ">=16GB", "cpu_cores": ">=8"}
    }
)
def train_model(data):
    pass
```

### 3. Latency-Based (延迟优化)
```python
class LatencyBasedBalancer:
    def __init__(self):
        self.latency_history = {}
    
    async def select_node(self, available_nodes, client_location=None):
        """基于历史延迟选择最快节点"""
        best_node = None
        lowest_latency = float('inf')
        
        for node in available_nodes:
            # 获取历史延迟数据
            avg_latency = self.get_average_latency(node.id, client_location)
            
            # 考虑当前负载对延迟的影响
            current_load = await self.get_current_load(node.id)
            adjusted_latency = avg_latency * (1 + current_load * 0.5)
            
            if adjusted_latency < lowest_latency:
                lowest_latency = adjusted_latency
                best_node = node
        
        return best_node

# 配置延迟优化负载均衡
@remote(
    function_name="train_model",
    load_balancing={
        "strategy": "latency_based", 
        "max_latency": 100,  # 最大可接受延迟(ms)
        "prefer_local": True
    }
)
def train_model(data):
    pass
```

### 4. Cost-Aware (成本优化)
```python
class CostAwareBalancer:
    async def select_node(self, available_nodes, budget_constraints=None):
        """基于成本选择最经济节点"""
        eligible_nodes = []
        
        for node in available_nodes:
            node_cost = await self.get_node_cost_per_hour(node.id)
            estimated_duration = await self.estimate_execution_time(node.id)
            total_cost = node_cost * (estimated_duration / 3600)
            
            # 检查预算约束
            if budget_constraints and total_cost > budget_constraints.get("max_cost", float('inf')):
                continue
                
            eligible_nodes.append({
                "node": node,
                "cost": total_cost,
                "performance_ratio": await self.get_performance_ratio(node.id)
            })
        
        if not eligible_nodes:
            raise BudgetExceededError("No nodes within budget constraints")
        
        # 选择性价比最高的节点
        best_node = max(eligible_nodes, key=lambda x: x["performance_ratio"] / x["cost"])
        return best_node["node"]

# 配置成本优化负载均衡
@remote(
    function_name="train_model",
    load_balancing={
        "strategy": "cost_aware",
        "budget": {"max_cost": 5.0, "currency": "USD"}
    }
)
def train_model(data):
    pass
```

### 5. Smart Adaptive (智能自适应)
```python
class SmartAdaptiveBalancer:
    def __init__(self):
        self.performance_history = {}
        self.ml_predictor = MLPredictor()
    
    async def select_node(self, available_nodes, request_context):
        """使用机器学习预测最优节点"""
        
        # 收集特征数据
        features = []
        for node in available_nodes:
            node_features = await self.extract_node_features(node, request_context)
            features.append(node_features)
        
        # ML预测每个节点的性能
        performance_predictions = await self.ml_predictor.predict_performance(features)
        
        # 选择预测性能最佳的节点
        best_index = performance_predictions.argmax()
        selected_node = available_nodes[best_index]
        
        # 记录实际结果用于模型训练
        asyncio.create_task(self.record_actual_performance(selected_node, request_context))
        
        return selected_node
    
    async def extract_node_features(self, node, request_context):
        """提取节点特征用于ML预测"""
        stats = await self.get_node_stats(node.id)
        
        return {
            "cpu_usage": stats.cpu_usage,
            "memory_usage": stats.memory_usage,
            "gpu_usage": stats.gpu_usage,
            "current_queue_length": stats.queue_length,
            "historical_avg_time": self.get_historical_avg_time(node.id),
            "time_of_day": datetime.now().hour,
            "request_size": request_context.get("data_size", 0),
            "request_complexity": request_context.get("complexity_score", 1.0)
        }

# 配置智能自适应负载均衡
@remote(
    function_name="train_model",
    load_balancing={
        "strategy": "smart_adaptive",
        "learning_enabled": True,
        "optimization_target": "minimize_latency"  # or "maximize_throughput", "minimize_cost"
    }
)
def train_model(data):
    pass
```

## 实现细节

### Gateway端负载均衡器

```python
class EasyRemoteLoadBalancer:
    def __init__(self, gateway):
        self.gateway = gateway
        self.balancers = {
            "round_robin": RoundRobinBalancer(),
            "resource_aware": ResourceAwareBalancer(),
            "latency_based": LatencyBasedBalancer(),
            "cost_aware": CostAwareBalancer(),
            "smart_adaptive": SmartAdaptiveBalancer()
        }
        self.node_monitor = NodeHealthMonitor()
    
    async def route_request(self, function_name: str, request_data: dict, balancing_config: dict):
        """路由请求到最优节点"""
        
        # 1. 查找提供该函数的所有节点
        available_nodes = await self.find_function_providers(function_name)
        
        # 2. 过滤健康节点
        healthy_nodes = await self.filter_healthy_nodes(available_nodes)
        
        if not healthy_nodes:
            raise NoHealthyNodesError(f"No healthy nodes available for {function_name}")
        
        # 3. 选择负载均衡策略
        strategy = balancing_config.get("strategy", "resource_aware")
        balancer = self.balancers[strategy]
        
        # 4. 选择最优节点
        selected_node = await balancer.select_node(healthy_nodes, request_data)
        
        # 5. 执行请求
        result = await self.execute_on_node(selected_node, function_name, request_data)
        
        # 6. 更新性能统计
        await self.update_performance_stats(selected_node, result)
        
        return result
    
    async def find_function_providers(self, function_name: str):
        """查找所有提供指定函数的节点"""
        providers = []
        
        for node_id, node_info in self.gateway.registered_nodes.items():
            if function_name in node_info.provided_functions:
                providers.append(node_info)
        
        return providers
    
    async def filter_healthy_nodes(self, nodes):
        """过滤出健康可用的节点"""
        healthy_nodes = []
        
        for node in nodes:
            health_status = await self.node_monitor.check_node_health(node.id)
            
            if health_status.is_healthy and health_status.is_available:
                healthy_nodes.append(node)
        
        return healthy_nodes
```

### 节点健康监控

```python
class NodeHealthMonitor:
    def __init__(self):
        self.health_cache = {}
        self.monitoring_interval = 10  # 10秒检查一次
    
    async def check_node_health(self, node_id: str):
        """检查节点健康状态"""
        # 检查缓存
        if node_id in self.health_cache:
            cached_health = self.health_cache[node_id]
            if time.time() - cached_health.timestamp < self.monitoring_interval:
                return cached_health
        
        try:
            # 发送健康检查请求
            health_response = await self.send_health_check(node_id)
            
            health_status = NodeHealthStatus(
                node_id=node_id,
                is_healthy=True,
                is_available=health_response.current_load < 0.9,
                cpu_usage=health_response.cpu_usage,
                memory_usage=health_response.memory_usage,
                gpu_usage=health_response.gpu_usage,
                current_load=health_response.current_load,
                response_time=health_response.response_time,
                timestamp=time.time()
            )
            
        except Exception as e:
            health_status = NodeHealthStatus(
                node_id=node_id,
                is_healthy=False,
                is_available=False,
                error=str(e),
                timestamp=time.time()
            )
        
        # 更新缓存
        self.health_cache[node_id] = health_status
        return health_status
    
    async def start_continuous_monitoring(self):
        """启动持续健康监控"""
        while True:
            await asyncio.sleep(self.monitoring_interval)
            
            # 检查所有注册节点的健康状态
            for node_id in self.gateway.registered_nodes:
                await self.check_node_health(node_id)
```

### 性能指标收集

```python
class PerformanceCollector:
    def __init__(self):
        self.metrics_db = MetricsDatabase()
    
    async def record_request_metrics(self, node_id: str, function_name: str, 
                                   execution_time: float, success: bool):
        """记录请求性能指标"""
        
        metrics = {
            "node_id": node_id,
            "function_name": function_name,
            "execution_time": execution_time,
            "success": success,
            "timestamp": time.time()
        }
        
        await self.metrics_db.insert("request_metrics", metrics)
    
    async def get_node_performance_stats(self, node_id: str, time_window: int = 3600):
        """获取节点性能统计"""
        
        since_time = time.time() - time_window
        
        stats = await self.metrics_db.query(
            "SELECT AVG(execution_time) as avg_time, "
            "COUNT(*) as total_requests, "
            "SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_requests "
            "FROM request_metrics "
            "WHERE node_id = ? AND timestamp > ?",
            [node_id, since_time]
        )
        
        return {
            "average_execution_time": stats.avg_time or 0,
            "total_requests": stats.total_requests or 0,
            "success_rate": (stats.successful_requests / stats.total_requests) if stats.total_requests > 0 else 0
        }
```

## 📊 负载均衡配置示例

### 基础配置
```python
# 简单负载均衡
@remote(function_name="process_data", load_balancing=True)
def process_data(data):
    pass
```

### 高级配置
```python
# 复杂负载均衡配置
@remote(
    function_name="train_model",
    load_balancing={
        "strategy": "smart_adaptive",
        "fallback_strategy": "resource_aware",
        "health_check": {
            "enabled": True,
            "timeout": 5.0,
            "retry_count": 3
        },
        "requirements": {
            "gpu_memory": ">=16GB",
            "cpu_cores": ">=8",
            "available_memory": ">=32GB"
        },
        "preferences": {
            "prefer_local": True,
            "max_latency": 100,
            "cost_limit": 10.0
        },
        "scaling": {
            "auto_scale": True,
            "min_nodes": 2,
            "max_nodes": 10,
            "scale_up_threshold": 0.8,
            "scale_down_threshold": 0.3
        }
    }
)
def train_model(data):
    pass
```

### 动态负载均衡
```python
class DynamicLoadBalancer:
    """动态调整负载均衡策略"""
    
    async def adapt_strategy(self, current_metrics: dict):
        """根据当前系统状态动态调整策略"""
        
        # 高负载时优先资源分配
        if current_metrics["average_cpu_usage"] > 0.8:
            return "resource_aware"
        
        # 网络延迟高时优化延迟
        elif current_metrics["average_latency"] > 200:
            return "latency_based"
        
        # 成本敏感时期
        elif current_metrics["budget_utilization"] > 0.8:
            return "cost_aware"
        
        # 默认使用智能策略
        else:
            return "smart_adaptive"

# 使用动态负载均衡
dynamic_balancer = DynamicLoadBalancer()

@remote(
    function_name="flexible_task",
    load_balancing={
        "strategy": "dynamic",
        "balancer": dynamic_balancer
    }
)
def flexible_task(data):
    pass
```

##  性能优化

### 1. 连接池管理
```python
class NodeConnectionPool:
    def __init__(self, max_connections_per_node=10):
        self.pools = {}
        self.max_connections = max_connections_per_node
    
    async def get_connection(self, node_id: str):
        """获取到节点的连接"""
        if node_id not in self.pools:
            self.pools[node_id] = asyncio.Queue(maxsize=self.max_connections)
            
            # 预创建连接
            for _ in range(self.max_connections):
                conn = await self.create_connection(node_id)
                await self.pools[node_id].put(conn)
        
        return await self.pools[node_id].get()
    
    async def return_connection(self, node_id: str, connection):
        """归还连接到池中"""
        if not connection.is_closed():
            await self.pools[node_id].put(connection)
```

### 2. 请求缓存
```python
class RequestCache:
    def __init__(self, ttl=300):  # 5分钟TTL
        self.cache = {}
        self.ttl = ttl
    
    async def get_cached_result(self, function_name: str, args_hash: str):
        """获取缓存结果"""
        cache_key = f"{function_name}:{args_hash}"
        
        if cache_key in self.cache:
            cached_item = self.cache[cache_key]
            
            if time.time() - cached_item["timestamp"] < self.ttl:
                return cached_item["result"]
            else:
                del self.cache[cache_key]
        
        return None
    
    async def cache_result(self, function_name: str, args_hash: str, result):
        """缓存结果"""
        cache_key = f"{function_name}:{args_hash}"
        
        self.cache[cache_key] = {
            "result": result,
            "timestamp": time.time()
        }
```

## 📈 监控和分析

### 负载均衡仪表板
```python
class LoadBalancingDashboard:
    async def get_real_time_metrics(self):
        """获取实时负载均衡指标"""
        return {
            "total_requests": await self.get_total_requests(),
            "requests_per_second": await self.get_rps(),
            "average_response_time": await self.get_avg_response_time(),
            "node_distribution": await self.get_node_distribution(),
            "strategy_effectiveness": await self.get_strategy_effectiveness(),
            "error_rates": await self.get_error_rates()
        }
    
    async def generate_optimization_report(self):
        """生成负载均衡优化建议"""
        metrics = await self.get_historical_metrics(days=7)
        
        recommendations = []
        
        # 分析节点利用率不均衡
        if metrics["node_utilization_variance"] > 0.3:
            recommendations.append({
                "type": "load_distribution",
                "message": "Consider adjusting load balancing strategy",
                "suggested_strategy": "resource_aware"
            })
        
        # 分析高延迟问题
        if metrics["average_latency"] > 500:
            recommendations.append({
                "type": "latency_optimization", 
                "message": "High latency detected",
                "suggested_strategy": "latency_based"
            })
        
        return {
            "analysis_period": "7 days",
            "recommendations": recommendations,
            "performance_trends": metrics["trends"]
        }
```

##  最佳实践

### 1. 策略选择指南
```python
def choose_load_balancing_strategy(use_case: str, constraints: dict):
    """根据使用场景选择最佳负载均衡策略"""
    
    strategy_recommendations = {
        # 高性能计算：优先资源利用率
        "hpc": "resource_aware",
        
        # 实时应用：优先低延迟
        "real_time": "latency_based", 
        
        # 批处理作业：优先成本效益
        "batch_processing": "cost_aware",
        
        # 用户交互：综合优化
        "interactive": "smart_adaptive",
        
        # 简单应用：轮询即可
        "simple": "round_robin"
    }
    
    base_strategy = strategy_recommendations.get(use_case, "resource_aware")
    
    # 根据约束条件调整
    if constraints.get("budget_limited"):
        return "cost_aware"
    elif constraints.get("latency_critical"):
        return "latency_based"
    elif constraints.get("high_availability"):
        return "smart_adaptive"
    
    return base_strategy
```

### 2. 节点配置优化
```python
# 为不同节点设置合适的负载均衡参数
@node.register(
    load_balancing=True,
    max_concurrent=5,           # 根据硬件能力设置
    queue_size=20,              # 请求队列大小
    timeout=300,                # 超时时间
    priority="high",            # 节点优先级
    cost_per_hour=2.5,          # 成本信息
    performance_tier="premium"   # 性能等级
)
def gpu_intensive_task(data):
    return process_on_gpu(data)
```

### 3. 监控告警
```python
class LoadBalancingAlerts:
    async def check_and_alert(self, metrics):
        """检查指标并发送告警"""
        
        # 节点不可用告警
        if metrics["unhealthy_nodes"] > 0:
            await self.send_alert("Node Health Alert", 
                                f"{metrics['unhealthy_nodes']} nodes are unhealthy")
        
        # 负载不均衡告警
        if metrics["load_variance"] > 0.5:
            await self.send_alert("Load Imbalance Alert",
                                "Significant load imbalance detected")
        
        # 延迟过高告警
        if metrics["avg_latency"] > 1000:
            await self.send_alert("High Latency Alert",
                                f"Average latency: {metrics['avg_latency']}ms")
```

---

*通过这套完整的负载均衡机制，EasyRemote能够自动将计算任务分配到最适合的节点上，实现高效的资源利用和最佳的用户体验。* 