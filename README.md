# 🇨🇭 Zürich WG Tracker

Finde und verwalte WG-Zimmer in Zürich – automatisch und visuell.

---

## 🔎 Unterstützte Webseiten

- [wgzimmer.ch](https://www.wgzimmer.ch/)
- [woko.ch](https://www.woko.ch/)
- [students.ch](https://www.students.ch/)

---

## ⚙️ Was macht das Tool?

- Scraped WG-Zimmer auf den o.g. Plattformen
- Speichert alle Daten lokal in `db.json` (TinyDB)
- Berechnet:
  - 📍 Geokoordinaten (OpenCage)
  - 🚲 Fahrradzeit & Strecke zur ETH (OpenRouteService)
  - 🚋 ÖV-Verbindung für 8 Uhr morgens zur ETH
- Web-Oberfläche (Streamlit):
  - Filtern (Preis, Datum, gesehen/gemerkt, Fahrradzeit)
  - Sortieren (Preis, Datum, Aufgegeben)
  - Anzeigen auf Karte
  - Detailansicht pro Inserat
  - Manuelles Updaten/Fetchen möglich

---

## 🧠 `wgzimmer.ch` scrapen mit Playwright

Die Seite `wgzimmer.ch` verwendet interaktives JavaScript und Captchas, daher benötigen wir einen echten Browser.

Wir verwenden [`Playwright`](https://playwright.dev/)

- den kompletten Ablauf im Hintergrund auszuführen
- den lokalen Bildschirm nicht zu blockieren
- automatisch alle Wohnungsangebote zu scrapen
- Erweiterungen wie `uBlock` zur Captcha-Vermeidung zu laden

- Python 3.12
- [uBlock](https://objects.githubusercontent.com/github-production-release-asset-2e65be/33263118/81b2267f-a192-450a-aad3-69e6ec986b11?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=releaseassetproduction%2F20250517%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20250517T204142Z&X-Amz-Expires=300&X-Amz-Signature=441e8d5187d584267d8baa3456bece29f441bd1fe6db1f7a674a036c7d7e352b&X-Amz-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3DuBlock0_1.64.0.chromium.zip&response-content-type=application%2Foctet-stream)

## 🚀 Installation

### Setup

```bash
git clone https://github.com/ffhammer/wg-zimmer-tracker-zuerich.git
cd wg-tracker
cp .env.example .env # API Keys eintragen

pip install -r requirements.txt
```

---

## 🗝️ .env Beispiel

```dotenv
LOCATIONIQ_API_KEY=dein_LOCATIONIQ_API_KEY
OPENROUTESERVICE_API_KEY=dein_openrouteservice_key
TIME_ZONE=Europe/Zurich
```

## 🧠 Geo APIs

- 🌍 **Geocoding:** [LOCATIONIQ](https://de.locationiq.com//)
- 🧭 **Routing:** [OpenRouteService](https://openrouteservice.org/)

---

## 📺 Web-Oberfläche

---

## 🧪 Website starten

```bash
streamlit run src/app.py
```

Läuft automatisch unter:  
[http://localhost:8501](http://localhost:8501)

---
