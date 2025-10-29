# Requirements Document

## Introduction

Eine automatisierte Backup-Lösung für OpenStack, die basierend auf Tags an Instanzen und Volumes zeitgesteuerte Snapshots und Backups erstellt. Das System unterstützt sowohl einfache Snapshots als auch erweiterte Backup-Strategien mit Full- und Incremental-Backups, einschließlich konfigurierbarer Retention-Policies.

## Glossary

- **OpenStack_Backup_System**: Das zu entwickelnde automatisierte Backup-System
- **Instance**: Eine virtuelle Maschine in OpenStack (Nova)
- **Volume**: Ein Block-Storage-Volume in OpenStack (Cinder)
- **Snapshot**: Ein Point-in-Time-Abbild einer Instanz oder eines Volumes
- **Full_Backup**: Ein vollständiges Backup aller Daten
- **Incremental_Backup**: Ein Backup nur der seit dem letzten Backup geänderten Daten
- **Tag**: Ein Metadaten-Label an OpenStack-Ressourcen
- **Retention_Policy**: Regel zur automatischen Bereinigung alter Backups
- **Application_Credential**: OpenStack-Authentifizierungsmethode mit begrenzten Rechten
- **Schedule_Tag**: Ein speziell formatierter Tag zur Definition von Backup-Zeitplänen

## Requirements

### Requirement 1

**User Story:** Als OpenStack-Administrator möchte ich Instanzen und Volumes mit Tags markieren können, damit automatische Backups basierend auf diesen Tags erstellt werden.

#### Acceptance Criteria

1. WHEN eine Instance oder ein Volume einen Schedule_Tag erhält, THE OpenStack_Backup_System SHALL die Ressource für automatische Backups registrieren
2. THE OpenStack_Backup_System SHALL Schedule_Tags im Format "SNAPSHOT-{FREQUENCY}-{TIME}" und "BACKUP-{FREQUENCY}-{TIME}" erkennen
3. THE OpenStack_Backup_System SHALL DAILY, WEEKLY, MONTHLY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY als gültige Frequency-Werte akzeptieren
4. THE OpenStack_Backup_System SHALL Zeitangaben im Format HHMM (24-Stunden-Format) verarbeiten
5. THE OpenStack_Backup_System SHALL ungültige Tag-Formate protokollieren und ignorieren

### Requirement 2

**User Story:** Als OpenStack-Administrator möchte ich Snapshots mit flexiblen Zeitplänen erstellen lassen, damit ich regelmäßige Point-in-Time-Wiederherstellungspunkte habe.

#### Acceptance Criteria

1. WHEN eine Ressource einen Tag "SNAPSHOT-{FREQUENCY}-{TIME}" trägt, THE OpenStack_Backup_System SHALL entsprechend dem Zeitplan einen Snapshot erstellen
2. THE OpenStack_Backup_System SHALL DAILY, WEEKLY, MONTHLY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY als gültige Frequency-Werte für Snapshots akzeptieren
3. THE OpenStack_Backup_System SHALL Snapshots für Nova-Instanzen über die OpenStack-API erstellen
4. THE OpenStack_Backup_System SHALL Snapshots für Cinder-Volumes über die OpenStack-API erstellen
5. THE OpenStack_Backup_System SHALL jeden Snapshot mit Zeitstempel und Quell-Ressource benennen
6. IF ein Snapshot-Vorgang fehlschlägt, THEN THE OpenStack_Backup_System SHALL den Fehler protokollieren und beim nächsten Zeitpunkt erneut versuchen

### Requirement 3

**User Story:** Als OpenStack-Administrator möchte ich Backups mit flexiblen Zeitplänen erstellen lassen, damit ich umfassende Backup-Strategien implementieren kann.

#### Acceptance Criteria

1. WHEN eine Ressource einen Tag "BACKUP-{FREQUENCY}-{TIME}" trägt, THE OpenStack_Backup_System SHALL entsprechend dem Zeitplan ein Backup erstellen
2. THE OpenStack_Backup_System SHALL DAILY, WEEKLY, MONTHLY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY als gültige Frequency-Werte für Backups akzeptieren
3. THE OpenStack_Backup_System SHALL für das erste Backup einer Ressource immer ein Full_Backup erstellen
4. THE OpenStack_Backup_System SHALL die Backup-Historie jeder Ressource verfolgen
5. THE OpenStack_Backup_System SHALL Backup-Metadaten mit Typ (Full/Incremental), Zeitstempel und Quell-Ressource speichern

### Requirement 4

**User Story:** Als OpenStack-Administrator möchte ich Full- und Incremental-Backup-Strategien konfigurieren können, damit ich Speicherplatz effizient nutzen kann.

#### Acceptance Criteria

1. WHEN eine Ressource den Tag "BACKUP-DAILY-{TIME}" trägt, THE OpenStack_Backup_System SHALL eine Full- und Incremental-Backup-Strategie anwenden
2. THE OpenStack_Backup_System SHALL alle 7 Tage ein Full_Backup erstellen (konfigurierbar)
3. THE OpenStack_Backup_System SHALL zwischen Full_Backups täglich Incremental_Backups erstellen
4. THE OpenStack_Backup_System SHALL die Anzahl der Tage zwischen Full_Backups als Konfigurationsparameter akzeptieren
5. THE OpenStack_Backup_System SHALL Incremental_Backups auf das letzte Full_Backup oder das letzte Incremental_Backup basieren

### Requirement 5

**User Story:** Als OpenStack-Administrator möchte ich Retention-Policies definieren können, damit alte Backups automatisch bereinigt werden und Speicherplatz freigesetzt wird.

#### Acceptance Criteria

1. THE OpenStack_Backup_System SHALL Retention-Policies über Konfigurationsdateien oder zusätzliche Tags akzeptieren
2. WHEN ein Backup älter als die definierte Retention-Zeit ist, THE OpenStack_Backup_System SHALL das Backup automatisch löschen
3. THE OpenStack_Backup_System SHALL täglich eine Bereinigungsroutine ausführen
4. THE OpenStack_Backup_System SHALL vor der Löschung von Backups eine Bestätigung in den Logs ausgeben
5. WHEN ein Full_Backup gelöscht werden soll, THE OpenStack_Backup_System SHALL zuerst alle abhängigen Incremental_Backups löschen
6. THE OpenStack_Backup_System SHALL Full_Backups nur löschen, wenn keine Incremental_Backups mehr davon abhängen
7. THE OpenStack_Backup_System SHALL niemals das letzte verfügbare Full_Backup einer Ressource löschen, außer alle abhängigen Incremental_Backups sind bereits gelöscht

### Requirement 6

**User Story:** Als OpenStack-Administrator möchte ich das System mit Application Credentials oder Username/Password authentifizieren können, damit ich flexible und sichere Zugriffsmöglichkeiten habe.

#### Acceptance Criteria

1. THE OpenStack_Backup_System SHALL Application_Credentials als primäre Authentifizierungsmethode unterstützen
2. THE OpenStack_Backup_System SHALL Username/Password-Authentifizierung als Alternative unterstützen
3. THE OpenStack_Backup_System SHALL Authentifizierungsdaten sicher in Konfigurationsdateien oder Umgebungsvariablen speichern
4. THE OpenStack_Backup_System SHALL bei Authentifizierungsfehlern aussagekräftige Fehlermeldungen ausgeben
5. THE OpenStack_Backup_System SHALL die OpenStack-Verbindung bei Bedarf automatisch erneuern

### Requirement 7

**User Story:** Als Entwickler möchte ich eine modulare und gut dokumentierte Lösung haben, damit ich sie öffentlich bereitstellen und andere sie verstehen und erweitern können.

#### Acceptance Criteria

1. THE OpenStack_Backup_System SHALL eine klare Modulstruktur mit getrennten Verantwortlichkeiten haben
2. THE OpenStack_Backup_System SHALL umfassende Dokumentation mit Installationsanweisungen enthalten
3. THE OpenStack_Backup_System SHALL Konfigurationsbeispiele und Use-Case-Dokumentation bereitstellen
4. THE OpenStack_Backup_System SHALL aussagekräftige Logging-Ausgaben für Debugging und Monitoring erzeugen
5. THE OpenStack_Backup_System SHALL über eine standardisierte Konfigurationsdatei (YAML/JSON) konfigurierbar sein

### Requirement 8

**User Story:** Als OpenStack-Administrator möchte ich bei Fehlern sofort per E-Mail benachrichtigt werden, damit ich schnell auf Probleme reagieren kann.

#### Acceptance Criteria

1. THE OpenStack_Backup_System SHALL nach jedem Backup- oder Snapshot-Vorgang den Erfolg verifizieren
2. THE OpenStack_Backup_System SHALL bei fehlgeschlagenen Backup- oder Snapshot-Vorgängen eine E-Mail-Benachrichtigung senden
3. THE OpenStack_Backup_System SHALL bei Authentifizierungsfehlern eine E-Mail-Benachrichtigung senden
4. THE OpenStack_Backup_System SHALL bei kritischen Systemfehlern eine E-Mail-Benachrichtigung senden
5. THE OpenStack_Backup_System SHALL die E-Mail-Adresse für Benachrichtigungen als Konfigurationsparameter akzeptieren
6. THE OpenStack_Backup_System SHALL das lokale Mail-System (sendmail/postfix) für E-Mail-Versand verwenden
7. THE OpenStack_Backup_System SHALL in E-Mail-Benachrichtigungen Details zum Fehler, betroffene Ressource und Zeitstempel enthalten

### Requirement 9

**User Story:** Als OpenStack-Administrator möchte ich mehrere Backup- und Snapshot-Operationen parallel ausführen lassen, damit die Gesamtlaufzeit bei vielen Ressourcen reduziert wird.

#### Acceptance Criteria

1. THE OpenStack_Backup_System SHALL mehrere Backup- und Snapshot-Operationen gleichzeitig ausführen können
2. THE OpenStack_Backup_System SHALL die Anzahl paralleler Operationen als Konfigurationsparameter akzeptieren
3. THE OpenStack_Backup_System SHALL Snapshots mit höherer Priorität als Backups behandeln
4. THE OpenStack_Backup_System SHALL Timeouts für einzelne Operationen konfigurierbar machen
5. THE OpenStack_Backup_System SHALL bei parallelen Operationen die OpenStack-API-Limits respektieren
6. THE OpenStack_Backup_System SHALL fehlgeschlagene parallele Operationen individuell behandeln ohne andere zu beeinträchtigen

### Requirement 10

**User Story:** Als OpenStack-Administrator möchte ich das Backup-System als Service oder Cron-Job betreiben können, damit es kontinuierlich und zuverlässig läuft.

#### Acceptance Criteria

1. THE OpenStack_Backup_System SHALL als Daemon-Prozess ausführbar sein
2. THE OpenStack_Backup_System SHALL mit systemd-Service-Dateien ausgeliefert werden
3. THE OpenStack_Backup_System SHALL alternativ als Cron-Job konfigurierbar sein
4. THE OpenStack_Backup_System SHALL Gesundheitschecks und Status-Endpoints bereitstellen
5. THE OpenStack_Backup_System SHALL regelmäßige Status-Reports per E-Mail senden können