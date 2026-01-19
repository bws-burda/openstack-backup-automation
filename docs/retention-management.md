# Retention Management - Advanced Features

## Overview

This document covers advanced retention management features for power users and system administrators. For basic retention configuration, see the [README](../README.md#tag-format).

The retention management system includes two key advanced features:

1. **🚀 Batch Deletion** - Parallel deletion for improved performance
2. **🏷️ Policy Priority System** - How retention policies are resolved

## 🚀 Batch Deletion

### How It Works

Instead of deleting backups sequentially, they are processed in parallel batches:

```python
# Old Method (Sequential)
for backup in backups:
    await delete_backup(backup)  # 2s per backup

# New Method (Batch)
await delete_backups_batch(backups, batch_size=5)  # 5 parallel, ~8s per batch
```

### Performance Improvement

| Backup Count | Sequential | Batch (5) | Improvement |
|--------------|------------|-----------|-------------|
| 50           | 1:40 min   | 1:20 min  | 20% faster  |
| 200          | 6:40 min   | 5:20 min  | 25% faster  |
| 1000         | 33 min     | 27 min    | 30% faster  |

### Configuration

```python
# Enable batch deletion
cleanup_result = await retention_manager.cleanup_expired_backups(
    retention_policies=policies,
    use_batch_deletion=True,
    batch_size=5  # Number of parallel deletions
)
```

## 🏷️ Backup Chain Integrity

### Automatic Chain Protection

The system automatically ensures backup chain integrity:

- **Minimum Retention**: At least 1 backup is always kept
- **Full Backup Protection**: Full backups are only deleted when no incrementals depend on them
- **Complete Chains**: Incremental chains remain complete and functional
- **Orphan Detection**: Orphaned incrementals are automatically identified and cleaned up

### Example

```
BACKUP-DAILY-0300-RETAIN90
│      │     │     │
│      │     │     └─ 90 days retention
│      │     └─ At 03:00
│      └─ Daily
└─ Backup operation

Chain integrity is automatically ensured:
- At least 1 backup always remains
- Full backups only deleted when no dependent incrementals exist
- Incremental chains remain complete
```

## Policy Priority System

The system applies retention policies in the following order:

### 1. Tag-Embedded Retention (HIGHEST Priority)
```
BACKUP-DAILY-0300-RETAIN90
→ Uses 90 days retention with automatic chain integrity
```

### 2. Global Policy Mapping (MEDIUM Priority)
```yaml
retention_policies:
  daily: {retention_days: 30}
  snapshots: {retention_days: 7}
  instances: {retention_days: 60}
```

Matching order:
- By backup type: `snapshots`, `full_backups`, `incremental_backups`
- By resource type: `instances`, `volumes`
- By schedule frequency: `daily`, `weekly`, `monthly`

### 3. Default Policy (FALLBACK)
```yaml
retention_policies:
  default: {retention_days: 30, min_backups_to_keep: 1}
```

## Usage

### Basic Usage
```python
# Standard cleanup with tag policies
cleanup_result = await retention_manager.cleanup_expired_backups(
    retention_policies=config.retention_policies,
    use_tag_policies=True,      # Enable tag-based policies
    use_batch_deletion=True,    # Enable batch deletion
    batch_size=5               # 5 parallel deletions
)
```

### Advanced Usage
```python
# Use only tag-based policies
backups_to_delete = retention_manager.get_backups_to_delete_with_tag_policies(
    default_retention_policy=RetentionPolicy(retention_days=30),
    global_retention_policies=config.retention_policies
)

# Use batch deletion separately
batch_result = await retention_manager.delete_backups_batch(
    backups=backups_to_delete,
    batch_size=10
)
```

## Configuration

### Advanced YAML Configuration
```yaml
# config.yaml
retention_policies:
  # Default policy (fallback)
  default:
    retention_days: 30
    min_backups_to_keep: 1
  
  # Special policies for different use cases
  critical:
    retention_days: 90
    min_backups_to_keep: 5
  
  testing:
    retention_days: 7
    min_backups_to_keep: 1
  
  snapshots:
    retention_days: 3
    min_backups_to_keep: 1
  
  daily:
    retention_days: 30
    min_backups_to_keep: 3
  
  weekly:
    retention_days: 60
    min_backups_to_keep: 2

backup:
  # Batch deletion settings
  max_concurrent_operations: 5  # Also used for batch deletion
  operation_timeout_minutes: 60
```

## Monitoring & Logging

### Cleanup Results
```python
cleanup_result = {
    "use_tag_policies": True,
    "use_batch_deletion": True,
    "batch_size": 5,
    "deleted_count": 45,
    "failed_count": 2,
    "space_freed_bytes": 1073741824,  # 1GB
    "policies_applied": ["default", "daily", "snapshots"],
    "batch_results": {...},
    "chain_deletions": [...]
}
```

### Log Output
```
INFO: Evaluating backups for deletion using tag-based retention policies
DEBUG: Backup backup-123 marked for deletion (policy: 90d retention)
INFO: Using batch deletion for 25 standalone backups
INFO: Batch deletion completed: 23 successful, 2 failed, 1073741824 bytes freed
```

## Best Practices

### 1. Tag Design
- **Consistent naming**: Always use `RETAIN{n}` format
- **Sensible defaults**: Not every tag needs retention info
- **Documentation**: Document tag meanings

### 2. Batch Sizes
- **Standard**: 5 parallel deletions (good compromise)
- **Small OpenStack**: 2-3 (respect API limits)
- **Large OpenStack**: 8-10 (better performance)

### 3. Policy Hierarchy
- **Tag retention**: For special requirements
- **Global policies**: For standard categories
- **Default policy**: Conservative (longer retention)

### 4. Monitoring
- **Cleanup reports**: Regular reports on deleted backups
- **Error tracking**: Monitor failed deletions
- **Storage monitoring**: Track freed space

## Troubleshooting

### Common Issues

**Problem**: Batch deletion fails
```
Solution: Reduce batch size or use sequential deletion
use_batch_deletion=False
```

**Problem**: Tag retention is ignored
```
Solution: Check tag format, must be exactly RETAIN{n}
Wrong: RETAIN-30, retain30
Correct: RETAIN30
```

**Problem**: Too many backups are deleted
```
Solution: Increase min_backups_to_keep
```

### Debug Mode
```python
# Enable detailed logging
import logging
logging.getLogger('retention.manager').setLevel(logging.DEBUG)

# Dry-run for testing
cleanup_result = await retention_manager.schedule_cleanup_operation(
    retention_policies=policies,
    dry_run=True  # Only plan, don't execute
)
```