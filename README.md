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

## 🧠 `wgzimmer.ch` scrapen mit Docker & browser-use

Die Seite `wgzimmer.ch` verwendet interaktives JS + Google Captcha → wir brauchen einen echten Browser.

Wir nutzen [`browser-use`](https://github.com/browser-use/browser-use) in einem separaten Docker-Container, damit:

- das Ganze Hintergrund läuft
- der lokale Bildschirm nicht blockiert wird
- alles automatisch und ohne manuellen Eingriff funktioniert

---

## 🚀 Installation

### Voraussetzungen

- Docker
- Docker Compose

### Setup

```bash
git clone https://github.com/ffhammer/wg-zimmer-tracker-zuerich.git
cd wg-tracker
cp .env.example .env # API Keys eintragen
docker-compose up --build
pip install -r requirements.txt
```

---

## 🗝️ .env Beispiel

```dotenv
LOCATIONIQ_API_KEY=dein_LOCATIONIQ_API_KEY
OPENROUTESERVICE_API_KEY=dein_openrouteservice_key
GEMINI_API_KEY=optional
TIME_ZONE=Europe/Zurich
```

## 🧠 Geo APIs

- 🌍 **Geocoding:** [LOCATIONIQ](https://de.locationiq.com//)
- 🧭 **Routing:** [OpenRouteService](https://openrouteservice.org/)
- 🤖 **Optional – AI:** [Gemini (Google AI)](https://ai.google.dev/)

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

## 📁 Struktur

```text
src/
├── app.py                  # Streamlit UI
├── database.py             # DB-Handling (TinyDB)
├── refresh.py              # Aktualisiert DB aus Files/API
├── geo/                    # Geo-Abfragen + Routing
├── render/                 # UI-Komponenten
└── wg_zimmer_ch/           # Browser-basierter Fetch
```
