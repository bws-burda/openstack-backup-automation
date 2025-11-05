"""Notification service implementation."""

import logging
import smtplib
import socket
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from ..backup.models import OperationResult
from ..config.models import EmailSettings
from ..interfaces import NotificationServiceInterface


class NotificationService(NotificationServiceInterface):
    """Handles email notifications for backup operations and errors."""

    def __init__(self, email_settings: Optional[EmailSettings] = None):
        self.email_settings = email_settings
        self.logger = logging.getLogger(__name__)
        self.email_enabled = email_settings is not None and email_settings.enabled

    def send_error_notification(
        self, error: Exception, context: Dict[str, Any]
    ) -> bool:
        """Send error notification email with enhanced error categorization."""
        if not self.email_enabled:
            self.logger.info(f"Email notifications disabled - logging error: {error}")
            return True  # Consider it successful since logging is the fallback

        error_type = self._categorize_error(error)
        operation = context.get("operation", "Unknown Operation")

        subject = f"🚨 OpenStack Backup {error_type} - {operation}"

        # Get error-specific template
        body = self._get_error_template(error, error_type, context)

        return self._send_email(subject, body)

    def _categorize_error(self, error: Exception) -> str:
        """Categorize error type for better notification handling."""
        error_str = str(error).lower()
        error_type = type(error).__name__

        if (
            "auth" in error_str
            or "credential" in error_str
            or "unauthorized" in error_str
        ):
            return "Authentication Error"
        elif "quota" in error_str or "limit" in error_str:
            return "Quota/Limit Error"
        elif (
            "network" in error_str
            or "connection" in error_str
            or isinstance(error, (socket.error, ConnectionError))
        ):
            return "Network Error"
        elif "timeout" in error_str or "timed out" in error_str:
            return "Timeout Error"
        elif "not found" in error_str or "404" in error_str:
            return "Resource Not Found"
        elif "permission" in error_str or "forbidden" in error_str:
            return "Permission Error"
        else:
            return f"System Error ({error_type})"

    def _get_error_template(
        self, error: Exception, error_type: str, context: Dict[str, Any]
    ) -> str:
        """Get error-specific email template."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        operation = context.get("operation", "Unknown")
        resource_id = context.get("resource_id", "Unknown")
        resource_type = context.get("resource_type", "Unknown")

        # Base template
        body = f"""
OpenStack Backup Automation - {error_type}

🕐 Time: {timestamp}
🔧 Operation: {operation}
📦 Resource: {resource_id} ({resource_type})
❌ Error Type: {error_type}

Error Details:
{str(error)}

"""

        # Add error-specific guidance
        if "Authentication" in error_type:
            body += """
🔍 Troubleshooting Steps:
1. Check OpenStack credentials in configuration
2. Verify application credential is not expired
3. Ensure proper permissions are granted
4. Test authentication manually with OpenStack CLI

"""
        elif "Network" in error_type:
            body += """
🔍 Troubleshooting Steps:
1. Check network connectivity to OpenStack endpoint
2. Verify firewall rules allow access
3. Check if OpenStack services are running
4. Review DNS resolution for auth_url

"""
        elif "Quota" in error_type:
            body += """
🔍 Troubleshooting Steps:
1. Check OpenStack project quotas
2. Clean up old snapshots/backups if needed
3. Contact OpenStack administrator for quota increase
4. Review retention policies to free up space

"""
        elif "Timeout" in error_type:
            body += """
🔍 Troubleshooting Steps:
1. Check OpenStack service performance
2. Consider increasing operation timeout
3. Reduce concurrent operations if system is overloaded
4. Check for large volumes that may take longer to backup

"""

        # Add context information
        if context:
            body += "Context Information:\n"
            for key, value in context.items():
                if key not in ["operation", "resource_id", "resource_type"]:
                    body += f"  {key}: {value}\n"
            body += "\n"

        body += """
Please check the system logs for more detailed information.

---
OpenStack Backup Automation System
"""
        return body

    def send_backup_report(
        self,
        successful_operations: List[OperationResult],
        failed_operations: List[OperationResult],
    ) -> bool:
        """Send backup operation summary report."""
        if not self.email_enabled:
            self.logger.info(
                f"Email notifications disabled - backup report: {len(successful_operations)} successful, {len(failed_operations)} failed"
            )
            return True

        total_operations = len(successful_operations) + len(failed_operations)
        success_rate = (
            (len(successful_operations) / total_operations * 100)
            if total_operations > 0
            else 0
        )

        subject = f"OpenStack Backup Report - {len(successful_operations)}/{total_operations} Successful"

        body = f"""
OpenStack Backup Automation Report

Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
Total Operations: {total_operations}
Successful: {len(successful_operations)}
Failed: {len(failed_operations)}
Success Rate: {success_rate:.1f}%

"""

        if successful_operations:
            body += "Successful Operations:\n"
            body += "-" * 50 + "\n"
            for result in successful_operations:
                duration = result.duration_seconds or 0
                body += f"  ✓ {result.operation.resource_name} ({result.operation.resource_type})\n"
                body += f"    Operation: {result.operation.operation_type.value}\n"
                body += f"    Duration: {duration:.1f}s\n"
                if result.backup_info:
                    body += f"    Backup ID: {result.backup_info.backup_id}\n"
                body += "\n"

        if failed_operations:
            body += "Failed Operations:\n"
            body += "-" * 50 + "\n"
            for result in failed_operations:
                body += f"  ✗ {result.operation.resource_name} ({result.operation.resource_type})\n"
                body += f"    Operation: {result.operation.operation_type.value}\n"
                body += f"    Error: {result.error_message or 'Unknown error'}\n"
                body += "\n"

        body += """
---
OpenStack Backup Automation System
"""

        return self._send_email(subject, body)

    def send_retention_report(self, deleted_count: int, errors: List[str]) -> bool:
        """Send retention cleanup report."""
        if not self.email_enabled:
            self.logger.info(
                f"Email notifications disabled - retention report: {deleted_count} backups deleted, {len(errors)} errors"
            )
            return True

        subject = f"OpenStack Backup Retention Report - {deleted_count} Backups Cleaned"

        body = f"""
OpenStack Backup Retention Cleanup Report

Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
Backups Deleted: {deleted_count}
Errors: {len(errors)}

"""

        if errors:
            body += "Cleanup Errors:\n"
            body += "-" * 50 + "\n"
            for error in errors:
                body += f"  ✗ {error}\n"
            body += "\n"

        if deleted_count > 0:
            body += f"Successfully cleaned up {deleted_count} expired backups.\n\n"
        else:
            body += "No backups were eligible for cleanup at this time.\n\n"

        body += """
---
OpenStack Backup Automation System
"""

        return self._send_email(subject, body)

    def _send_email(self, subject: str, body: str) -> bool:
        """Send an email using the configured SMTP settings with enhanced error handling."""
        try:
            # Create message
            msg = MIMEMultipart()
            msg["From"] = self.email_settings.sender
            msg["To"] = self.email_settings.recipient
            msg["Subject"] = subject
            msg["Date"] = datetime.now(timezone.utc).strftime(
                "%a, %d %b %Y %H:%M:%S +0000"
            )

            # Attach body
            msg.attach(MIMEText(body, "plain", "utf-8"))

            # Connect to SMTP server with timeout
            server = None
            try:
                if self.email_settings.use_tls:
                    server = smtplib.SMTP(
                        self.email_settings.smtp_server,
                        self.email_settings.smtp_port,
                        timeout=30,
                    )
                    server.starttls()
                else:
                    server = smtplib.SMTP(
                        self.email_settings.smtp_server,
                        self.email_settings.smtp_port,
                        timeout=30,
                    )

                # Login if credentials provided
                if self.email_settings.username and self.email_settings.password:
                    server.login(
                        self.email_settings.username, self.email_settings.password
                    )

                # Send email
                text = msg.as_string()
                server.sendmail(
                    self.email_settings.sender, self.email_settings.recipient, text
                )

                self.logger.info(f"Email notification sent successfully: {subject}")
                return True

            finally:
                if server:
                    try:
                        server.quit()
                    except Exception:
                        pass  # Ignore cleanup errors

        except smtplib.SMTPAuthenticationError as e:
            self.logger.error(f"SMTP authentication failed: {e}")
        except smtplib.SMTPRecipientsRefused as e:
            self.logger.error(f"SMTP recipients refused: {e}")
        except smtplib.SMTPServerDisconnected as e:
            self.logger.error(f"SMTP server disconnected: {e}")
        except socket.timeout as e:
            self.logger.error(f"SMTP connection timeout: {e}")
        except socket.gaierror as e:
            self.logger.error(f"SMTP DNS resolution failed: {e}")
        except Exception as e:
            self.logger.error(f"Failed to send email notification: {e}")

        return False
