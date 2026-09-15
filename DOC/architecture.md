# Architektur und Datenvertrag

Stand: Version 1.0.1. Diese Datei beschreibt den dauerhaften technischen Vertrag; Review-Ergebnisse und Messprotokolle sind keine Architekturvorgabe.

## Komponenten

Die Architektur bleibt unverändert: Config Entry → eine SensorEntity → HA-unabhängige Aufbereitung. Es gibt keine Netzwerkabfrage, keinen Dienst und keine zusätzliche Laufzeitabhängigkeit.

| Datei | Verantwortung |
|---|---|
| __init__.py | Plattform laden, bei Optionsänderung neu laden, sauber entladen |
| config_flow.py | Quellen validieren, Optionen und Haltestellengruppen über die UI speichern |
| const.py | Domain und Standardwerte |
| processing.py | Typ-/Zeitnormalisierung, Deduplizierung, Sortierung, Zeitfenster |
| sensor.py | HA-Zustände beobachten, Quellenzustand bewerten, Cache und Countdown verwalten |

Ein DataUpdateCoordinator würde hier weder eine gemeinsame API-Abfrage koordinieren noch mehrere Entities versorgen. Er ist daher nicht erforderlich. DeviceInfo bleibt ebenfalls bewusst aus: Die einzelne virtuelle Hilfs-Entity repräsentiert kein physisches Gerät. Die Geräteanforderung der HA-Gold-Qualitätsstufe wird nicht beansprucht.

## Datenfluss

1. Beim Setup registriert der Sensor eine auf die ausgewählten Entities beschränkte Ereignissubskription und einen Minutentimer.
2. Jeder Durchlauf liest die Quellenzustände und prüft Verfügbarkeit, departures-Typ und last_reported.
3. Nur wenn sich die nutzbaren Quelllisten oder die HA-Zeitzone geändert haben, läuft prepare_departures.
4. prepare_departures normalisiert jede Zeile einmal, dedupliziert per Dictionary und sortiert die bereinigten Zeilen einmal.
5. PreparedBoard.at projiziert aus diesem Cache den aktuellen Zeitraum und berechnet countdown_minutes.
6. Die neue Ausgabe wird mit der bisherigen Ausgabe verglichen. Nur bei einer sichtbaren Änderung wird async_write_ha_state aufgerufen.
7. Beim Entfernen oder Neuladen werden die Subskription und der Timer durch HA entfernt.

Unveränderte Minutentakte führen damit zu keiner erneuten Zeitstempelanalyse oder Sortierung. Der Timer bleibt notwendig, weil ohne Quellenänderung trotzdem Abfahrten vergehen und Quellen veralten können. Bei leerer Tafel schreibt der Timer keine unveränderten Zustände.

Cache-Einträge halten nur Referenzen auf die von HA bereitgestellten Quelllisten. Die Listen werden nicht kopiert oder verändert. Dies setzt den HA-Vertrag voraus, dass veröffentlichte Zustände nicht nachträglich in-place verändert werden. Eine fehlerhafte Integration, die ihre bereits veröffentlichten Listen heimlich mutiert, kann nicht zuverlässig über Änderungsereignisse erkannt werden.

Für die sichtbaren Abfahrten entstehen neue flache Zeilendictionaries, damit ein neuer Countdown keine älteren HA-Zustände verändert. Herkunftslisten werden nach Vorbereitung nicht mehr verändert.

## Dublettenschlüssel

Der Schlüssel besteht aus:

**Haltestellengruppe + Verkehrsmittelfamilie + normalisierte Linie + normalisiertes Ziel + Zeitbasis + Zeitwert**

- Eine leere Haltestellengruppe wird durch die Quell-Entity-ID ersetzt. Verschiedene Stationen bleiben getrennt.
- Bekannte Synonyme eines Verkehrsmittels werden vereinheitlicht: etwa train, rail und suburban zur Familie train. Bus, Tram, U-Bahn und Fähre bleiben getrennte Familien. Unbekannte Typen behalten ihren normalisierten eigenen Namen.
- Groß-/Kleinschreibung ist bei Gruppe, Linie und Ziel unerheblich. Linien-Leerzeichen werden entfernt; Ziel-Leerzeichen werden vereinheitlicht.
- Die generische Abkürzung Hauptbahnhof → Hbf dient sowohl der Anzeige als auch dem Zielvergleich.
- Als Zeitwert gilt die gelieferte Planzeit.
- Fehlt die Planzeit, wird sie bei bekannter numerischer Verspätung aus Abfahrtszeit minus Verspätung abgeleitet. Die konfigurierte Sekunden-/Minuteneinheit wird vorher berücksichtigt.
- Erst wenn keine Planzeit verfügbar oder ableitbar ist, gilt die exakte Abfahrtszeit als Ersatz. Diese Ersatzbasis wird von einer Planzeit unterschieden.

**Nicht im Schlüssel:** Betreiber, Gleis, aktuelle Abfahrtszeit bei bekannter Planzeit, Verspätung und Minuten bis Abfahrt. Deshalb erzeugen ein anderer Betreiber oder geänderte Echtzeitprognosen für denselben planmäßigen Halt keine zusätzlichen Zeilen.

Bei einem Konflikt gewinnt die erste gültige Quellzeile in der gespeicherten Quellreihenfolge. Ihre Zeiten, Gleisangabe und übrigen Felder bleiben zusammen. Nur die Listen agencies und source_entities werden um weitere Herkunftsangaben ergänzt. Gleis und Zeit werden nicht aus widersprüchlichen Meldungen verschiedener Anbieter zusammengebaut.

## Identitätsgrenzen

Die Integration nimmt weder konkrete Stationen noch Liniennummern oder Betreiber an. Sie erwartet jedoch das dokumentierte Feldschema.

Ohne stabile Planzeit oder ableitbare Planzeit kann aus zwei verschiedenen Echtzeitangaben allein nicht festgestellt werden, ob es dieselbe Fahrt oder die nächste Fahrt ist. Solche Zeilen bleiben konservativ getrennt. Es gibt keine unscharfe Zeit-Toleranz, die reale Fahrten im dichten Takt verschlucken könnte.

Umgekehrt können zwei tatsächlich verschiedene Fahrten mit identischer Station, Verkehrsmittelfamilie, Linie, Ziel und Planzeit ohne weitere Identitätsdaten nicht auseinandergehalten werden. Eine optionale, quellenübergreifend belastbare Fahrt-ID ist ein sinnvoller nächster Schritt für Version 1.1, aber nicht Teil des Vertrags 1.0.1. Abweichende Verkehrsmittelbezeichnungen oder Ziel-Aliasse, die nicht als gleich bekannt sind, werden nicht geraten.

## Zeit- und Fehlerbehandlung

- ISO-Zeitstempel benötigen Datum und Uhrzeit. Ein bloßes Datum oder eine Uhrzeit ohne Datum ist ungültig.
- Offsets werden nach UTC umgerechnet. Naive Zeitwerte verwenden die HA-Zeitzone. Bei der doppelt vorkommenden Stunde der Zeitumstellung ist ein expliziter Offset notwendig.
- Fehlt die tatsächliche Zeit, wird die Planzeit plus bekannte Verspätung verwendet. Eine unbekannte Verspätung wird nicht als bestätigte Pünktlichkeit ausgegeben.
- Nicht endliche Zahlen, boolesche Zahlenersatzwerte und strukturierte Werte werden verworfen.
- Zeilen ohne Linie, Ziel oder verwendbare Abfahrtszeit werden übersprungen und gezählt.
- unavailable, unknown, fehlende Entities sowie fehlende/falsche departures-Attribute werden als Quellenprobleme gemeldet.
- Eine leere Liste ist eine verfügbare Quelle ohne Abfahrten. Einzelne fehlerhafte Zeilen machen gültige Nachbarzeilen nicht unbrauchbar.
- Bei Teil-Ausfällen bleibt die übrige Tafel verfügbar. Bei Totalausfall wird departures geleert und der Sensor unavailable.
- Quellenfehler werden bei Zustandswechsel auf Debug-Ebene protokolliert. Fahrplaninhalte und personenbezogene Kontextdaten werden nicht geloggt.
- Es gibt kein pauschales except Exception: Erwartbare Datenfehler werden an ihrer Grenze behandelt; Programmierfehler werden nicht als scheinbar gesunde Daten versteckt. Eine absolute Garantie gegen Speichererschöpfung, HA-Fehler oder beliebige Fremdobjekte ist technisch nicht möglich.

## Ausgabe und Kompatibilität

Die Domain public_transport_dashboard, die Default-Entity-ID sensor.public_transport_dashboard und das Unique-ID-Schema bleiben erhalten. Die Konfigurationsversion bleibt 1, da sich die gespeicherte Struktur nicht ändert. Vorhandene Optionen benötigen keine Migration.

Der übersetzte Entity-Name ist Abfahrten/Departures; has_entity_name ist aktiv. Eine vom Benutzer vergebene Entity-ID oder ein Benutzername behält Vorrang über die Registry.

minutes_until_departure bleibt der numerische Quellwert; countdown_minutes ist der laufende lokale Countdown. delay wird immer in Minuten ausgegeben. Eine rekonstruierte Planzeit erscheint ebenfalls als planned_time. Das ist die fachliche Ergänzung gegenüber 1.0.0.

Die überschaubare Sensorzustandszahl kann aufgezeichnet werden; departures, source_issues und source_entities sind über _unrecorded_attributes von regulärer Recorder-Attributaufzeichnung ausgenommen.

## Performance und Erweiterbarkeit

Für N Quellzeilen und U eindeutige Abfahrten kostet die Vorbereitung im üblichen Fall O(N + U log U). Lange Herkunftslisten können zusätzliche lineare Mitgliedschaftsprüfungen verursachen. Der Takt kostet O(S + U) im ungünstigsten Fall, mit S Quellen; tatsächlich endet die Suche nach Erreichen des Zeitfensters oder Zeilenlimits. Es werden höchstens max_departures Zeilendictionaries kopiert.

Zusätzliche bekannte Verkehrsmittel können über MODE_FAMILIES und die Icon-Zuordnung aufgenommen werden. Die fachliche Identität hängt nicht von der Icon-Grafik ab. Zusätzliche Quellfelder gehören in die Normalisierung samt Tests, nicht in die Sensor-Lebenszykluslogik. Anbieterabhängige Adapter sollten bei Bedarf explizit vorgeschaltet werden.

## Maßgebliche Referenzen

- [HA-Manifest und calculated](https://developers.home-assistant.io/docs/creating_integration_manifest/#iot-class)
- [HA-Datenaktualisierung](https://developers.home-assistant.io/docs/integration_fetching_data/)
- [HA-Entity-Namen](https://developers.home-assistant.io/docs/core/entity/#entity-naming)
- [HA-Options-Flow](https://developers.home-assistant.io/docs/core/integration/options_flow/)
- [HACS-Anforderungen](https://www.hacs.xyz/docs/publish/integration/)
