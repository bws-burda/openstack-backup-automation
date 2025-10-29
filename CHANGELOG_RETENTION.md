# Retention Management - Changelog

## 🚀 Neue Features (v2.0)

### ❌ Entfernt: `min_backups_to_keep`
- **Grund**: Vereinfachung der Konfiguration
- **Ersetzt durch**: Automatische Chain-Integrität
- **Verhalten**: System behält automatisch mindestens 1 Backup und schützt Backup-Chains

### ➕ Neu: Full Backup Intervall in Tags
- **Format**: `FULL{n}` - z.B. `FULL7` für alle 7 Tage
- **Beispiel**: `BACKUP-DAILY-0300-RETAIN90-FULL7`
- **Nutzen**: Individuelle Full Backup Strategien pro Resource

### 🤖 Neu: Intelligente Backup-Typ-Entscheidung
- **Methode**: `should_create_new_full_backup()`
- **Methode**: `get_backup_strategy_for_resource()`
- **Logik**: Automatische Entscheidung zwischen Full und Incremental Backup

## 📋 Geänderte Tag-Formate

### Vorher (v1.0):
```
BACKUP-DAILY-0300-RETAIN90-MIN5-KEEP_LAST
BACKUP-WEEKLY-2300-RETAIN7-MIN1
SNAPSHOT-DAILY-1200-RETAIN3-NO_KEEP_LAST
```

### Nachher (v2.0):
```
BACKUP-DAILY-0300-RETAIN90-FULL7
BACKUP-WEEKLY-2300-RETAIN7
SNAPSHOT-DAILY-1200-RETAIN3
```

## 🔧 Geänderte Konfiguration

### Vorher (v1.0):
```yaml
retention_policies:
  default:
    retention_days: 30
    min_backups_to_keep: 1
    keep_last_full_backup: true
```

### Nachher (v2.0):
```yaml
retention_policies:
  default:
    retention_days: 30
    keep_last_full_backup: true  # min_backups_to_keep entfernt
```

## 🆕 Neue Methoden

### RetentionManager
```python
# Full Backup Intervall aus Tag extrahieren
extract_full_backup_interval_from_tag(schedule_tag: str) -> Optional[int]

# Prüfen ob neues Full Backup nötig
should_create_new_full_backup(resource_id: str, schedule_tag: str) -> bool

# Backup-Strategie für Resource ermitteln
get_backup_strategy_for_resource(resource_id: str, schedule_tag: str) -> Dict[str, any]

# Erweiterte Tag-Info-Extraktion
extract_retention_from_tag(schedule_tag: str) -> Optional[Dict[str, any]]
```

## 📊 Beispiele

### 1. Kritische Datenbank
```
Tag: BACKUP-DAILY-0300-RETAIN90-FULL7
→ Tägliche Backups, 90 Tage behalten, neues Full Backup alle 7 Tage
```

### 2. Development Environment
```
Tag: BACKUP-DAILY-0200-RETAIN14-FULL3
→ Tägliche Backups, 14 Tage behalten, neues Full Backup alle 3 Tage
```

### 3. Archive System
```
Tag: BACKUP-MONTHLY-0100-RETAIN365-FULL30
→ Monatliche Backups, 1 Jahr behalten, neues Full Backup alle 30 Tage
```

## 🔄 Migration von v1.0 zu v2.0

### Automatische Migration
- Bestehende Tags ohne `FULL{n}` verwenden Standard-Intervall (7 Tage)
- `min_backups_to_keep` wird ignoriert (System behält automatisch mindestens 1 Backup)
- `KEEP_LAST`/`NO_KEEP_LAST` werden ignoriert (System schützt automatisch Chain-Integrität)

### Empfohlene Schritte
1. **Tags aktualisieren**: Füge `FULL{n}` Parameter hinzu wo gewünscht
2. **Konfiguration vereinfachen**: Entferne `min_backups_to_keep` aus retention_policies
3. **Testen**: Verwende neue Methoden für Backup-Strategie-Entscheidungen

## ✅ Vorteile

### Einfachheit
- Weniger Parameter in Konfiguration
- Klarere Tag-Struktur
- Automatische Chain-Integrität

### Flexibilität
- Individuelle Full Backup Intervalle pro Resource
- Intelligente Backup-Typ-Entscheidung
- Tag-basierte Konfiguration

### Robustheit
- Automatischer Schutz vor Chain-Brüchen
- Garantiert mindestens 1 Backup pro Resource
- Bessere Fehlerbehandlung

## 🧪 Tests

Neue Test-Szenarien:
- Full Backup Intervall-Extraktion aus Tags
- Backup-Strategie-Entscheidungslogik
- Chain-Integrität ohne min_backups_to_keep
- Tag-basierte Retention Policy-Erstellung

## 📚 Dokumentation

Aktualisierte Dateien:
- `docs/retention-management.md`
- `examples/updated_retention_examples.py`
- `CHANGELOG_RETENTION.md` (diese Datei)

## 🔮 Zukunft

Mögliche Erweiterungen:
- Weitere Tag-Parameter (z.B. `COMPRESS`, `ENCRYPT`)
- Dynamische Full Backup Intervalle basierend auf Änderungsrate
- Integration mit Monitoring-Systemen für optimale Backup-Zeitpunkte