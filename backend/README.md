# VeyaCare backend

FastAPI serves the doctor and appointment APIs and creates one Pipecat pipeline per SmallWebRTC connection. The voice path is SmallWebRTC audio input → ElevenLabs realtime STT → Silero VAD and Pipecat user context → Gemini function calling → ElevenLabs streaming TTS → SmallWebRTC audio output. SQLite and SQLAlchemy store doctors, slots, and appointments; startup creates the tables and seeds sample data if no doctors exist.

## Requirements and setup

The tested environment uses Python 3.12 and Pipecat 1.17.0. Install dependencies in a virtual environment:

```powershell
cd "D:\Voice AI Doc\backend"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `GOOGLE_API_KEY`, `ELEVENLABS_API_KEY`, and `ELEVENLABS_VOICE_ID`. `GEMINI_MODEL` defaults to `gemini-2.5-flash`. Keys stay on the backend and are not returned to API clients. Do not commit `.env`.

Start the backend from the `backend` directory so SQLite uses `backend/appointments.db`:

```powershell
cd "D:\Voice AI Doc\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## HTTP API

- `GET /` and `GET /health`
- `GET /api/doctors`
- `GET /api/availability?speciality=Cardiology&date=YYYY-MM-DD`
- `POST /api/appointments` with `phone_number` (string), `doctor_id`, `slot_id`, and optional `patient_name`
- `POST /api/appointments/cancel` with `phone_number` and `appointment_id`
- `GET /api/appointments?phone_number=...`
- `POST /api/offer` and `PATCH /api/offer` for SmallWebRTC negotiation and ICE updates

HTTP appointment operations accept a caller-supplied phone number; they do not authenticate the caller. Cancellation checks that the supplied number matches the stored appointment.

## Voice tools and confirmations

Gemini receives Pipecat standard `FunctionSchema` tools for availability, listing active appointments, setting/confirming a phone number, booking, and cancellation. Each call has its own `PipelineTask.app_resources` state. The frame processor records only final ElevenLabs transcriptions; an explicit affirmative transcript grants one confirmation for the exact staged details, and a later caller utterance revokes an unused grant. Booking also requires the same confirmed phone and an actually available doctor/slot; cancellation verifies the appointment and phone before asking for confirmation. Tool handlers return results through Pipecat's awaited `FunctionCallParams.result_callback`, which the assistant context aggregator adds to context before the next Gemini run.

The Google service uses Pipecat 1.17's `stream_idle_timeout_secs` and `retry_timeout_secs` settings. The former bounds gaps between streamed chunks (including initial output); the latter is used for the first chunk only when `retry_on_timeout=True`. The voice pipeline allows a 90-second stream gap and one retry after a 30-second first-chunk wait. Silero VAD uses a 600 ms stop threshold to avoid splitting normal pauses, with a 5-second user-turn stop grace period. These are starting values; audio-device gain and background noise still need live-call tuning.

This is a speech-based safeguard, not identity verification. STT can mishear speech, and another person may speak or repeat a phone number. The phone number and spoken yes do not prove the caller owns the number. Use a stronger authentication process if the service needs identity assurance.

## Local verification

Run the backend checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests use temporary SQLite databases and mocked provider constructors; they do not make provider calls.

## Limitations

No live provider voice call was made as part of local verification; that requires valid provider credentials and browser audio. The current CORS allowlist is `http://localhost:5173`. Sample availability dates are generated at first initialization. The HTTP endpoints themselves do not require spoken confirmation.
