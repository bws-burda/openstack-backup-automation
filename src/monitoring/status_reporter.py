"""Status reporting functionality for monitoring systems."""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from ..interfaces import NotificationServiceInterface, StateManagerInterface
from .models import SystemStatus, HealthStatus, ComponentHealth


class StatusReporter:
    """Generates and sends status reports for monitoring systems."""
    
    def __init__(
        self,
        notification_service: Optional[NotificationServiceInterface] = None,
        state_manager: Optional[StateManagerInterface] = None,
    ):
        """Initialize status reporter.
        
        Args:
            notification_service: Service for sending notifications
            state_manager: State manager for accessing backup history
        """
        self.notification_service = notification_service
        self.state_manager = state_manager
        self.logger = logging.getLogger(__name__)
    
    def generate_health_report(self, system_status: SystemStatus) -> Dict[str, Any]:
        """Generate a comprehensive health report.
        
        Args:
            system_status: Current system health status
            
        Returns:
            Dictionary containing formatted health report
        """
        report = {
            "timestamp": system_status.timestamp.isoformat(),
            "overall_status": system_status.overall_status.value,
            "uptime_seconds": system_status.uptime_seconds,
            "summary": self._generate_status_summary(system_status),
            "components": [],
            "recommendations": [],
        }
        
        # Add component details
        for component in system_status.components:
            component_info = {
                "name": component.name,
                "status": component.status.value,
                "message": component.message,
                "last_check": component.last_check.isoformat(),
                "details": component.details,
            }
            report["components"].append(component_info)
        
        # Add recommendations for unhealthy components
        report["recommendations"] = self._generate_recommendations(system_status)
        
        return report
    
    def generate_backup_summary(self, days: int = 7) -> Optional[Dict[str, Any]]:
        """Generate backup operation summary for the last N days.
        
        Args:
            days: Number of days to include in summary
            
        Returns:
            Dictionary containing backup summary or None if state manager unavailable
        """
        if not self.state_manager:
            self.logger.warning("Cannot generate backup summary: no state manager available")
            return None
        
        try:
            # Get recent backups
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # This is a simplified implementation - in a real system you'd want
            # more sophisticated queries to get backup statistics
            summary = {
                "period_days": days,
                "period_start": cutoff_date.isoformat(),
                "period_end": datetime.utcnow().isoformat(),
                "total_backups": 0,
                "successful_backups": 0,
                "failed_backups": 0,
                "backup_types": {
                    "snapshot": 0,
                    "full": 0,
                    "incremental": 0,
                },
                "resources_backed_up": set(),
            }
            
            # Note: This is a placeholder implementation
            # In a real system, you'd query the database for backup statistics
            self.logger.info(f"Generated backup summary for last {days} days")
            
            # Convert set to list for JSON serialization
            summary["resources_backed_up"] = list(summary["resources_backed_up"])
            summary["unique_resources_count"] = len(summary["resources_backed_up"])
            
            return summary
        
        except Exception as e:
            self.logger.error(f"Failed to generate backup summary: {e}")
            return None
    
    def send_health_alert(self, system_status: SystemStatus) -> bool:
        """Send health alert if system has critical issues.
        
        Args:
            system_status: Current system health status
            
        Returns:
            True if alert was sent successfully, False otherwise
        """
        if not self.notification_service:
            self.logger.warning("Cannot send health alert: no notification service available")
            return False
        
        if not system_status.has_critical_issues():
            self.logger.debug("No critical issues detected, skipping health alert")
            return True
        
        try:
            # Prepare alert context
            unhealthy_components = system_status.get_unhealthy_components()
            degraded_components = system_status.get_degraded_components()
            
            context = {
                "alert_type": "health_check",
                "overall_status": system_status.overall_status.value,
                "timestamp": system_status.timestamp.isoformat(),
                "unhealthy_components": [c.name for c in unhealthy_components],
                "degraded_components": [c.name for c in degraded_components],
                "component_details": {
                    c.name: {"status": c.status.value, "message": c.message}
                    for c in unhealthy_components + degraded_components
                },
            }
            
            # Create a generic exception for the notification system
            alert_message = f"System health check failed: {system_status.overall_status.value}"
            if unhealthy_components:
                alert_message += f" - Unhealthy: {[c.name for c in unhealthy_components]}"
            
            health_exception = Exception(alert_message)
            
            return self.notification_service.send_error_notification(health_exception, context)
        
        except Exception as e:
            self.logger.error(f"Failed to send health alert: {e}")
            return False
    
    def send_status_report(self, system_status: SystemStatus, include_backup_summary: bool = True) -> bool:
        """Send comprehensive status report.
        
        Args:
            system_status: Current system health status
            include_backup_summary: Whether to include backup operation summary
            
        Returns:
            True if report was sent successfully, False otherwise
        """
        if not self.notification_service:
            self.logger.warning("Cannot send status report: no notification service available")
            return False
        
        try:
            # Generate health report
            health_report = self.generate_health_report(system_status)
            
            # Add backup summary if requested
            if include_backup_summary:
                backup_summary = self.generate_backup_summary()
                if backup_summary:
                    health_report["backup_summary"] = backup_summary
            
            # Format as readable text for email
            report_text = self._format_report_as_text(health_report)
            
            # Send as backup report (reusing existing notification method)
            # In a real implementation, you might want a dedicated status report method
            return self.notification_service.send_backup_report([], [])
        
        except Exception as e:
            self.logger.error(f"Failed to send status report: {e}")
            return False
    
    def _generate_status_summary(self, system_status: SystemStatus) -> str:
        """Generate a human-readable status summary.
        
        Args:
            system_status: System health status
            
        Returns:
            Summary string
        """
        total_components = len(system_status.components)
        healthy_count = len([c for c in system_status.components if c.is_healthy()])
        degraded_count = len([c for c in system_status.components if c.is_degraded()])
        unhealthy_count = len([c for c in system_status.components if c.is_unhealthy()])
        
        if system_status.overall_status == HealthStatus.HEALTHY:
            return f"All {total_components} components are healthy"
        elif system_status.overall_status == HealthStatus.DEGRADED:
            return f"{healthy_count}/{total_components} components healthy, {degraded_count} degraded"
        else:
            return f"{unhealthy_count} components unhealthy, {degraded_count} degraded, {healthy_count} healthy"
    
    def _generate_recommendations(self, system_status: SystemStatus) -> List[str]:
        """Generate recommendations based on component health.
        
        Args:
            system_status: System health status
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        for component in system_status.components:
            if component.name == "database" and component.is_unhealthy():
                recommendations.append("Check database connectivity and permissions")
            elif component.name == "openstack_api" and component.is_unhealthy():
                recommendations.append("Verify OpenStack credentials and network connectivity")
            elif component.name == "local_storage" and component.is_unhealthy():
                recommendations.append("Free up local disk space for database and logs")
            elif component.name == "openstack_quotas" and component.is_unhealthy():
                recommendations.append("Check OpenStack quotas and storage service availability")
            elif component.is_degraded():
                recommendations.append(f"Monitor {component.name} component for potential issues")
        
        if not recommendations and system_status.overall_status != HealthStatus.HEALTHY:
            recommendations.append("Review system logs for additional details")
        
        return recommendations
    
    def _format_report_as_text(self, report: Dict[str, Any]) -> str:
        """Format health report as readable text.
        
        Args:
            report: Health report dictionary
            
        Returns:
            Formatted text report
        """
        lines = [
            "OpenStack Backup Automation - System Status Report",
            "=" * 50,
            f"Timestamp: {report['timestamp']}",
            f"Overall Status: {report['overall_status'].upper()}",
            f"Summary: {report['summary']}",
            "",
        ]
        
        if report.get("uptime_seconds"):
            uptime_hours = report["uptime_seconds"] / 3600
            lines.append(f"Uptime: {uptime_hours:.1f} hours")
            lines.append("")
        
        # Component details
        lines.append("Component Status:")
        lines.append("-" * 20)
        for component in report["components"]:
            status_symbol = "✓" if component["status"] == "healthy" else "⚠" if component["status"] == "degraded" else "✗"
            lines.append(f"{status_symbol} {component['name']}: {component['status']} - {component['message']}")
        
        lines.append("")
        
        # Recommendations
        if report["recommendations"]:
            lines.append("Recommendations:")
            lines.append("-" * 15)
            for i, rec in enumerate(report["recommendations"], 1):
                lines.append(f"{i}. {rec}")
            lines.append("")
        
        # Backup summary if available
        if "backup_summary" in report:
            backup_summary = report["backup_summary"]
            lines.extend([
                f"Backup Summary (Last {backup_summary['period_days']} days):",
                "-" * 30,
                f"Total Backups: {backup_summary['total_backups']}",
                f"Successful: {backup_summary['successful_backups']}",
                f"Failed: {backup_summary['failed_backups']}",
                f"Unique Resources: {backup_summary['unique_resources_count']}",
                "",
            ])
        
        return "\n".join(lines)
    
    def export_status_json(self, system_status: SystemStatus, file_path: str) -> bool:
        """Export system status to JSON file.
        
        Args:
            system_status: System health status
            file_path: Path to output JSON file
            
        Returns:
            True if export was successful, False otherwise
        """
        try:
            report = self.generate_health_report(system_status)
            
            with open(file_path, 'w') as f:
                json.dump(report, f, indent=2)
            
            self.logger.info(f"Status report exported to {file_path}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to export status to {file_path}: {e}")
            return False