# Roadmap

This document outlines planned features and improvements for OpenStack Backup Automation.

## Planned Features

### 1. Full Incremental Backup Chain Management

**Status:** Infrastructure ready, implementation pending

**Goal:** Implement intelligent full/incremental backup chains to optimize storage usage.

**Current State:**
- Tag format already supports `FULL{DAYS}` parameter (e.g., `BACKUP-DAILY-0300-FULL7`)
- Config has `full_backup_interval_days` setting
- Database tracks backup types (full/incremental)

**What's Missing:**
- Scheduling of incremental backups
- Proper backup chain validation (ensure incrementals have a full backup base)
- Chain integrity checks (detect broken chains)
- Smart cleanup that preserves chain integrity

**Example Target Behavior:**
```bash
# Tag: BACKUP-DAILY-0300-FULL7
Day 1: Full backup
Day 2-7: Incremental backups (based on Day 1)
Day 8: Full backup (new chain starts)
Day 9-14: Incremental backups (based on Day 8)
```

**Benefits:**
- Significant storage savings (incrementals are much smaller)
- Faster backup operations (incrementals are quicker)
- Configurable balance between storage and restore speed

---

### 2. Multi-Project Support

**Status:** Not implemented

**Goal:** Manage backups across multiple OpenStack projects from a single installation.

**Current State:**
- Single project per config file
- Need separate installation per project

**Proposed Solution:**
```yaml
# config.yaml
projects:
  - name: "production"
    auth_url: "https://openstack.example.com:5000/v3"
    application_credential_id: "prod-cred-id"
    application_credential_secret: "prod-secret"
    project_name: "production-project"
    
  - name: "staging"
    auth_url: "https://openstack.example.com:5000/v3"
    application_credential_id: "staging-cred-id"
    application_credential_secret: "staging-secret"
    project_name: "staging-project"
    
  - name: "development"
    auth_url: "https://openstack.example.com:5000/v3"
    application_credential_id: "dev-cred-id"
    application_credential_secret: "dev-secret"
    project_name: "dev-project"

# Optional: Per-project overrides
backup:
  default:
    full_backup_interval_days: 7
    retention_days: 30
  
  project_overrides:
    production:
      retention_days: 90
    development:
      retention_days: 7
```

**Benefits:**
- Single installation manages multiple projects
- Centralized backup management
- Reduced maintenance overhead
- Consistent backup policies across projects

**Implementation Considerations:**
- Database schema needs project identifier
- Separate backup tracking per project
- Backward compatibility with single-project configs

---

### 2. Multi Tagging Ressources

**Status:** Not implemented

**Goal:** Use multiple tags on the same ressource.

---

## Contributing

Have ideas for new features? Open an issue or submit a pull request!
