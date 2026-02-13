# EasyRemote 高级场景教程

##  学习目标

本教程将带您深入EasyRemote的高级应用场景：
- 构建分布式AI推理服务
- 实现智能负载均衡策略
- 部署边缘计算网络
- 处理实时数据流
- 构建容错和高可用系统

## 📋 前置要求

- 已完成 [基础使用教程](basic-usage.md)
- 熟悉Python异步编程
- 了解基本的AI/ML概念
- 具备网络编程经验

## 🤖 场景一：分布式AI推理服务

### 目标
构建一个支持多模型、多节点的AI推理服务，实现负载分担和模型热切换。

### 架构设计

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client Apps   │    │   Web Dashboard │    │  Mobile Apps    │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │      Gateway Server       │
                    │    (Load Balancer)        │
                    └─────────────┬─────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            │                     │                     │
    ┌───────▼───────┐    ┌────────▼────────┐    ┌──────▼──────┐
    │  GPU Node 1   │    │   GPU Node 2    │    │ CPU Node 3  │
    │  (BERT Model) │    │ (Image Classifier│    │ (Text Proc) │
    └───────────────┘    └─────────────────┘    └─────────────┘
```

### 实现步骤

#### 1. 创建模型抽象基类

```python
# ai_models/base_model.py
from abc import ABC, abstractmethod
import time
import logging

class BaseAIModel(ABC):
    def __init__(self, model_name: str, model_path: str = None):
        self.model_name = model_name
        self.model_path = model_path
        self.model = None
        self.load_time = None
        self.inference_count = 0
        self.logger = logging.getLogger(f"AIModel.{model_name}")
        
    @abstractmethod
    def load_model(self):
        """加载模型到内存"""
        pass
    
    @abstractmethod
    def preprocess(self, raw_input):
        """预处理输入数据"""
        pass
    
    @abstractmethod
    def inference(self, processed_input):
        """执行模型推理"""
        pass
    
    @abstractmethod
    def postprocess(self, raw_output):
        """后处理输出结果"""
        pass
    
    def predict(self, input_data):
        """完整的预测流程"""
        start_time = time.time()
        
        try:
            # 预处理
            processed_input = self.preprocess(input_data)
            
            # 推理
            raw_output = self.inference(processed_input)
            
            # 后处理
            result = self.postprocess(raw_output)
            
            # 更新统计信息
            self.inference_count += 1
            inference_time = time.time() - start_time
            
            self.logger.info(f"推理完成，耗时: {inference_time:.3f}s")
            
            return {
                "result": result,
                "model_name": self.model_name,
                "inference_time": inference_time,
                "confidence": getattr(self, '_last_confidence', None)
            }
            
        except Exception as e:
            self.logger.error(f"推理失败: {e}")
            raise
    
    def get_stats(self):
        """获取模型统计信息"""
        return {
            "model_name": self.model_name,
            "inference_count": self.inference_count,
            "load_time": self.load_time,
            "model_loaded": self.model is not None
        }
```

#### 2. 实现具体AI模型

```python
# ai_models/bert_model.py
import torch
from transformers import BertTokenizer, BertForSequenceClassification
from .base_model import BaseAIModel

class BertSentimentModel(BaseAIModel):
    def __init__(self):
        super().__init__("bert-sentiment", "bert-base-uncased")
        self.tokenizer = None
        self.max_length = 512
        
    def load_model(self):
        """加载BERT模型"""
        start_time = time.time()
        
        self.logger.info("开始加载BERT模型...")
        
        # 加载tokenizer和模型
        self.tokenizer = BertTokenizer.from_pretrained(self.model_path)
        self.model = BertForSequenceClassification.from_pretrained(
            self.model_path,
            num_labels=3  # positive, negative, neutral
        )
        
        # 设置为评估模式
        self.model.eval()
        
        self.load_time = time.time() - start_time
        self.logger.info(f"BERT模型加载完成，耗时: {self.load_time:.2f}s")
        
    def preprocess(self, text_input):
        """预处理文本输入"""
        if isinstance(text_input, str):
            texts = [text_input]
        else:
            texts = text_input
            
        # 分词和编码
        encoded = self.tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=self.max_length,
            return_tensors='pt'
        )
        
        return encoded
    
    def inference(self, encoded_input):
        """执行BERT推理"""
        with torch.no_grad():
            outputs = self.model(**encoded_input)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
        return predictions
    
    def postprocess(self, predictions):
        """后处理推理结果"""
        # 获取预测标签和置信度
        predicted_classes = torch.argmax(predictions, dim=-1)
        confidences = torch.max(predictions, dim=-1).values
        
        # 标签映射
        label_map = {0: "negative", 1: "neutral", 2: "positive"}
        
        results = []
        for i, (pred_class, confidence) in enumerate(zip(predicted_classes, confidences)):
            results.append({
                "label": label_map[pred_class.item()],
                "confidence": confidence.item()
            })
            
        # 保存最后的置信度用于统计
        self._last_confidence = confidences.mean().item()
        
        return results[0] if len(results) == 1 else results

# ai_models/image_classifier.py  
import torch
import torchvision.transforms as transforms
from PIL import Image
import io
import base64
from .base_model import BaseAIModel

class ImageClassificationModel(BaseAIModel):
    def __init__(self):
        super().__init__("resnet-imagenet", "resnet50")
        self.transform = None
        self.class_names = None
        
    def load_model(self):
        """加载图像分类模型"""
        start_time = time.time()
        
        self.logger.info("开始加载ResNet模型...")
        
        # 加载预训练的ResNet模型
        self.model = torch.hub.load('pytorch/vision:v0.10.0', 'resnet50', pretrained=True)
        self.model.eval()
        
        # 定义图像预处理
        self.transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225]),
        ])
        
        # 加载ImageNet类别名称
        self._load_imagenet_classes()
        
        self.load_time = time.time() - start_time
        self.logger.info(f"ResNet模型加载完成，耗时: {self.load_time:.2f}s")
        
    def _load_imagenet_classes(self):
        """加载ImageNet类别名称"""
        # 简化版本，实际应该从文件加载
        self.class_names = [f"class_{i}" for i in range(1000)]
    
    def preprocess(self, image_input):
        """预处理图像输入"""
        if isinstance(image_input, str):
            # 假设是base64编码的图像
            image_data = base64.b64decode(image_input)
            image = Image.open(io.BytesIO(image_data))
        elif isinstance(image_input, bytes):
            image = Image.open(io.BytesIO(image_input))
        else:
            raise ValueError("不支持的图像输入格式")
            
        # 转换为RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        # 应用变换
        tensor = self.transform(image).unsqueeze(0)
        return tensor
    
    def inference(self, image_tensor):
        """执行图像分类推理"""
        with torch.no_grad():
            outputs = self.model(image_tensor)
            probabilities = torch.nn.functional.softmax(outputs[0], dim=0)
            
        return probabilities
    
    def postprocess(self, probabilities):
        """后处理分类结果"""
        # 获取top-5预测
        top5_prob, top5_indices = torch.topk(probabilities, 5)
        
        results = []
        for i, (prob, idx) in enumerate(zip(top5_prob, top5_indices)):
            results.append({
                "rank": i + 1,
                "class_id": idx.item(),
                "class_name": self.class_names[idx.item()],
                "probability": prob.item()
            })
            
        self._last_confidence = top5_prob[0].item()
        return results
```

#### 3. 创建AI节点管理器

```python
# ai_nodes/ai_node_manager.py
from easyremote import ComputeNode
import threading
import queue
import time
from ai_models.bert_model import BertSentimentModel
from ai_models.image_classifier import ImageClassificationModel

class AINodeManager:
    def __init__(self, server_address, node_type="general"):
        self.node = ComputeNode(server_address)
        self.node_type = node_type
        self.models = {}
        self.model_queue = queue.Queue()
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_response_time": 0
        }
        
    def load_models(self):
        """根据节点类型加载相应模型"""
        if self.node_type in ["nlp", "general"]:
            self.logger.info("加载NLP模型...")
            bert_model = BertSentimentModel()
            bert_model.load_model()
            self.models["bert_sentiment"] = bert_model
            
        if self.node_type in ["vision", "general"]:
            self.logger.info("加载视觉模型...")
            image_model = ImageClassificationModel()
            image_model.load_model()
            self.models["image_classification"] = image_model
            
    def register_ai_functions(self):
        """注册AI推理函数"""
        
        @self.node.register
        def text_sentiment_analysis(text):
            """文本情感分析"""
            if "bert_sentiment" not in self.models:
                raise RuntimeError("BERT模型未加载")
                
            start_time = time.time()
            try:
                result = self.models["bert_sentiment"].predict(text)
                self._update_stats(True, time.time() - start_time)
                return result
            except Exception as e:
                self._update_stats(False, time.time() - start_time)
                raise
        
        @self.node.register
        def image_classification(image_data):
            """图像分类"""
            if "image_classification" not in self.models:
                raise RuntimeError("图像分类模型未加载")
                
            start_time = time.time()
            try:
                result = self.models["image_classification"].predict(image_data)
                self._update_stats(True, time.time() - start_time)
                return result
            except Exception as e:
                self._update_stats(False, time.time() - start_time)
                raise
        
        @self.node.register
        def batch_text_analysis(texts):
            """批量文本分析"""
            if "bert_sentiment" not in self.models:
                raise RuntimeError("BERT模型未加载")
                
            results = []
            for text in texts:
                try:
                    result = self.models["bert_sentiment"].predict(text)
                    results.append(result)
                except Exception as e:
                    results.append({"error": str(e)})
                    
            return results
        
        @self.node.register
        def get_node_status():
            """获取节点状态"""
            model_stats = {}
            for name, model in self.models.items():
                model_stats[name] = model.get_stats()
                
            return {
                "node_type": self.node_type,
                "loaded_models": list(self.models.keys()),
                "model_stats": model_stats,
                "request_stats": self.stats
            }
            
    def _update_stats(self, success, response_time):
        """更新统计信息"""
        self.stats["total_requests"] += 1
        if success:
            self.stats["successful_requests"] += 1
        else:
            self.stats["failed_requests"] += 1
            
        # 更新平均响应时间
        total_time = self.stats["average_response_time"] * (self.stats["total_requests"] - 1)
        self.stats["average_response_time"] = (total_time + response_time) / self.stats["total_requests"]
    
    def start_serving(self):
        """开始提供服务"""
        self.load_models()
        self.register_ai_functions()
        
        print(f"🤖 AI节点启动 - 类型: {self.node_type}")
        print(f"📚 已加载模型: {list(self.models.keys())}")
        
        self.node.serve()
```

#### 4. 创建智能负载均衡器

```python
# load_balancer/smart_balancer.py
import time
import random
from collections import defaultdict
from typing import Dict, List, Optional

class SmartLoadBalancer:
    def __init__(self):
        self.nodes = {}
        self.node_stats = defaultdict(dict)
        self.model_to_nodes = defaultdict(list)
        self.strategies = {
            "round_robin": self._round_robin,
            "least_connections": self._least_connections,
            "resource_aware": self._resource_aware,
            "model_affinity": self._model_affinity
        }
        
    def register_node(self, node_id: str, node_info: dict):
        """注册计算节点"""
        self.nodes[node_id] = {
            "info": node_info,
            "last_seen": time.time(),
            "active_requests": 0,
            "total_requests": 0,
            "average_response_time": 0
        }
        
        # 更新模型到节点的映射
        for model in node_info.get("models", []):
            if node_id not in self.model_to_nodes[model]:
                self.model_to_nodes[model].append(node_id)
    
    def select_node(self, function_name: str, strategy: str = "resource_aware") -> Optional[str]:
        """选择最优节点"""
        if strategy not in self.strategies:
            strategy = "resource_aware"
            
        return self.strategies[strategy](function_name)
    
    def _round_robin(self, function_name: str) -> Optional[str]:
        """轮询策略"""
        available_nodes = self._get_available_nodes(function_name)
        if not available_nodes:
            return None
            
        # 简单轮询
        return available_nodes[int(time.time()) % len(available_nodes)]
    
    def _least_connections(self, function_name: str) -> Optional[str]:
        """最少连接策略"""
        available_nodes = self._get_available_nodes(function_name)
        if not available_nodes:
            return None
            
        # 选择活跃请求数最少的节点
        min_connections = float('inf')
        best_node = None
        
        for node_id in available_nodes:
            connections = self.nodes[node_id]["active_requests"]
            if connections < min_connections:
                min_connections = connections
                best_node = node_id
                
        return best_node
    
    def _resource_aware(self, function_name: str) -> Optional[str]:
        """资源感知策略"""
        available_nodes = self._get_available_nodes(function_name)
        if not available_nodes:
            return None
            
        # 综合考虑CPU、内存、响应时间等因素
        best_score = float('inf')
        best_node = None
        
        for node_id in available_nodes:
            node = self.nodes[node_id]
            stats = self.node_stats[node_id]
            
            # 计算综合评分
            cpu_score = stats.get("cpu_usage", 50) / 100
            memory_score = stats.get("memory_usage", 50) / 100
            response_score = node["average_response_time"] / 10  # 假设10s为基准
            load_score = node["active_requests"] / 10  # 假设10为基准
            
            total_score = cpu_score + memory_score + response_score + load_score
            
            if total_score < best_score:
                best_score = total_score
                best_node = node_id
                
        return best_node
    
    def _model_affinity(self, function_name: str) -> Optional[str]:
        """模型亲和性策略"""
        # 根据函数名推断所需模型
        model_map = {
            "text_sentiment_analysis": "bert_sentiment",
            "image_classification": "image_classification",
            "batch_text_analysis": "bert_sentiment"
        }
        
        required_model = model_map.get(function_name)
        if required_model and required_model in self.model_to_nodes:
            candidate_nodes = self.model_to_nodes[required_model]
            available_nodes = [n for n in candidate_nodes if self._is_node_available(n)]
            
            if available_nodes:
                # 在有相关模型的节点中选择负载最低的
                return self._least_connections_from_nodes(available_nodes)
        
        # 回退到资源感知策略
        return self._resource_aware(function_name)
    
    def _get_available_nodes(self, function_name: str) -> List[str]:
        """获取可用节点列表"""
        return [node_id for node_id in self.nodes 
                if self._is_node_available(node_id)]
    
    def _is_node_available(self, node_id: str) -> bool:
        """检查节点是否可用"""
        if node_id not in self.nodes:
            return False
            
        node = self.nodes[node_id]
        # 检查节点是否在最近30秒内活跃
        return time.time() - node["last_seen"] < 30
    
    def _least_connections_from_nodes(self, nodes: List[str]) -> Optional[str]:
        """从指定节点中选择连接数最少的"""
        if not nodes:
            return None
            
        min_connections = float('inf')
        best_node = None
        
        for node_id in nodes:
            connections = self.nodes[node_id]["active_requests"]
            if connections < min_connections:
                min_connections = connections
                best_node = node_id
                
        return best_node
    
    def update_node_stats(self, node_id: str, stats: dict):
        """更新节点统计信息"""
        if node_id in self.nodes:
            self.nodes[node_id]["last_seen"] = time.time()
            self.node_stats[node_id].update(stats)
    
    def start_request(self, node_id: str):
        """标记请求开始"""
        if node_id in self.nodes:
            self.nodes[node_id]["active_requests"] += 1
            self.nodes[node_id]["total_requests"] += 1
    
    def finish_request(self, node_id: str, response_time: float):
        """标记请求完成"""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node["active_requests"] = max(0, node["active_requests"] - 1)
            
            # 更新平均响应时间
            total_time = node["average_response_time"] * (node["total_requests"] - 1)
            node["average_response_time"] = (total_time + response_time) / node["total_requests"]
```

#### 5. 智能网关服务器

```python
# gateway/smart_gateway.py
from easyremote import Server
import asyncio
import time
import logging
from load_balancer.smart_balancer import SmartLoadBalancer

class SmartGatewayServer:
    def __init__(self, host="0.0.0.0", port=8080):
        self.server = Server(host=host, port=port)
        self.load_balancer = SmartLoadBalancer()
        self.logger = logging.getLogger("SmartGateway")
        
    def setup_advanced_routing(self):
        """设置高级路由逻辑"""
        
        @self.server.register_middleware
        def intelligent_routing(request):
            """智能路由中间件"""
            function_name = request.function_name
            
            # 选择最优节点
            selected_node = self.load_balancer.select_node(
                function_name, 
                strategy="model_affinity"
            )
            
            if not selected_node:
                raise RuntimeError(f"没有可用节点处理函数: {function_name}")
            
            # 记录请求开始
            self.load_balancer.start_request(selected_node)
            request.target_node = selected_node
            
            return request
        
        @self.server.register_middleware
        def request_monitoring(request):
            """请求监控中间件"""
            start_time = time.time()
            
            try:
                # 执行请求
                response = yield
                
                # 记录成功
                response_time = time.time() - start_time
                self.load_balancer.finish_request(
                    request.target_node, 
                    response_time
                )
                
                self.logger.info(
                    f"请求成功 - 函数: {request.function_name}, "
                    f"节点: {request.target_node}, "
                    f"耗时: {response_time:.3f}s"
                )
                
                return response
                
            except Exception as e:
                # 记录失败
                response_time = time.time() - start_time
                self.load_balancer.finish_request(
                    request.target_node, 
                    response_time
                )
                
                self.logger.error(
                    f"请求失败 - 函数: {request.function_name}, "
                    f"节点: {request.target_node}, "
                    f"错误: {e}"
                )
                
                raise
        
    async def start_health_monitor(self):
        """启动健康监控"""
        while True:
            try:
                # 收集所有节点的健康状态
                for node_id in list(self.load_balancer.nodes.keys()):
                    try:
                        # 这里应该调用节点的健康检查函数
                        # stats = await self.call_node_function(node_id, "get_node_status")
                        # self.load_balancer.update_node_stats(node_id, stats)
                        pass
                    except Exception as e:
                        self.logger.warning(f"节点 {node_id} 健康检查失败: {e}")
                
                await asyncio.sleep(10)  # 每10秒检查一次
                
            except Exception as e:
                self.logger.error(f"健康监控错误: {e}")
                await asyncio.sleep(5)
    
    def start(self):
        """启动智能网关"""
        self.setup_advanced_routing()
        
        # 启动健康监控
        asyncio.create_task(self.start_health_monitor())
        
        self.logger.info(" 智能网关启动，支持以下功能:")
        self.logger.info("  - 智能负载均衡")
        self.logger.info("  - 模型亲和性路由")
        self.logger.info("  - 实时健康监控")
        self.logger.info("  - 请求链路追踪")
        
        self.server.start()

# 使用示例
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gateway = SmartGatewayServer()
    gateway.start()
```

## 🌐 场景二：边缘计算网络

### 目标
构建一个分布式边缘计算网络，支持就近计算、数据本地化和智能协调。

### 实现

```python
# edge_computing/edge_device.py
import json
import time
import psutil
import asyncio
from datetime import datetime
from easyremote import ComputeNode, Client

class EdgeDevice:
    def __init__(self, device_id, location, gateway_address):
        self.device_id = device_id
        self.location = location
        self.node = ComputeNode(gateway_address)
        self.client = Client(gateway_address)
        self.local_cache = {}
        self.device_stats = {}
        
    def register_edge_functions(self):
        """注册边缘计算函数"""
        
        @self.node.register
        def process_sensor_data(sensor_readings):
            """处理传感器数据"""
            timestamp = datetime.now().isoformat()
            
            # 本地数据处理
            processed_data = {
                "device_id": self.device_id,
                "location": self.location,
                "timestamp": timestamp,
                "raw_readings": sensor_readings,
                "processed_readings": {
                    "average": sum(sensor_readings) / len(sensor_readings),
                    "max": max(sensor_readings),
                    "min": min(sensor_readings),
                    "variance": self._calculate_variance(sensor_readings)
                },
                "anomaly_detected": self._detect_anomaly(sensor_readings)
            }
            
            # 缓存处理结果
            self.local_cache[timestamp] = processed_data
            
            return processed_data
        
        @self.node.register
        def edge_analytics(data_points, analysis_type="trend"):
            """边缘数据分析"""
            if analysis_type == "trend":
                return self._trend_analysis(data_points)
            elif analysis_type == "correlation":
                return self._correlation_analysis(data_points)
            elif analysis_type == "prediction":
                return self._simple_prediction(data_points)
            else:
                raise ValueError(f"不支持的分析类型: {analysis_type}")
        
        @self.node.register
        def coordinate_with_neighbors(task_data):
            """与邻近设备协调"""
            nearby_devices = self._find_nearby_devices()
            
            results = []
            for device in nearby_devices:
                try:
                    # 委托部分任务给邻近设备
                    result = self.client.execute(
                        f"edge_task_delegation_{device}",
                        task_data
                    )
                    results.append({
                        "device": device,
                        "result": result,
                        "success": True
                    })
                except Exception as e:
                    results.append({
                        "device": device,
                        "error": str(e),
                        "success": False
                    })
            
            return {
                "coordinator": self.device_id,
                "task_results": results,
                "coordination_time": datetime.now().isoformat()
            }
        
        @self.node.register
        def get_device_metrics():
            """获取设备指标"""
            return {
                "device_id": self.device_id,
                "location": self.location,
                "system_metrics": {
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_usage": psutil.disk_usage('/').percent,
                    "network_io": psutil.net_io_counters()._asdict(),
                    "boot_time": psutil.boot_time()
                },
                "cache_stats": {
                    "cached_items": len(self.local_cache),
                    "cache_size_mb": self._get_cache_size()
                },
                "timestamp": datetime.now().isoformat()
            }
    
    def _calculate_variance(self, values):
        """计算方差"""
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values)
    
    def _detect_anomaly(self, values):
        """简单异常检测"""
        if len(values) < 2:
            return False
            
        mean = sum(values) / len(values)
        variance = self._calculate_variance(values)
        threshold = 2 * (variance ** 0.5)  # 2倍标准差
        
        return any(abs(x - mean) > threshold for x in values)
    
    def _trend_analysis(self, data_points):
        """趋势分析"""
        if len(data_points) < 2:
            return {"trend": "insufficient_data"}
        
        # 简单线性趋势
        x_values = list(range(len(data_points)))
        y_values = data_points
        
        n = len(data_points)
        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values))
        sum_x2 = sum(x * x for x in x_values)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        
        return {
            "trend": "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable",
            "slope": slope,
            "confidence": abs(slope) * 100  # 简化的置信度
        }
    
    def _correlation_analysis(self, data_points):
        """相关性分析"""
        # 这里简化为与时间的相关性
        if len(data_points) < 3:
            return {"correlation": "insufficient_data"}
        
        x_values = list(range(len(data_points)))
        correlation = self._pearson_correlation(x_values, data_points)
        
        return {
            "time_correlation": correlation,
            "interpretation": self._interpret_correlation(correlation)
        }
    
    def _simple_prediction(self, data_points):
        """简单预测"""
        if len(data_points) < 3:
            return {"prediction": "insufficient_data"}
        
        # 使用简单移动平均
        window_size = min(3, len(data_points))
        recent_average = sum(data_points[-window_size:]) / window_size
        
        # 计算趋势
        trend = self._trend_analysis(data_points)
        
        # 简单预测下一个值
        if trend["trend"] == "increasing":
            prediction = recent_average * 1.1
        elif trend["trend"] == "decreasing":
            prediction = recent_average * 0.9
        else:
            prediction = recent_average
        
        return {
            "predicted_value": prediction,
            "confidence": min(90, len(data_points) * 10),  # 简化的置信度
            "method": "moving_average_with_trend"
        }
    
    def _pearson_correlation(self, x, y):
        """计算皮尔逊相关系数"""
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)
        sum_y2 = sum(yi * yi for yi in y)
        
        numerator = n * sum_xy - sum_x * sum_y
        denominator = ((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)) ** 0.5
        
        return numerator / denominator if denominator != 0 else 0
    
    def _interpret_correlation(self, correlation):
        """解释相关系数"""
        abs_corr = abs(correlation)
        if abs_corr > 0.8:
            return "strong"
        elif abs_corr > 0.5:
            return "moderate"
        elif abs_corr > 0.3:
            return "weak"
        else:
            return "very_weak"
    
    def _find_nearby_devices(self):
        """查找邻近设备"""
        # 简化的邻近设备发现
        all_devices = ["edge_001", "edge_002", "edge_003", "edge_004"]
        return [d for d in all_devices if d != self.device_id][:2]  # 最多2个邻近设备
    
    def _get_cache_size(self):
        """获取缓存大小（MB）"""
        total_size = 0
        for value in self.local_cache.values():
            total_size += len(str(value))
        return total_size / (1024 * 1024)  # 转换为MB
    
    async def start_data_collection(self):
        """启动数据收集"""
        while True:
            try:
                # 模拟传感器数据收集
                sensor_data = [
                    random.uniform(20, 30),  # 温度
                    random.uniform(40, 60),  # 湿度
                    random.uniform(990, 1020)  # 气压
                ]
                
                # 处理数据
                result = await self.process_sensor_data_async(sensor_data)
                
                # 如果检测到异常，通知其他设备
                if result.get("anomaly_detected"):
                    await self.notify_anomaly(result)
                
                await asyncio.sleep(10)  # 每10秒收集一次数据
                
            except Exception as e:
                print(f"数据收集错误: {e}")
                await asyncio.sleep(5)
    
    async def process_sensor_data_async(self, sensor_data):
        """异步处理传感器数据"""
        # 这里应该调用实际的处理函数
        return {
            "device_id": self.device_id,
            "data": sensor_data,
            "timestamp": datetime.now().isoformat()
        }
    
    async def notify_anomaly(self, anomaly_data):
        """通知异常情况"""
        print(f"🚨 检测到异常: {anomaly_data}")
        
        # 通知邻近设备
        nearby_devices = self._find_nearby_devices()
        for device in nearby_devices:
            try:
                await self.client.execute_async(
                    f"receive_anomaly_alert_{device}",
                    anomaly_data
                )
            except Exception as e:
                print(f"通知设备 {device} 失败: {e}")
    
    def start_serving(self):
        """开始提供边缘计算服务"""
        self.register_edge_functions()
        
        print(f"🌐 边缘设备启动")
        print(f"📍 设备ID: {self.device_id}")
        print(f"📍 位置: {self.location}")
        print(f"🔧 提供服务:")
        print(f"  - 传感器数据处理")
        print(f"  - 本地数据分析")
        print(f"  - 设备协调")
        print(f"  - 系统监控")
        
        # 启动数据收集
        asyncio.create_task(self.start_data_collection())
        
        self.node.serve()

# 使用示例
if __name__ == "__main__":
    import random
    
    # 创建边缘设备
    devices = [
        EdgeDevice("edge_beijing_001", "Beijing, China", "gateway:8080"),
        EdgeDevice("edge_shanghai_002", "Shanghai, China", "gateway:8080"),
        EdgeDevice("edge_shenzhen_003", "Shenzhen, China", "gateway:8080")
    ]
    
    # 启动第一个设备（在实际环境中，每个设备独立运行）
    devices[0].start_serving()
```

## 📊 场景三：实时流处理系统

### 目标
构建一个支持实时数据流处理的分布式系统，能够处理高并发数据流并提供实时分析。

### 实现

```python
# streaming/stream_processor.py
import asyncio
import queue
import time
import json
from collections import deque, defaultdict
from easyremote import ComputeNode, Client

class StreamProcessor:
    def __init__(self, processor_id, gateway_address):
        self.processor_id = processor_id
        self.node = ComputeNode(gateway_address)
        self.client = Client(gateway_address)
        
        # 流处理组件
        self.input_queue = asyncio.Queue(maxsize=1000)
        self.output_queue = asyncio.Queue(maxsize=1000)
        self.processing_stats = defaultdict(int)
        
        # 窗口处理
        self.time_windows = defaultdict(deque)
        self.window_size = 60  # 60秒窗口
        
    def register_stream_functions(self):
        """注册流处理函数"""
        
        @self.node.register
        def process_stream_data(data_batch):
            """处理流数据批次"""
            results = []
            
            for item in data_batch:
                try:
                    processed_item = self._process_single_item(item)
                    results.append(processed_item)
                    self.processing_stats["processed"] += 1
                except Exception as e:
                    results.append({"error": str(e), "original": item})
                    self.processing_stats["errors"] += 1
            
            return {
                "processor_id": self.processor_id,
                "batch_size": len(data_batch),
                "results": results,
                "processing_time": time.time()
            }
        
        @self.node.register
        def window_aggregation(window_type="time", window_size=60):
            """窗口聚合"""
            current_time = time.time()
            
            if window_type == "time":
                # 时间窗口聚合
                window_data = self._get_time_window_data(current_time, window_size)
                return self._aggregate_window_data(window_data)
            
            elif window_type == "count":
                # 计数窗口聚合
                window_data = self._get_count_window_data(window_size)
                return self._aggregate_window_data(window_data)
            
            else:
                raise ValueError(f"不支持的窗口类型: {window_type}")
        
        @self.node.register
        def real_time_analytics(data_stream, metric_type="average"):
            """实时分析"""
            if metric_type == "average":
                return self._calculate_moving_average(data_stream)
            elif metric_type == "trend":
                return self._detect_trend(data_stream)
            elif metric_type == "anomaly":
                return self._detect_stream_anomaly(data_stream)
            else:
                raise ValueError(f"不支持的分析类型: {metric_type}")
        
        @self.node.register
        def stream_join(stream_a, stream_b, join_key):
            """流连接操作"""
            return self._join_streams(stream_a, stream_b, join_key)
        
        @self.node.register
        def get_stream_stats():
            """获取流处理统计"""
            return {
                "processor_id": self.processor_id,
                "stats": dict(self.processing_stats),
                "queue_sizes": {
                    "input": self.input_queue.qsize(),
                    "output": self.output_queue.qsize()
                },
                "window_stats": {
                    key: len(window) 
                    for key, window in self.time_windows.items()
                }
            }
    
    def _process_single_item(self, item):
        """处理单个数据项"""
        # 添加处理时间戳
        processed_item = {
            "original": item,
            "processed_time": time.time(),
            "processor_id": self.processor_id
        }
        
        # 根据数据类型进行不同处理
        if isinstance(item, dict):
            processed_item.update(self._process_dict_item(item))
        elif isinstance(item, (int, float)):
            processed_item.update(self._process_numeric_item(item))
        elif isinstance(item, str):
            processed_item.update(self._process_text_item(item))
        else:
            processed_item["type"] = "unknown"
        
        # 添加到时间窗口
        window_key = int(time.time() // self.window_size)
        self.time_windows[window_key].append(processed_item)
        
        # 清理旧窗口
        self._cleanup_old_windows()
        
        return processed_item
    
    def _process_dict_item(self, item):
        """处理字典类型数据"""
        return {
            "type": "dict",
            "keys": list(item.keys()),
            "size": len(item),
            "has_timestamp": "timestamp" in item,
            "summary": self._summarize_dict(item)
        }
    
    def _process_numeric_item(self, item):
        """处理数值类型数据"""
        return {
            "type": "numeric",
            "value": item,
            "is_integer": isinstance(item, int),
            "absolute_value": abs(item),
            "normalized": self._normalize_value(item)
        }
    
    def _process_text_item(self, item):
        """处理文本类型数据"""
        words = item.split()
        return {
            "type": "text",
            "length": len(item),
            "word_count": len(words),
            "has_numbers": any(char.isdigit() for char in item),
            "uppercase_ratio": sum(1 for c in item if c.isupper()) / len(item) if item else 0
        }
    
    def _summarize_dict(self, item):
        """字典数据摘要"""
        summary = {}
        for key, value in item.items():
            if isinstance(value, (int, float)):
                summary[f"{key}_type"] = "numeric"
                summary[f"{key}_value"] = value
            elif isinstance(value, str):
                summary[f"{key}_type"] = "text"
                summary[f"{key}_length"] = len(value)
            else:
                summary[f"{key}_type"] = type(value).__name__
        return summary
    
    def _normalize_value(self, value):
        """归一化数值"""
        # 简单的归一化，实际应该基于历史数据
        return max(-1, min(1, value / 100))
    
    def _get_time_window_data(self, current_time, window_size):
        """获取时间窗口数据"""
        target_window = int((current_time - window_size) // self.window_size)
        window_data = []
        
        for window_key, items in self.time_windows.items():
            if window_key >= target_window:
                window_data.extend(items)
        
        return window_data
    
    def _get_count_window_data(self, count):
        """获取计数窗口数据"""
        all_items = []
        for items in self.time_windows.values():
            all_items.extend(items)
        
        return all_items[-count:] if len(all_items) >= count else all_items
    
    def _aggregate_window_data(self, window_data):
        """聚合窗口数据"""
        if not window_data:
            return {"count": 0, "message": "no_data"}
        
        # 基础统计
        count = len(window_data)
        
        # 数值统计
        numeric_values = []
        for item in window_data:
            if item.get("type") == "numeric":
                numeric_values.append(item["value"])
        
        aggregation = {
            "count": count,
            "numeric_count": len(numeric_values),
            "window_start": min(item["processed_time"] for item in window_data),
            "window_end": max(item["processed_time"] for item in window_data)
        }
        
        if numeric_values:
            aggregation.update({
                "sum": sum(numeric_values),
                "average": sum(numeric_values) / len(numeric_values),
                "min": min(numeric_values),
                "max": max(numeric_values),
                "median": sorted(numeric_values)[len(numeric_values) // 2]
            })
        
        # 类型分布
        type_counts = defaultdict(int)
        for item in window_data:
            type_counts[item.get("type", "unknown")] += 1
        
        aggregation["type_distribution"] = dict(type_counts)
        
        return aggregation
    
    def _calculate_moving_average(self, data_stream, window=10):
        """计算移动平均"""
        if len(data_stream) < window:
            window = len(data_stream)
        
        if window == 0:
            return {"average": 0, "count": 0}
        
        recent_values = data_stream[-window:]
        numeric_values = [x for x in recent_values if isinstance(x, (int, float))]
        
        if not numeric_values:
            return {"average": 0, "count": 0, "message": "no_numeric_data"}
        
        return {
            "average": sum(numeric_values) / len(numeric_values),
            "count": len(numeric_values),
            "window_size": window,
            "min": min(numeric_values),
            "max": max(numeric_values)
        }
    
    def _detect_trend(self, data_stream):
        """检测趋势"""
        if len(data_stream) < 3:
            return {"trend": "insufficient_data"}
        
        # 取最近的数值数据
        numeric_values = [x for x in data_stream[-10:] if isinstance(x, (int, float))]
        
        if len(numeric_values) < 3:
            return {"trend": "insufficient_numeric_data"}
        
        # 简单趋势检测
        differences = [numeric_values[i+1] - numeric_values[i] 
                      for i in range(len(numeric_values)-1)]
        
        positive_changes = sum(1 for d in differences if d > 0)
        negative_changes = sum(1 for d in differences if d < 0)
        
        if positive_changes > negative_changes:
            trend = "increasing"
        elif negative_changes > positive_changes:
            trend = "decreasing"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "confidence": abs(positive_changes - negative_changes) / len(differences),
            "change_points": len(differences),
            "average_change": sum(differences) / len(differences)
        }
    
    def _detect_stream_anomaly(self, data_stream):
        """检测流异常"""
        if len(data_stream) < 5:
            return {"anomaly": False, "reason": "insufficient_data"}
        
        numeric_values = [x for x in data_stream if isinstance(x, (int, float))]
        
        if len(numeric_values) < 5:
            return {"anomaly": False, "reason": "insufficient_numeric_data"}
        
        # 使用简单的统计方法检测异常
        mean = sum(numeric_values) / len(numeric_values)
        variance = sum((x - mean) ** 2 for x in numeric_values) / len(numeric_values)
        std_dev = variance ** 0.5
        
        # 检测最新值是否异常
        latest_value = numeric_values[-1]
        z_score = abs(latest_value - mean) / std_dev if std_dev > 0 else 0
        
        is_anomaly = z_score > 2  # 2倍标准差
        
        return {
            "anomaly": is_anomaly,
            "z_score": z_score,
            "latest_value": latest_value,
            "mean": mean,
            "std_dev": std_dev,
            "threshold": 2
        }
    
    def _join_streams(self, stream_a, stream_b, join_key):
        """连接两个流"""
        result = []
        
        # 创建连接索引
        index_b = {}
        for item in stream_b:
            if isinstance(item, dict) and join_key in item:
                key_value = item[join_key]
                if key_value not in index_b:
                    index_b[key_value] = []
                index_b[key_value].append(item)
        
        # 执行连接
        for item_a in stream_a:
            if isinstance(item_a, dict) and join_key in item_a:
                key_value = item_a[join_key]
                if key_value in index_b:
                    for item_b in index_b[key_value]:
                        joined_item = {
                            "stream_a": item_a,
                            "stream_b": item_b,
                            "join_key": join_key,
                            "join_value": key_value
                        }
                        result.append(joined_item)
        
        return {
            "joined_count": len(result),
            "stream_a_size": len(stream_a),
            "stream_b_size": len(stream_b),
            "join_key": join_key,
            "results": result
        }
    
    def _cleanup_old_windows(self):
        """清理旧的时间窗口"""
        current_time = time.time()
        cutoff_window = int((current_time - self.window_size * 5) // self.window_size)
        
        # 删除超过5个窗口期的旧数据
        old_windows = [key for key in self.time_windows.keys() if key < cutoff_window]
        for key in old_windows:
            del self.time_windows[key]
    
    async def stream_worker(self):
        """流处理工作者"""
        while True:
            try:
                # 检查输入队列
                if not self.input_queue.empty():
                    # 批量处理
                    batch = []
                    batch_size = min(10, self.input_queue.qsize())
                    
                    for _ in range(batch_size):
                        try:
                            item = await asyncio.wait_for(
                                self.input_queue.get(), 
                                timeout=0.1
                            )
                            batch.append(item)
                        except asyncio.TimeoutError:
                            break
                    
                    if batch:
                        # 处理批次
                        result = await self.process_batch_async(batch)
                        await self.output_queue.put(result)
                
                await asyncio.sleep(0.01)  # 防止过度占用CPU
                
            except Exception as e:
                print(f"流处理工作者错误: {e}")
                await asyncio.sleep(1)
    
    async def process_batch_async(self, batch):
        """异步处理批次"""
        # 这里可以调用实际的流处理函数
        return {
            "batch_id": int(time.time() * 1000),
            "processed_items": len(batch),
            "processor_id": self.processor_id,
            "timestamp": time.time()
        }
    
    def start_serving(self):
        """开始提供流处理服务"""
        self.register_stream_functions()
        
        print(f"🌊 流处理器启动")
        print(f"🆔 处理器ID: {self.processor_id}")
        print(f"🔧 提供服务:")
        print(f"  - 实时数据流处理")
        print(f"  - 窗口聚合分析")
        print(f"  - 流连接操作")
        print(f"  - 异常检测")
        
        # 启动流处理工作者
        asyncio.create_task(self.stream_worker())
        
        self.node.serve()

# 使用示例
if __name__ == "__main__":
    processor = StreamProcessor("stream_proc_001", "gateway:8080")
    processor.start_serving()
```

## 🔗 集成与部署

### 完整部署脚本

```python
# deploy/deploy_advanced_system.py
import asyncio
import subprocess
import time
import json
from pathlib import Path

class AdvancedSystemDeployer:
    def __init__(self, config_file="deployment_config.json"):
        self.config = self._load_config(config_file)
        self.processes = []
        
    def _load_config(self, config_file):
        """加载部署配置"""
        default_config = {
            "gateway": {
                "host": "0.0.0.0",
                "port": 8080,
                "enable_monitoring": True
            },
            "ai_nodes": [
                {"type": "nlp", "count": 2},
                {"type": "vision", "count": 1},
                {"type": "general", "count": 1}
            ],
            "edge_devices": [
                {"id": "edge_001", "location": "Beijing"},
                {"id": "edge_002", "location": "Shanghai"},
                {"id": "edge_003", "location": "Shenzhen"}
            ],
            "stream_processors": [
                {"id": "stream_001", "type": "analytics"},
                {"id": "stream_002", "type": "aggregation"}
            ]
        }
        
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            config = default_config
            # 保存默认配置
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
        
        return config
    
    def deploy_gateway(self):
        """部署智能网关"""
        print(" 部署智能网关...")
        
        gateway_script = f"""
from gateway.smart_gateway import SmartGatewayServer
import logging

logging.basicConfig(level=logging.INFO)
gateway = SmartGatewayServer(
    host="{self.config['gateway']['host']}", 
    port={self.config['gateway']['port']}
)
gateway.start()
"""
        
        # 启动网关进程
        process = subprocess.Popen([
            "python", "-c", gateway_script
        ])
        self.processes.append(("gateway", process))
        
        # 等待网关启动
        time.sleep(3)
        print("✅ 智能网关部署完成")
    
    def deploy_ai_nodes(self):
        """部署AI计算节点"""
        print("🤖 部署AI计算节点...")
        
        server_address = f"{self.config['gateway']['host']}:{self.config['gateway']['port']}"
        
        for node_config in self.config['ai_nodes']:
            node_type = node_config['type']
            count = node_config['count']
            
            for i in range(count):
                node_script = f"""
from ai_nodes.ai_node_manager import AINodeManager
import logging

logging.basicConfig(level=logging.INFO)
node = AINodeManager("{server_address}", "{node_type}")
node.start_serving()
"""
                
                process = subprocess.Popen([
                    "python", "-c", node_script
                ])
                self.processes.append((f"ai_node_{node_type}_{i}", process))
                
                time.sleep(2)  # 避免同时启动过多进程
        
        print("✅ AI计算节点部署完成")
    
    def deploy_edge_devices(self):
        """部署边缘设备"""
        print("🌐 部署边缘计算设备...")
        
        server_address = f"{self.config['gateway']['host']}:{self.config['gateway']['port']}"
        
        for device_config in self.config['edge_devices']:
            device_id = device_config['id']
            location = device_config['location']
            
            device_script = f"""
from edge_computing.edge_device import EdgeDevice
import logging

logging.basicConfig(level=logging.INFO)
device = EdgeDevice("{device_id}", "{location}", "{server_address}")
device.start_serving()
"""
            
            process = subprocess.Popen([
                "python", "-c", device_script
            ])
            self.processes.append((f"edge_{device_id}", process))
            
            time.sleep(1)
        
        print("✅ 边缘计算设备部署完成")
    
    def deploy_stream_processors(self):
        """部署流处理器"""
        print("🌊 部署流处理器...")
        
        server_address = f"{self.config['gateway']['host']}:{self.config['gateway']['port']}"
        
        for proc_config in self.config['stream_processors']:
            proc_id = proc_config['id']
            proc_type = proc_config['type']
            
            proc_script = f"""
from streaming.stream_processor import StreamProcessor
import logging

logging.basicConfig(level=logging.INFO)
processor = StreamProcessor("{proc_id}", "{server_address}")
processor.start_serving()
"""
            
            process = subprocess.Popen([
                "python", "-c", proc_script
            ])
            self.processes.append((f"stream_{proc_id}", process))
            
            time.sleep(1)
        
        print("✅ 流处理器部署完成")
    
    def deploy_all(self):
        """部署完整系统"""
        print(" 开始部署EasyRemote高级分布式系统...")
        print("=" * 60)
        
        try:
            # 按顺序部署各组件
            self.deploy_gateway()
            self.deploy_ai_nodes()
            self.deploy_edge_devices()
            self.deploy_stream_processors()
            
            print("\n" + "=" * 60)
            print("🎉 系统部署完成！")
            print(f"📊 已启动 {len(self.processes)} 个组件")
            print(f"🌐 网关地址: {self.config['gateway']['host']}:{self.config['gateway']['port']}")
            
            # 显示组件状态
            self.show_system_status()
            
        except Exception as e:
            print(f"❌ 部署失败: {e}")
            self.cleanup()
    
    def show_system_status(self):
        """显示系统状态"""
        print("\n📋 系统组件状态:")
        print("-" * 40)
        
        for name, process in self.processes:
            status = "运行中" if process.poll() is None else "已停止"
            print(f"  {name}: {status}")
    
    def cleanup(self):
        """清理所有进程"""
        print("\n🧹 清理系统进程...")
        
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
        
        self.processes.clear()
        print("✅ 清理完成")

# 使用示例
if __name__ == "__main__":
    deployer = AdvancedSystemDeployer()
    
    try:
        deployer.deploy_all()
        
        # 保持运行
        print("\n按 Ctrl+C 停止系统...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n收到停止信号...")
        deployer.cleanup()
    except Exception as e:
        print(f"系统错误: {e}")
        deployer.cleanup()
```

## 🏁 总结

通过本高级教程，您已经学会了：

1. **🤖 分布式AI推理服务**: 构建支持多模型的智能计算网络
2. **⚖️ 智能负载均衡**: 实现资源感知和模型亲和性路由
3. **🌐 边缘计算网络**: 部署分布式边缘设备协作系统
4. **🌊 实时流处理**: 处理高并发数据流和实时分析
5. ** 系统集成部署**: 完整的分布式系统部署方案

这些高级场景展示了EasyRemote在复杂分布式计算环境中的强大能力。您可以根据实际需求选择和组合这些组件，构建适合的分布式计算解决方案。

## 🔗 相关资源

- 📖 [基础使用教程](basic-usage.md)
- 📚 [API参考文档](../user-guide/api-reference.md)
- 🏗️ [架构设计文档](../architecture/overview.md)
- 💡 [示例代码库](../user-guide/examples.md) 