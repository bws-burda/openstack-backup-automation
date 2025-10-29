#!/usr/bin/env python3
"""
Aktualisierte Beispiele für die erweiterte Retention Management Funktionalität.

Neue Features:
1. Entfernung von min_backups_to_keep (vereinfacht)
2. Full Backup Intervall in Tags (FULL{n})
3. Vereinfachte Tag-Struktur
"""

import asyncio
from datetime import datetime, UTC
from typing import Dict

def example_updated_tag_formats():
    """Beispiele für die neuen, vereinfachten Tag-Formate."""
    
    examples = {
        # Basis-Tags (ohne Retention-Info)
        "basic_daily": "BACKUP-DAILY-0300",
        "basic_weekly": "SNAPSHOT-WEEKLY-1200",
        
        # Tags mit Retention-Informationen
        "critical_db": "BACKUP-DAILY-0300-RETAIN90-FULL7",
        "test_system": "BACKUP-WEEKLY-2300-RETAIN7",
        "quick_snapshots": "SNAPSHOT-DAILY-1200-RETAIN3",
        "monthly_archive": "BACKUP-MONTHLY-0100-RETAIN365-FULL30",
        
        # Verschiedene Full Backup Intervalle
        "dev_environment": "BACKUP-DAILY-0200-RETAIN14-FULL3",
        "log_backups": "BACKUP-DAILY-0400-RETAIN30-FULL10",
        "emergency_snapshots": "SNAPSHOT-MONDAY-0600-RETAIN1",
        
        # Spezielle Anwendungsfälle
        "database_prod": "BACKUP-DAILY-0100-RETAIN180-FULL14",  # 6 Monate, Full alle 2 Wochen
        "file_server": "BACKUP-DAILY-0500-RETAIN60-FULL7",      # 2 Monate, Full wöchentlich
        "temp_storage": "BACKUP-WEEKLY-2200-RETAIN14",          # 2 Wochen, nur Retention
    }
    
    print("🏷️  Neue Tag-Format Beispiele:")
    print("=" * 60)
    
    for name, tag in examples.items():
        print(f"{name:20} → {tag}")
        
        # Simuliere Tag-Parsing
        parts = tag.split('-')
        retention_info = []
        
        for part in parts:
            if part.startswith('RETAIN'):
                retention_info.append(f"Retention: {part[6:]} Tage")
            elif part.startswith('FULL'):
                retention_info.append(f"Neues Full Backup alle {part[4:]} Tage")
        
        if retention_info:
            print(f"{' ' * 20}   → {', '.join(retention_info)}")
        else:
            print(f"{' ' * 20}   → Verwendet Default-Einstellungen")
        print()


def example_full_backup_strategies():
    """Beispiele für verschiedene Full Backup Strategien."""
    
    print("🔄 Full Backup Strategien:")
    print("=" * 50)
    
    strategies = [
        {
            "name": "Kritische Datenbank",
            "tag": "BACKUP-DAILY-0300-RETAIN90-FULL7",
            "description": "Tägliche Backups, 90 Tage behalten, neues Full Backup alle 7 Tage",
            "use_case": "Produktions-DB mit hoher Änderungsrate"
        },
        {
            "name": "File Server",
            "tag": "BACKUP-DAILY-0500-RETAIN60-FULL14", 
            "description": "Tägliche Backups, 60 Tage behalten, neues Full Backup alle 14 Tage",
            "use_case": "File Server mit moderater Änderungsrate"
        },
        {
            "name": "Archive System",
            "tag": "BACKUP-MONTHLY-0100-RETAIN365-FULL30",
            "description": "Monatliche Backups, 1 Jahr behalten, neues Full Backup alle 30 Tage",
            "use_case": "Langzeit-Archivierung mit seltenen Änderungen"
        },
        {
            "name": "Development Environment",
            "tag": "BACKUP-DAILY-0200-RETAIN14-FULL3",
            "description": "Tägliche Backups, 14 Tage behalten, neues Full Backup alle 3 Tage",
            "use_case": "Entwicklungsumgebung mit häufigen Änderungen"
        },
        {
            "name": "Log Storage",
            "tag": "BACKUP-DAILY-0400-RETAIN30-FULL10",
            "description": "Tägliche Backups, 30 Tage behalten, neues Full Backup alle 10 Tage",
            "use_case": "Log-Dateien mit kontinuierlichem Wachstum"
        }
    ]
    
    for strategy in strategies:
        print(f"\n📋 {strategy['name']}:")
        print(f"   Tag: {strategy['tag']}")
        print(f"   Beschreibung: {strategy['description']}")
        print(f"   Anwendungsfall: {strategy['use_case']}")


def example_simplified_config():
    """Beispiel für vereinfachte Konfiguration ohne min_backups_to_keep."""
    
    config_example = """
# backup-automation.yaml - Vereinfachte Konfiguration

openstack:
  auth_method: "application_credential"
  application_credential_id: "your-app-cred-id"
  application_credential_secret: "your-app-cred-secret"
  auth_url: "https://openstack.example.com:5000/v3"
  project_name: "backup-project"

backup:
  full_backup_interval_days: 7  # Standard-Intervall für Full Backups
  max_concurrent_operations: 5
  operation_timeout_minutes: 60

# Vereinfachte Retention Policies (ohne min_backups_to_keep)
retention_policies:
  # Standard-Policy (Fallback)
  default:
    retention_days: 30
    keep_last_full_backup: true
  
  # Kritische Systeme - längere Aufbewahrung
  critical:
    retention_days: 90
    keep_last_full_backup: true
  
  # Test-Systeme - kurze Aufbewahrung
  testing:
    retention_days: 7
    keep_last_full_backup: false
  
  # Snapshots - sehr kurze Aufbewahrung
  snapshots:
    retention_days: 3
    keep_last_full_backup: false
  
  # Tägliche Backups
  daily:
    retention_days: 30
    keep_last_full_backup: true
  
  # Wöchentliche Backups
  weekly:
    retention_days: 60
    keep_last_full_backup: true

notifications:
  email_recipient: "admin@example.com"
  email_sender: "backup-system@example.com"

scheduling:
  mode: "cron"
  check_interval_minutes: 15
"""
    
    print("⚙️  Vereinfachte Konfiguration:")
    print("=" * 50)
    print(config_example)


def example_backup_decision_logic():
    """Zeigt die Logik für Full vs Incremental Backup Entscheidungen."""
    
    print("🤖 Backup-Entscheidungslogik:")
    print("=" * 45)
    
    scenarios = [
        {
            "resource": "database-prod",
            "tag": "BACKUP-DAILY-0300-RETAIN90-FULL7",
            "last_full_backup": "vor 3 Tagen",
            "decision": "Incremental Backup",
            "reasoning": "Letztes Full Backup ist erst 3 Tage alt (Intervall: 7 Tage)"
        },
        {
            "resource": "database-prod", 
            "tag": "BACKUP-DAILY-0300-RETAIN90-FULL7",
            "last_full_backup": "vor 8 Tagen",
            "decision": "Full Backup",
            "reasoning": "Letztes Full Backup ist 8 Tage alt (Intervall: 7 Tage)"
        },
        {
            "resource": "file-server",
            "tag": "BACKUP-DAILY-0500-RETAIN60-FULL14",
            "last_full_backup": "vor 10 Tagen", 
            "decision": "Incremental Backup",
            "reasoning": "Letztes Full Backup ist erst 10 Tage alt (Intervall: 14 Tage)"
        },
        {
            "resource": "new-system",
            "tag": "BACKUP-DAILY-0200-RETAIN30-FULL7",
            "last_full_backup": "nie",
            "decision": "Full Backup",
            "reasoning": "Kein vorheriges Full Backup vorhanden"
        }
    ]
    
    for scenario in scenarios:
        print(f"\n📊 Resource: {scenario['resource']}")
        print(f"   Tag: {scenario['tag']}")
        print(f"   Letztes Full Backup: {scenario['last_full_backup']}")
        print(f"   → Entscheidung: {scenario['decision']}")
        print(f"   → Begründung: {scenario['reasoning']}")


def example_retention_benefits():
    """Zeigt die Vorteile der vereinfachten Retention-Logik."""
    
    print("\n✨ Vorteile der vereinfachten Retention:")
    print("=" * 50)
    
    benefits = [
        {
            "title": "Einfachere Konfiguration",
            "description": "Keine min_backups_to_keep Parameter mehr nötig",
            "example": "retention_days: 30  # Das reicht!"
        },
        {
            "title": "Intelligente Chain-Integrität", 
            "description": "System behält automatisch mindestens 1 Backup und schützt Chains",
            "example": "Letztes Full Backup wird automatisch geschützt"
        },
        {
            "title": "Flexible Full Backup Intervalle",
            "description": "FULL{n} Parameter in Tags für individuelle Strategien",
            "example": "BACKUP-DAILY-0300-RETAIN90-FULL7"
        },
        {
            "title": "Weniger Verwirrung",
            "description": "Klare, einfache Regeln ohne komplexe Parameter",
            "example": "Nur retention_days und optional FULL{n} nötig"
        }
    ]
    
    for benefit in benefits:
        print(f"\n🎯 {benefit['title']}:")
        print(f"   {benefit['description']}")
        print(f"   Beispiel: {benefit['example']}")


async def example_usage_with_new_features():
    """Beispiele für die Verwendung der neuen Features."""
    
    print("\n🚀 Verwendung der neuen Features:")
    print("=" * 45)
    
    print("\n1. 📋 Backup-Strategie für Resource ermitteln:")
    print("```python")
    print("strategy = retention_manager.get_backup_strategy_for_resource(")
    print("    resource_id='db-prod-001',")
    print("    schedule_tag='BACKUP-DAILY-0300-RETAIN90-FULL7'")
    print(")")
    print("print(f'Empfohlen: {strategy[\"backup_type_recommended\"]}')") 
    print("print(f'Begründung: {strategy[\"reasoning\"]}')") 
    print("```")
    
    print("\n2. 🔍 Full Backup Intervall aus Tag extrahieren:")
    print("```python")
    print("interval = retention_manager.extract_full_backup_interval_from_tag(")
    print("    'BACKUP-DAILY-0300-RETAIN90-FULL7'")
    print(")")
    print("print(f'Full Backup alle {interval} Tage')")
    print("```")
    
    print("\n3. ✅ Prüfen ob neues Full Backup nötig:")
    print("```python")
    print("should_create = retention_manager.should_create_new_full_backup(")
    print("    resource_id='db-prod-001',")
    print("    schedule_tag='BACKUP-DAILY-0300-RETAIN90-FULL7'")
    print(")")
    print("if should_create:")
    print("    print('Neues Full Backup erstellen')")
    print("else:")
    print("    print('Incremental Backup ausreichend')")
    print("```")


if __name__ == "__main__":
    print("🔧 OpenStack Backup Automation - Aktualisierte Retention Features")
    print("=" * 75)
    
    example_updated_tag_formats()
    print("\n" + "=" * 75)
    
    example_full_backup_strategies()
    print("\n" + "=" * 75)
    
    example_simplified_config()
    print("\n" + "=" * 75)
    
    example_backup_decision_logic()
    print("\n" + "=" * 75)
    
    example_retention_benefits()
    print("\n" + "=" * 75)
    
    asyncio.run(example_usage_with_new_features())
    
    print("\n" + "=" * 75)
    print("✅ Alle aktualisierten Beispiele abgeschlossen!")
    print("\nNeue Features:")
    print("- ❌ min_backups_to_keep entfernt (vereinfacht)")
    print("- ➕ FULL{n} Parameter für Full Backup Intervalle")
    print("- 🤖 Intelligente Backup-Typ-Entscheidung")
    print("- 🔄 Automatische Chain-Integrität")