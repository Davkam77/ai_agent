# Project Context

Updated: `2026-03-22`

This file records the current engineering state of the project after the runtime orchestration remediation. The main deliverable remains a LiveKit OSS end-to-end Armenian voice banking agent. Telegram remains a text-only demo and fallback surface.

## Project goal

Build a local AI support agent for Armenian banks with these boundaries:

- Python backend
- knowledge base only from official bank sources
- only three supported topics:
  - `credits`
  - `deposits`
  - `branch_locations`
- no live scraping in runtime
- Telegram only as a demo/fallback UI
- primary voice target is self-hosted LiveKit OSS
- local browser-based LiveKit test UI is now part of the repo for practical voice-room verification

## End-to-end flow

```text
scrape
  ->
raw JSON
  ->
clean
  ->
clean JSON
  ->
chunk + embed
  ->
SQLite + local vector store
  ->
SupportAgentService
  ->
conversational flow or retrieval flow
  ->
OpenAI grounded answer
  ->
Telegram text demo, local LiveKit test UI, or LiveKit OSS voice runtime
```

## Runtime contracts

### Bootstrap

`app/bootstrap.py`

- loads settings
- resolves the project `.env` explicitly through `Settings.from_env()`
- initializes runtime directories
- initializes SQLite and vector store when needed
- wires `TopicClassifier`, `RetrievalService`, and `SupportAgentService`
- builds `LiveKitVoiceRuntime` with OpenAI STT/TTS providers and the existing support backend
- now also builds `DemoStackSupervisor` for the combined local demo stack

### Scraping

`app/scraping/service.py`

- reads `SourceConfig` from `app/scraping/sources.py`
- uses bank-specific or generic extractor
- writes `RawDocument` files under `data/raw`

### Cleaning

`app/cleaning/service.py`

- reads raw JSON
- normalizes text via `TextCleaner`
- writes `CleanDocument` files under `data/clean`
- converts helper pages to tombstone clean JSON when the source should not stay retrievable

### Ingestion

`app/ingestion/service.py`

- reads clean JSON
- compares `content_hash`
- deactivates old source rows when needed
- chunks text
- computes embeddings
- writes metadata to SQLite
- writes vectors to local numpy vector store

### Retrieval

`app/retrieval/service.py`

- normalizes the question
- detects language
- detects optional bank filter
- builds a multilingual retrieval query
- runs topic-scoped vector search
- reranks candidates with hybrid semantic + lexical scoring
- diversifies selected results across banks when the question is generic and no bank is specified
- returns internal debug metadata only

### LLM layer

`app/llm/service.py`

- routes greetings and openers into natural conversational replies
- routes vague in-scope intents into clarification-first steering
- routes supported-domain questions into retrieval
- keeps clearly out-of-scope requests as polite refusal plus steering back to the supported topics
- sanitizes final answer text before returning it to the user
- keeps debug metadata internal

### Telegram runtime

`app/telegram_ui/bot.py`

- registers one text handler and one voice/audio handler
- forwards text to `SupportAgentService`
- has an in-memory duplicate-update guard
- ensures one final reply per processed update/message
- is explicitly text-only now
- returns a clear fallback for Telegram voice/audio that points users to LiveKit for voice testing

### Voice runtime

`app/voice/livekit_runtime.py`

- joins a LiveKit room as a visible agent by default for local debug/demo, with hidden mode still available explicitly
- subscribes to remote audio tracks
- segments incoming audio with a lightweight silence detector
- preprocesses utterances before STT with DC offset removal and simple level normalization
- skips obviously empty or too-short segments before STT
- retries STT once without a forced language hint when a speech-like segment comes back empty
- uses OpenAI STT for Armenian-first transcription
- handles OpenAI STT `429 rate_limit` / `insufficient_quota` as a controlled runtime fallback instead of crashing the utterance processor
- routes transcript text into the existing `SupportAgentService`
- publishes a short Armenian repeat prompt when speech-like audio still produces an empty transcript
- publishes a short Armenian service-unavailable prompt when STT quota/rate-limit blocks transcription
- uses OpenAI TTS for Armenian speech synthesis
- publishes synthesized audio back into the same LiveKit room

### Local web UI

`app/web_ui/server.py`

- serves a minimal local browser client from the Python project itself
- exposes `/api/config` for default `LIVEKIT_URL` and room settings
- exposes `/api/token` for local participant token generation without leaking secrets to the browser
- keeps the client scope narrow: connection status, mic toggle, remote audio playback, and basic event log
- the browser client keeps a participant store, pending-track reconciliation map, and initial room snapshot handling for reliable remote audio playback
- remote audio playback does not depend on participant visibility in the local UI store; orphan audio tracks attach immediately and reconcile metadata later
- local debug/demo now defaults the agent to visible mode because hidden-agent browser playback can still hit SDK-side participant reconciliation issues

### Combined demo supervisor

`app/runtime/demo_stack.py`

- launches Telegram text demo and LiveKit voice runtime as separate child processes
- validates that combined mode has both Telegram and LiveKit/OpenAI settings
- logs high-level startup configuration without exposing secrets
- stops both children on `Ctrl+C`
- treats unexpected child exit as a supervisor failure and shuts down the remaining runtime

## Process model

The runtime model is now explicit:

1. `python -m scripts.run_bot`
   - Telegram text only
2. `python -m scripts.run_voice_agent --room bank-support-demo`
   - LiveKit voice only
3. `python -m scripts.run_livekit_test_ui --room bank-support-demo`
   - local browser client for room testing
4. `python -m scripts.run_demo_stack --room bank-support-demo`
   - combined local demo stack

Important architectural point:

- starting LiveKit voice does not implicitly start Telegram
- starting Telegram does not implicitly start LiveKit
- the previous confusion was caused by the absence of a combined launcher, not by shared-state corruption between runtimes

## What changed in this update

### Added

- `app/runtime/demo_stack.py`
- `app/web_ui/server.py`
- `app/web_ui/static/index.html`
- `app/web_ui/static/app.js`
- `app/web_ui/static/styles.css`
- `scripts/run_demo_stack.py`
- `scripts/run_livekit_test_ui.py`
- `tests/test_runtime_orchestration.py`
- `tests/test_web_ui_server.py`

### Changed

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
- `.env.example`
- `pyproject.toml`
- `tests/test_classifier.py`
- `tests/test_logging_utils.py`
- `tests/test_openai_runtime_diagnostics.py`
- `tests/test_support_agent_service.py`
- `tests/test_web_ui_client.py`
- `tests/test_voice_runtime.py`
- `tests/test_web_ui_server.py`
- `README.md`
- `PROJECT_CONTEXT.md`

## Why the problem existed

The project already had:

- scraping
- cleaning
- ingestion
- retrieval
- OpenAI answer generation
- Telegram text runtime
- LiveKit voice runtime

But it still lacked:

- a supervisor/orchestration layer for keeping Telegram text demo and LiveKit voice runtime alive together
- explicit operational messaging that Telegram is text-only and that Telegram voice is not part of the current scope
- test coverage for separate runtime entry points versus combined runtime startup
- a softer conversational policy for greetings, intros, and vague banking intents, so the assistant was falling into `unsupported_topic` too early
- stronger voice robustness around quiet / imperfect microphone input, so speech-like segments would not disappear into empty transcript as often
- browser microphone capture still depended on implicit browser/WebRTC defaults rather than explicit speech-friendly constraints
- voice quality thresholds, normalization targets, and model choices were mostly hardcoded inside runtime code instead of being controlled from settings
- an explicit, inspectable source-of-truth for `OPENAI_API_KEY`, so a stale process-level environment variable would not silently override the project `.env`
- clearer meta/system answers for scope questions such as supported banks, supported topics, and why some requests are refused
- log-level separation between useful high-level runtime events and noisy low-level transport logs
- structured voice diagnostics for segmentation decisions and STT/LLM/TTS latency were missing
- explicit JWT secret hygiene guidance for local LiveKit dev
- a project-owned local room client, so voice testing no longer depends on `meet.livekit.io`
- a browser-side participant/track reconciliation layer, so hidden agent audio is not lost when event ordering is unstable
- a local debug-mode visibility toggle for the LiveKit agent, so browser playback is not blocked by hidden-participant SDK edge cases

## How it works now

### Voice path

1. `scripts/run_voice_agent.py` starts the LiveKit runtime.
2. `build_voice_runtime()` wires:
   - `OpenAISTTProvider`
   - `SupportAgentLLMProvider`
   - `OpenAITTSProvider`
   - `LiveKitVoiceRuntime`
3. The runtime creates a LiveKit access token internally with room-join grants and a visible-by-default local demo identity.
4. The agent connects to the room and publishes a local audio track for responses.
5. Incoming remote audio is segmented into utterances.
6. Each utterance is preprocessed and checked for duration, frame count, and energy before STT.
7. Speech-like but quiet segments are prepared with conservative gain staging:
   - DC offset removal
   - configurable input pre-gain
   - optional normalization toward a target input dBFS
   - a configurable maximum gain cap
8. Each utterance is transcribed with OpenAI STT.
9. If STT returns an empty transcript for a speech-like segment, the runtime retries once without a forced language hint.
10. If STT returns `429 rate_limit` or `insufficient_quota`, the runtime logs a safe high-level reason and publishes a controlled Armenian fallback prompt instead of crashing the processor.
11. If the transcript is still empty, the runtime can publish a short Armenian repeat prompt instead of silently failing.
12. The transcript is passed unchanged into the existing `SupportAgentService`.
13. `SupportAgentService` decides:
   - conversational flow
   - retrieval flow
   - refusal
   - meta/system answer
14. The final sanitized Armenian answer is synthesized with OpenAI TTS using configurable model, voice, response format, and speaking rate.
15. The synthesized audio is published back to the room.

For local browser testing, `LIVEKIT_AGENT_HIDDEN=false` is now the default so the LiveKit JS client can reconcile participant state and remote audio more reliably. Hidden mode remains available as an explicit opt-in.

The runtime now logs:

- the active voice quality profile at startup
- input and output audio format
- segmentation thresholds and normalization targets
- per-turn STT latency
- per-turn LLM latency
- per-turn TTS latency

### Combined demo path

1. `scripts/run_demo_stack.py` loads settings and configures logging.
2. `build_demo_stack_supervisor()` builds `DemoStackSupervisor`.
3. The supervisor spawns:
   - `python -m scripts.run_bot`
   - `python -m scripts.run_voice_agent --room ... --identity ...`
4. Both child processes inherit the current environment.
5. The supervisor polls both children, stops both on shutdown, and fails fast if either child exits unexpectedly.

### Local web UI path

1. `scripts/run_livekit_test_ui.py` starts a small local HTTP server.
2. The server provides:
   - `/`
   - `/app.js`
   - `/styles.css`
   - `/api/config`
   - `/api/token`
3. The browser client loads default room settings from `/api/config`.
4. The browser also receives explicit microphone capture defaults from `/api/config`:
   - `echoCancellation`
   - `noiseSuppression`
   - `autoGainControl`
   - `sampleRate`
   - `channelCount`
5. The browser can either paste a token manually or ask the local server to mint one.
6. The client builds a local participant store and reconciles it against `room.remoteParticipants`.
7. The client attaches remote audio immediately on `TrackSubscribed`, even if no participant object is available yet.
8. Pending state is used only for later participant metadata reconciliation, not as an audio-playback gate.
9. The client can still recover from `track before participant` ordering by reconciling pending or snapshot state later.
10. The client connects to the room, toggles the microphone with explicit capture options, attaches remote audio tracks, and shows high-level event/debug state.

### Shared conversational policy

The shared `SupportAgentService` behavior is now:

1. greeting / opener
   - short natural reply
   - no refusal
   - introduces the supported banking scope
2. meta/system question
   - explains who the agent is
   - lists supported banks and supported topics
   - explains how to ask questions
   - explains why unsupported requests are refused
3. vague in-scope intent
   - clarification-first steering
   - asks for bank, product, city, or branch detail when needed
4. supported banking question
   - existing retrieval flow
   - natural Armenian answer style
5. clearly out-of-scope request
   - polite refusal
   - steers the user back to credits, deposits, or branch locations

This policy is shared by Telegram text and LiveKit voice because both runtimes call the same `SupportAgentService`.

## Operational messaging

Startup logging now makes these contracts visible:

- `run_bot`
  - Telegram text active
  - Telegram voice unsupported
  - whether Telegram token and OpenAI key are configured
  - database and vector-store paths
- `run_voice_agent`
  - LiveKit voice active
  - Telegram voice unsupported
  - room, identity, agent hidden/visible mode, LiveKit URL
  - whether OpenAI is configured
  - masked OpenAI key diagnostics: source, length, last 8 characters, and process-env conflict flag
  - STT/LLM/TTS model names, voice-quality profile, browser capture hints, and KB paths
- `run_demo_stack`
  - combined stack active
  - Telegram text + LiveKit voice both expected
  - room, identity, LiveKit URL
  - whether Telegram token and OpenAI key are configured
- `run_livekit_test_ui`
  - local web UI active
  - browser URL
  - target LiveKit URL and default room
  - whether local token generation is available
  - browser audio capture defaults and voice-quality mode

## Voice-specific configuration

### Required for voice runtime

- `OPENAI_API_KEY`
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `VOICE_TRANSPORT_LOG_LEVEL` is optional but recommended for cleaner default logs

### Required for combined demo stack

- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

### Optional voice defaults

- `VOICE_HIGH_QUALITY_MODE`
- `OPENAI_CHAT_MODEL`
- `OPENAI_CHAT_TEMPERATURE`
- `OPENAI_CHAT_TOP_P`
- `OPENAI_CHAT_MAX_COMPLETION_TOKENS`
- `OPENAI_CHAT_VERBOSITY`
- `OPENAI_STT_MODEL`
- `OPENAI_TTS_MODEL`
- `OPENAI_TTS_VOICE`
- `OPENAI_TTS_RESPONSE_FORMAT`
- `OPENAI_TTS_SPEED`
- `LIVEKIT_ROOM_NAME`
- `LIVEKIT_AGENT_IDENTITY`
- `LIVEKIT_AGENT_HIDDEN`
- `BROWSER_ECHO_CANCELLATION`
- `BROWSER_NOISE_SUPPRESSION`
- `BROWSER_AUTO_GAIN_CONTROL`
- `BROWSER_AUDIO_SAMPLE_RATE`
- `BROWSER_AUDIO_CHANNEL_COUNT`
- `VOICE_INPUT_PRE_GAIN`
- `VOICE_NORMALIZE_INPUT_AUDIO`
- `VOICE_TARGET_INPUT_LEVEL_DBFS`
- `VOICE_MAX_INPUT_GAIN_DB`
- `VOICE_SILENCE_THRESHOLD_DBFS`
- `VOICE_MIN_SPEECH_SECONDS`
- `VOICE_END_OF_UTTERANCE_DELAY_SECONDS`
- `VOICE_MAX_UTTERANCE_SECONDS`
- `VOICE_PREROLL_SECONDS`
- `VOICE_MIN_TRANSCRIPTION_DURATION_SECONDS`
- `VOICE_MIN_TRANSCRIPTION_RMS_DBFS`
- `VOICE_MIN_TRANSCRIPTION_PEAK_DBFS`
- `VOICE_STT_RETRY_DURATION_SECONDS`
- `VOICE_STT_RETRY_RMS_DBFS`
- `VOICE_TRANSPORT_LOG_LEVEL`

### Token flow

`app/voice/token.py`

- uses `livekit-api`
- generates room-join JWTs
- supports hidden agent tokens and normal user tokens
- exposed via `scripts/generate_livekit_token.py`
- warns once when `LIVEKIT_API_SECRET` is shorter than the recommended 32 characters
- suppresses low-level repeated JWT key-length warnings after the high-level app warning is emitted

### OpenAI key resolution

`app/config/settings.py`

- reads the project `.env` file explicitly from the repo root
- resolves `OPENAI_API_KEY` from `.env` first for local runtime determinism
- uses process environment only as fallback when the key is absent from `.env`
- records masked diagnostics:
  - present or missing
  - length
  - last 8 characters
- source
- whether process env disagreed with `.env`

### Voice quality profile contract

`app/config/settings.py` plus `app/bootstrap.py`

- `VOICE_HIGH_QUALITY_MODE=true` switches the default quality profile without code edits
- quality mode changes only defaults; explicit env values still win
- the current high-quality profile uses:
  - stronger STT default: `gpt-4o-transcribe`
  - stronger LLM default: `gpt-4.1`
  - higher-quality TTS default: `tts-1-hd`
  - less aggressive end-of-utterance timing
  - more preroll
  - conservative input pre-gain plus normalization toward a stronger target level
- browser capture defaults are part of the same contract and are delivered to the local web UI from backend settings

## Debug diagnostics

Internal debug and logs include:

- original question
- normalized question
- detected language
- detected topic
- detected bank
- top retrieved chunks
- top retrieved sources
- refusal reason
- source count
- voice transcript text
- finalized utterance duration / RMS / peak / gain summary
- voice answer summary per participant
- runtime startup contract logs
- transport-log separation via `VOICE_TRANSPORT_LOG_LEVEL`

These diagnostics are intentionally not shown in final user-facing answers.

## Verification status

### Automated

```powershell
pytest -q
```

Current result:

- `66 passed`

### Verified in this update

- `build_voice_runtime()` bootstraps successfully
- `build_demo_stack_supervisor()` bootstraps successfully
- `build_livekit_test_ui_server(...).build_client_config()` now exposes browser capture defaults and voice quality mode
- `scripts/generate_livekit_token.py` emits a valid room token
- `scripts/run_livekit_test_ui.py --help` completes successfully
- localhost smoke check for `/api/config` returns the expected LiveKit URL and room name
- runtime smoke-check confirms the active local defaults for:
  - `voice_high_quality_mode`
  - `OPENAI_STT_MODEL`
  - `OPENAI_CHAT_MODEL`
  - `OPENAI_TTS_MODEL`
  - `OPENAI_TTS_RESPONSE_FORMAT`
  - `OPENAI_TTS_SPEED`
  - browser capture defaults
  - runtime target input level and silence threshold
- tests cover:
  - voice token/config bootstrap
  - weak-secret app-level warning without noisy low-level JWT warnings
  - voice turn detection
  - explicit `.env`-first OpenAI key resolution with masked diagnostics and process-env conflict detection
  - `VOICE_HIGH_QUALITY_MODE` profile defaults
  - quiet-segment normalization before STT
  - configured chat generation params
  - configured TTS speed and response format
  - support-agent provider delegation
  - transcript -> answer -> TTS publish wiring
  - empty-transcript guard
  - STT retry without forced language hint
  - STT `insufficient_quota` fallback without utterance-processor crash
  - repeat-prompt fallback after empty transcript
  - local web UI config defaults
  - local web UI token generation
  - local web UI startup wiring
  - local web UI immediate audio attach when `TrackSubscribed` arrives without a participant object
  - local web UI later metadata reconciliation after orphan audio attach
  - local web UI immediate playback attach even when no participant ever appears in the browser snapshot/store
  - local web UI snapshot reconciliation for an existing hidden audio-only agent participant
  - local web UI microphone enable flow with explicit capture defaults
  - visible-by-default local demo mode plus explicit hidden-agent override
  - Telegram duplicate-reply guard
  - explicit Telegram voice fallback contract
  - separate `run_bot` startup contract
  - separate `run_voice_agent` startup contract
  - combined `run_demo_stack` startup contract
  - supervisor start/stop semantics
  - Armenian greeting handling without refusal
  - meta/system answers for supported banks, question phrasing, and scope limits
  - clarification-first steering for vague Armenian banking intents
  - polite out-of-scope handling
  - logging contract for noisy transport loggers
  - voice startup/runtime logs for active model/config selection and latency reporting

## Recommended local verification

```powershell
pytest -q
livekit-server --dev
python -m scripts.run_bot
python -m scripts.run_voice_agent --room bank-support-demo
python -m scripts.run_livekit_test_ui --room bank-support-demo --open-browser
python -m scripts.run_demo_stack --room bank-support-demo
python -m scripts.generate_livekit_token --room bank-support-demo --identity local-user
```

Then:

- send text questions to Telegram and confirm replies still work
- open the local test UI and connect to `bank-support-demo`
- publish microphone audio and ask Armenian questions such as:
  - `Բարև`
  - `Վարկերի մասին հարց ունեմ`
  - `Ի՞նչ ավանդներ կան։`
  - `Որքա՞ն է նվազագույն գումարը ավանդ բացելու համար։`
  - `Ի՞նչ սպառողական վարկեր կան։`
  - `Որտե՞ղ է գտնվում Arabkir մասնաճյուղը։`
  - `Ինչ եղանակ է այսօր`
- send a Telegram voice/audio message and confirm the bot clearly says that Telegram is text-only and LiveKit is the supported voice path

Expected behavior:

- small-talk goes through conversational flow
- vague banking intents trigger clarification before refusal
- supported banking questions go through retrieval
- mixed Armenian + English product names remain retrievable
- refusal happens only when official evidence is missing
- internal debug markers do not leak into spoken or text output
- combined stack keeps both runtimes alive together

## Remaining limitations

### Runtime / demo

- current turn detection is still silence-based, not a production VAD
- audio preprocessing is intentionally conservative; it adds gain staging and normalization for STT, but it is not a full DSP, denoiser, or acoustic echo cancellation pipeline on the Python side
- the local web UI is intentionally minimal and focused on connection, mic control, remote audio playback, and debug state
- the browser UI currently loads the LiveKit JS SDK from a pinned CDN URL rather than bundling it inside the repo
- browser capture constraints such as `echoCancellation`, `noiseSuppression`, and `autoGainControl` are best-effort browser/WebRTC hints, not hard guarantees
- the transcript panel is best-effort only and depends on room-level transcription events that the current backend does not publish separately
- hidden-agent browser playback is still best-effort; local demo defaults to visible agent mode to avoid this SDK edge case
- Telegram voice/audio remains intentionally unsupported
- conversational steering is softer and language-aware for Armenian, Russian, and English openers, but the assistant still remains strictly limited to credits, deposits, and branch locations
- grounded factual answers remain Armenian-first; multilingual behavior is mainly for greeting, clarification, and polite steering

### Knowledge base coverage

#### Acba

- current deposit and branch coverage is comparatively strong
- no major missing selector requirement identified for the currently tested fields

#### Ameriabank

- deposits page currently exposes mostly list-level names in the KB
- consumer-loan page currently exposes product names and categories, but not deep per-product fields
- service-network page currently yields head-office data, not a full branch list

#### Inecobank

- deposit list page covers product names, tags, and links, but not every detail field
- exact rate/currency/minimum/term for `Simple Deposit` is not present in the current KB
- branch extraction is still pending because `/en/map` is not a stable branch-list source

## What needs to be sent

These exact gaps need additional selectors, XHR material, or client pieces if fuller coverage is required:

- `Inecobank`
  - page: `https://www.inecobank.am/en/Individual/deposits/simple`
  - missing field coverage: exact interest rate, currencies, minimum amount, term for `Simple Deposit`
  - needed: stable detail-page selectors or XHR/JSON response sample for product-detail data
- `Inecobank`
  - page: `https://www.inecobank.am/en/map`
  - missing field coverage: branch list, addresses, schedules
  - needed: stable branch-card selectors or XHR/JSON response sample with branch records
- `Ameriabank`
  - page: `https://ameriabank.am/en/personal/saving/deposits/see-all`
  - missing field coverage: deposit currencies, minimum amount, detailed terms per product
  - needed: selectors for product-detail sections/pages or XHR/JSON response sample
- `Ameriabank`
  - page: `https://ameriabank.am/en/personal/loans/consumer-loans/consumer-loans`
  - missing field coverage: detailed consumer-loan conditions per product
  - needed: selectors for detail sections/pages or XHR/JSON response sample
- `Ameriabank`
  - page: `https://ameriabank.am/en/service-network`
  - missing field coverage: full branch list beyond head office
  - needed: stable branch-list selectors or XHR/JSON response sample
