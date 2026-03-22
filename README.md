# Armenian Voice AI Support Agent

Local Python project for an Armenian banking support agent that answers only within three supported topics:

- `credits`
- `deposits`
- `branch_locations`

The system uses a local knowledge base built only from official bank websites. Telegram is a text-only demo and fallback surface. The primary target runtime is a self-hosted LiveKit OSS voice agent.

## Architecture

```text
official bank pages
  ->
scraping
  ->
raw JSON
  ->
cleaning
  ->
clean JSON
  ->
chunking + embeddings
  ->
SQLite metadata + local numpy vector store
  ->
SupportAgentService
  ->
conversational flow or retrieval flow
  ->
OpenAI grounded answer generation
  ->
Telegram text demo or LiveKit OSS voice runtime
```

## Why the pipeline is split as raw -> clean -> ingest

- `raw JSON` preserves exactly what was fetched from official sources.
- `clean JSON` separates normalization from fetching and makes reprocessing repeatable.
- `SQLite` stores metadata, source traceability, and active/inactive document state.
- The local numpy vector store keeps embeddings local and lightweight.
- Runtime never scrapes live during user interaction.
- New banks can be added by extending source configs and, when needed, bank-specific extractors.

## Runtime contract

- `Telegram` is a text-only demo and fallback surface.
- `LiveKit OSS` is the primary voice demo runtime.
- `Local web UI` is now the primary room client for local LiveKit voice testing.
- `Telegram voice/audio` is intentionally not supported in the current scope.
- `python -m scripts.run_bot` starts only Telegram text polling.
- `python -m scripts.run_voice_agent --room bank-support-demo` starts only the LiveKit voice runtime.
- `python -m scripts.run_demo_stack --room bank-support-demo` starts both runtimes together under one local supervisor.
- `python -m scripts.run_livekit_test_ui --room bank-support-demo` starts a minimal local browser client for testing the LiveKit voice room.

This process model is explicit because the forensic analysis showed that the earlier confusion was not a shared-state bug between Telegram and LiveKit. The real gap was the absence of a combined launcher for two independent blocking runtimes.

## Current bank coverage

### Acba

- bank-specific extractor for product pages and branches
- child-page expansion from seed pages
- current KB coverage is strongest here

### Ameriabank

- generic extractor for deposits, credits, and service-network page
- current KB coverage is shallower because extraction is still mostly list/static level

### Inecobank

- bank-specific extractor for deposits and consumer-loans list pages
- list-page expansion into per-product detail pages for deposits and consumer loans
- detail pages ingested as first-class sources with section-preserving text
- branches remain excluded from final retrieval because `/en/map` is not yet a stable branch-record source

## Runtime flow

### Conversational flow

The shared service layer now distinguishes four conversational modes:

1. greeting / opener
2. vague in-scope intent that needs clarification
3. supported banking question
4. clearly out-of-scope request

What this means in practice:

- greetings like `Պարև`, `Здравствуйте`, or `Hi` get a short natural reply instead of `unsupported_topic`
- vague banking intents like `Վարկերի մասին հարց ունեմ` or `Где ваши филиалы` get clarification and steering instead of refusal
- supported banking questions still go through retrieval
- only clearly out-of-scope requests get a polite refusal with a return to the supported topics

### Knowledge retrieval flow

For supported banking questions the runtime does:

1. normalize the question
2. detect language
3. classify topic
4. detect bank if possible
5. build a multilingual retrieval query
6. run topic-scoped vector search
7. rerank with hybrid semantic + lexical scoring
8. apply source-aware chunk selection (same page/section first, then adjacent context chunks)
9. diversify results across banks when the user did not specify a single bank, including explicit multi-bank comparison questions
10. generate a natural Armenian answer only from retrieved official evidence

If a requested field is not present in retrieved official data, the answer says so explicitly instead of inventing it.

## Recent changes

### Added files

- `app/runtime/demo_stack.py`
- `app/web_ui/server.py`
- `app/web_ui/static/index.html`
- `app/web_ui/static/app.js`
- `app/web_ui/static/styles.css`
- `scripts/run_demo_stack.py`
- `scripts/run_livekit_test_ui.py`
- `tests/test_runtime_orchestration.py`
- `tests/test_web_ui_server.py`

### Updated code files

- `app/config/settings.py`
- `app/bootstrap.py`
- `app/llm/conversation.py`
- `app/llm/openai_client.py`
- `app/llm/prompts.py`
- `app/llm/service.py`
- `app/logging_utils.py`
- `app/retrieval/classifier.py`
- `app/retrieval/query_utils.py`
- `app/runtime/demo_stack.py`
- `app/telegram_ui/bot.py`
- `app/web_ui/server.py`
- `app/web_ui/static/app.js`
- `app/voice/audio.py`
- `app/voice/livekit_runtime.py`
- `app/voice/providers.py`
- `app/voice/token.py`
- `scripts/run_bot.py`
- `scripts/run_demo_stack.py`
- `scripts/run_livekit_test_ui.py`
- `scripts/run_voice_agent.py`
- `tests/test_classifier.py`
- `tests/test_logging_utils.py`
- `tests/test_openai_runtime_diagnostics.py`
- `tests/test_support_agent_service.py`
- `tests/test_web_ui_client.py`
- `tests/test_voice_runtime.py`
- `tests/test_web_ui_server.py`
- `pyproject.toml`
- `.env.example`

### Why there was a problem

- `run_bot` and `run_voice_agent` were separate long-running blocking entry points
- there was no supervisor/orchestration layer for running Telegram text fallback and LiveKit voice runtime together
- Telegram voice was only a stub
- conversational behavior was too binary and fell into `unsupported_topic` too early for greetings, intros, and vague banking intents
- some quiet or imperfect voice segments were reaching STT unreliably and part of real microphone input ended up as empty transcript
- browser microphone capture was relying on implicit defaults instead of explicit speech-friendly constraints
- voice quality thresholds, normalization targets, and model choices were mostly hardcoded inside runtime code rather than controlled from settings
- `OPENAI_API_KEY` resolution was implicit through `load_dotenv()` plus `os.getenv()`, so a stale process-level environment variable could silently win over the project `.env`
- a LiveKit voice utterance processor could crash on OpenAI STT `429 rate_limit` / `insufficient_quota` instead of degrading gracefully
- the runtime still tolerated weak local JWT secrets, which caused avoidable security warnings
- default logs included too much low-level transport noise compared with the useful room/transcript/answer events
- voice logs did not clearly expose active STT/LLM/TTS config, segmentation decisions, or STT/LLM/TTS latencies
- practical voice-room testing still depended on `meet.livekit.io`, which made local playback/debugging less predictable than a project-owned client
- the first local web UI version relied too heavily on incremental participant/track events and could lose agent audio when track ordering was ahead of local participant reconciliation
- hidden-agent local demo mode could still trigger LiveKit JS participant/track reconciliation issues in the browser even when backend TTS had already been generated

### How it works now

The LiveKit voice agent flow is:

1. connect the agent to a self-hosted LiveKit room, visible by default for local debug/demo and optionally hidden when explicitly enabled
2. use the local web UI as the browser-side room client with explicit microphone capture defaults:
   - `echoCancellation`
   - `noiseSuppression`
   - `autoGainControl`
   - `sampleRate`
   - `channelCount`
3. subscribe to remote microphone audio tracks
4. segment incoming audio into utterances with a lightweight silence detector
5. apply conservative speech-friendly preprocessing before STT:
   - DC offset removal
   - configurable input pre-gain
   - configurable level normalization toward a target dBFS
   - configurable maximum gain cap
   - minimum duration / frame / energy checks before transcription
6. send only speech-like WAV utterances to OpenAI STT with Armenian-first settings
7. if STT returns an empty transcript for a speech-like segment, retry once without a forced language hint
8. if OpenAI STT returns `429 rate_limit` or `insufficient_quota`, keep the processor alive, emit a safe high-level log, and publish a controlled Armenian fallback prompt instead of crashing
9. if the transcript is still empty but the segment still looks like real speech, publish a short Armenian repeat prompt instead of failing silently
10. pass the transcript into the existing `SupportAgentService`
11. let `SupportAgentService` choose conversational vs retrieval flow
12. synthesize the final answer with OpenAI TTS using configurable model, voice, output format, and speaking rate
13. publish synthesized audio back into the same LiveKit room as an audio track

The voice quality path is now settings-driven instead of hardcoded. The runtime logs the active audio/STT/LLM/TTS profile at startup and logs per-turn STT, LLM, and TTS latencies.

### High quality voice mode

Set:

```env
VOICE_HIGH_QUALITY_MODE=true
```

This switches the default voice profile to a quality-first configuration without code edits:

- `OPENAI_STT_MODEL=gpt-4o-transcribe`
- `OPENAI_CHAT_MODEL=gpt-4.1`
- `OPENAI_TTS_MODEL=tts-1-hd`
- slightly longer end-of-utterance delay
- slightly more preroll
- conservative input pre-gain plus normalization toward a stronger target level

You can still override any individual setting explicitly in `.env`.

The shared conversational policy now does:

1. language-aware greeting/help/small-talk handling
2. explicit meta/system answers for supported banks, supported topics, how to ask questions, and why scope is limited
3. clarification-first steering for vague in-scope intents
4. natural Armenian factual answers for supported retrieval hits
5. polite out-of-scope refusal only when the request is truly outside credits, deposits, and branch locations

The logging and runtime hygiene now do:

1. keep high-level voice events visible by default:
   - room connected
   - remote audio subscribed
   - utterance finalized
   - transcript received
   - retrieval/answer summary
   - TTS generated
2. push noisy transport loggers such as `livekit.rtc`, `aioice`, `httpx`, and `websockets` down to a separate transport log level
3. warn once if `LIVEKIT_API_SECRET` is shorter than the recommended length, while still allowing local development
4. resolve `OPENAI_API_KEY` from the project `.env` first, use process environment only as fallback, and log only masked startup diagnostics:
   - key present or missing
   - key length
   - last 8 characters
   - source and process-env conflict flag

The local web UI flow now does:

1. serve a minimal local page from the Python project itself
2. prefill `LIVEKIT_URL` and default room values from backend settings
3. optionally generate a participant token server-side through a local `/api/token` endpoint
4. connect to the LiveKit room from the browser
5. build a local participant store and reconcile it against `room.remoteParticipants`
6. handle both initial room snapshot and later incremental participant/track events
7. attach remote audio immediately on `TrackSubscribed`, even when participant metadata is missing
8. keep pending state only for later participant-label/store reconciliation, not as a playback gate
9. enable or mute the microphone with one button while passing explicit audio capture constraints from backend settings
10. attach and play remote audio tracks from the agent, including hidden/audio-only cases when the SDK still surfaces the track
11. show basic connection, speaker, and event-log state for debugging
12. keep hidden-participant playback best-effort, while defaulting the local demo runtime to a visible agent to avoid browser-side SDK reconciliation glitches

The runtime orchestration flow is:

1. `run_bot` starts Telegram text polling only
2. `run_voice_agent` starts LiveKit room handling only
3. `run_demo_stack` starts both runtimes as separate child processes
4. each runtime logs its startup contract without exposing secrets
5. the supervisor keeps both children alive, stops both on `Ctrl+C`, and fails fast if one child exits unexpectedly

## Environment

Copy `.env.example` to `.env` and fill values.

### Required for backend and voice

```env
OPENAI_API_KEY=your_openai_api_key_here
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=your_livekit_api_key_here
LIVEKIT_API_SECRET=replace_with_a_long_random_secret_at_least_32_chars
DATABASE_URL=sqlite:///./data/bank_support_agent.db
VECTOR_DB_PATH=./data/vector_store
SCRAPER_OUTPUT_DIR=./data
LOG_LEVEL=INFO
VOICE_TRANSPORT_LOG_LEVEL=WARNING
```

### Required only for Telegram demo UI

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

### Optional voice defaults already supported

```env
VOICE_HIGH_QUALITY_MODE=false
OPENAI_CHAT_MODEL=gpt-4.1-mini
OPENAI_CHAT_TEMPERATURE=0.1
OPENAI_CHAT_TOP_P=1.0
OPENAI_CHAT_MAX_COMPLETION_TOKENS=500
OPENAI_CHAT_VERBOSITY=medium
OPENAI_STT_MODEL=gpt-4o-mini-transcribe
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=sage
OPENAI_TTS_RESPONSE_FORMAT=wav
OPENAI_TTS_SPEED=1.0
LIVEKIT_ROOM_NAME=bank-support-demo
LIVEKIT_AGENT_IDENTITY=bank-support-agent
LIVEKIT_AGENT_HIDDEN=false
BROWSER_ECHO_CANCELLATION=true
BROWSER_NOISE_SUPPRESSION=true
BROWSER_AUTO_GAIN_CONTROL=true
BROWSER_AUDIO_SAMPLE_RATE=48000
BROWSER_AUDIO_CHANNEL_COUNT=1
VOICE_INPUT_PRE_GAIN=1.0
VOICE_NORMALIZE_INPUT_AUDIO=true
VOICE_TARGET_INPUT_LEVEL_DBFS=-20.0
VOICE_MAX_INPUT_GAIN_DB=14.0
VOICE_SILENCE_THRESHOLD_DBFS=-36.0
VOICE_MIN_SPEECH_SECONDS=0.35
VOICE_END_OF_UTTERANCE_DELAY_SECONDS=0.75
VOICE_MAX_UTTERANCE_SECONDS=15.0
VOICE_PREROLL_SECONDS=0.2
VOICE_MIN_TRANSCRIPTION_DURATION_SECONDS=0.28
VOICE_MIN_TRANSCRIPTION_RMS_DBFS=-54.0
VOICE_MIN_TRANSCRIPTION_PEAK_DBFS=-36.0
VOICE_STT_RETRY_DURATION_SECONDS=0.7
VOICE_STT_RETRY_RMS_DBFS=-46.0
```

### Optional KB cleaning/retrieval tuning

```env
KB_CLEANING_DEBUG=false
KB_CLEANING_DEBUG_SAMPLE_SIZE=8
KB_CHUNK_MAX_CHARS=1000
KB_CHUNK_OVERLAP_LINES=2
KB_RETRIEVAL_TOP_K=7
KB_RETRIEVAL_CANDIDATE_POOL_SIZE=40
KB_RETRIEVAL_MIN_SCORE=0.2
KB_RETRIEVAL_MIN_COMBINED_SCORE=0.26
KB_RETRIEVAL_MIN_LEXICAL_SCORE=0.12
KB_RETRIEVAL_MAX_CHUNKS_PER_SOURCE=3
KB_RETRIEVAL_ADJACENT_WINDOW=1
KB_RETRIEVAL_DEBUG=false
```

Important:

- store real secrets only in `.env`
- keep `.env.example` placeholder-only
- for this local project, `OPENAI_API_KEY` is resolved from the project `.env` first; process environment is only a fallback and startup logs show the masked source diagnostics
- use a random `LIVEKIT_API_SECRET` with at least 32 characters
- keep `VOICE_TRANSPORT_LOG_LEVEL=WARNING` unless you intentionally want low-level transport/debug logs
- `VOICE_HIGH_QUALITY_MODE=true` switches to a stronger quality-first STT/LLM/TTS profile without code edits
- browser capture defaults come from backend settings and are exposed to the local web UI through `/api/config`

## Local run

### Install

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

### Build the local KB

```powershell
python -m scripts.init_db
python -m scripts.scrape
python -m scripts.clean
python -m scripts.ingest
```

### Run Telegram text demo only

```powershell
python -m scripts.run_bot
```

Expected contract:

- Telegram text questions are supported
- Telegram voice/audio replies with an explicit text-only fallback
- LiveKit is not started by this command

### Run LiveKit voice runtime only

Start the self-hosted LiveKit server:

```powershell
livekit-server --dev
```

Start the voice runtime:

```powershell
python -m scripts.run_voice_agent --room bank-support-demo
```

Optional:

```powershell
python -m scripts.run_voice_agent --room bank-support-demo --hidden-agent
```

Generate a client token for a human tester:

```powershell
python -m scripts.generate_livekit_token --room bank-support-demo --identity local-user
```

Expected contract:

- LiveKit voice runtime starts
- local debug/demo uses a visible agent by default so the browser client can reconcile participant + audio state reliably
- hidden agent mode remains available through `LIVEKIT_AGENT_HIDDEN=true` or `--hidden-agent`
- Telegram is not started by this command

### Run the local web UI for LiveKit testing

```powershell
python -m scripts.run_livekit_test_ui --room bank-support-demo --open-browser
```

Expected contract:

- a local page opens at `http://127.0.0.1:8766`
- the page prefills `LIVEKIT_URL` and room defaults from `.env`
- you can generate a token locally or paste one manually
- you can connect, toggle the microphone, and hear remote audio from the agent
- this replaces the need to use `meet.livekit.io` for local debugging

### Run the combined local demo stack

```powershell
python -m scripts.run_demo_stack --room bank-support-demo
```

This supervisor starts:

- `python -m scripts.run_bot`
- `python -m scripts.run_voice_agent --room bank-support-demo`

Expected contract:

- both runtimes log separate startup messages
- Telegram remains text-only
- LiveKit remains the voice path
- `Ctrl+C` stops both child processes
- if one child exits unexpectedly, the supervisor stops the other and returns a non-zero exit code

## How to refresh bank data

```powershell
python -m scripts.scrape
python -m scripts.clean
python -m scripts.ingest
```

Ingestion updates changed sources by `content_hash`. The current ingestion logic also auto-rebuilds unchanged sources when it detects legacy chunk metadata or missing vectors, so older KB snapshots migrate forward without manual DB reset.

## How to verify

### Automated tests

```powershell
pytest -q
```

Current result:

- `70 passed`

### Startup and orchestration smoke checks

```powershell
python -m scripts.run_bot
python -m scripts.run_voice_agent --room smoke-room
python -m scripts.run_livekit_test_ui --room smoke-room
python -m scripts.run_demo_stack --room smoke-room
```

What to look for in logs:

- Telegram text runtime announces that Telegram voice is not supported
- LiveKit runtime announces room, identity, and voice configuration at a high level
- LiveKit runtime logs the active quality profile, input/output audio format, segmentation thresholds, normalization settings, and STT/LLM/TTS model selection
- the local web UI exposes room connection status, mic state, remote audio elements, and an event log
- combined stack announces both runtimes and supervises child lifecycle
- utterance-level logs show finalized speech segments, segmentation end reason, gain staging, and transcript/answer progress
- STT, LLM, and TTS logs show per-turn latency
- low-level RTT/ping/transport noise stays hidden unless you lower `VOICE_TRANSPORT_LOG_LEVEL`

### Voice bootstrap and token flow

```powershell
python -m scripts.generate_livekit_token --room smoke-room --identity smoke-user
python -c "from app.bootstrap import build_settings, build_voice_runtime; s=build_settings(); r=build_voice_runtime(s); print(type(r).__name__, r.room_name, r.agent_identity)"
python -c "from app.bootstrap import build_settings; import json; s=build_settings(); print(json.dumps(s.openai_api_key_diagnostics()))"
python -c "from app.bootstrap import build_settings, build_livekit_test_ui_server, build_voice_runtime; s=build_settings(); server=build_livekit_test_ui_server(s); r=build_voice_runtime(s); print({'voice_high_quality_mode': s.voice_high_quality_mode, 'stt_model': s.openai_stt_model, 'llm_model': s.openai_chat_model, 'tts_model': s.openai_tts_model, 'tts_voice': s.openai_tts_voice, 'tts_format': s.openai_tts_response_format, 'tts_speed': s.openai_tts_speed, 'browser_capture': server.build_client_config()['audioCaptureOptions'], 'runtime_target_input_level_dbfs': r.target_input_level_dbfs, 'runtime_silence_threshold_dbfs': r.silence_threshold_dbfs})"
```

### Local end-to-end voice flow

1. start `livekit-server --dev`
2. run `python -m scripts.run_voice_agent --room bank-support-demo` or `python -m scripts.run_demo_stack --room bank-support-demo`
3. run `python -m scripts.run_livekit_test_ui --room bank-support-demo --open-browser`
4. in the browser page, click `Generate token` if the local server has LiveKit credentials, or paste a token manually
5. click `Connect`, allow microphone access, and if needed click `Resume audio`
6. if you started `run_demo_stack`, verify that Telegram text replies still work in parallel
7. ask questions such as:
   - `Պարև`
   - `Վարկերի մասին հարց ունեմ`
   - `Ի՞նչ ավանդներ կան։`
   - `Որքա՞ն է նվազագույն գումարը ավանդ բացելու համար։`
   - `Որտե՞ղ է մոտակա մասնաճյուղը։`
   - `Ինչ եղանակ է այսօր`

Expected behavior:

- small-talk should stay conversational and not hit retrieval
- meta/system questions should get natural explanatory answers without leaving the banking scope
- vague banking intents should trigger clarification before refusal
- supported banking questions should go through retrieval
- mixed Armenian + English product-name questions should still retrieve relevant chunks
- refusal should happen only when the request is truly outside the supported banking scope or when official evidence is genuinely missing
- internal debug labels must not appear in final spoken or text responses
- quiet but speech-like utterances should normalize better before STT
- empty transcript cases should either recover on retry or get a short Armenian repeat prompt instead of failing silently
- hidden/audio-only agent playback should still attach and play even if `TrackSubscribed` arrives before any participant object is available locally

### What was actually verified in this update

- `pytest -q` passed with `70 passed`
- `python -m scripts.generate_livekit_token --room smoke-room --identity smoke-user` produced a valid token
- `build_voice_runtime()` bootstrap completed successfully
- `build_livekit_test_ui_server(...).build_client_config()` now exposes browser capture defaults and quality mode
- masked OpenAI key diagnostics now show the runtime source-of-truth and conflict state, for example:
  - `{\"present\": true, \"length\": 164, \"tail\": \"OoWswI0A\", \"source\": \".env\", \"process_env_conflict\": true, ...}`
- a runtime smoke-check confirmed the currently active local defaults:
  - `voice_high_quality_mode=False`
  - `stt_model=gpt-4o-mini-transcribe`
  - `llm_model=gpt-4.1-mini`
  - `tts_model=gpt-4o-mini-tts`
  - `tts_format=wav`
  - `tts_speed=1.0`
  - `browser_capture={echoCancellation: true, noiseSuppression: true, autoGainControl: true, sampleRate: 48000, channelCount: 1}`
- `python -m scripts.run_livekit_test_ui --help` completed successfully
- localhost smoke check for `http://127.0.0.1:8777/api/config` returned the expected `LIVEKIT_URL` and room name
- `run_bot`, `run_voice_agent`, and `run_demo_stack` startup contracts are covered by smoke tests
- local web UI server tests now cover config defaults, server-side token generation, and startup wiring
- local web UI client tests now cover:
  - immediate remote-audio attach when `TrackSubscribed` arrives without a participant object
  - later participant metadata reconciliation after orphan audio attach
  - immediate playback attach even when no participant ever appears in the browser snapshot/store
  - initial snapshot reconciliation for an already-present hidden audio-only agent participant
- `DemoStackSupervisor` startup and shutdown semantics are covered by tests
- weak LiveKit secrets now produce one clear app-level warning instead of repeated low-level JWT noise
- Telegram voice/audio fallback explicitly says that Telegram is text-only and that LiveKit is the supported voice path
- greetings like `Պարև` now stay conversational instead of falling into `unsupported_topic`
- vague Armenian banking intents now trigger clarification instead of a hard refusal
- meta/system questions about supported banks, how to ask, and why scope is limited are covered by tests
- voice runtime tests now cover quiet-segment normalization, STT retry without forced language, and repeat-prompt fallback after empty transcript
- OpenAI client tests now cover configured chat generation params and TTS speed/format wiring
- settings tests now cover `VOICE_HIGH_QUALITY_MODE` profile defaults
- local web UI client tests now cover explicit microphone capture defaults on connect
- voice runtime tests now cover STT `insufficient_quota` fallback without crashing the utterance processor
- voice runtime now defaults to a visible agent for local debug/demo and keeps hidden mode as an explicit opt-in
- runtime tests now cover visible-by-default local demo mode and explicit hidden-agent override
- logging tests now verify that noisy transport loggers are pushed down to the configured transport log level

## Limitations

- `Inecobank` branches are still pending because `/en/map` does not yet expose a stable branch-record source for ingestion.
- `Ameriabank` deposits and consumer-loan coverage is still shallow in the current KB because extraction still captures mostly list-level/static content, not full product-detail fields.
- `Inecobank` deposits and consumer loans now ingest detail pages, but some product pages still do not expose exact rate tables/limits in static HTML.
- `Inecobank` deposits list-page scraping can intermittently hit Cloudflare `403` from this environment; previously scraped detail pages remain usable in KB, but fresh refresh may need retry.
- The current voice runtime still uses a lightweight silence detector, not a production-grade VAD/turn detector.
- Audio preprocessing is intentionally conservative; it adds gain staging and normalization for STT, but it is not a full DSP, denoiser, or acoustic echo cancellation pipeline on the Python side.
- The local web UI is intentionally minimal and focused on room connection, microphone control, remote audio playback, and event logging, not on polished product UX.
- The browser test UI currently loads the LiveKit JS SDK from a pinned CDN URL, so first load still needs internet access unless you vendor the SDK locally later.
- Browser capture constraints such as `echoCancellation`, `noiseSuppression`, and `autoGainControl` are best-effort browser/WebRTC hints, not hard guarantees.
- The transcript panel is best-effort only; it will show transcription events if the room emits them, but the current backend does not publish a dedicated transcript stream.
- Hidden-agent playback remains best-effort because it depends on LiveKit browser SDK event ordering; local demo now defaults to a visible agent to avoid this failure mode.
- Telegram remains a text-only demo UI and not the main voice architecture.
- Conversational steering is softer and language-aware for Armenian, Russian, and English openers, but the assistant still remains strictly limited to credits, deposits, and branch locations.
- Grounded factual answers remain Armenian-first; multilingual behavior is mainly for greeting, clarification, and polite steering.

## What needs to be sent

If deeper KB coverage or a fully self-contained local demo is required, these exact gaps remain:

- `Inecobank`
  - page: `https://www.inecobank.am/en/Individual/deposits/simple`
  - missing fields in KB: exact interest rate, currencies, minimum amount, term for `Simple Deposit`
  - needed: stable detail-page selectors for rate/currency/min-amount/term, or the XHR/JSON response used to populate these fields
- `Inecobank`
  - page: `https://www.inecobank.am/en/map`
  - missing fields in KB: final branch records and schedules
  - needed: stable branch-card DOM selectors or XHR/JSON response sample with branch data
- `Ameriabank`
  - page: `https://ameriabank.am/en/personal/saving/deposits/see-all`
  - missing fields in KB: deposit currencies, minimum amount, detailed conditions per product
  - needed: selectors for product-detail cards/pages, or XHR/JSON response sample for deposit detail data
- `Ameriabank`
  - page: `https://ameriabank.am/en/personal/loans/consumer-loans/consumer-loans`
  - missing fields in KB: detailed consumer-loan conditions per product
  - needed: selectors for per-product detail sections/pages, or XHR/JSON response sample
- `Ameriabank`
  - page: `https://ameriabank.am/en/service-network`
  - missing fields in KB: full branch list beyond head office
  - needed: stable branch-list selectors or XHR/JSON response sample for service-network data
