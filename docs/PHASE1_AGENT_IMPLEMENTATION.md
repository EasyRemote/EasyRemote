# Phase 1: Agent化基础设施实现方案

> **目标：3-6个月内将EasyRemote的ComputeNode升级为智能ComputeAgent**

---

##  阶段目标

将当前的**"被动函数执行节点"**升级为**"主动智能协作代理"**，实现：

1. **智能能力描述系统** - Agent能够描述和发布自己的计算能力
2. **基础协作协议** - Agent之间可以协商和协作执行任务  
3. **智能负载均衡** - 基于能力和性能的智能任务分配
4. **任务上下文感知** - 任务执行带有丰富的上下文信息

---

## 🏗️ 核心架构设计

### **1. ComputeAgent 架构**

```python
# easyremote/core/agents/compute_agent.py

from typing import Dict, List, Set, Optional, Union, Any
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from datetime import datetime

from ..nodes.compute_node import ComputeNode
from .capability_system import CapabilityRegistry, AgentCapability
from .collaboration_protocol import CollaborationProtocol
from .performance_tracker import PerformanceTracker
from .resource_monitor import ResourceMonitor


class TaskComplexity(Enum):
    """任务复杂度级别"""
    TRIVIAL = "trivial"      # 简单任务，资源需求低
    SIMPLE = "simple"        # 基础任务，适中资源需求
    MODERATE = "moderate"    # 中等任务，需要一定算力
    COMPLEX = "complex"      # 复杂任务，高资源需求
    EXTREME = "extreme"      # 极复杂任务，需要协作


@dataclass
class TaskContext:
    """任务执行上下文"""
    task_id: str
    function_name: str
    complexity: TaskComplexity
    estimated_duration: Optional[float] = None
    resource_requirements: Dict[str, Any] = field(default_factory=dict)
    quality_requirements: Dict[str, Any] = field(default_factory=dict)
    deadline: Optional[datetime] = None
    priority: int = 5  # 1-10, 10为最高优先级
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class AgentCapabilitySpec:
    """Agent能力规格说明"""
    name: str
    description: str
    function_signatures: List[str]
    resource_requirements: Dict[str, Any]
    performance_characteristics: Dict[str, Any]
    cost_model: Dict[str, Any]
    quality_guarantees: Dict[str, Any]
    collaboration_patterns: List[str] = field(default_factory=list)


class ComputeAgent(ComputeNode):
    """
    智能计算代理 - ComputeNode的Agent化升级版本
    
    新增核心能力：
    1. 智能能力描述与发布
    2. 任务复杂度分析与自适应处理
    3. 多Agent协作与任务分解
    4. 性能学习与优化
    5. 资源预测与调度建议
    """
    
    def __init__(self, 
                 gateway_address: str,
                 agent_id: str = None,
                 specializations: List[str] = None,
                 max_complexity: TaskComplexity = TaskComplexity.MODERATE,
                 collaboration_enabled: bool = True,
                 learning_enabled: bool = True):
        """
        初始化智能计算代理
        
        Args:
            gateway_address: 网关地址
            agent_id: 代理唯一标识
            specializations: 专业化能力领域
            max_complexity: 最大可处理任务复杂度
            collaboration_enabled: 是否启用协作功能
            learning_enabled: 是否启用学习功能
        """
        super().__init__(gateway_address, agent_id)
        
        # Agent核心属性
        self.agent_id = agent_id or self.node_id
        self.specializations = set(specializations or [])
        self.max_complexity = max_complexity
        self.collaboration_enabled = collaboration_enabled
        self.learning_enabled = learning_enabled
        
        # 核心组件
        self.capability_registry = CapabilityRegistry()
        self.collaboration_protocol = CollaborationProtocol(self)
        self.performance_tracker = PerformanceTracker(self.agent_id)
        self.resource_monitor = ResourceMonitor()
        
        # 状态管理
        self._registered_capabilities: Dict[str, AgentCapabilitySpec] = {}
        self._active_collaborations: Dict[str, Any] = {}
        self._performance_history: List[Dict] = []
        
        self.info(f"ComputeAgent initialized: {self.agent_id}")
        self.info(f"Max complexity: {max_complexity.value}")
        self.info(f"Specializations: {self.specializations}")
    
    def register_capability(self, 
                           capability_name: str,
                           cost: float = 1.0,
                           quality: float = 0.8,
                           **metadata) -> callable:
        """
        注册Agent能力 - 升级版的函数注册装饰器
        
        Args:
            capability_name: 能力名称
            cost: 执行成本系数 (0.1-10.0)
            quality: 质量保证系数 (0.0-1.0)
            **metadata: 额外的能力元数据
            
        Returns:
            装饰器函数
            
        Example:
            @agent.register_capability("image_enhancement", cost=0.5, quality=0.95)
            async def enhance_image(image_data, context: TaskContext):
                # 智能图像增强逻辑
                return enhanced_image
        """
        def decorator(func):
            # 分析函数签名和特征
            capability_spec = self._analyze_function_capability(
                func, capability_name, cost, quality, metadata
            )
            
            # 注册到能力系统
            self.capability_registry.register_capability(capability_spec)
            self._registered_capabilities[capability_name] = capability_spec
            
            # 包装原函数，加入Agent智能处理
            async def agent_wrapper(*args, **kwargs):
                return await self._intelligent_execution_wrapper(
                    func, capability_name, *args, **kwargs
                )
            
            # 保持函数元信息
            agent_wrapper.__name__ = func.__name__
            agent_wrapper.__doc__ = func.__doc__
            agent_wrapper.__annotations__ = func.__annotations__
            agent_wrapper._capability_spec = capability_spec
            
            # 使用父类注册机制
            self.register(agent_wrapper)
            
            self.info(f"Agent capability registered: {capability_name}")
            return agent_wrapper
        
        return decorator
    
    async def _intelligent_execution_wrapper(self,
                                           func: callable,
                                           capability_name: str,
                                           *args, **kwargs) -> Any:
        """
        智能执行包装器 - 为函数执行添加Agent智能
        
        核心功能：
        1. 任务复杂度分析
        2. 资源需求评估  
        3. 协作决策
        4. 性能监控
        5. 学习反馈
        """
        execution_start = datetime.now()
        
        try:
            # 1. 创建任务上下文
            task_context = await self._create_task_context(
                capability_name, args, kwargs
            )
            
            self.debug(f"Task context created: {task_context.task_id}")
            
            # 2. 任务复杂度分析
            complexity = await self._analyze_task_complexity(
                capability_name, args, kwargs
            )
            task_context.complexity = complexity
            
            # 3. 决策：本地执行 vs 协作执行
            if await self._should_request_collaboration(task_context):
                self.info(f"Task {task_context.task_id} requires collaboration")
                return await self._execute_with_collaboration(
                    func, task_context, *args, **kwargs
                )
            else:
                self.debug(f"Task {task_context.task_id} executing locally")
                return await self._execute_locally_with_monitoring(
                    func, task_context, *args, **kwargs
                )
                
        except Exception as e:
            # 错误处理和学习
            await self._handle_execution_error(capability_name, e)
            raise
        finally:
            # 性能记录
            execution_time = (datetime.now() - execution_start).total_seconds()
            await self._record_execution_performance(
                capability_name, execution_time, len(args) + len(kwargs)
            )
    
    async def _create_task_context(self, 
                                 capability_name: str, 
                                 args: tuple, 
                                 kwargs: dict) -> TaskContext:
        """创建任务执行上下文"""
        import uuid
        
        # 估算资源需求
        resource_requirements = await self._estimate_resource_requirements(
            capability_name, args, kwargs
        )
        
        # 获取质量要求
        quality_requirements = kwargs.get('quality_requirements', {})
        
        return TaskContext(
            task_id=str(uuid.uuid4()),
            function_name=capability_name,
            complexity=TaskComplexity.SIMPLE,  # 后续会更新
            resource_requirements=resource_requirements,
            quality_requirements=quality_requirements,
            deadline=kwargs.get('deadline'),
            priority=kwargs.get('priority', 5),
            metadata={
                'args_count': len(args),
                'kwargs_count': len(kwargs),
                'agent_id': self.agent_id
            }
        )
    
    async def _analyze_task_complexity(self, 
                                     capability_name: str,
                                     args: tuple, 
                                     kwargs: dict) -> TaskComplexity:
        """
        智能任务复杂度分析
        
        基于多个维度评估任务复杂度：
        - 数据大小
        - 计算类型
        - 历史执行时间
        - 资源需求
        """
        # 数据大小分析
        data_size_score = await self._analyze_data_size(args, kwargs)
        
        # 计算类型复杂度
        computation_score = await self._analyze_computation_complexity(capability_name)
        
        # 历史性能数据
        historical_score = await self._get_historical_complexity_score(capability_name)
        
        # 综合评分
        total_score = (data_size_score + computation_score + historical_score) / 3
        
        # 映射到复杂度等级
        if total_score < 0.2:
            return TaskComplexity.TRIVIAL
        elif total_score < 0.4:
            return TaskComplexity.SIMPLE
        elif total_score < 0.6:
            return TaskComplexity.MODERATE
        elif total_score < 0.8:
            return TaskComplexity.COMPLEX
        else:
            return TaskComplexity.EXTREME
    
    async def _should_request_collaboration(self, task_context: TaskContext) -> bool:
        """
        协作决策逻辑
        
        决策因素：
        1. 任务复杂度是否超过本Agent能力
        2. 当前资源使用情况
        3. 协作的性价比分析
        4. 历史协作成功率
        """
        # 1. 复杂度检查
        if task_context.complexity.value > self.max_complexity.value:
            return True
        
        # 2. 资源使用情况检查
        current_load = await self.resource_monitor.get_current_load()
        if current_load > 0.8:  # 80%以上负载
            return True
        
        # 3. 预期执行时间检查
        estimated_time = await self._estimate_execution_time(task_context)
        if task_context.deadline:
            time_pressure = (task_context.deadline - datetime.now()).total_seconds()
            if estimated_time > time_pressure * 0.7:  # 需要70%+时间
                return True
        
        # 4. 质量要求检查
        required_quality = task_context.quality_requirements.get('accuracy', 0.8)
        my_capability = self._registered_capabilities.get(task_context.function_name)
        if my_capability and my_capability.quality_guarantees.get('accuracy', 0.8) < required_quality:
            return True
        
        return False
    
    async def _execute_with_collaboration(self,
                                        func: callable,
                                        task_context: TaskContext,
                                        *args, **kwargs) -> Any:
        """
        协作执行模式
        
        协作流程：
        1. 寻找协作伙伴
        2. 任务分解
        3. 分工执行
        4. 结果合并
        """
        self.info(f"Starting collaborative execution for {task_context.task_id}")
        
        # 1. 寻找协作伙伴
        collaboration_partners = await self.collaboration_protocol.find_collaboration_partners(
            task_requirements={
                'capability': task_context.function_name,
                'complexity': task_context.complexity.value,
                'quality_requirements': task_context.quality_requirements,
                'resource_requirements': task_context.resource_requirements
            }
        )
        
        if not collaboration_partners:
            self.warning(f"No collaboration partners found for {task_context.task_id}, falling back to local execution")
            return await self._execute_locally_with_monitoring(func, task_context, *args, **kwargs)
        
        # 2. 建立协作契约
        collaboration_contract = await self.collaboration_protocol.establish_collaboration_contract(
            partners=collaboration_partners,
            task_context=task_context
        )
        
        # 3. 协作执行
        collaboration_result = await self.collaboration_protocol.execute_collaborative_task(
            contract=collaboration_contract,
            local_function=func,
            args=args,
            kwargs=kwargs
        )
        
        self.info(f"Collaborative execution completed for {task_context.task_id}")
        return collaboration_result
    
    async def _execute_locally_with_monitoring(self,
                                             func: callable,
                                             task_context: TaskContext,
                                             *args, **kwargs) -> Any:
        """
        本地监控执行模式
        """
        self.debug(f"Executing locally: {task_context.task_id}")
        
        # 添加上下文到kwargs
        kwargs['context'] = task_context
        
        # 监控执行
        start_time = datetime.now()
        try:
            # 检查是否是异步函数
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                # 在线程池中执行同步函数
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, func, *args, **kwargs)
            
            # 记录成功执行
            execution_time = (datetime.now() - start_time).total_seconds()
            await self.performance_tracker.record_successful_execution(
                task_context, execution_time, result
            )
            
            return result
            
        except Exception as e:
            # 记录执行失败
            execution_time = (datetime.now() - start_time).total_seconds()
            await self.performance_tracker.record_failed_execution(
                task_context, execution_time, e
            )
            raise
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """获取Agent状态信息"""
        current_load = await self.resource_monitor.get_current_load()
        
        return {
            'agent_id': self.agent_id,
            'specializations': list(self.specializations),
            'max_complexity': self.max_complexity.value,
            'registered_capabilities': list(self._registered_capabilities.keys()),
            'current_load': current_load,
            'collaboration_enabled': self.collaboration_enabled,
            'learning_enabled': self.learning_enabled,
            'active_collaborations': len(self._active_collaborations),
            'total_executions': len(self._performance_history),
            'average_execution_time': await self.performance_tracker.get_average_execution_time()
        }
    
    # 辅助方法的实现
    async def _analyze_function_capability(self, func, capability_name, cost, quality, metadata):
        """分析函数能力特征"""
        import inspect
        
        signature = inspect.signature(func)
        
        return AgentCapabilitySpec(
            name=capability_name,
            description=func.__doc__ or f"Capability: {capability_name}",
            function_signatures=[str(signature)],
            resource_requirements=metadata.get('resource_requirements', {}),
            performance_characteristics={
                'cost_factor': cost,
                'quality_factor': quality,
                'estimated_complexity': metadata.get('complexity', 'moderate')
            },
            cost_model={'base_cost': cost, 'scaling_factor': 1.0},
            quality_guarantees={'accuracy': quality},
            collaboration_patterns=metadata.get('collaboration_patterns', [])
        )
    
    async def _analyze_data_size(self, args, kwargs):
        """分析数据大小复杂度"""
        total_size = 0
        
        # 简单的大小估算
        for arg in args:
            if hasattr(arg, '__len__'):
                total_size += len(arg)
            elif hasattr(arg, '__sizeof__'):
                total_size += arg.__sizeof__()
        
        for value in kwargs.values():
            if hasattr(value, '__len__'):
                total_size += len(value)
            elif hasattr(value, '__sizeof__'):
                total_size += value.__sizeof__()
        
        # 归一化到0-1
        if total_size < 1024:  # 1KB
            return 0.1
        elif total_size < 1024 * 1024:  # 1MB
            return 0.3
        elif total_size < 10 * 1024 * 1024:  # 10MB
            return 0.5
        elif total_size < 100 * 1024 * 1024:  # 100MB
            return 0.7
        else:
            return 0.9
    
    async def _analyze_computation_complexity(self, capability_name):
        """分析计算复杂度"""
        # 基于能力名称的简单启发式
        complexity_keywords = {
            'train': 0.8, 'training': 0.8,
            'predict': 0.4, 'inference': 0.4,
            'process': 0.5, 'transform': 0.5,
            'analyze': 0.6, 'compute': 0.6,
            'simple': 0.2, 'basic': 0.2,
            'complex': 0.8, 'advanced': 0.8
        }
        
        name_lower = capability_name.lower()
        max_complexity = 0.3  # 默认值
        
        for keyword, complexity in complexity_keywords.items():
            if keyword in name_lower:
                max_complexity = max(max_complexity, complexity)
        
        return max_complexity
    
    async def _get_historical_complexity_score(self, capability_name):
        """获取历史复杂度评分"""
        # 从性能历史中获取
        relevant_history = [
            h for h in self._performance_history 
            if h.get('capability_name') == capability_name
        ]
        
        if not relevant_history:
            return 0.5  # 默认中等复杂度
        
        # 计算平均执行时间作为复杂度指标
        avg_time = sum(h.get('execution_time', 1) for h in relevant_history) / len(relevant_history)
        
        # 归一化：1秒以下=简单，10秒以上=复杂
        if avg_time < 1:
            return 0.2
        elif avg_time < 5:
            return 0.4
        elif avg_time < 10:
            return 0.6
        elif avg_time < 30:
            return 0.8
        else:
            return 1.0
    
    async def _estimate_resource_requirements(self, capability_name, args, kwargs):
        """估算资源需求"""
        # 基础资源需求
        base_requirements = {
            'cpu': 1,
            'memory': 512,  # MB
            'gpu': False
        }
        
        # 根据能力调整
        if 'train' in capability_name.lower() or 'training' in capability_name.lower():
            base_requirements['cpu'] = 4
            base_requirements['memory'] = 2048
            base_requirements['gpu'] = True
        elif 'image' in capability_name.lower() or 'video' in capability_name.lower():
            base_requirements['memory'] = 1024
            base_requirements['gpu'] = True
        
        return base_requirements
    
    async def _estimate_execution_time(self, task_context):
        """估算执行时间"""
        # 基于历史数据和任务复杂度
        capability_name = task_context.function_name
        complexity = task_context.complexity
        
        # 查找历史数据
        relevant_history = [
            h for h in self._performance_history 
            if h.get('capability_name') == capability_name
        ]
        
        if relevant_history:
            avg_time = sum(h.get('execution_time', 10) for h in relevant_history) / len(relevant_history)
        else:
            # 基于复杂度的默认估算
            complexity_multipliers = {
                TaskComplexity.TRIVIAL: 1,
                TaskComplexity.SIMPLE: 5,
                TaskComplexity.MODERATE: 15,
                TaskComplexity.COMPLEX: 60,
                TaskComplexity.EXTREME: 300
            }
            avg_time = complexity_multipliers.get(complexity, 10)
        
        # 基于当前负载调整
        current_load = await self.resource_monitor.get_current_load()
        load_multiplier = 1 + current_load  # 负载越高，执行时间越长
        
        return avg_time * load_multiplier
    
    async def _record_execution_performance(self, capability_name, execution_time, data_size):
        """记录执行性能"""
        performance_record = {
            'timestamp': datetime.now(),
            'capability_name': capability_name,
            'execution_time': execution_time,
            'data_size': data_size,
            'agent_id': self.agent_id
        }
        
        self._performance_history.append(performance_record)
        
        # 保持历史记录在合理范围内
        if len(self._performance_history) > 1000:
            self._performance_history = self._performance_history[-1000:]
        
        # 如果启用学习，更新性能模型
        if self.learning_enabled:
            await self.performance_tracker.update_performance_model(performance_record)
    
    async def _handle_execution_error(self, capability_name, error):
        """处理执行错误"""
        error_record = {
            'timestamp': datetime.now(),
            'capability_name': capability_name,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'agent_id': self.agent_id
        }
        
        self.error(f"Execution error in {capability_name}: {error}")
        
        # 记录错误用于学习
        if self.learning_enabled:
            await self.performance_tracker.record_error(error_record)
```

### **2. 能力注册系统**

```python
# easyremote/core/agents/capability_system.py

from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime


class CapabilityType(Enum):
    """能力类型枚举"""
    COMPUTATION = "computation"
    DATA_PROCESSING = "data_processing"
    MACHINE_LEARNING = "machine_learning"
    IMAGE_PROCESSING = "image_processing"
    VIDEO_PROCESSING = "video_processing"
    NATURAL_LANGUAGE = "natural_language"
    AUDIO_PROCESSING = "audio_processing"
    SCIENTIFIC_COMPUTING = "scientific_computing"
    WEB_SCRAPING = "web_scraping"
    DATABASE_OPERATIONS = "database_operations"


@dataclass
class ResourceRequirement:
    """资源需求规格"""
    cpu_cores: Optional[int] = None
    memory_mb: Optional[int] = None
    gpu_required: bool = False
    gpu_memory_mb: Optional[int] = None
    disk_space_mb: Optional[int] = None
    network_bandwidth_mbps: Optional[int] = None
    special_hardware: List[str] = field(default_factory=list)


@dataclass
class PerformanceMetrics:
    """性能指标"""
    throughput: Optional[str] = None  # e.g., "1000 req/s"
    latency: Optional[str] = None     # e.g., "<50ms"
    accuracy: Optional[float] = None   # 0.0-1.0
    reliability: Optional[float] = None  # 0.0-1.0
    scalability: Optional[str] = None   # e.g., "linear", "logarithmic"


@dataclass
class CostModel:
    """成本模型"""
    base_cost: float = 1.0
    scaling_factor: float = 1.0
    unit: str = "per_request"
    currency: str = "credits"
    discount_rules: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityGuarantee:
    """质量保证"""
    availability: Optional[float] = None  # 0.0-1.0
    accuracy: Optional[float] = None      # 0.0-1.0
    response_time: Optional[float] = None  # seconds
    error_rate: Optional[float] = None    # 0.0-1.0
    consistency: Optional[float] = None   # 0.0-1.0


@dataclass
class AgentCapability:
    """Agent能力完整描述"""
    # 基本信息
    name: str
    capability_type: CapabilityType
    description: str
    version: str = "1.0.0"
    
    # 技术规格
    function_signatures: List[str] = field(default_factory=list)
    input_formats: List[str] = field(default_factory=list)
    output_formats: List[str] = field(default_factory=list)
    
    # 资源和性能
    resource_requirements: ResourceRequirement = field(default_factory=ResourceRequirement)
    performance_metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    
    # 商业模型
    cost_model: CostModel = field(default_factory=CostModel)
    quality_guarantees: QualityGuarantee = field(default_factory=QualityGuarantee)
    
    # 协作特性
    collaboration_patterns: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    
    # 元数据
    tags: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'name': self.name,
            'capability_type': self.capability_type.value,
            'description': self.description,
            'version': self.version,
            'function_signatures': self.function_signatures,
            'input_formats': self.input_formats,
            'output_formats': self.output_formats,
            'resource_requirements': {
                'cpu_cores': self.resource_requirements.cpu_cores,
                'memory_mb': self.resource_requirements.memory_mb,
                'gpu_required': self.resource_requirements.gpu_required,
                'gpu_memory_mb': self.resource_requirements.gpu_memory_mb
            },
            'performance_metrics': {
                'throughput': self.performance_metrics.throughput,
                'latency': self.performance_metrics.latency,
                'accuracy': self.performance_metrics.accuracy
            },
            'cost_model': {
                'base_cost': self.cost_model.base_cost,
                'scaling_factor': self.cost_model.scaling_factor,
                'unit': self.cost_model.unit
            },
            'collaboration_patterns': self.collaboration_patterns,
            'tags': list(self.tags),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class CapabilityRegistry:
    """Agent能力注册中心"""
    
    def __init__(self):
        self._capabilities: Dict[str, AgentCapability] = {}
        self._capability_index: Dict[str, Set[str]] = {
            'type': {},
            'tags': {},
            'patterns': {}
        }
    
    def register_capability(self, capability: AgentCapability) -> bool:
        """
        注册新能力
        
        Args:
            capability: 能力规格
            
        Returns:
            注册是否成功
        """
        try:
            # 更新时间戳
            capability.updated_at = datetime.now()
            
            # 存储能力
            self._capabilities[capability.name] = capability
            
            # 更新索引
            self._update_capability_index(capability)
            
            return True
            
        except Exception as e:
            print(f"Failed to register capability {capability.name}: {e}")
            return False
    
    def find_capabilities(self, 
                         capability_type: Optional[CapabilityType] = None,
                         tags: Optional[Set[str]] = None,
                         resource_requirements: Optional[ResourceRequirement] = None,
                         performance_requirements: Optional[Dict[str, Any]] = None) -> List[AgentCapability]:
        """
        查找匹配的能力
        
        Args:
            capability_type: 能力类型
            tags: 标签集合
            resource_requirements: 资源需求
            performance_requirements: 性能需求
            
        Returns:
            匹配的能力列表
        """
        candidates = list(self._capabilities.values())
        
        # 按类型过滤
        if capability_type:
            candidates = [c for c in candidates if c.capability_type == capability_type]
        
        # 按标签过滤
        if tags:
            candidates = [c for c in candidates if tags.issubset(c.tags)]
        
        # 按资源需求过滤
        if resource_requirements:
            candidates = [c for c in candidates 
                         if self._meets_resource_requirements(c, resource_requirements)]
        
        # 按性能需求过滤
        if performance_requirements:
            candidates = [c for c in candidates 
                         if self._meets_performance_requirements(c, performance_requirements)]
        
        return candidates
    
    def get_capability(self, name: str) -> Optional[AgentCapability]:
        """获取指定名称的能力"""
        return self._capabilities.get(name)
    
    def list_all_capabilities(self) -> List[AgentCapability]:
        """列出所有已注册的能力"""
        return list(self._capabilities.values())
    
    def remove_capability(self, name: str) -> bool:
        """移除指定能力"""
        if name in self._capabilities:
            capability = self._capabilities.pop(name)
            self._remove_from_index(capability)
            return True
        return False
    
    def _update_capability_index(self, capability: AgentCapability):
        """更新能力索引"""
        # 类型索引
        cap_type = capability.capability_type.value
        if cap_type not in self._capability_index['type']:
            self._capability_index['type'][cap_type] = set()
        self._capability_index['type'][cap_type].add(capability.name)
        
        # 标签索引
        for tag in capability.tags:
            if tag not in self._capability_index['tags']:
                self._capability_index['tags'][tag] = set()
            self._capability_index['tags'][tag].add(capability.name)
        
        # 协作模式索引
        for pattern in capability.collaboration_patterns:
            if pattern not in self._capability_index['patterns']:
                self._capability_index['patterns'][pattern] = set()
            self._capability_index['patterns'][pattern].add(capability.name)
    
    def _remove_from_index(self, capability: AgentCapability):
        """从索引中移除能力"""
        # 从类型索引移除
        cap_type = capability.capability_type.value
        if cap_type in self._capability_index['type']:
            self._capability_index['type'][cap_type].discard(capability.name)
        
        # 从标签索引移除
        for tag in capability.tags:
            if tag in self._capability_index['tags']:
                self._capability_index['tags'][tag].discard(capability.name)
        
        # 从协作模式索引移除
        for pattern in capability.collaboration_patterns:
            if pattern in self._capability_index['patterns']:
                self._capability_index['patterns'][pattern].discard(capability.name)
    
    def _meets_resource_requirements(self, 
                                   capability: AgentCapability, 
                                   requirements: ResourceRequirement) -> bool:
        """检查能力是否满足资源需求"""
        cap_req = capability.resource_requirements
        
        # CPU需求检查
        if requirements.cpu_cores and cap_req.cpu_cores:
            if cap_req.cpu_cores < requirements.cpu_cores:
                return False
        
        # 内存需求检查
        if requirements.memory_mb and cap_req.memory_mb:
            if cap_req.memory_mb < requirements.memory_mb:
                return False
        
        # GPU需求检查
        if requirements.gpu_required and not cap_req.gpu_required:
            return False
        
        # GPU内存需求检查
        if requirements.gpu_memory_mb and cap_req.gpu_memory_mb:
            if cap_req.gpu_memory_mb < requirements.gpu_memory_mb:
                return False
        
        return True
    
    def _meets_performance_requirements(self, 
                                      capability: AgentCapability, 
                                      requirements: Dict[str, Any]) -> bool:
        """检查能力是否满足性能需求"""
        cap_perf = capability.performance_metrics
        
        # 准确率需求
        if 'accuracy' in requirements and cap_perf.accuracy:
            if cap_perf.accuracy < requirements['accuracy']:
                return False
        
        # 可靠性需求
        if 'reliability' in requirements and cap_perf.reliability:
            if cap_perf.reliability < requirements['reliability']:
                return False
        
        return True


# 使用示例
def create_example_capabilities():
    """创建示例能力规格"""
    
    # 图像处理能力
    image_processing = AgentCapability(
        name="advanced_image_enhancement",
        capability_type=CapabilityType.IMAGE_PROCESSING,
        description="Advanced AI-powered image enhancement with multiple algorithms",
        function_signatures=["enhance_image(image_data, enhancement_type, quality_level)"],
        input_formats=["jpeg", "png", "tiff", "raw"],
        output_formats=["jpeg", "png", "tiff"],
        resource_requirements=ResourceRequirement(
            cpu_cores=4,
            memory_mb=2048,
            gpu_required=True,
            gpu_memory_mb=4096
        ),
        performance_metrics=PerformanceMetrics(
            throughput="50 images/min",
            latency="<2s per image",
            accuracy=0.95,
            reliability=0.99
        ),
        cost_model=CostModel(
            base_cost=0.1,
            scaling_factor=1.2,
            unit="per_image"
        ),
        quality_guarantees=QualityGuarantee(
            availability=0.999,
            accuracy=0.95,
            response_time=2.0
        ),
        collaboration_patterns=["pipeline", "ensemble"],
        tags={"image", "ai", "enhancement", "quality"}
    )
    
    # 机器学习训练能力
    ml_training = AgentCapability(
        name="distributed_ml_training",
        capability_type=CapabilityType.MACHINE_LEARNING,
        description="Distributed machine learning model training with auto-scaling",
        function_signatures=["train_model(dataset, model_config, training_params)"],
        input_formats=["csv", "json", "parquet", "numpy"],
        output_formats=["pickle", "onnx", "tensorflow", "pytorch"],
        resource_requirements=ResourceRequirement(
            cpu_cores=8,
            memory_mb=8192,
            gpu_required=True,
            gpu_memory_mb=16384
        ),
        performance_metrics=PerformanceMetrics(
            throughput="1000 samples/s",
            accuracy=0.92,
            reliability=0.95
        ),
        cost_model=CostModel(
            base_cost=1.0,
            scaling_factor=1.5,
            unit="per_epoch"
        ),
        collaboration_patterns=["distributed_training", "federated_learning"],
        tags={"ml", "training", "distributed", "scalable"}
    )
    
    return [image_processing, ml_training]
```

---

##  实现步骤

### **Step 1: 基础Agent架构 (Week 1-2)**

1. **创建ComputeAgent基类**
   - 继承现有ComputeNode
   - 添加Agent核心属性和组件
   - 实现基础的能力注册装饰器

2. **实现能力描述系统**
   - AgentCapability数据结构
   - CapabilityRegistry注册中心
   - 能力查询和匹配算法

### **Step 2: 智能执行包装器 (Week 3-4)**

1. **任务上下文系统**
   - TaskContext数据结构
   - 任务复杂度分析算法
   - 资源需求评估

2. **智能执行决策**
   - 本地vs协作执行决策逻辑
   - 性能监控和记录
   - 错误处理和学习

### **Step 3: 协作协议基础 (Week 5-8)**

1. **协作伙伴发现**
   - 基于能力的伙伴匹配
   - 网络拓扑发现协议
   - 协作成本效益分析

2. **基础协作执行**
   - 简单的任务分解
   - 协作契约建立
   - 结果聚合机制

### **Step 4: 性能优化和学习 (Week 9-12)**

1. **性能跟踪系统**
   - 执行历史记录
   - 性能指标分析
   - 趋势预测

2. **智能负载均衡升级**
   - 基于Agent能力的负载均衡
   - 预测性资源调度
   - 动态策略调整

---

## 🧪 测试计划

### **单元测试**

```python
# tests/test_compute_agent.py

import pytest
import asyncio
from easyremote.core.agents import ComputeAgent, TaskComplexity

class TestComputeAgent:
    
    @pytest.fixture
    async def agent(self):
        """创建测试Agent"""
        agent = ComputeAgent(
            gateway_address="localhost:8080",
            agent_id="test-agent",
            specializations=["image_processing", "ml"],
            max_complexity=TaskComplexity.MODERATE
        )
        return agent
    
    async def test_capability_registration(self, agent):
        """测试能力注册"""
        
        @agent.register_capability("test_function", cost=0.5, quality=0.9)
        async def test_func(data, context):
            return f"processed_{data}"
        
        # 验证能力已注册
        assert "test_function" in agent._registered_capabilities
        assert agent._registered_capabilities["test_function"].cost_model.base_cost == 0.5
    
    async def test_task_complexity_analysis(self, agent):
        """测试任务复杂度分析"""
        
        # 简单任务
        simple_complexity = await agent._analyze_task_complexity(
            "simple_process", ("small_data",), {}
        )
        assert simple_complexity in [TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE]
        
        # 复杂任务
        complex_complexity = await agent._analyze_task_complexity(
            "complex_training", ("large_dataset" * 1000,), {}
        )
        assert complex_complexity in [TaskComplexity.COMPLEX, TaskComplexity.EXTREME]
    
    async def test_collaboration_decision(self, agent):
        """测试协作决策逻辑"""
        from easyremote.core.agents import TaskContext
        
        # 超出能力范围的任务应该请求协作
        complex_task = TaskContext(
            task_id="test-task",
            function_name="test_function",
            complexity=TaskComplexity.EXTREME
        )
        
        should_collaborate = await agent._should_request_collaboration(complex_task)
        assert should_collaborate == True
        
        # 简单任务应该本地执行
        simple_task = TaskContext(
            task_id="test-task",
            function_name="test_function", 
            complexity=TaskComplexity.SIMPLE
        )
        
        should_collaborate = await agent._should_request_collaboration(simple_task)
        assert should_collaborate == False
```

### **集成测试**

```python
# tests/test_agent_collaboration.py

import pytest
import asyncio
from easyremote.core.agents import ComputeAgent

class TestAgentCollaboration:
    
    async def test_multi_agent_collaboration(self):
        """测试多Agent协作"""
        
        # 创建两个专业化的Agent
        image_agent = ComputeAgent(
            gateway_address="localhost:8080",
            agent_id="image-specialist",
            specializations=["image_processing"]
        )
        
        ml_agent = ComputeAgent(
            gateway_address="localhost:8080",
            agent_id="ml-specialist", 
            specializations=["machine_learning"]
        )
        
        # 在image_agent上注册图像处理能力
        @image_agent.register_capability("enhance_image", quality=0.9)
        async def enhance_image(image_data, context):
            return f"enhanced_{image_data}"
        
        # 在ml_agent上注册ML推理能力
        @ml_agent.register_capability("predict", quality=0.95) 
        async def predict(model_data, context):
            return f"prediction_{model_data}"
        
        # 测试协作场景：复杂任务需要两个Agent配合
        # 这里需要模拟协作协议的工作
        
        # 验证Agent可以发现彼此的能力
        # 验证可以建立协作契约
        # 验证可以协同执行任务
```

---

## 📊 成功指标

### **技术指标**

- [ ] Agent自动发现和注册成功率 > 95%
- [ ] 任务复杂度分析准确率 > 85%
- [ ] 协作决策正确率 > 90%
- [ ] 智能负载均衡性能提升 > 30%
- [ ] Agent间协作成功率 > 80%

### **用户体验指标**

- [ ] API向后兼容性 100%
- [ ] 新Agent API学习曲线 < 1天
- [ ] 复杂任务处理能力提升 > 50%
- [ ] 系统稳定性保持 > 99%

### **业务指标**

- [ ] 用户采用新Agent API比例 > 60%
- [ ] 整体任务执行效率提升 > 40%
- [ ] 系统资源利用率提升 > 35%
- [ ] 用户满意度评分 > 4.2/5

---

这个Phase 1实现方案将为EasyRemote从"远程函数工具"向"智慧计算平台"的演进奠定坚实基础。你觉得这个方案的技术路径和实现细节如何？我们是否可以开始具体的代码实现？ 