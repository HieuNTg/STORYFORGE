"""
Real-time Analytics & Cost Tracking System (Phase 4 - Module 4)
Monitor costs, performance, and system health in real-time with alerting
"""
import time
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

class MetricType(Enum):
    LATENCY = "latency"
    COST = "cost"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    TOKEN_USAGE = "token_usage"

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class MetricPoint:
    timestamp: float
    value: float
    metric_type: MetricType
    tags: Dict[str, str] = field(default_factory=dict)

@dataclass
class Alert:
    level: AlertLevel
    message: str
    metric_name: str
    current_value: float
    threshold: float
    triggered_at: float = field(default_factory=time.time)
    resolved: bool = False

class RealTimeAnalytics:
    def __init__(self, alerting_enabled: bool = True):
        self.metrics: Dict[str, List[MetricPoint]] = defaultdict(list)
        self.alerts: List[Alert] = []
        self.alerting_enabled = alerting_enabled
        
        # Thresholds for alerting
        self.thresholds = {
            "avg_latency_ms": 5000,  # 5 seconds
            "cost_per_request": 0.10,  # $0.10
            "error_rate_percent": 5.0,  # 5%
            "tokens_per_second": 10000,
            "request_duration_s": 60  # 60 seconds
        }
        
        # Cost tracking
        self.cost_tracker = {
            "total_cost": 0.0,
            "cost_by_model": defaultdict(float),
            "cost_by_operation": defaultdict(float),
            "requests_count": 0
        }
        
        # Performance tracking
        self.perf_tracker = {
            "latencies": [],
            "throughput_samples": [],
            "errors": 0,
            "total_requests": 0
        }
        
        # Time window for recent metrics (seconds)
        self.time_window = 300  # 5 minutes
    
    def record_metric(self, metric_name: str, value: float, 
                     metric_type: MetricType, tags: Optional[Dict] = None):
        """Record a metric point"""
        point = MetricPoint(
            timestamp=time.time(),
            value=value,
            metric_type=metric_type,
            tags=tags or {}
        )
        self.metrics[metric_name].append(point)
        
        # Clean old metrics outside time window
        self._cleanup_old_metrics(metric_name)
        
        # Check thresholds and trigger alerts
        if self.alerting_enabled:
            self._check_thresholds(metric_name, value)
    
    def record_cost(self, model: str, operation: str, cost: float, 
                   tokens_used: int = 0):
        """Track LLM costs"""
        self.cost_tracker["total_cost"] += cost
        self.cost_tracker["cost_by_model"][model] += cost
        self.cost_tracker["cost_by_operation"][operation] += cost
        self.cost_tracker["requests_count"] += 1
        
        self.record_metric(
            f"cost_{operation}",
            cost,
            MetricType.COST,
            {"model": model, "tokens": str(tokens_used)}
        )
    
    def record_latency(self, operation: str, latency_ms: float,
                      story_id: str = ""):
        """Track operation latency"""
        self.perf_tracker["latencies"].append(latency_ms)
        self.perf_tracker["total_requests"] += 1
        
        # Keep only recent latencies
        if len(self.perf_tracker["latencies"]) > 1000:
            self.perf_tracker["latencies"] = self.perf_tracker["latencies"][-1000:]
        
        self.record_metric(
            f"latency_{operation}",
            latency_ms,
            MetricType.LATENCY,
            {"story_id": story_id}
        )
    
    def record_error(self, error_type: str, operation: str):
        """Track errors"""
        self.perf_tracker["errors"] += 1
        self.record_metric(
            "error_rate",
            self.get_error_rate(),
            MetricType.ERROR_RATE,
            {"error_type": error_type, "operation": operation}
        )
    
    def _cleanup_old_metrics(self, metric_name: str):
        """Remove metrics older than time window"""
        cutoff = time.time() - self.time_window
        self.metrics[metric_name] = [
            p for p in self.metrics[metric_name]
            if p.timestamp > cutoff
        ]
    
    def _check_thresholds(self, metric_name: str, value: float):
        """Check if value exceeds threshold and create alert"""
        if metric_name not in self.thresholds:
            return
        
        threshold = self.thresholds[metric_name]
        if value > threshold:
            level = AlertLevel.CRITICAL if value > threshold * 1.5 else AlertLevel.WARNING
            
            alert = Alert(
                level=level,
                message=f"{metric_name} exceeded threshold: {value:.2f} > {threshold:.2f}",
                metric_name=metric_name,
                current_value=value,
                threshold=threshold
            )
            self.alerts.append(alert)
    
    def get_avg_latency(self, window_seconds: int = 300) -> float:
        """Get average latency over time window"""
        if not self.perf_tracker["latencies"]:
            return 0.0
        
        recent = self.perf_tracker["latencies"][-100:]  # Last 100 samples
        return sum(recent) / len(recent) if recent else 0.0
    
    def get_error_rate(self) -> float:
        """Get current error rate percentage"""
        total = self.perf_tracker["total_requests"]
        if total == 0:
            return 0.0
        return (self.perf_tracker["errors"] / total) * 100
    
    def get_throughput(self) -> float:
        """Get requests per second over time window"""
        cutoff = time.time() - self.time_window
        recent_count = sum(
            1 for points in self.metrics.values()
            for p in points
            if p.timestamp > cutoff and p.metric_type == MetricType.THROUGHPUT
        )
        return recent_count / self.time_window if self.time_window > 0 else 0.0
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost breakdown"""
        return {
            "total_cost": round(self.cost_tracker["total_cost"], 4),
            "total_requests": self.cost_tracker["requests_count"],
            "avg_cost_per_request": round(
                self.cost_tracker["total_cost"] / max(self.cost_tracker["requests_count"], 1), 4
            ),
            "cost_by_model": dict(self.cost_tracker["cost_by_model"]),
            "cost_by_operation": dict(self.cost_tracker["cost_by_operation"])
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics"""
        latencies = self.perf_tracker["latencies"]
        return {
            "avg_latency_ms": round(self.get_avg_latency(), 2),
            "p95_latency_ms": round(
                sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0, 2
            ),
            "error_rate_percent": round(self.get_error_rate(), 2),
            "total_requests": self.perf_tracker["total_requests"],
            "throughput_rps": round(self.get_throughput(), 2)
        }
    
    def get_active_alerts(self) -> List[Alert]:
        """Get unresolved alerts"""
        return [a for a in self.alerts if not a.resolved]
    
    def resolve_alert(self, alert_index: int):
        """Mark alert as resolved"""
        if 0 <= alert_index < len(self.alerts):
            self.alerts[alert_index].resolved = True
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data"""
        return {
            "performance": self.get_performance_summary(),
            "costs": self.get_cost_summary(),
            "active_alerts": len(self.get_active_alerts()),
            "recent_alerts": [
                {
                    "level": a.level.value,
                    "message": a.message,
                    "triggered_at": time.strftime('%Y-%m-%d %H:%M:%S', 
                                                   time.localtime(a.triggered_at))
                }
                for a in self.alerts[-10:]  # Last 10 alerts
            ],
            "system_health": self._calculate_health_score()
        }
    
    def _calculate_health_score(self) -> float:
        """Calculate overall system health score (0-100)"""
        score = 100.0
        
        # Deduct for high error rate
        error_rate = self.get_error_rate()
        if error_rate > 1:
            score -= min(error_rate * 5, 30)
        
        # Deduct for high latency
        avg_latency = self.get_avg_latency()
        if avg_latency > 5000:
            score -= min((avg_latency - 5000) / 1000, 20)
        
        # Deduct for active alerts
        active_alerts = len(self.get_active_alerts())
        score -= min(active_alerts * 10, 30)
        
        return max(score, 0)

if __name__ == "__main__":
    analytics = RealTimeAnalytics()
    print("✓ RealTimeAnalytics initialized successfully")
