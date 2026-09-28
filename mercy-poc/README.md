# Mercy — Compassionate Voice AI Agent (POC)

Mercy is a proof-of-concept compassionate voice AI agent built with Flutter, Firebase, and Python Cloud Functions. It provides real-time voice conversations powered by speech-to-text, large language models, and text-to-speech, with built-in safety monitoring at every step.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Client Layer                               │
│                                                                     │
│   ┌───────────────┐        ┌──────────────────────────────────┐     │
│   │  Flutter App   │───────▶│  Firebase Hosting (app/build/web) │     │
│   │  (Web/Mobile)  │        └──────────────────────────────────┘     │
│   └───────┬───────┘                                                 │
│           │  HTTPS / gRPC                                           │
└───────────┼─────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Firebase Cloud Functions (Python 3.12)        │
│                                                                     │
│   ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│   │ start_session │  │ process_audio│  │ get_session_metrics    │   │
│   └──────┬───────┘  └──────┬───────┘  └────────────┬───────────┘   │
│          │                 │                        │               │
│          │    ┌────────────┴────────────┐           │               │
│          │    │    Voice AI Pipeline     │           │               │
│          │    │                          │           │               │
│          │    │  ┌─────┐ ┌─────┐ ┌────┐ │           │               │
│          │    │  │ STT │▶│ LLM │▶│TTS │ │           │               │
│          │    │  └──┬──┘ └──┬──┘ └─┬──┘ │           │               │
│          │    │     │       │      │     │           │               │
│          │    │  ┌──┴───────┴──────┴──┐  │           │               │
│          │    │  │   Safety Checker   │  │           │               │
│          │    │  └────────────────────┘  │           │               │
│          │    └─────────────────────────┘           │               │
│          │                                          │               │
└──────────┼──────────────────────────────────────────┼───────────────┘
           │                                          │
           ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Cloud Firestore                            │
│                                                                     │
│   ┌───────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────────┐  │
│   │ /sessions │  │ /transcripts │  │ /metrics │  │/safety_logs │  │
│   │           │  │ (subcoll.)   │  │          │  │             │  │
│   └───────────┘  └──────────────┘  └──────────┘  └─────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

External Providers:
  ├── Deepgram / Google Cloud STT   (Speech-to-Text)
  ├── OpenAI GPT / Google Gemini    (LLM)
  └── ElevenLabs / Google Cloud TTS (Text-to-Speech)
```

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Flutter | 3.22+ | [flutter.dev/docs/get-started](https://flutter.dev/docs/get-started/install) |
| Python | 3.12+ | [python.org](https://www.python.org/downloads/) |
| Firebase CLI | 13+ | `npm install -g firebase-tools` |
| Node.js | 18+ | Required by Firebase CLI |

## Project Structure

```
mercy-poc/
├── app/                          # Flutter application
│   ├── lib/
│   │   ├── config/
│   │   │   └── app_config.dart   # Firebase & API configuration
│   │   ├── models/
│   │   │   ├── session.dart      # Session data model
│   │   │   └── metrics.dart      # Metrics data model
│   │   ├── services/             # Firebase, audio, API services
│   │   ├── screens/              # UI screens
│   │   └── widgets/              # Reusable components
│   ├── pubspec.yaml
│   └── analysis_options.yaml
│
├── functions/                    # Python Cloud Functions
│   ├── main.py                   # Function entry points
│   ├── requirements.txt
│   └── pipeline/
│       ├── __init__.py
│       ├── stt.py                # Speech-to-Text integration
│       ├── llm.py                # LLM conversation engine
│       ├── tts.py                # Text-to-Speech synthesis
│       └── safety.py             # Safety checking layer
│
├── firebase.json                 # Firebase project configuration
├── firestore.rules               # Firestore security rules
├── firestore.indexes.json        # Composite index definitions
├── .firebaserc                   # Firebase project alias
├── .env.example                  # Environment variable template
├── .gitignore
└── README.md
```

## Setup

### 1. Clone and Configure Environment

```bash
git clone <repo-url> mercy-poc
cd mercy-poc
cp .env.example .env
# Edit .env with your actual project ID and API keys
```

### 2. Firebase Setup

```bash
firebase login
firebase use --add          # Select or create your Firebase project
firebase projects:list      # Verify project is linked
```

Update `.firebaserc` with your actual Firebase project ID.

### 3. Flutter App Setup

```bash
cd app
flutter pub get
flutter build web           # Build for Firebase Hosting
```

### 4. Python Functions Setup

```bash
cd functions
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Running Locally

Start all Firebase emulators to develop without touching production:

```bash
firebase emulators:start
```

| Emulator | URL |
|----------|-----|
| Hosting | http://localhost:5000 |
| Functions | http://localhost:5001 |
| Firestore | http://localhost:8080 |
| Auth | http://localhost:9099 |
| Emulator UI | http://localhost:4000 |

For Flutter web development with hot reload against emulators:

```bash
cd app
flutter run -d chrome --web-port=8888
```

The app's `app_config.dart` should detect the emulator environment and connect automatically.

## Deployment

### Deploy Everything

```bash
flutter build web --release -t lib/main.dart   # from app/
cd ..
firebase deploy
```

### Deploy Individual Components

```bash
firebase deploy --only hosting
firebase deploy --only functions
firebase deploy --only firestore:rules
firebase deploy --only firestore:indexes
```

## Cloud Functions API

All functions are deployed to the region specified by `FUNCTIONS_REGION` (default: `us-central1`).

### `start_session`

Creates a new conversation session.

| Field | Value |
|-------|-------|
| **Type** | HTTPS Callable |
| **Auth** | Required (Firebase Auth) |

**Request:**
```json
{
  "data": {
    "userId": "string",
    "config": {
      "sttProvider": "deepgram | google",
      "llmProvider": "openai | google",
      "ttsProvider": "elevenlabs | google"
    }
  }
}
```

**Response:**
```json
{
  "result": {
    "sessionId": "string",
    "status": "active",
    "startTime": "ISO-8601"
  }
}
```

### `process_audio`

Processes a user audio turn through the full STT → LLM → TTS pipeline with safety checks.

| Field | Value |
|-------|-------|
| **Type** | HTTPS Callable |
| **Auth** | Required (Firebase Auth) |

**Request:**
```json
{
  "data": {
    "sessionId": "string",
    "audioBase64": "string (base64-encoded audio)",
    "mimeType": "audio/webm"
  }
}
```

**Response:**
```json
{
  "result": {
    "transcriptIn": "string (user speech)",
    "responseText": "string (agent reply)",
    "audioBase64": "string (base64-encoded reply audio)",
    "safetyFlags": [],
    "turnNumber": 1
  }
}
```

### `get_session_metrics`

Retrieves aggregated metrics for a session (admin only).

| Field | Value |
|-------|-------|
| **Type** | HTTPS Callable |
| **Auth** | Required (admin custom claim) |

**Request:**
```json
{
  "data": {
    "sessionId": "string"
  }
}
```

**Response:**
```json
{
  "result": {
    "sessionId": "string",
    "totalTurns": 12,
    "avgLatencyMs": 1450,
    "safetyFlagCount": 0,
    "sttProvider": "deepgram",
    "llmProvider": "openai",
    "ttsProvider": "elevenlabs"
  }
}
```

## Firestore Data Model

### `/sessions/{sessionId}`

| Field | Type | Description |
|-------|------|-------------|
| `userId` | string | Firebase Auth UID of the session owner |
| `status` | string | `active`, `completed`, `flagged` |
| `startTime` | timestamp | Session creation time |
| `endTime` | timestamp | Session end time (null if active) |
| `config` | map | Provider configuration for this session |
| `turnCount` | number | Total conversation turns |
| `safetyFlagCount` | number | Number of safety flags raised |

### `/sessions/{sessionId}/transcripts/{transcriptId}`

| Field | Type | Description |
|-------|------|-------------|
| `turnNumber` | number | Sequential turn index |
| `userText` | string | STT transcription of user speech |
| `agentText` | string | LLM-generated response |
| `timestamp` | timestamp | When this turn occurred |
| `latencyMs` | number | End-to-end pipeline latency |
| `safetyFlags` | array | Any safety flags for this turn |

### `/metrics/{metricId}`

| Field | Type | Description |
|-------|------|-------------|
| `sessionId` | string | Reference to parent session |
| `totalTurns` | number | Total turns in session |
| `avgLatencyMs` | number | Average pipeline latency |
| `sttProvider` | string | STT provider used |
| `llmProvider` | string | LLM provider used |
| `ttsProvider` | string | TTS provider used |
| `createdAt` | timestamp | When metrics were computed |

### `/safety_logs/{logId}`

| Field | Type | Description |
|-------|------|-------------|
| `sessionId` | string | Session that triggered the flag |
| `turnNumber` | number | Which turn was flagged |
| `flagType` | string | Category: `self_harm`, `violence`, `crisis`, etc. |
| `severity` | string | `low`, `medium`, `high`, `critical` |
| `inputText` | string | The text that triggered the flag |
| `action` | string | Action taken: `logged`, `redirected`, `terminated` |
| `timestamp` | timestamp | When the flag was raised |

### `/users/{userId}`

| Field | Type | Description |
|-------|------|-------------|
| `displayName` | string | User display name |
| `email` | string | User email |
| `createdAt` | timestamp | Account creation time |
| `lastActive` | timestamp | Last session activity |
| `sessionCount` | number | Total sessions created |

## Safety Checks

Every conversation turn passes through a safety checking layer **before** the response is delivered to the user. The pipeline:

1. **Input Check** — User speech transcription is scanned for crisis indicators, self-harm language, and violent content.
2. **Output Check** — The LLM response is validated to ensure it does not contain harmful, misleading, or clinically inappropriate content.
3. **Action Routing** — Based on severity:
   - `low` — Flag is logged, conversation continues normally.
   - `medium` — Flag is logged, agent gently steers conversation.
   - `high` — Agent provides crisis resource information.
   - `critical` — Session is terminated, crisis resources are displayed immediately.

All safety events are written to `/safety_logs` via the Admin SDK (server-side only — no client write access).

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FIREBASE_PROJECT_ID` | Yes | Firebase project identifier |
| `FIREBASE_API_KEY` | Yes | Firebase web API key |
| `FIREBASE_AUTH_DOMAIN` | Yes | Firebase Auth domain |
| `FIREBASE_STORAGE_BUCKET` | Yes | Cloud Storage bucket |
| `OPENAI_API_KEY` | If using OpenAI | OpenAI API key for GPT |
| `GOOGLE_CLOUD_PROJECT` | If using Google | GCP project for STT/TTS/Gemini |
| `DEEPGRAM_API_KEY` | If using Deepgram | Deepgram STT API key |
| `ELEVENLABS_API_KEY` | If using ElevenLabs | ElevenLabs TTS API key |
| `SAFETY_CHECK_ENABLED` | No | Enable/disable safety layer (default: `true`) |
| `SAFETY_LOG_LEVEL` | No | Logging verbosity (default: `INFO`) |
| `FUNCTIONS_REGION` | No | Cloud Functions region (default: `us-central1`) |

## License

This is a proof-of-concept project. See LICENSE for details.
