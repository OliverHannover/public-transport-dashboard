# Public Transport Dashboard

Version **1.0.1**. Eine lokale Home-Assistant-Custom-Integration, die vorhandene Abfahrtssensoren zu einer bereinigten ÖPNV-Tafel zusammenführt. Kein AppDaemon, kein pyscript, keine Einträge in configuration.yaml.

**Ausgabe:** sensor.public_transport_dashboard  
**Zustand:** Anzahl der angezeigten Abfahrten  
**Daten:** Attribut departures

## Installation in fünf Schritten

1. ZIP entpacken. Den enthaltenen Ordner custom_components/public_transport_dashboard nach /config/custom_components/public_transport_dashboard auf Deinem Home-Assistant-System kopieren. manifest.json muss direkt in diesem Ordner liegen.
2. Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Public Transport Dashboard** öffnen.
4. Quellen auswählen, z. B. sensor.station_rail. Anschließend Haltestellengruppen und Verspätungseinheiten festlegen.
5. **Flex Table Card** installieren und den Inhalt von lovelace/departure-board.yaml als manuelle Dashboard-Karte einfügen.

Die Integration wird vollständig über ihren Config Flow eingerichtet. Die YAML-Datei ist ausschließlich die Lovelace-Kartenkonfiguration im Dashboard-Editor, keine Systemkonfiguration.

## Voraussetzungen und Lokalität

- Aktuelles Home Assistant; die verwendeten APIs setzen mindestens 2025.1 voraus. Ein Test über alle älteren Versionen wurde nicht durchgeführt.
- Bereits funktionierende Sensoren mit einer Liste im Attribut departures.
- Für die Darstellung: lokal installierte [Flex Table Card](https://github.com/custom-cards/flex-table-card).
- Keine weiteren Python-Abhängigkeiten, Konten, Tokens, API-Schlüssel oder Dienste für diese Integration.
- Die Integration liest ausschließlich die HA-Zustandsmaschine. Sie ruft keine Server auf.
- Fahrplandaten kommen weiterhin aus den vorhandenen Quellsensoren. Deren Datenanbieter benötigen gegebenenfalls Internet. Diese Lösung macht einen Online-Fahrplananbieter nicht offline verfügbar.
- HACS/Downloads benötigen zur Installation oder Aktualisierung Internet; der installierte Dashboard-Code nicht.

## Einrichtung und Optionen

Im ersten Dialog:

| Einstellung | Bedeutung | Standard |
|---|---|---|
| Quellsensoren | Mehrfachauswahl ohne künstliches Quellenlimit | keine |
| Maximale Abfahrten | 1–200 Einträge nach Bereinigung und Sortierung | 30 |
| Vorschau | Zeitraum ab jetzt, 1–1.440 Minuten | 180 |
| Quelle veraltet nach | Minuten ohne Zustandsmeldung, 0 deaktiviert die Prüfung | 15 |

Neue Quellen müssen beim Einrichten ein departures-Attribut vom Typ Liste haben. Eine leere Liste ist gültig. Bereits konfigurierte, vorübergehend ausgefallene Quellen können in den Optionen erhalten bleiben. Der erzeugte Dashboard-Sensor selbst wird als Quelle abgewiesen.

Im zweiten Dialog erscheinen je Quellsensor zwei Felder:

- **group:sensor.…:** frei wählbare Haltestellengruppe. Leer bedeutet: Diese Quelle bleibt eine eigene Haltestelle.
- **unit:sensor.…:** Einheit des gelieferten delay-Wertes: minutes oder seconds. Die Ausgabe ist immer in Minuten.

Beispiel:

| Quellsensor | Gruppe | Einheit |
|---|---|---|
| sensor.station_rail | North Station | minutes |
| sensor.station_alternative | North Station | minutes |
| sensor.station_bus | North Station | minutes |
| sensor.other_station | South Station | minutes |

Die zusätzlichen Sensor-IDs sind Beispiele. Wähle nur tatsächlich vorhandene Sensoren.

**Gruppiere nur dieselbe Haltestelle.** Ansonsten kann dieselbe Fahrt an verschiedenen Stationen fälschlich zu einer einzigen Abfahrt werden. Die Gruppe wird auch unter dem Ziel angezeigt; bei leerem Feld steht dort die Quell-Entity-ID.

Änderungen: **Einstellungen → Geräte & Dienste → Public Transport Dashboard → Konfigurieren/Optionen**. Nach dem Speichern wird der Eintrag neu geladen; ein HA-Neustart ist dafür nicht erforderlich.

Die zuerst gewählte Quelle hat Vorrang. Zur Änderung der Reihenfolge die Auswahl im Dialog entfernen und in der gewünschten Reihenfolge neu auswählen. Die gespeicherte Reihenfolge steht im Sensorattribut source_entities.

## Bereinigungsregeln

1. Alle nutzbaren Quellen werden in Auswahlreihenfolge gelesen.
2. Linie und Ziel müssen skalare, nicht leere Werte sein.
3. Datumswerte werden aus ISO-8601 gelesen und in UTC ausgegeben. Werte ohne Zeitzone werden als HA-Lokalzeit interpretiert. Bei der Zeitumstellung sind explizite UTC-Offsets nötig, um die doppelte Stunde eindeutig zu unterscheiden.
4. departure_time hat Vorrang. Fehlt der Wert, werden planned_time und die bekannte Verspätung verwendet. Ohne bekannte Verspätung gilt die Planzeit als Anzeigezeit; delay bleibt unbekannt.
5. Ist delay nicht numerisch, wird es nur aus tatsächlich vorhandener Abfahrtszeit und Planzeit berechnet. Ohne ausreichende Zeitdaten bleibt es null.
6. Dubletten werden anhand von **Haltestellengruppe + Verkehrsmittelfamilie + Linie + Ziel + Planzeit** erkannt. Groß-/Kleinschreibung und Linien-Leerzeichen werden normalisiert, Hauptbahnhof wird für den Zielvergleich zu Hbf.
7. agency und platform gehören nicht zum Schlüssel: Betreiber-Doppelmeldungen und Gleiswechsel erzeugen keine zusätzliche Fahrt.
8. Fehlt die Planzeit, wird sie bei bekannter Verspätung aus Abfahrtszeit minus Verspätung rekonstruiert. Nur ohne diese Information wird die exakte Abfahrtszeit als eigene Ersatzbasis verwendet.
9. Bei Konflikten gewinnt der **vollständige Datensatz der ersten Quelle**, innerhalb derselben Quelle die erste Zeile. Es werden keine widersprüchlichen Zeit-/Gleiswerte aus verschiedenen Meldungen vermischt. Betreiber und Herkunfts-Entities werden gesammelt.
10. Der bereinigte Bestand wird einmal chronologisch nach Abfahrtszeit sortiert. Bei jeder Anzeigeaktualisierung werden vergangene Fahrten entfernt, das Vorschaufenster angewendet und die Anzahl begrenzt.

Es gibt bewusst keine unscharfe „± fünf Minuten“-Deduplizierung: Damit würden im dichten Takt echte Fahrten verschwinden. Unterschiedliche Zielschreibweisen wie „Central Hbf“ und „Central Hauptbahnhof“ werden erkannt; völlig andere Zielbezeichnungen nicht. Ohne Fahrt-ID und konsistente Zeiten ist eine garantiert perfekte Dublettenerkennung nicht möglich.

Abfahrten verschwinden spätestens beim nächsten Minutentakt nach ihrer Abfahrtszeit. Der Countdown rundet verbleibende Teilminuten auf. Die Genauigkeit der Prognose hängt vom Quellsensor ab.

## Ausgabeformat

Beispiel einer bereinigten Zeile:

~~~yaml
departures:
  - line: R9
    destination: Central Hauptbahnhof
    destination_short: Central Hbf
    departure_time: "2026-09-14T10:07:00+00:00"
    planned_time: "2026-09-14T10:05:00+00:00"
    delay: 2
    platform: "2"
    transportation_type: suburban
    icon: mdi:train
    minutes_until_departure: 7
    countdown_minutes: 7
    agency: Operator A
    agencies:
      - Operator A
      - Operator B
    source_entities:
      - sensor.station_rail
    stop_group: North Station
    cancelled: false
~~~

| Attribut/Feld | Verhalten |
|---|---|
| minutes_until_departure | Numerischer Originalwert der gewählten Quellzeile; wird nicht heruntergezählt |
| countdown_minutes | Lokal aus departure_time berechnet; wird mindestens minütlich aktualisiert |
| delay | Minuten, auch negativ oder gebrochen; null bedeutet unbekannt |
| platform | Gleis/Bussteig als Text; null bei fehlender Angabe |
| transportation_type | Originale Verkehrsmittelbezeichnung, unknown bei fehlender Angabe |
| icon | Lokales MDI-Icon; bei unbekanntem Typ allgemeines ÖPNV-Icon |
| cancelled | true nur bei explizitem booleschem cancelled: true; Karte zeigt „Ausfall“ |
| source_issues | Sensorattribut mit Problemen je Quelle |
| active_sources | Zahl momentan verwendbarer Quellen |
| invalid_rows | Zahl unbrauchbarer Zeilen aus den aktuell verwendbaren Quellen |
| duplicates_removed | Entfernte Dubletten vor Zeit- und Mengenfilter |
| source_entities | Konfigurierte Prioritätsreihenfolge |

Bus, Tram/streetcar, U-Bahn/subway/metro, S-Bahn/suburban und mehrere Bahn-Typen sowie ferry besitzen Icons. Weitere Bezeichnungen fallen auf das allgemeine ÖPNV-Icon zurück. Unbekannte Zusatzfelder werden nicht unkontrolliert in den neuen Sensor kopiert.

## Aktualisierung und Ausfälle

- Jede Zustands-/Attributänderung einer Quelle aktualisiert die Tafel.
- Zusätzlich läuft ein lokaler Timer im Abstand von einer Minute.
- unavailable/unknown, fehlende Entities und ungültige departures-Attribute werden gemeldet und ausgeschlossen.
- Die Altersprüfung verwendet HA last_reported, also die letzte Zustandsmeldung, auch wenn sich deren Inhalt nicht verändert hat.
- Eine Quelle mit leerer Liste gilt als verfügbar. Der Dashboard-Zustand kann daher korrekt 0 sein.
- Bleiben gültige Quellen übrig, wird eine Teilansicht angezeigt.
- Sind alle Quellen unbrauchbar, wird der Sensor unavailable und departures wird geleert. Es werden keine alten Fahrten als aktuelle ausgegeben.
- Nach Neustart oder Neuladen werden Timer und Ereignis-Listener neu eingerichtet; beim Entladen werden sie entfernt.

Wenn ein Quellsensor absichtlich länger als 15 Minuten nichts meldet, die Altersgrenze passend erhöhen. 0 deaktiviert sie. Die Prüfung erkennt ausgebliebene HA-Meldungen; sie kann nicht erkennen, ob ein Anbieter immer wieder alte Fahrplandaten als neu liefert.

Die umfangreiche departures-Liste ist über _unrecorded_attributes von der regulären Recorder-Attributaufzeichnung ausgenommen. Andere Integrationen oder externe Aufzeichner können Daten trotzdem speichern.

## Lovelace-Karte

### Flex Table Card installieren

Mit HACS: nach **Flex Table Card** suchen und herunterladen. Browser danach vollständig neu laden.

Ohne HACS: flex-table-card.js aus dem offiziellen Repository nach /config/www/flex-table-card.js kopieren. Im Dashboard unter **Ressourcen** eine JavaScript-Modul-Ressource mit /local/flex-table-card.js hinzufügen. Ressourcen sind je nach HA-Oberfläche erst im erweiterten Benutzermodus sichtbar. Keine CDN-Ressource verwenden.

### Karte hinzufügen

**Dashboard bearbeiten → Karte hinzufügen → Manuell**. Den gesamten Inhalt von lovelace/departure-board.yaml einfügen.

Die Karte zeigt eine gemeinsame Tabelle aller Quellen:

- Dunkler Hintergrund, helle Schrift, abwechselnd leicht abgesetzte Zeilen.
- Verkehrsmittel-Icon und fette Linie.
- Hauptbahnhof → Hbf, lange Ziele umbrechen; vollständiges Ziel als Tooltip.
- Haltestelle und Gleis/Steig unter dem Ziel.
- Abfahrtszeit und Verspätung: grün ≤ 0, gelb > 0 und < 5, rosa/rot ≥ 5 Minuten.
- Unbekannte Verspätung: „k. A.“ in neutraler Farbe, kein falsches „pünktlich“.
- Minuten rechtsbündig, mit eigener Countdown-Spalte.
- Containerabhängiges Layout auch in schmalen Dashboard-Spalten. Keine zusätzliche card-mod-Abhängigkeit.
- Uhrzeit in der Zeitzone des anzeigenden Browsers. Auf Geräten außerhalb Deutschlands bei Bedarf in toLocaleTimeString zusätzlich timeZone: 'Europe/Berlin' setzen.

max_rows in der Karte ist auf 30 gesetzt. Wird das Sensorlimit erhöht, bei Bedarf auch diesen Wert anpassen.

Optional kann lovelace/source-status.yaml als kleine Markdown-Karte oberhalb eingefügt werden. Sie zeigt auch Teil-Ausfälle an. Ohne diese Zusatzkarte stehen genaue Quellenprobleme unter **Entwicklerwerkzeuge → Zustände** im Attribut source_issues.

Der Frontend-Code erzeugt dynamischen Text mit textContent und verwendet eine feste Icon-Auswahlliste. Fremde Linien- und Zielnamen werden nicht als ausführbares HTML eingesetzt. Die modify-Ausdrücke selbst müssen vertrauenswürdig bleiben.

## HACS und Veröffentlichung

Repository: [OliverHannover/public-transport-dashboard](https://github.com/OliverHannover/public-transport-dashboard)

Unter **HACS → Menü → Benutzerdefinierte Repositories** diese URL eintragen und Kategorie **Integration** wählen. Anschließend herunterladen, HA neu starten und die Integration über Geräte & Dienste einrichten.

Die Struktur enthält genau eine Integration, vollständige Manifest-Metadaten, hacs.json, Versionsnummer, MIT-Lizenz und eine lokale Grafik unter custom_components/public_transport_dashboard/brand/icon.png. Lokale Brand-Grafiken werden von neueren HA-Versionen unterstützt; ältere unterstützte Versionen können stattdessen ein generisches Icon anzeigen. Die bisherige Mindestversion 2025.1 bleibt erhalten.

HACS lädt den Integrationsordner aus dem Repository. Das vollständige Release-ZIP enthält zusätzlich Karte, Dokumentation und Tests; zip_release ist deshalb nicht aktiviert. Eine Aufnahme in den HACS-Standardkatalog wird nicht behauptet.

Für einen eigenen Fork kann python tools/prepare_repository.py OWNER/REPOSITORY die Veröffentlichungsmetadaten anpassen. Das Skript führt keinen Upload durch. Bei Organisations-Repositories muss codeowners den tatsächlichen betreuenden Benutzer nennen.

## Architektur und Aktualisierung

Die bestehende Trennung zwischen Config Flow, SensorEntity und reiner Python-Aufbereitung bleibt bestehen. Ein Coordinator oder DeviceInfo für ein erfundenes Gerät würde hier keinen fachlichen Mehrwert bringen. iot_class ist calculated: Die Integration berechnet Daten aus vorhandenen HA-Zuständen.

prepare_departures normalisiert, dedupliziert und sortiert nur bei geänderten Quelllisten oder HA-Zeitzone. Der Minutentakt verwendet diesen Cache für Zeitfenster und Countdown. Der Sensor schreibt nur, wenn sich Zustand, Attribute oder Verfügbarkeit ändern. Ein Listener und ein Minutentimer werden beim Entladen entfernt.

Der übersetzte Entity-Name lautet Abfahrten/Departures. Die bisherige Default-Entity-ID und das Unique-ID-Schema bleiben erhalten; eine Konfigurationsmigration ist nicht nötig.

Details zu Datenfluss, Dublettenschlüssel, Fehlerbehandlung, Performance und Erweiterbarkeit stehen in [DOC/architecture.md](DOC/architecture.md). Änderungen je Version stehen im [Changelog](CHANGELOG.md).

## Entwicklung und Tests

Struktur:

~~~text
custom_components/public_transport_dashboard/
  __init__.py       Setup, Reload, Unload
  config_flow.py    Einrichtung und Optionen
  const.py          Konstanten
  processing.py     HA-unabhängige Bereinigung
  sensor.py         HA-Ereignisse, Countdown, Quellenstatus
  manifest.json
  strings.json
  translations/de.json
  translations/en.json
  brand/icon.png
lovelace/
  departure-board.yaml
  source-status.yaml
tests/
  test_processing.py
  test_sensor.py
  ha/conftest.py
  ha/test_integration.py
tools/
  build_zip.py
  prepare_repository.py
  test_card.cjs
~~~

Lokale Daten- und Sensor-Unit-Tests, Python ≥ 3.12, ohne Paketinstallation:

~~~bash
python -m unittest discover -s tests -v
~~~

HA-Lebenszyklus-Tests unter Linux in einer passenden Python-Umgebung:

~~~bash
python -m pip install pytest-homeassistant-custom-component
python -m pytest tests/ha -v
~~~

Die GitHub-Actions-Datei führt beide Testsuiten mit Python 3.14 aus. Die HA-Testabhängigkeit folgt der jeweils verfügbaren Version; bei Änderungen der HA-Python-Anforderung die Workflow-Version mitziehen.

Browserprüfung: PyYAML und Playwright installieren, den offiziellen flex-table-card.js nach .qa/flex-table-card.js laden und die Karten-YAML als .qa/card.json konvertieren. Danach node tools/test_card.cjs ausführen. PLAYWRIGHT_MODULE und BROWSER_PATH sind optionale Pfadüberschreibungen. Der Test verwendet echte Flex-Table-Logik, aber vereinfachte ha-card/ha-icon-Testelemente; HA-eigene Icon-Grafiken und der komplette HA-Dialog sind damit nicht geprüft.

**Prüfung:** Die lokalen Unit-Tests decken Datenlogik und Sensorlogik ab. Bei den Sensor-Unit-Tests werden nur HA-Laufzeitgrenzen ersetzt; sie sind kein Ersatz für den vollständigen HA-Test. Die Linux-CI führt zusätzlich echte HA-Integrationstests, hassfest und HACS-Validierung aus. Den jeweiligen Status im Actions-Bereich prüfen. Tests, Benchmark und verbleibende Grenzen des Reviews werden im separat gelieferten Review-Bericht dokumentiert.

ZIP neu erstellen:

~~~bash
python tools/build_zip.py
~~~

## Fehlerbehebung

| Symptom | Prüfung |
|---|---|
| Integration fehlt in der Suche | Ordnerpfad prüfen, HA vollständig neu starten, Browser neu laden |
| Quellsensor wird abgewiesen | departures muss eine Liste sein; einmal eine erfolgreiche Quellenaktualisierung abwarten |
| Dubletten aus zwei Quellen bleiben | Gleiche Haltestellengruppe? Identische Planzeit und normalisierte Linie/Ziel? |
| Reale Abfahrt verschwindet | Nicht versehentlich unterschiedliche Haltestellen gleich gruppieren |
| Keine Abfahrten | Quellliste, Zeitstempel, Vorschau und source_issues prüfen |
| Viel zu hohe Verspätungen | Je Quelle seconds statt minutes erforderlich? |
| Minuten unterscheiden sich | Originalwert und laufender Countdown erfüllen unterschiedliche Zwecke |
| „Custom element doesn't exist“ | Flex Table Card und Modul-Ressource fehlen oder Browsercache ist alt |
| Sensor erhält Suffix _2 | Gewünschte Entity-ID bereits belegt; in der Entity-Verwaltung bereinigen und Karten-ID anpassen |

## Quellen

- [Home Assistant: Config Flow](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/)
- [Home Assistant: Options Flow](https://developers.home-assistant.io/docs/core/integration/options_flow/)
- [Flex Table Card: Konfigurationsreferenz](https://github.com/custom-cards/flex-table-card/blob/master/docs/config-ref.md)
- [HACS: Integrationsanforderungen](https://www.hacs.xyz/docs/publish/integration/)

## Dokumentationsführung

Diese README und DOC/architecture.md im Repository sind die führenden technischen Dokumente. Lokale Spiegel werden ausschließlich aus dieser Quelle aktualisiert.
