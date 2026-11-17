# Gen X Task Manager

App: **genxtask v1.0.0** · [Release und Downloads](https://github.com/5nus/Gen-X-Task-Manager/releases/tag/v1.0.0) · [MIT-Lizenz](LICENSE)

Ein Linux-Task-Manager im Windows-95-Look: Aufgaben erstellen, bearbeiten, nach
Priorität sortieren und nach Bestätigung dauerhaft löschen. Mit Kalender,
Uhrzeitauswahl, unabhängigen Desktop-Erinnerungen und Harold P. Wiggins, einem
abwesenden Büroangestellten mit eigenem Messenger. Harold ist kein Assistent.

![genxtask mit Harold Messenger](docs/screenshots/genxtask.png)

[Harold-App-Icon als PNG herunterladen](packaging/genxtask.png).
Projekt und Repository heißen weiterhin **Gen X Task Manager**; die installierte
Anwendung und ihr Startbefehl heißen **genxtask**.

## Voraussetzungen

- Linux, `/usr/bin/python3` ab Python 3.9, Tkinter und SQLite.
- Für Erinnerungen zusätzlich: systemd-User-Manager, ein D-Bus-Session-Bus,
  `notify-send` und ein Desktop-Benachrichtigungsdienst wie GNOME, KDE oder Xfce.
- Debian/Ubuntu: Die Systempakete heißen `python3`, `python3-tk` und für
  Erinnerungen `libnotify-bin`. Es werden keine zusätzlichen Python-Pakete benötigt.
- Getestet mit Python 3.12, Tk 8.6 und X11. Wayland kann für Benachrichtigungen
  verwendet werden; Fenster- und Taskleisten-Icons hängen vom Desktop und dessen
  XWayland-/Tk-Unterstützung ab.

## Installation ohne Root-Rechte

Aus einem heruntergeladenen Repository:

```bash
git clone https://github.com/5nus/Gen-X-Task-Manager.git
cd Gen-X-Task-Manager
/usr/bin/python3 install.py
```

Oder aus dem vorbereiteten Release-Archiv:

```bash
tar -xzf genxtask-v1.0.0.tar.gz
cd genxtask-v1.0.0
/usr/bin/python3 install.py
```

Danach im Anwendungsmenü **genxtask** auswählen. Alternativ:

```bash
"$HOME/.local/bin/genxtask"
"$HOME/.local/bin/genxtask" --version
```

Wenn `~/.local/bin` bereits im `PATH` liegt, genügt `genxtask`. Die Menüverknüpfung
verwendet einen absoluten, korrekt quotierten Pfad und benötigt keinen angepassten
`PATH`, kein sichtbares Terminal und kein manuelles `PYTHONPATH`. Das Download- oder
Repository-Verzeichnis kann nach der Installation entfernt werden.

### Installierte Dateien und Updates

| Inhalt | Standardpfad |
| --- | --- |
| Python-Paket, Assets, Deinstaller, Installationsmanifest | `~/.local/share/genx.tasks/` |
| GUI, Reminder und Deinstallationsbefehl | `~/.local/bin/genxtask`, `genxtask-reminder`, `genxtask-uninstall` |
| Anwendungsmenü | `~/.local/share/applications/genxtask.desktop` |
| Harold-Icons | `~/.local/share/icons/hicolor/{size}x{size}/apps/genxtask.png` |
| Reminder-Units | `~/.config/systemd/user/gen-x-task-reminder.{service,timer}` |
| Optionaler Sitzungs-Autostart, noch nicht aktiviert | `~/.local/share/genx.tasks/integration/gen-x-task-reminder.desktop` |

Der Installer berücksichtigt `XDG_DATA_HOME` und `XDG_CONFIG_HOME`. Die Startprogramme
merken sich den bei der Installation gewählten Datenordner, damit GUI und Reminder
auch außerhalb des Download-Verzeichnisses denselben Standard verwenden.
Die technische Paketbezeichnung `task_manager`, bestehende Datenbankpfade und
systemd-Unit-Namen bleiben erhalten.
Der interne Programmordner `genx.tasks` bleibt für bestehende Installationen
erhalten. Bei erneuter Installation werden die bisherigen Launcher und Icons
durch die neuen `genxtask`-Einträge ersetzt; Aufgabendaten bleiben unverändert.

Für ein Update die neue Version herunterladen und `install.py` erneut ausführen.
Vorhandene Datenbanken und `reminder.env` bleiben erhalten. Bereits aktivierte
Reminder-Timer werden nicht abgeschaltet; eine neue Installation aktiviert sie
nicht automatisch. Nach einem Wechsel des XDG-Installationsorts die alte
Installation zuerst deinstallieren und den vorhandenen Datenbankpfad ausdrücklich
beibehalten.

Harolds unverändertes Messenger-Avatar ist die einzige Icon-Quelle. Sein vorhandener
quadratischer weißer Hintergrund wird übernommen; alle sieben Icon-Größen
(16, 24, 32, 48, 64, 128 und 256 Pixel) verwenden Nearest-Neighbor-Skalierung.
Tkinter setzt diese Icons auch als Fenster-Icon und Vorgabe für weitere Fenster.
`StartupWMClass=genxtask` unterstützt die Zuordnung zur Taskleiste. Die endgültige
Darstellung im Anwendungsmenü, in der Taskleiste und bei Alt-Tab bestimmt der Desktop.

## Datenbankpfad

Die bisherigen Aufgaben bleiben unter `$XDG_DATA_HOME/task-manager/tasks.sqlite3`
beziehungsweise `~/.local/share/task-manager/tasks.sqlite3`. Sie liegen getrennt vom
installierten Programm. Es gibt keine neue Datenbankmigration und keine automatische
Löschung alter Daten.

GUI und Reminder verwenden dieselbe Pfadermittlung, in dieser Reihenfolge:

1. Expliziter Parameter `--database`.
2. Umgebungsvariable `TASK_MANAGER_DATABASE`.
3. Standardpfad im bei der Installation gewählten XDG-Datenordner.

```bash
"$HOME/.local/bin/genxtask" --database /absolute/path/tasks.sqlite3
"$HOME/.local/bin/genxtask-reminder" --database /absolute/path/tasks.sqlite3
```

**Ein eigener GUI-Pfad muss auch im Reminder konfiguriert werden.** Unabhängige
Prozesse übernehmen keine Kommandozeilenargumente voneinander. Dazu in
`${XDG_CONFIG_HOME:-$HOME/.config}/gen-x-task-manager/reminder.env` beispielsweise:

```ini
TASK_MANAGER_DATABASE="/absolute/path/tasks.sqlite3"
```

Das Verzeichnis bei Bedarf anlegen. Die Datei ist eine systemd-EnvironmentFile,
kein Shell-Skript: kein `export`, kein `$HOME`, nur absolute Pfade. Bei einem
Upgrade bleiben bestehende Einträge erhalten. Alte `PYTHONPATH`-Einträge sind nach
der Installation nicht mehr erforderlich; die installierten Startprogramme laden
ihre eigene Paketkopie.

## Erinnerungen aktivieren und prüfen

Die Installation stellt die Units bereit. Sie aktiviert den Timer nicht und
verspricht ohne geeignete Desktop-Sitzung keine Benachrichtigungen. Die GUI
funktioniert auch ohne aktivierte Erinnerungen.

Im Terminal der grafischen Sitzung:

```bash
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY
systemctl --user daemon-reload
systemctl --user enable --now gen-x-task-reminder.timer
systemctl --user start gen-x-task-reminder.service
```

Nicht gesetzte Variablen der jeweils anderen Display-Art werden ignoriert.
Mindestens `DISPLAY` oder `WAYLAND_DISPLAY` muss im User-Manager gesetzt sein.
Der Dienst verwendet den D-Bus-Bus desselben Benutzers unter `unix:path=%t/bus`.
Sein Python-Pfad zeigt auf die installierte Paketkopie, nicht auf den Download.

Die Units sind an `graphical-session.target` angebunden. Prüfen:

```bash
systemctl --user is-active graphical-session.target
```

Bei Desktops mit aktivem Target startet der aktivierte Timer mit der Sitzung.
**Bei Xfce und anderen Sitzungen ohne dieses Target** den bereitgestellten
Autostart-Eintrag zusätzlich installieren:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
install -m 644 "${XDG_DATA_HOME:-$HOME/.local/share}/genx.tasks/integration/gen-x-task-reminder.desktop" "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/"
```

Dieser übernimmt beim nächsten grafischen Login die Sitzungsumgebung und startet
denselben Timer. Er setzt keinen Repository-Pfad voraus. Wiederholtes Starten
führt nicht zu mehreren Timer-Instanzen. Ein SSH-Login ersetzt keine grafische
Sitzung; `loginctl enable-linger` ist nicht nötig.

```bash
systemctl --user status gen-x-task-reminder.timer
systemctl --user list-timers --all gen-x-task-reminder.timer
systemctl --user status gen-x-task-reminder.service
journalctl --user -u gen-x-task-reminder.service -n 50 --no-pager
```

Der `oneshot`-Service ist zwischen erfolgreichen Läufen normalerweise `inactive
(dead)`; der Timer soll aktiv sein. Ein manueller einmaliger Prüflauf ist möglich:

```bash
"$HOME/.local/bin/genxtask-reminder"
```

### Fehler eingrenzen

- **Keine Datenbank:** Im Journal genannten absoluten Pfad mit dem GUI-Aufruf und
  `reminder.env` vergleichen. Der Reminder erzeugt keine leere Ersatzdatenbank.
- **Python-Modul fehlt:** Installation erneut ausführen. Die Download-Dateien sind
  nicht nötig; die installierte Kopie unter `genx.tasks/lib/` muss vorhanden sein.
- **Kein Display / D-Bus:** Sitzungsumgebung aus einem Desktop-Terminal importieren;
  bei Xfce zusätzlich den Autostart-Eintrag verwenden.
- **`notify-send` fehlt:** Systempaket installieren, unter Debian/Ubuntu
  `libnotify-bin`. Ein direkter Test im grafischen Terminal:

  ```bash
  notify-send -- "Task Reminder" "Manual notification test"
  ```

- **Aufruf erfolgreich, kein Banner:** Nicht-stören-Modus und Einstellungen des
  Benachrichtigungsdienstes prüfen. Annahme ist kein Nachweis tatsächlicher Wahrnehmung.
- **`database is locked`:** Nach Ende des anderen Schreibzugriffs erneut speichern.
  Formularänderungen bleiben bei Fehlern vollständig ungespeichert. Ein Reminder
  hält seine Schreibsperre während eines auf fünf Sekunden begrenzten Aufrufs.
- **Launcher/Icon fehlt:** Erneut anmelden oder Installation erneut ausführen.
  Vorhandene Werkzeuge `update-desktop-database` und `gtk-update-icon-cache` werden
  automatisch verwendet; bei fehlenden Werkzeugen kann der Desktop seinen Cache
  erst beim nächsten Login erneuern.

### Erinnerungen deaktivieren

```bash
systemctl --user disable --now gen-x-task-reminder.timer
systemctl --user stop gen-x-task-reminder.service
```

Einen zuvor installierten Autostart-Eintrag außerdem in den Desktop-Einstellungen
deaktivieren oder entfernen, damit er den Timer nicht beim nächsten Login startet.

## Deinstallation

```bash
"$HOME/.local/bin/genxtask-uninstall"
```

Alternativ aus dem ursprünglichen Download:

```bash
/usr/bin/python3 install.py --uninstall
```

Der Deinstaller stoppt und deaktiviert den Reminder-Timer, entfernt Programm,
Launcher, Icons, Units und den optionalen Autostart. Aufgabendatenbanken und
`reminder.env` bleiben erhalten. Es werden ausschließlich registrierte
Installationsdateien entfernt; unbekannte Dateien im Programmordner werden nicht
pauschal gelöscht. Die installierte Deinstallation funktioniert auch dann, wenn
der ursprüngliche Download nicht mehr existiert.

Für isolierte Tests oder Offline-Staging kann `install.py --no-systemd` verwendet
werden; beim Deinstallieren gilt `--uninstall --no-systemd`. Diese Option überspringt
ausschließlich die Kommunikation mit dem User-Manager. Bei einer normalen
Deinstallation sollte der Reminder vorher zuverlässig gestoppt werden.

## Ablauf und Zustellgrenzen

Ein User-Timer startet ungefähr jede Minute einen kurzen Prüflauf. Zwischen den
Läufen läuft kein zusätzlicher Python-Prozess. Das ist für V1 einfacher als ein
ständig laufender Daemon mit eigener Schleife, Neustartlogik oder Threads.
`OnStartupSec=10s` sorgt für einen ersten Lauf; `OnUnitInactiveSec=60s` und
`AccuracySec=5s` für weitere Prüfungen. Es gibt keine sekundengenaue Termingarantie.
Der Timer weckt den Rechner nicht aus dem Standby.

1. Eine indexgestützte SQL-Abfrage wählt ausschließlich fällige, noch nicht
   versendete Aufgaben mit gesetztem `remind_at`. Vergleiche erfolgen in UTC.
2. Für jede Aufgabe beginnt eine kurze SQLite-Transaktion mit `BEGIN IMMEDIATE`.
   Darin werden Existenz, Zeitpunkt und Versandstatus erneut gelesen. Bereits
   gelöschte, verschobene oder inzwischen verarbeitete Erinnerungen werden übersprungen.
3. `notify-send` übergibt „Task Reminder“ und den aktuellen Aufgabentitel an den
   Desktop-Dienst. Argumente werden ohne Shell übergeben; Titel-Markup wird maskiert.
4. Erst nach erfolgreichem Aufruf wird `reminder_sent` für den erwarteten Zeitpunkt
   gesetzt und die Transaktion committed. Aufruf- oder Datenbankfehler lassen den
   Status offen. Andere Reminder-Prozesse und GUI-Schreiber werden dabei serialisiert.

`notify-send` verwendet den üblichen Linux-Benachrichtigungsdienst und erspart
eine zusätzliche D-Bus-Python-Bibliothek. Die Schnittstelle ist in der
[Desktop Notifications Specification](https://specifications.freedesktop.org/notification/latest/protocol.html)
beschrieben; Optionen dokumentiert die [notify-send-Manpage](https://manpages.debian.org/trixie/libnotify-bin/notify-send.1.en.html).
Timer und Sitzungseinbindung folgen der
[systemd-Timer-Dokumentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
und den [Hinweisen zu Desktop-Sitzungen](https://github.com/systemd/systemd/blob/main/docs/DESKTOP_ENVIRONMENTS.md).

Während Ausschalten oder Standby überfällige Erinnerungen werden beim nächsten
geeigneten Lauf nachgeholt. Erfolgreich gespeicherte Versandstatus verhindern
erneute Meldungen bei normalen Neustarts. Fehlt die Sitzungsumgebung oder schlägt
der Benachrichtigungsaufruf fehl, bleibt die Zustellung offen. V1 richtet sich an eine grafische
Sitzung pro Benutzer; die Auswahl zwischen mehreren parallelen Desktops wird
nicht verwaltet.

**Keine Exactly-once-Garantie:** Datenbank und Desktop-Dienst besitzen keine gemeinsame
Transaktion. Ein Absturz nach Annahme der Benachrichtigung, aber vor dem Commit,
kann bei erneutem Versuch eine doppelte Meldung verursachen. Auch ein Timeout
kann auftreten, nachdem der Desktop eine Anfrage bereits angenommen hat.
Nicht-stören-Modus und andere Desktop-Regeln können sichtbare Meldungen unterdrücken.
Eine bereits abgesendete Benachrichtigung lässt sich durch späteres Löschen oder
Ändern der Aufgabe nicht zurücknehmen.

## Aufgabenbearbeitung und Persistenz

`TaskService` validiert Titel und Modellwerte vor dem Schreiben. Titel werden
getrimmt und müssen 1–200 Zeichen enthalten. `TaskService.update(id, **changes)`
übernimmt ausschließlich explizit geänderte Felder: Titel, Beschreibung, Priorität,
Fälligkeit und Erinnerungszeitpunkt. Ein Formular speichert diese gemeinsam mit
einem einzigen parametrisierten SQL-UPDATE in einer Transaktion. Bei einem Fehler
bleibt keine Teiländerung bestehen. `id` und `created_at` sind unveränderlich.

Die Service-Schicht fordert bei Änderungen des Erinnerungsfeldes einen bedingten
Reset an. Das Repository vergleicht dafür den tatsächlich gespeicherten Zeitpunkt
atomar im SQL-UPDATE. Nur ein geänderter Zeitpunkt setzt `reminder_sent=False`.
Unveränderte Erinnerungszeiten und andere Feldänderungen erhalten einen inzwischen
vom Reminder gesetzten Status. Konkurrierende Änderungen desselben Aufgabenfeldes
folgen weiterhin dem letzten Schreibzugriff. Mehrere getrennte Service-Aufrufe
bilden keine gemeinsame Formulartransaktion.

SQLite ist die einzige persistente Datenquelle. UUID4-IDs und zeitzonenbewusste
ISO-Zeitstempel liegen als Text vor; Zeitstempel sind auf UTC mit Mikrosekunden
normalisiert. Boolean-Werte liegen als 0/1 vor. Fehlende Aufgaben erzeugen im
Service `KeyError`, ungültige Werte `TypeError` oder `ValueError`. SQLite-Fehler
werden weitergegeben. Das Repository enthält keine GUI- oder Benachrichtigungslogik.

Erledigen bedeutet dauerhaft löschen. Eine Bestätigung in der GUI ist erforderlich.
Gelöschte Aufgaben erscheinen nicht mehr in der Reminder-Abfrage und veraltete
Schreibzugriffe können sie nicht wiederherstellen.

## Kalender und GUI

Die englische Oberfläche behält graue Fenster, dunkelblaue Titel, 3D-Schaltflächen
und mehrzeilige Titel. Aufgaben mit hoher Priorität stehen zuerst; Low, Normal
und High entsprechen 1, 2 und 3.

Fälligkeit und Erinnerung besitzen einen Kalender mit Monatsnavigation und Today.
Die Eingabe akzeptiert `MM/DD/YYYY`, `MM-DD-YYYY` und ISO-Daten; im US-Format steht
der Monat zuerst. Stunden und Minuten werden mit Spinboxen gewählt oder eingegeben.
Neue Eingaben verwenden die lokale Linux-Zeitzone einschließlich Sommerzeit;
Zeitpunkte in einer Sommerzeitlücke werden abgelehnt. Clear entfernt den Zeitpunkt.
Vollständige ISO-Zeitpunkte mit Offset bleiben einfügbar. Unveränderte Zeitpunkte
behalten Sekunden und Mikrosekunden.

## Harold Messenger

Harold bleibt ein separater, nicht modaler Messenger mit Pixel-Avatar, „Away“,
„Last seen: Unknown“, scrollbarem Verlauf und lokalen Uhrzeiten. Mehrfaches Öffnen
zeigt dasselbe Fenster. Der Avatar und sein Generierungsprompt liegen in
`src/task_manager/assets/` und benötigen keine zusätzliche Bildbibliothek.

Harold schreibt unabhängig von Benutzernachrichten höchstens drei belanglose
Nachrichten pro Anwendungssitzung, in zufälligen Abständen von 3–10 Minuten.
Jeder Sendeversuch öffnet einen separaten „Messenger Service“-Dialog. Diese Meldung
landet niemals im Chatverlauf; direkte Antworten von Harold gibt es nicht.
OK, Escape und das Schließen-Kreuz schließen den Systemdialog.

Verlauf und Nachrichtenlimit bleiben beim Schließen des Chats im Arbeitsspeicher.
`after()`-Timer laufen ohne Threads und werden beim Beenden der GUI abgebrochen.
Harold hat keinen Zugriff auf den Reminder-Prozess und sendet keine Desktop-Meldungen.

## Entwicklung, Tests und Release-Verfahren

Aus dem Repository kann weiterhin ohne Installation gestartet werden:

```bash
PYTHONPATH=src python3 -m task_manager
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Alle GUI- und Installationstests mit Xvfb ausführen:

```bash
xvfb-run -a env PYTHONPATH=src python3 -m unittest discover -s tests -v
desktop-file-validate packaging/genxtask.desktop
desktop-file-validate systemd/gen-x-task-reminder.desktop
```

Für die vollständigen Linux-Integrationstests werden außerdem `xwininfo` und
`xprop` benötigt (Debian/Ubuntu: `x11-utils`). GIO- und systemd-Validator-Tests
werden nur ausgeführt, wenn die entsprechenden Systemwerkzeuge vorhanden sind.

Installationstests verwenden frische Benutzerverzeichnisse mit Leerzeichen und
kontaktieren dabei keinen echten systemd-User-Manager. Desktop-Launcher werden
validiert und, wenn GIO vorhanden ist, von GIO ausgeführt. Die installierte GUI
wird ohne manuelles `PYTHONPATH` aus einem anderen Arbeitsverzeichnis gestartet;
X11-Fensterklasse und Icon-Eigenschaften werden geprüft. Reminder-Aufrufe verwenden
ein gemocktes Benachrichtigungswerkzeug. Wiederholte Installation, Deinstallation
mit Datenerhalt und Start nach Entfernen des Downloads werden ebenfalls geprüft.

Prüfstand für dieses Review: **113 Tests bestanden**, einschließlich frischer
Installation, wiederholter Installation, GIO-Launcher, installierter GUI, Icons,
Reminder, Deinstallation und reproduzierbarem Archiv. Zusätzlich wurde eine
temporäre Installation in der echten X11-Desktop-Sitzung aus `/` ohne
`PYTHONPATH` gestartet. Fensterklasse und Fenster-Icon wurden geprüft. Das
konkrete Aussehen in jeder Taskleiste und Alt-Tab-Oberfläche sowie Wayland wurden
nicht manuell überprüft. Der dauerhafte Reminder-Autostart wurde für dieses
Installationsreview nicht im echten Benutzerkonto aktiviert.

Zusätzlicher Test in einem separaten Arch-Linux-Container: **72 Tests bestanden**,
41 Tests mangels grafischer Sitzung beziehungsweise optionaler Werkzeuge
übersprungen. Installation des Release-Archivs in einem frischen Benutzerordner,
Startbefehle ohne `PYTHONPATH`, Reminder-Aufruf und Deinstallation funktionieren
auch dort. Das ist ein zusätzlicher Linux-Umgebungstest, kein Test auf einem
zweiten physischen Rechner.

### Reproduzierbares Release-Archiv

```bash
python3 scripts/build_release.py
cd dist
sha256sum -c genxtask-v1.0.0.tar.gz.sha256
```

Das Skript liest die Version aus `task_manager.__version__` und erzeugt
`dist/genxtask-v1.0.0.tar.gz` mit zugehöriger SHA-256-Datei. Es enthält Quellcode,
Installer, Icons, Units, Dokumentation und Tests. Eine feste Dateiauswahl und
normalisierte Archiv-Metadaten halten `.git`, Benutzerdaten und Cache-Dateien
heraus. Zwei Builds desselben Stands sind bytegleich. Ein grafisches Display ist
zum Erstellen des Archivs nicht nötig.
Zusätzlich liegt Harolds App-Icon separat als `dist/genxtask.png` zum Download vor.

Die Icon-Dateien sind eingecheckt. Nur bei einer bewussten Änderung der zugrunde
liegenden Grafik werden sie mit dem Standardbibliothek-Werkzeug neu erstellt:

```bash
xvfb-run -a python3 scripts/generate_icons.py
```

Das Build-Skript erstellt weder einen Git-Tag noch ein GitHub-Release. Das
veröffentlichte Archiv und das separate Harold-Icon liegen im
[GitHub-Release v1.0.0](https://github.com/5nus/Gen-X-Task-Manager/releases/tag/v1.0.0).

## Lizenz

MIT, Copyright (c) 2026 Simon Korber. Der vollständige Lizenztext liegt in
[`LICENSE`](LICENSE) und wird sowohl im Release-Archiv als auch mit der
Benutzerinstallation mitgeliefert.

```text
install.py                     Benutzerinstallation und Deinstallation
packaging/genxtask.desktop    Desktop-Launcher
scripts/generate_icons.py      Skalierung des unveränderten Harold-Avatars
scripts/build_release.py       Reproduzierbares Release-Archiv
src/task_manager/              Anwendung und Assets
systemd/                       Reminder-Units und optionaler Sitzungs-Autostart
tests/                         unittest-Tests
docs/screenshots/              Oberfläche
```

Nicht Teil von V1: wiederkehrende Aufgaben, Cloud-Synchronisierung, Benutzerkonten,
Statistiken, IPC, neue GUI-Frameworks, AppImage, Flatpak, Snap und Distributionspakete.
