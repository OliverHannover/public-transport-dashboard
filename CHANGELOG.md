# Changelog

## 1.0.1 — 2026-09-14

### Korrigiert

- IoT-Klasse auf calculated gesetzt, passend zur ausschließlich berechneten HA-Hilfs-Entity.
- Verkehrsmittelfamilie in den Dublettenschlüssel aufgenommen: gleiche Liniennummern von Bus und Tram werden nicht mehr verschmolzen.
- Fehlende Planzeit wird bei bekannter Verspätung aus der tatsächlichen Abfahrtszeit rekonstruiert; verschiedene Echtzeitmeldungen derselben Planfahrt bleiben eine Zeile.
- Reine Datumsangaben, fehlerhafte Quellcontainer und übergroße skalare Werte werden sicher verworfen.
- Sensorname und Auswahl der Verspätungseinheit werden übersetzt; Entity-ID und Unique-ID-Schema bleiben erhalten.
- Echte Repository-, Dokumentations-, Issue- und Codeowner-Metadaten sowie lokale Brand-Grafik ergänzt.
- ZIP-Dateiname wird aus der Manifest-Version abgeleitet.

### Optimiert

- Normalisierung und Sortierung nur bei geänderten Quelllisten oder HA-Zeitzone.
- Minutentakt verwendet den vorbereiteten Datenbestand und aktualisiert nur Zeitfenster/Countdown.
- Unveränderte Sensorzustände werden nicht erneut geschrieben.
- Doppelte Zeitstempelanalysen und Kopien großer Herkunftslisten reduziert.
- Debug-Logging auf Änderungen des Quellenzustands begrenzt.

### Qualitätssicherung

- Regressionstests für Echtzeit-Dubletten, Verkehrsmittel, mehrere Stationen, ungültige Daten, Quellenfehler, Cache und Countdown ergänzt.
- Belastungsfall mit 1.000 Quellzeilen ergänzt.
- HA-Lebenszyklus-Tests sowie HACS- und hassfest-Validierung in CI aufgenommen.
- Architektur, Datenfluss, Identitätsgrenzen und Erweiterbarkeit dokumentiert.

Die gespeicherte Konfiguration bleibt kompatibel mit 1.0.0. Kein Coordinator, kein künstliches Gerät und keine neue Laufzeitabhängigkeit.

## 1.0.0 — 2026-09-14

- Erste lokale Integration mit Config Flow, Options Flow und gemeinsamem Abfahrtssensor.
- Betreiber-Dublettenbereinigung, chronologische Sortierung, Countdown und Quellenstatus.
- Dunkle responsive Flex-Table-Karte und Installationsanleitung.
