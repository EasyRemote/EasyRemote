#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote Configuration Management Module

This module provides comprehensive configuration management for the EasyRemote
distributed computing framework. It supports multiple configuration sources,
environment variable overrides, validation, and dynamic configuration updates
with thread-safe operations.

Architecture:
- Builder Pattern: Fluent configuration construction with validation
- Singleton Pattern: Global configuration management with thread safety
- Factory Pattern: Configuration creation from multiple sources

Key Features:
1. Multi-Source Configuration:
   * Default values with intelligent defaults
   * Environment variable overrides
   * Configuration file loading (JSON, YAML)
   * Runtime configuration updates

2. Comprehensive Validation:
   * Type checking and value range validation
   * Cross-field dependency validation
   * Performance impact assessment

3. Environment-Aware Configuration:
   * Development, staging, production profiles
   * Automatic environment detection
   * Profile-specific configuration overrides

Usage Example:
    >>> # Basic configuration usage
    >>> config = EasyRemoteConfig.get_instance()
    >>> print(f"Server port: {config.server.port}")
    >>> 
    >>> # Environment-specific configuration
    >>> config = ConfigurationBuilder() \
    ...     .with_environment("production") \
    ...     .with_env_overrides() \
    ...     .build()

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 2.0.0
"""

import os
import logging
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# Configure module logger
_logger = logging.getLogger(__name__)


class Environment(Enum):
    """Enumeration of supported deployment environments."""
    DEVELOPMENT = "development"     # Local development with debug features
    TESTING = "testing"            # Automated testing environment
    STAGING = "staging"            # Pre-production staging environment
    PRODUCTION = "production"      # Production deployment
    
    @property
    def is_production_like(self) -> bool:
        """Check if environment requires production-grade configurations."""
        return self in (Environment.STAGING, Environment.PRODUCTION)
    
    @property
    def debug_enabled(self) -> bool:
        """Check if debug features should be enabled."""
        return self in (Environment.DEVELOPMENT, Environment.TESTING)


@dataclass
class ValidationResult:
    """Result of configuration validation with detailed error reporting."""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    validation_time: datetime = field(default_factory=datetime.now)
    
    def add_error(self, message: str, field: Optional[str] = None):
        """Add a validation error."""
        error_msg = f"{field}: {message}" if field else message
        self.errors.append(error_msg)
        self.is_valid = False
    
    def add_warning(self, message: str, field: Optional[str] = None):
        """Add a validation warning."""
        warning_msg = f"{field}: {message}" if field else message
        self.warnings.append(warning_msg)
    
    def merge(self, other: 'ValidationResult'):
        """Merge another validation result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.suggestions.extend(other.suggestions)
        if not other.is_valid:
            self.is_valid = False


@dataclass
class ServerConfiguration:
    """
    Comprehensive server configuration with intelligent defaults.
    
    This class configures all aspects of the EasyRemote server including
    network settings, performance parameters, and operational characteristics.
    """
    # Network configuration
    host: str = "0.0.0.0"                   # Server bind address
    port: int = 8080                        # Server port
    max_connections: int = 1000             # Maximum concurrent connections
    connection_timeout_seconds: float = 30.0  # Connection timeout
    
    # gRPC configuration
    grpc_max_message_size_mb: int = 100     # Maximum gRPC message size
    grpc_compression: str = "gzip"          # gRPC compression algorithm
    
    # Performance and capacity
    max_workers: int = 20                   # Maximum worker threads
    max_queue_size: int = 5000              # Maximum request queue size
    request_timeout_seconds: float = 300.0  # Default request timeout
    heartbeat_interval_seconds: float = 10.0 # Heartbeat check interval
    
    # Health and monitoring
    health_check_enabled: bool = True       # Enable health checks
    metrics_collection_enabled: bool = True # Enable metrics collection
    performance_monitoring_enabled: bool = True  # Enable performance monitoring
    
    # Cleanup and maintenance
    cleanup_interval_seconds: float = 300.0    # Cleanup task interval
    stale_connection_timeout_seconds: float = 600.0  # Stale connection cleanup
    
    # Feature flags
    enable_load_balancing: bool = True      # Enable intelligent load balancing
    enable_auto_scaling: bool = False       # Enable automatic scaling
    enable_caching: bool = True             # Enable response caching
    
    def validate(self) -> ValidationResult:
        """Validate server configuration parameters."""
        result = ValidationResult()
        
        # Network validation
        if not (1 <= self.port <= 65535):
            result.add_error("Port must be between 1 and 65535", "port")
        
        if self.max_connections <= 0:
            result.add_error("max_connections must be positive", "max_connections")
        
        # Performance validation
        if self.max_workers <= 0:
            result.add_error("max_workers must be positive", "max_workers")
        
        if self.max_queue_size <= 0:
            result.add_error("max_queue_size must be positive", "max_queue_size")
        
        # Performance recommendations
        if self.max_workers > 50:
            result.add_warning("High worker count may impact performance", "max_workers")
        
        return result
    
    def optimize_for_environment(self, environment: Environment):
        """Optimize configuration for specific environment."""
        if environment == Environment.DEVELOPMENT:
            self.max_workers = 5
            self.max_connections = 100
        elif environment == Environment.TESTING:
            self.max_workers = 10
            self.max_connections = 200
        elif environment == Environment.PRODUCTION:
            self.max_workers = 50
            self.max_connections = 2000
            self.enable_auto_scaling = True
        elif environment == Environment.STAGING:
            self.max_workers = 20
            self.max_connections = 500


@dataclass
class NodeConfiguration:
    """
    Comprehensive compute node configuration.
    
    This class configures compute node behavior including connection
    management, execution parameters, and reliability features.
    """
    # Connection configuration
    server_host: str = "localhost"          # Server hostname/IP
    server_port: int = 8080                 # Server port
    connection_timeout_seconds: float = 10.0  # Connection establishment timeout
    reconnect_interval_seconds: float = 5.0   # Reconnection retry interval
    max_reconnect_attempts: int = 10        # Maximum reconnection attempts
    
    # Execution configuration
    max_concurrent_executions: int = 5      # Maximum parallel executions
    execution_timeout_seconds: float = 600.0  # Default execution timeout
    queue_size_limit: int = 100             # Local execution queue limit
    
    # Heartbeat and health
    heartbeat_interval_seconds: float = 5.0   # Heartbeat frequency
    health_report_interval_seconds: float = 30.0  # Health report frequency
    enable_self_monitoring: bool = True     # Enable self-health monitoring
    
    # Resource management
    cpu_usage_limit_percent: float = 90.0  # CPU usage limit
    memory_usage_limit_percent: float = 85.0  # Memory usage limit
    enable_resource_monitoring: bool = True # Enable resource usage monitoring
    
    # Performance optimization
    enable_function_caching: bool = True    # Enable function result caching
    cache_size_mb: int = 512               # Function cache size
    
    # Reliability and fault tolerance
    max_retry_attempts: int = 3             # Maximum execution retries
    retry_backoff_multiplier: float = 2.0  # Retry backoff multiplier
    enable_graceful_shutdown: bool = True  # Enable graceful shutdown
    
    # Logging
    log_level: str = "INFO"                 # Logging level
    enable_execution_logging: bool = True   # Log execution details
    
    def validate(self) -> ValidationResult:
        """Validate node configuration parameters."""
        result = ValidationResult()
        
        # Connection validation
        if not (1 <= self.server_port <= 65535):
            result.add_error("server_port must be between 1 and 65535", "server_port")
        
        if self.connection_timeout_seconds <= 0:
            result.add_error("connection_timeout_seconds must be positive", "connection_timeout_seconds")
        
        # Execution validation
        if self.max_concurrent_executions <= 0:
            result.add_error("max_concurrent_executions must be positive", "max_concurrent_executions")
        
        # Resource limits validation
        if not (0 < self.cpu_usage_limit_percent <= 100):
            result.add_error("cpu_usage_limit_percent must be between 0 and 100", "cpu_usage_limit_percent")
        
        # Performance recommendations
        if self.max_concurrent_executions > 20:
            result.add_warning("High concurrency may impact performance", "max_concurrent_executions")
        
        return result
    
    def optimize_for_environment(self, environment: Environment):
        """Optimize configuration for specific environment."""
        if environment == Environment.DEVELOPMENT:
            self.max_concurrent_executions = 2
            self.log_level = "DEBUG"
        elif environment == Environment.TESTING:
            self.max_concurrent_executions = 3
            self.execution_timeout_seconds = 120.0
        elif environment == Environment.PRODUCTION:
            self.max_concurrent_executions = 10
        elif environment == Environment.STAGING:
            self.max_concurrent_executions = 5


@dataclass
class MonitoringConfiguration:
    """
    Comprehensive monitoring and observability configuration.
    
    This class configures all aspects of system monitoring including
    performance metrics, health checks, and observability features.
    """
    # Metrics collection
    enable_metrics_collection: bool = True  # Enable metrics collection
    metrics_collection_interval_seconds: float = 10.0  # Collection frequency
    metrics_retention_hours: int = 72       # Metrics retention period
    
    # Performance monitoring
    enable_performance_monitoring: bool = True  # Enable performance monitoring
    performance_analysis_window_hours: int = 6  # Analysis time window
    performance_alert_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "cpu_usage": 85.0,
        "memory_usage": 90.0,
        "response_time_ms": 2000.0,
        "error_rate": 5.0
    })
    
    # Health monitoring
    enable_health_monitoring: bool = True   # Enable health monitoring
    health_check_interval_seconds: float = 30.0  # Health check frequency
    health_check_timeout_seconds: float = 5.0    # Health check timeout
    
    # Logging configuration
    log_level: str = "INFO"                 # Global log level
    enable_structured_logging: bool = True  # Enable structured logging
    log_format: str = "json"               # Log format (json, text)
    enable_log_rotation: bool = True        # Enable log rotation
    max_log_file_size_mb: int = 100         # Maximum log file size
    
    def validate(self) -> ValidationResult:
        """Validate monitoring configuration."""
        result = ValidationResult()
        
        # Intervals validation
        if self.metrics_collection_interval_seconds <= 0:
            result.add_error("metrics_collection_interval_seconds must be positive", "metrics_collection_interval_seconds")
        
        if self.health_check_interval_seconds <= 0:
            result.add_error("health_check_interval_seconds must be positive", "health_check_interval_seconds")
        
        # Thresholds validation
        for metric, threshold in self.performance_alert_thresholds.items():
            if threshold <= 0:
                result.add_error(f"Alert threshold for {metric} must be positive", "performance_alert_thresholds")
        
        return result


class EasyRemoteConfiguration:
    """
    Main configuration class for the EasyRemote distributed computing framework.
    
    This class provides centralized configuration management with support for
    multiple sources, validation, environment-specific settings, and dynamic updates.
    """
    
    _instance: Optional['EasyRemoteConfiguration'] = None
    _lock = threading.RLock()
    
    def __init__(self,
                 environment: Environment = Environment.DEVELOPMENT,
                 enable_env_overrides: bool = True):
        """Initialize EasyRemote configuration."""
        # Configuration sections
        self.server = ServerConfiguration()
        self.node = NodeConfiguration()
        self.monitoring = MonitoringConfiguration()
        
        # Configuration metadata
        self.environment = environment
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self.version = "2.0.0"
        
        # Optimize for environment
        self._optimize_for_environment(environment)
        
        # Apply environment variable overrides
        if enable_env_overrides:
            self._apply_env_overrides()
        
        _logger.info(f"Initialized EasyRemoteConfiguration for {environment.value} environment")
    
    @classmethod
    def get_instance(cls, 
                    environment: Optional[Environment] = None,
                    force_recreate: bool = False) -> 'EasyRemoteConfiguration':
        """Get singleton configuration instance with thread safety."""
        with cls._lock:
            if cls._instance is None or force_recreate:
                if environment is None:
                    environment = cls._detect_environment()
                cls._instance = cls(environment=environment)
            return cls._instance
    
    @staticmethod
    def _detect_environment() -> Environment:
        """Automatically detect the deployment environment."""
        env_name = os.environ.get('EASYREMOTE_ENVIRONMENT', 
                                 os.environ.get('ENVIRONMENT', 'development')).lower()
        
        try:
            return Environment(env_name)
        except ValueError:
            _logger.warning(f"Unknown environment '{env_name}', defaulting to development")
            return Environment.DEVELOPMENT
    
    def _optimize_for_environment(self, environment: Environment):
        """Optimize all configuration sections for the target environment."""
        self.server.optimize_for_environment(environment)
        self.node.optimize_for_environment(environment)
        
        # Environment-specific monitoring settings
        if environment == Environment.PRODUCTION:
            self.monitoring.metrics_retention_hours = 168  # 7 days
        elif environment == Environment.DEVELOPMENT:
            self.monitoring.log_level = "DEBUG"
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration."""
        # Server configuration overrides
        if os.environ.get('EASYREMOTE_SERVER_PORT'):
            try:
                self.server.port = int(os.environ['EASYREMOTE_SERVER_PORT'])
            except ValueError:
                _logger.warning("Invalid EASYREMOTE_SERVER_PORT value")
        
        if os.environ.get('EASYREMOTE_SERVER_HOST'):
            self.server.host = os.environ['EASYREMOTE_SERVER_HOST']
        
        if os.environ.get('EASYREMOTE_MAX_WORKERS'):
            try:
                self.server.max_workers = int(os.environ['EASYREMOTE_MAX_WORKERS'])
            except ValueError:
                _logger.warning("Invalid EASYREMOTE_MAX_WORKERS value")
        
        # Node configuration overrides
        if os.environ.get('EASYREMOTE_NODE_SERVER_HOST'):
            self.node.server_host = os.environ['EASYREMOTE_NODE_SERVER_HOST']
        
        if os.environ.get('EASYREMOTE_NODE_SERVER_PORT'):
            try:
                self.node.server_port = int(os.environ['EASYREMOTE_NODE_SERVER_PORT'])
            except ValueError:
                _logger.warning("Invalid EASYREMOTE_NODE_SERVER_PORT value")
        
        # Monitoring configuration overrides
        if os.environ.get('EASYREMOTE_LOG_LEVEL'):
            self.monitoring.log_level = os.environ['EASYREMOTE_LOG_LEVEL'].upper()
    
    def validate(self) -> ValidationResult:
        """Perform comprehensive validation of all configuration sections."""
        result = ValidationResult()
        
        # Validate individual sections
        server_validation = self.server.validate()
        node_validation = self.node.validate()
        monitoring_validation = self.monitoring.validate()
        
        # Merge validation results
        result.merge(server_validation)
        result.merge(node_validation)
        result.merge(monitoring_validation)
        
        # Cross-section validation
        if self.node.server_port != self.server.port:
            result.add_warning("Node server port differs from server port", "cross_validation")
        
        if self.server.request_timeout_seconds < self.node.execution_timeout_seconds:
            result.add_warning("Server timeout is less than node execution timeout", "cross_validation")
        
        return result
    
    def update_from_dict(self, config_dict: Dict[str, Any]):
        """Update configuration from dictionary."""
        with self._lock:
            try:
                # Update server configuration
                if 'server' in config_dict:
                    server_config = config_dict['server']
                    for key, value in server_config.items():
                        if hasattr(self.server, key):
                            setattr(self.server, key, value)
                
                # Update node configuration
                if 'node' in config_dict:
                    node_config = config_dict['node']
                    for key, value in node_config.items():
                        if hasattr(self.node, key):
                            setattr(self.node, key, value)
                
                # Update monitoring configuration
                if 'monitoring' in config_dict:
                    monitoring_config = config_dict['monitoring']
                    for key, value in monitoring_config.items():
                        if hasattr(self.monitoring, key):
                            setattr(self.monitoring, key, value)
                
                self.last_updated = datetime.now()
                _logger.info("Configuration updated from dictionary")
                
            except Exception as e:
                _logger.error(f"Failed to update configuration: {e}")
                raise
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary representation."""
        return {
            'server': {
                'host': self.server.host,
                'port': self.server.port,
                'max_workers': self.server.max_workers,
                'max_connections': self.server.max_connections,
                'enable_load_balancing': self.server.enable_load_balancing,
            },
            'node': {
                'server_host': self.node.server_host,
                'server_port': self.node.server_port,
                'max_concurrent_executions': self.node.max_concurrent_executions,
                'execution_timeout_seconds': self.node.execution_timeout_seconds,
                'enable_function_caching': self.node.enable_function_caching,
            },
            'monitoring': {
                'enable_metrics_collection': self.monitoring.enable_metrics_collection,
                'log_level': self.monitoring.log_level,
                'performance_alert_thresholds': self.monitoring.performance_alert_thresholds,
            },
            'metadata': {
                'environment': self.environment.value,
                'version': self.version,
                'created_at': self.created_at.isoformat(),
                'last_updated': self.last_updated.isoformat()
            }
        }


class ConfigurationBuilder:
    """
    Builder class for fluent configuration construction with validation.
    
    Example:
        >>> config = ConfigurationBuilder() \\
        ...     .with_environment(Environment.PRODUCTION) \\
        ...     .with_env_overrides() \\
        ...     .build()
    """
    
    def __init__(self):
        self._environment = Environment.DEVELOPMENT
        self._env_overrides = False
        self._validate_on_build = True
        self._config_dict: Dict[str, Any] = {}
    
    def with_environment(self, environment: Environment) -> 'ConfigurationBuilder':
        """Set target environment."""
        self._environment = environment
        return self
    
    def with_env_overrides(self, enabled: bool = True) -> 'ConfigurationBuilder':
        """Enable environment variable overrides."""
        self._env_overrides = enabled
        return self
    
    def with_dict(self, config_dict: Dict[str, Any]) -> 'ConfigurationBuilder':
        """Add configuration dictionary."""
        self._config_dict.update(config_dict)
        return self
    
    def validate_on_build(self, enabled: bool = True) -> 'ConfigurationBuilder':
        """Enable validation during build."""
        self._validate_on_build = enabled
        return self
    
    def build(self) -> EasyRemoteConfiguration:
        """Build configuration instance with all specified options."""
        # Create base configuration
        config = EasyRemoteConfiguration(
            environment=self._environment,
            enable_env_overrides=self._env_overrides
        )
        
        # Apply dictionary overrides
        if self._config_dict:
            config.update_from_dict(self._config_dict)
        
        # Validate if requested
        if self._validate_on_build:
            validation = config.validate()
            if not validation.is_valid:
                error_msg = f"Configuration validation failed: {'; '.join(validation.errors)}"
                raise ValueError(error_msg)
        
        return config


# Convenience functions for backward compatibility
def get_config() -> EasyRemoteConfiguration:
    """Get the global configuration instance."""
    return EasyRemoteConfiguration.get_instance()


def create_config(environment: Optional[Environment] = None) -> EasyRemoteConfiguration:
    """Create a new configuration instance."""
    if environment is None:
        environment = EasyRemoteConfiguration._detect_environment()
    return EasyRemoteConfiguration(environment=environment)


# Legacy compatibility aliases
default_config = get_config()
EasyRemoteConfig = EasyRemoteConfiguration
ServerConfig = ServerConfiguration
NodeConfig = NodeConfiguration
PerformanceConfig = MonitoringConfiguration  # Renamed to MonitoringConfiguration


# Export all public classes and functions
__all__ = [
    'EasyRemoteConfiguration',
    'ServerConfiguration', 
    'NodeConfiguration',
    'MonitoringConfiguration',
    'Environment',
    'ValidationResult',
    'ConfigurationBuilder',
    'get_config',
    'create_config',
    # Legacy compatibility
    'EasyRemoteConfig',
    'ServerConfig',
    'NodeConfig',
    'PerformanceConfig',
    'default_config'
] 
