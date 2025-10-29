"""Data models for monitoring and health checks."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class HealthStatus(Enum):
    """Health status enumeration."""
    
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a system component."""
    
    name: str
    status: HealthStatus
    message: str
    last_check: datetime
    details: Dict[str, Any] = field(default_factory=dict)
    
    def is_healthy(self) -> bool:
        """Check if component is healthy."""
        return self.status == HealthStatus.HEALTHY
    
    def is_degraded(self) -> bool:
        """Check if component is degraded."""
        return self.status == HealthStatus.DEGRADED
    
    def is_unhealthy(self) -> bool:
        """Check if component is unhealthy."""
        return self.status == HealthStatus.UNHEALTHY


@dataclass
class SystemStatus:
    """Overall system health status."""
    
    overall_status: HealthStatus
    components: List[ComponentHealth]
    timestamp: datetime
    uptime_seconds: Optional[float] = None
    
    def get_component(self, name: str) -> Optional[ComponentHealth]:
        """Get health status of a specific component."""
        for component in self.components:
            if component.name == name:
                return component
        return None
    
    def get_unhealthy_components(self) -> List[ComponentHealth]:
        """Get list of unhealthy components."""
        return [c for c in self.components if c.is_unhealthy()]
    
    def get_degraded_components(self) -> List[ComponentHealth]:
        """Get list of degraded components."""
        return [c for c in self.components if c.is_degraded()]
    
    def has_critical_issues(self) -> bool:
        """Check if system has critical health issues."""
        return self.overall_status == HealthStatus.UNHEALTHY
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert system status to dictionary for JSON serialization."""
        return {
            "overall_status": self.overall_status.value,
            "timestamp": self.timestamp.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "last_check": c.last_check.isoformat(),
                    "details": c.details,
                }
                for c in self.components
            ],
        }


@dataclass
class HealthCheckConfig:
    """Configuration for health checks."""
    
    enabled: bool = True
    check_interval_seconds: int = 60
    timeout_seconds: int = 30
    database_check_enabled: bool = True
    openstack_check_enabled: bool = True
    local_storage_check_enabled: bool = True
    local_storage_threshold_percent: int = 95  # Higher threshold since it's just metadata
    openstack_quota_check_enabled: bool = True
    
    def __post_init__(self):
        """Validate health check configuration."""
        if self.check_interval_seconds <= 0:
            raise ValueError("Check interval must be positive")
        
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be positive")
        
        if not (0 <= self.local_storage_threshold_percent <= 100):
            raise ValueError("Local storage threshold must be between 0 and 100")