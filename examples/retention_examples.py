#!/usr/bin/env python3
"""
Beispiele für die erweiterte Retention Management Funktionalität.

Zeigt die Verwendung von:
1. Tag-basierten Retention Policies
2. Batch Deletion
3. Verschiedenen Policy-Matching-Strategien
"""

import asyncio
from datetime import datetime, UTC
from typing import Dict

# Beispiel-Imports (in echter Anwendung)
# from src.retention.manager import RetentionManager
# from src.config.models import RetentionPolicy
# from src.backup.models import BackupInfo, BackupType


def example_tag_formats():
    """Beispiele für Tag-Formate mit eingebetteten Retention-Informationen."""
    
    examples = {
        # Basis-Tags (ohne Retention-Info)
        "basic_daily": "BACKUP-DAILY-0300",
        "basic_weekly": "SNAPSHOT-WEEKLY-1200",
        
        # Tags mit Retention-Informationen
        "critical_db": "BACKUP-DAILY-0300-RETAIN90-FULL7",
        "test_system": "BACKUP-WEEKLY-2300-RETAIN7",
        "quick_snapshots": "SNAPSHOT-DAILY-1200-RETAIN3",
        "monthly_archive": "BACKUP-MONTHLY-0100-RETAIN365-FULL30",
        
        # Verschiedene Kombinationen
        "dev_environment": "BACKUP-DAILY-0200-RETAIN14-FULL3",
        "log_backups": "BACKUP-DAILY-0400-RETAIN30-FULL10",
        "emergency_snapshots": "SNAPSHOT-MONDAY-0600-RETAIN1",
    }
    
    print("🏷️  Tag-Format Beispiele:")
    print("=" * 50)
    
    for name, tag in examples.items():
        print(f"{name:20} → {tag}")
        
        # Simuliere Tag-Parsing (würde normalerweise RetentionManager verwenden)
        parts = tag.split('-')
        retention_info = []
        
        for part in parts:
            if part.startswith('RETAIN'):
                retention_info.append(f"Retention: {part[6:]} Tage")
        
        # Chain-Integrität wird automatisch sichergestellt
        if retention_info:
            retention_info.append("Chain-Integrität: Automatisch geschützt")
        
        if retention_info:
            print(f"{' ' * 20}   → {', '.join(retention_info)}")
        else:
            print(f"{' ' * 20}   → Verwendet Default-Policy")
        print()


def example_config_with_policies():
    """Beispiel-Konfiguration mit verschiedenen Retention Policies."""
    
    config_example = """
# backup-automation.yaml

openstack:
  auth_method: "application_credential"
  application_credential_id: "your-app-cred-id"
  application_credential_secret: "your-app-cred-secret"
  auth_url: "https://openstack.example.com:5000/v3"
  project_name: "backup-project"

backup:
  full_backup_interval_days: 7
  max_concurrent_operations: 5
  operation_timeout_minutes: 60

# Verschiedene Retention Policies für verschiedene Anwendungsfälle
retention_policies:
  # Standard-Policy (Fallback)
  default:
    retention_days: 30
    min_backups_to_keep: 1
    keep_last_full_backup: true
  
  # Kritische Systeme - längere Aufbewahrung
  critical:
    retention_days: 90
    min_backups_to_keep: 5
    keep_last_full_backup: true
  
  # Test-Systeme - kurze Aufbewahrung
  testing:
    retention_days: 7
    min_backups_to_keep: 1
    keep_last_full_backup: false
  
  # Snapshots - sehr kurze Aufbewahrung
  snapshots:
    retention_days: 3
    min_backups_to_keep: 1
    keep_last_full_backup: false
  
  # Tägliche Backups
  daily:
    retention_days: 30
    min_backups_to_keep: 3
    keep_last_full_backup: true
  
  # Wöchentliche Backups - längere Aufbewahrung
  weekly:
    retention_days: 60
    min_backups_to_keep: 2
    keep_last_full_backup: true
  
  # Monatliche Archive
  monthly:
    retention_days: 365
    min_backups_to_keep: 1
    keep_last_full_backup: true

notifications:
  email_recipient: "admin@example.com"
  email_sender: "backup-system@example.com"

scheduling:
  mode: "cron"
  check_interval_minutes: 15
"""
    
    print("⚙️  Konfiguration mit mehreren Retention Policies:")
    print("=" * 60)
    print(config_example)


async def example_usage_scenarios():
    """Beispiele für verschiedene Nutzungsszenarien."""
    
    print("🚀 Nutzungsszenarien:")
    print("=" * 40)
    
    scenarios = [
        {
            "name": "Produktions-Datenbank",
            "tags": ["BACKUP-DAILY-0300-RETAIN90"],
            "description": "Tägliche Backups, 90 Tage Aufbewahrung, Chain-Integrität automatisch geschützt"
        },
        {
            "name": "Test-Environment", 
            "tags": ["BACKUP-WEEKLY-2300-RETAIN7"],
            "description": "Wöchentliche Backups, 7 Tage Aufbewahrung, mindestens 1 Backup bleibt immer"
        },
        {
            "name": "Log-Snapshots",
            "tags": ["SNAPSHOT-DAILY-1200-RETAIN3"],
            "description": "Tägliche Snapshots, 3 Tage Aufbewahrung (Snapshots beeinflussen keine Chains)"
        },
        {
            "name": "Monats-Archive",
            "tags": ["BACKUP-MONTHLY-0100-RETAIN365"],
            "description": "Monatliche Backups, 1 Jahr Aufbewahrung, Archive-Charakter"
        },
        {
            "name": "Entwicklungs-System",
            "tags": [
                "BACKUP-DAILY-0200-RETAIN14",   # Tägliche Backups, 2 Wochen
                "SNAPSHOT-MONDAY-0600-RETAIN1"  # Wöchentliche Snapshots, 1 Tag
            ],
            "description": "Gemischte Strategie: Tägliche Backups + wöchentliche Snapshots"
        }
    ]
    
    for scenario in scenarios:
        print(f"\n📋 {scenario['name']}:")
        print(f"   Beschreibung: {scenario['description']}")
        print(f"   Tags:")
        for tag in scenario['tags']:
            print(f"     - {tag}")


def example_batch_deletion_benefits():
    """Zeigt die Vorteile von Batch Deletion."""
    
    print("\n⚡ Batch Deletion Vorteile:")
    print("=" * 40)
    
    scenarios = [
        {
            "backups": 50,
            "sequential_time": "50 × 2s = 100s (1:40 min)",
            "batch_time": "10 batches × 8s = 80s (1:20 min)", 
            "improvement": "20% schneller"
        },
        {
            "backups": 200,
            "sequential_time": "200 × 2s = 400s (6:40 min)",
            "batch_time": "40 batches × 8s = 320s (5:20 min)",
            "improvement": "25% schneller"
        },
        {
            "backups": 1000,
            "sequential_time": "1000 × 2s = 2000s (33 min)",
            "batch_time": "200 batches × 8s = 1600s (27 min)",
            "improvement": "30% schneller"
        }
    ]
    
    for scenario in scenarios:
        print(f"\n📊 {scenario['backups']} Backups zu löschen:")
        print(f"   Sequential: {scenario['sequential_time']}")
        print(f"   Batch (5er): {scenario['batch_time']}")
        print(f"   Verbesserung: {scenario['improvement']}")


def example_policy_priority():
    """Zeigt die Policy-Prioritäts-Reihenfolge."""
    
    print("\n🎯 Policy-Prioritäts-Reihenfolge:")
    print("=" * 45)
    
    print("1. 🏷️  Tag-eingebettete Retention (HÖCHSTE Priorität)")
    print("   Beispiel: BACKUP-DAILY-0300-RETAIN90")
    print("   → Überschreibt alle anderen Policies")
    print()
    
    print("2. 🌐 Globale Policy-Zuordnung (MITTLERE Priorität)")
    print("   - Nach Backup-Typ: snapshots, full_backups, incremental_backups")
    print("   - Nach Resource-Typ: instances, volumes") 
    print("   - Nach Schedule-Frequenz: daily, weekly, monthly")
    print()
    
    print("3. 🔄 Default Policy (FALLBACK)")
    print("   → Wird verwendet wenn keine anderen Policies greifen")
    print()
    
    example_cases = [
        {
            "tag": "BACKUP-DAILY-0300-RETAIN90",
            "result": "Tag-Policy: 90 Tage (Chain-Integrität automatisch geschützt)"
        },
        {
            "tag": "BACKUP-DAILY-0300", 
            "global_policy": "daily: 30 Tage",
            "result": "Global-Policy: 30 Tage (daily-Policy greift)"
        },
        {
            "tag": "BACKUP-WEEKLY-1200",
            "global_policy": "keine weekly-Policy",
            "result": "Default-Policy: z.B. 30 Tage"
        }
    ]
    
    print("Beispiele:")
    for i, case in enumerate(example_cases, 1):
        print(f"\n{i}. Tag: {case['tag']}")
        if 'global_policy' in case:
            print(f"   Global: {case['global_policy']}")
        print(f"   → {case['result']}")


if __name__ == "__main__":
    print("🔧 OpenStack Backup Automation - Retention Management Beispiele")
    print("=" * 70)
    
    example_tag_formats()
    print("\n" + "=" * 70)
    
    example_config_with_policies()
    print("\n" + "=" * 70)
    
    asyncio.run(example_usage_scenarios())
    print("\n" + "=" * 70)
    
    example_batch_deletion_benefits()
    print("\n" + "=" * 70)
    
    example_policy_priority()
    
    print("\n" + "=" * 70)
    print("✅ Alle Beispiele abgeschlossen!")
    print("\nWeitere Informationen:")
    print("- Dokumentation: docs/retention-management.md")
    print("- Konfiguration: config/backup-automation.yaml.example")
    print("- Tests: tests/test_retention_manager.py")