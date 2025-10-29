"""Operation verification and failure reporting utilities."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..backup.models import BackupInfo, OperationResult, OperationStatus
from ..interfaces import NotificationServiceInterface, OpenStackClientInterface


class OperationVerifier:
    """Handles verification of backup and snapshot operations."""
    
    def __init__(
        self, 
        openstack_client: OpenStackClientInterface,
        notification_service: Optional[NotificationServiceInterface] = None
    ):
        self.openstack_client = openstack_client
        self.notification_service = notification_service
        self.logger = logging.getLogger(__name__)

    async def verify_backup_success(
        self, 
        backup_info: BackupInfo, 
        timeout_minutes: int = 60
    ) -> bool:
        """
        Verify that a backup was created successfully.
        
        Args:
            backup_info: Information about the backup to verify
            timeout_minutes: Maximum time to wait for verification
            
        Returns:
            bool: True if backup is verified as successful, False otherwise
        """
        start_time = datetime.now(timezone.utc)
        timeout_seconds = timeout_minutes * 60
        
        self.logger.info(
            f"Starting verification for {backup_info.backup_type.value} "
            f"{backup_info.backup_id} (timeout: {timeout_minutes}m)"
        )
        
        while True:
            try:
                # Check backup status via OpenStack API
                status = await self.openstack_client.get_backup_status(
                    backup_info.backup_id, 
                    backup_info.resource_type
                )
                
                if status is None:
                    self.logger.error(f"Backup {backup_info.backup_id} not found during verification")
                    return False
                
                status_lower = status.lower()
                
                # Check for successful completion
                if status_lower in ['available', 'completed', 'active']:
                    self.logger.info(f"Backup {backup_info.backup_id} verified as successful")
                    return True
                
                # Check for failure states
                if status_lower in ['error', 'failed', 'deleted']:
                    self.logger.error(f"Backup {backup_info.backup_id} failed with status: {status}")
                    return False
                
                # Check timeout
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                if elapsed >= timeout_seconds:
                    self.logger.error(
                        f"Verification timeout for backup {backup_info.backup_id} "
                        f"after {elapsed:.1f}s (status: {status})"
                    )
                    return False
                
                # Still in progress, wait and check again
                self.logger.debug(f"Backup {backup_info.backup_id} status: {status}, waiting...")
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error during backup verification: {e}")
                return False

    async def verify_operation_results(
        self, 
        results: List[OperationResult],
        timeout_minutes: int = 60
    ) -> List[OperationResult]:
        """
        Verify multiple operation results and update their status.
        
        Args:
            results: List of operation results to verify
            timeout_minutes: Timeout for each verification
            
        Returns:
            List[OperationResult]: Updated results with verification status
        """
        verification_tasks = []
        
        for result in results:
            if result.backup_info and result.status == OperationStatus.COMPLETED:
                task = self._verify_single_result(result, timeout_minutes)
                verification_tasks.append(task)
        
        if verification_tasks:
            await asyncio.gather(*verification_tasks, return_exceptions=True)
        
        return results

    async def _verify_single_result(
        self, 
        result: OperationResult, 
        timeout_minutes: int
    ) -> None:
        """Verify a single operation result and update its status."""
        try:
            if result.backup_info:
                is_verified = await self.verify_backup_success(
                    result.backup_info, 
                    timeout_minutes
                )
                
                if is_verified:
                    result.backup_info.verified = True
                    self.logger.info(
                        f"Verification successful for {result.operation.resource_name}"
                    )
                else:
                    result.status = OperationStatus.FAILED
                    result.error_message = "Backup verification failed"
                    self.logger.error(
                        f"Verification failed for {result.operation.resource_name}"
                    )
        except Exception as e:
            result.status = OperationStatus.FAILED
            result.error_message = f"Verification error: {str(e)}"
            self.logger.error(
                f"Verification error for {result.operation.resource_name}: {e}"
            )


class FailureReporter:
    """Handles reporting of operation failures and system issues."""
    
    def __init__(self, notification_service: NotificationServiceInterface):
        self.notification_service = notification_service
        self.logger = logging.getLogger(__name__)

    async def report_operation_failures(
        self, 
        failed_results: List[OperationResult],
        context: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Report multiple operation failures in a consolidated report.
        
        Args:
            failed_results: List of failed operation results
            context: Additional context information
            
        Returns:
            bool: True if report was sent successfully, False otherwise
        """
        if not failed_results:
            return True
        
        try:
            # Group failures by error type for better reporting
            failure_groups = self._group_failures_by_error(failed_results)
            
            # Send consolidated failure report
            success = self.notification_service.send_backup_report(
                successful_operations=[],
                failed_operations=failed_results
            )
            
            # Log failure summary
            self.logger.error(
                f"Reported {len(failed_results)} operation failures across "
                f"{len(failure_groups)} error categories"
            )
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to report operation failures: {e}")
            return False

    def _group_failures_by_error(
        self, 
        failed_results: List[OperationResult]
    ) -> Dict[str, List[OperationResult]]:
        """Group failed results by error type for better reporting."""
        groups = {}
        
        for result in failed_results:
            error_key = self._get_error_category(result.error_message or "Unknown error")
            if error_key not in groups:
                groups[error_key] = []
            groups[error_key].append(result)
        
        return groups

    def _get_error_category(self, error_message: str) -> str:
        """Categorize error message for grouping."""
        error_lower = error_message.lower()
        
        if "auth" in error_lower or "credential" in error_lower:
            return "Authentication Errors"
        elif "network" in error_lower or "connection" in error_lower:
            return "Network Errors"
        elif "quota" in error_lower or "limit" in error_lower:
            return "Quota/Limit Errors"
        elif "timeout" in error_lower:
            return "Timeout Errors"
        elif "not found" in error_lower:
            return "Resource Not Found Errors"
        elif "permission" in error_lower or "forbidden" in error_lower:
            return "Permission Errors"
        else:
            return "System Errors"

    async def report_system_health_issue(
        self, 
        issue_description: str,
        severity: str = "medium",
        additional_context: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Report a system health issue.
        
        Args:
            issue_description: Description of the health issue
            severity: Issue severity (low, medium, high, critical)
            additional_context: Additional context information
            
        Returns:
            bool: True if report was sent successfully, False otherwise
        """
        try:
            context = {
                "operation": "System Health Check",
                "resource_id": "system",
                "resource_type": "system",
                "severity": severity,
                "issue": issue_description,
            }
            
            if additional_context:
                context.update(additional_context)
            
            # Create a system health exception for notification
            health_exception = Exception(f"System Health Issue: {issue_description}")
            
            success = self.notification_service.send_error_notification(
                health_exception, 
                context
            )
            
            self.logger.warning(f"Reported system health issue: {issue_description}")
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to report system health issue: {e}")
            return False