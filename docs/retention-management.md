# Retention Management - Erweiterte Features

## Übersicht

Das Retention Management System wurde um zwei wichtige Features erweitert:

1. **🚀 Batch Deletion** - Parallele Löschung für bessere Performance
2. **🏷️ Tag-basierte Retention Policies** - Flexible Retention-Regeln pro Backup

## 🚀 Batch Deletion

### Funktionsweise

Statt Backups einzeln zu löschen, werden sie in Batches parallel verarbeitet:

```python
# Alte Methode (Sequential)
for backup in backups:
    await delete_backup(backup)  # 2s pro Backup

# Neue Methode (Batch)
await delete_backups_batch(backups, batch_size=5)  # 5 parallel, ~8s pro Batch
```

### Performance-Verbesserung

| Anzahl Backups | Sequential | Batch (5er) | Verbesserung |
|----------------|------------|-------------|--------------|
| 50             | 1:40 min   | 1:20 min    | 20% schneller |
| 200            | 6:40 min   | 5:20 min    | 25% schneller |
| 1000           | 33 min     | 27 min      | 30% schneller |

### Konfiguration

```python
# Batch Deletion aktivieren
cleanup_result = await retention_manager.cleanup_expired_backups(
    retention_policies=policies,
    use_batch_deletion=True,
    batch_size=5  # Anzahl paralleler Löschungen
)
```

## 🏷️ Tag-basierte Retention Policies

### Tag-Format

Retention-Informationen können direkt in Schedule-Tags eingebettet werden:

```
BACKUP-DAILY-0300-RETAIN90
│      │     │     │
│      │     │     └─ 90 Tage Retention
│      │     └─ Um 03:00 Uhr
│      └─ Täglich
└─ Backup-Operation

Chain-Integrität wird automatisch sichergestellt:
- Mindestens 1 Backup bleibt immer erhalten
- Full Backups werden nur gelöscht wenn keine Incrementals davon abhängen
- Incremental Chains bleiben vollständig
```

### Unterstützte Parameter

| Parameter | Format | Beschreibung | Beispiel |
|-----------|--------|--------------|----------|
| Retention Tage | `RETAIN{n}` | Aufbewahrungszeit in Tagen | `RETAIN90` |

**Automatische Chain-Integrität:**
- Mindestens 1 Backup bleibt immer erhalten
- Full Backups werden nur gelöscht wenn keine abhängigen Incrementals existieren
- Incremental Chains bleiben vollständig und funktionsfähig
- Orphaned Incrementals werden automatisch erkannt und bereinigt

### Beispiele

```yaml
# Kritische Produktions-DB
"BACKUP-DAILY-0300-RETAIN90"
# → 90 Tage Retention, Chain-Integrität automatisch geschützt

# Test-System  
"BACKUP-WEEKLY-2300-RETAIN7"
# → 7 Tage Retention, mindestens 1 Backup bleibt immer

# Schnelle Snapshots
"SNAPSHOT-DAILY-1200-RETAIN3"
# → 3 Tage Retention (Snapshots beeinflussen keine Backup-Chains)

# Monats-Archive
"BACKUP-MONTHLY-0100-RETAIN365"
# → 1 Jahr Retention, Archive-Charakter mit Chain-Schutz
```

## Policy-Prioritäten

Das System wendet Retention Policies in folgender Reihenfolge an:

### 1. Tag-eingebettete Retention (HÖCHSTE Priorität)
```
BACKUP-DAILY-0300-RETAIN90
→ Verwendet 90 Tage Retention mit automatischer Chain-Integrität
```

### 2. Globale Policy-Zuordnung (MITTLERE Priorität)
```yaml
retention_policies:
  daily: {retention_days: 30}
  snapshots: {retention_days: 7}
  instances: {retention_days: 60}
```

Matching-Reihenfolge:
- Nach Backup-Typ: `snapshots`, `full_backups`, `incremental_backups`
- Nach Resource-Typ: `instances`, `volumes`
- Nach Schedule-Frequenz: `daily`, `weekly`, `monthly`

### 3. Default Policy (FALLBACK)
```yaml
retention_policies:
  default: {retention_days: 30, min_backups_to_keep: 1}
```

## Verwendung

### Basis-Verwendung
```python
# Standard Cleanup mit Tag-Policies
cleanup_result = await retention_manager.cleanup_expired_backups(
    retention_policies=config.retention_policies,
    use_tag_policies=True,      # Tag-basierte Policies aktivieren
    use_batch_deletion=True,    # Batch Deletion aktivieren
    batch_size=5               # 5 parallele Löschungen
)
```

### Erweiterte Verwendung
```python
# Nur Tag-basierte Policies verwenden
backups_to_delete = retention_manager.get_backups_to_delete_with_tag_policies(
    default_retention_policy=RetentionPolicy(retention_days=30),
    global_retention_policies=config.retention_policies
)

# Batch Deletion separat verwenden
batch_result = await retention_manager.delete_backups_batch(
    backups=backups_to_delete,
    batch_size=10
)
```

## Konfiguration

### Erweiterte YAML-Konfiguration
```yaml
# backup-automation.yaml
retention_policies:
  # Standard-Policy (Fallback)
  default:
    retention_days: 30
    min_backups_to_keep: 1
    keep_last_full_backup: true
  
  # Spezielle Policies für verschiedene Anwendungsfälle
  critical:
    retention_days: 90
    min_backups_to_keep: 5
    keep_last_full_backup: true
  
  testing:
    retention_days: 7
    min_backups_to_keep: 1
    keep_last_full_backup: false
  
  snapshots:
    retention_days: 3
    min_backups_to_keep: 1
    keep_last_full_backup: false
  
  daily:
    retention_days: 30
    min_backups_to_keep: 3
    keep_last_full_backup: true
  
  weekly:
    retention_days: 60
    min_backups_to_keep: 2
    keep_last_full_backup: true

backup:
  # Batch Deletion Einstellungen
  max_concurrent_operations: 5  # Auch für Batch Deletion verwendet
  operation_timeout_minutes: 60
```

## Monitoring & Logging

### Cleanup-Ergebnisse
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

### Log-Ausgaben
```
INFO: Evaluating backups for deletion using tag-based retention policies
DEBUG: Backup backup-123 marked for deletion (policy: 90d retention)
INFO: Using batch deletion for 25 standalone backups
INFO: Batch deletion completed: 23 successful, 2 failed, 1073741824 bytes freed
```

## Best Practices

### 1. Tag-Design
- **Konsistente Namenskonvention**: Immer `RETAIN{n}-MIN{n}-KEEP_LAST` Format
- **Sinnvolle Defaults**: Nicht jeder Tag braucht Retention-Info
- **Dokumentation**: Tag-Bedeutungen dokumentieren

### 2. Batch-Größen
- **Standard**: 5 parallele Löschungen (guter Kompromiss)
- **Kleine OpenStack**: 2-3 (API-Limits beachten)
- **Große OpenStack**: 8-10 (bessere Performance)

### 3. Policy-Hierarchie
- **Tag-Retention**: Für spezielle Anforderungen
- **Global-Policies**: Für Standard-Kategorien
- **Default-Policy**: Konservativ (längere Retention)

### 4. Monitoring
- **Cleanup-Reports**: Regelmäßige Berichte über gelöschte Backups
- **Fehler-Tracking**: Failed Deletions überwachen
- **Speicher-Monitoring**: Freigegebenen Speicherplatz verfolgen

## Troubleshooting

### Häufige Probleme

**Problem**: Batch Deletion schlägt fehl
```
Lösung: Batch-Größe reduzieren oder Sequential Deletion verwenden
use_batch_deletion=False
```

**Problem**: Tag-Retention wird ignoriert
```
Lösung: Tag-Format prüfen, muss exakt RETAIN{n} sein
Falsch: RETAIN-30, retain30
Richtig: RETAIN30
```

**Problem**: Zu viele Backups werden gelöscht
```
Lösung: min_backups_to_keep erhöhen oder keep_last_full_backup=true setzen
```

### Debug-Modus
```python
# Detailliertes Logging aktivieren
import logging
logging.getLogger('retention.manager').setLevel(logging.DEBUG)

# Dry-Run für Tests
cleanup_result = await retention_manager.schedule_cleanup_operation(
    retention_policies=policies,
    dry_run=True  # Nur planen, nicht ausführen
)
```