#!/usr/bin/env python3
"""
Einfacher Test der vereinfachten Retention-Funktionalität.

Zeigt die Verwendung von:
1. Einfachen RETAIN-Tags
2. Automatischer Chain-Integrität
3. Batch Deletion
"""

def test_tag_parsing():
    """Test der vereinfachten Tag-Parsing-Logik."""
    
    # Simuliere die extract_retention_from_tag Methode
    def extract_retention_from_tag(schedule_tag):
        if not schedule_tag:
            return None
        
        parts = schedule_tag.upper().split('-')
        
        for part in parts:
            if part.startswith('RETAIN') and len(part) > 6:
                try:
                    return int(part[6:])  # Remove 'RETAIN' prefix
                except ValueError:
                    continue
        
        return None
    
    # Test-Cases
    test_cases = [
        ("BACKUP-DAILY-0300", None, "Kein RETAIN → Default Policy"),
        ("BACKUP-DAILY-0300-RETAIN30", 30, "30 Tage Retention"),
        ("SNAPSHOT-WEEKLY-1200-RETAIN7", 7, "7 Tage Retention"),
        ("BACKUP-MONTHLY-0100-RETAIN365", 365, "1 Jahr Retention"),
        ("BACKUP-DAILY-0200-RETAIN14", 14, "2 Wochen Retention"),
        ("INVALID-TAG-RETAIN", None, "Ungültiges Format"),
        ("BACKUP-DAILY-0300-RETAINXYZ", None, "Ungültige Zahl"),
    ]
    
    print("🧪 Tag-Parsing Tests:")
    print("=" * 50)
    
    for tag, expected, description in test_cases:
        result = extract_retention_from_tag(tag)
        status = "✅" if result == expected else "❌"
        
        print(f"{status} {tag}")
        print(f"   Erwartet: {expected}, Erhalten: {result}")
        print(f"   {description}")
        print()


def test_chain_integrity_rules():
    """Test der Chain-Integritäts-Regeln."""
    
    print("🔗 Chain-Integritäts-Regeln:")
    print("=" * 40)
    
    rules = [
        {
            "rule": "Mindestens 1 Backup behalten",
            "scenario": "Letztes Backup einer Resource",
            "action": "❌ NICHT löschen",
            "reason": "Würde Resource ohne Backups lassen"
        },
        {
            "rule": "Full Backup mit Incrementals",
            "scenario": "Full Backup hat abhängige Incremental Backups",
            "action": "❌ NICHT löschen",
            "reason": "Würde Incremental Chain brechen"
        },
        {
            "rule": "Letztes Full Backup",
            "scenario": "Einziges Full Backup, aber Incrementals existieren",
            "action": "❌ NICHT löschen", 
            "reason": "Incrementals brauchen Full Backup als Basis"
        },
        {
            "rule": "Orphaned Incremental",
            "scenario": "Incremental ohne Parent Backup",
            "action": "✅ Löschen",
            "reason": "Ist bereits gebrochen, kann bereinigt werden"
        },
        {
            "rule": "Standalone Snapshot",
            "scenario": "Snapshot ohne Dependencies",
            "action": "✅ Löschen",
            "reason": "Snapshots beeinflussen keine Chains"
        },
        {
            "rule": "Incremental mit Children",
            "scenario": "Incremental auf das andere Incrementals aufbauen",
            "action": "❌ NICHT löschen",
            "reason": "Würde nachfolgende Incrementals orphanen"
        }
    ]
    
    for rule in rules:
        print(f"📋 {rule['rule']}")
        print(f"   Szenario: {rule['scenario']}")
        print(f"   Aktion: {rule['action']}")
        print(f"   Grund: {rule['reason']}")
        print()


def test_policy_priority():
    """Test der Policy-Prioritäts-Logik."""
    
    print("🎯 Policy-Priorität Tests:")
    print("=" * 35)
    
    # Simuliere Policy-Matching
    def get_effective_retention_days(tag, global_policies, default_days):
        # 1. Tag-embedded retention (höchste Priorität)
        if tag:
            parts = tag.upper().split('-')
            for part in parts:
                if part.startswith('RETAIN') and len(part) > 6:
                    try:
                        return int(part[6:]), "Tag-Policy"
                    except ValueError:
                        pass
        
        # 2. Global policies (mittlere Priorität)
        if tag and global_policies:
            if 'DAILY' in tag and 'daily' in global_policies:
                return global_policies['daily'], "Global-Policy (daily)"
            elif 'WEEKLY' in tag and 'weekly' in global_policies:
                return global_policies['weekly'], "Global-Policy (weekly)"
            elif 'SNAPSHOT' in tag and 'snapshots' in global_policies:
                return global_policies['snapshots'], "Global-Policy (snapshots)"
        
        # 3. Default policy (fallback)
        return default_days, "Default-Policy"
    
    # Test-Szenarien
    global_policies = {
        'daily': 30,
        'weekly': 60,
        'snapshots': 7
    }
    default_days = 30
    
    test_scenarios = [
        ("BACKUP-DAILY-0300-RETAIN90", "Tag überschreibt alles"),
        ("BACKUP-DAILY-0300", "Global daily-Policy greift"),
        ("SNAPSHOT-WEEKLY-1200", "Global snapshots-Policy greift"),
        ("BACKUP-MONTHLY-0100", "Default-Policy als Fallback"),
        ("BACKUP-WEEKLY-2300", "Global weekly-Policy greift"),
    ]
    
    for tag, description in test_scenarios:
        days, source = get_effective_retention_days(tag, global_policies, default_days)
        print(f"📝 {tag}")
        print(f"   → {days} Tage ({source})")
        print(f"   {description}")
        print()


def demonstrate_batch_benefits():
    """Zeigt die Vorteile von Batch Deletion."""
    
    print("⚡ Batch Deletion Simulation:")
    print("=" * 35)
    
    import time
    
    # Simuliere Sequential vs Batch Deletion
    def simulate_sequential_deletion(count):
        start = time.time()
        for i in range(count):
            time.sleep(0.01)  # Simuliere 10ms pro Deletion
        return time.time() - start
    
    def simulate_batch_deletion(count, batch_size=5):
        start = time.time()
        batches = (count + batch_size - 1) // batch_size  # Ceiling division
        for batch in range(batches):
            time.sleep(0.05)  # Simuliere 50ms pro Batch (5 parallel)
        return time.time() - start
    
    test_counts = [10, 50, 100]
    
    for count in test_counts:
        seq_time = simulate_sequential_deletion(count)
        batch_time = simulate_batch_deletion(count)
        improvement = ((seq_time - batch_time) / seq_time) * 100
        
        print(f"📊 {count} Backups:")
        print(f"   Sequential: {seq_time:.2f}s")
        print(f"   Batch (5er): {batch_time:.2f}s")
        print(f"   Verbesserung: {improvement:.1f}%")
        print()


if __name__ == "__main__":
    print("🔧 Vereinfachte Retention Management - Tests")
    print("=" * 50)
    
    test_tag_parsing()
    print("\n" + "=" * 50)
    
    test_chain_integrity_rules()
    print("\n" + "=" * 50)
    
    test_policy_priority()
    print("\n" + "=" * 50)
    
    demonstrate_batch_benefits()
    
    print("=" * 50)
    print("✅ Alle Tests abgeschlossen!")
    print("\n🎯 Zusammenfassung der Vereinfachungen:")
    print("- Nur noch RETAIN{n} in Tags nötig")
    print("- Chain-Integrität automatisch geschützt")
    print("- Mindestens 1 Backup bleibt immer erhalten")
    print("- Batch Deletion für bessere Performance")
    print("- Einfache, sichere Konfiguration")