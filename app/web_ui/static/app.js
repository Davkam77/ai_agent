(function () {
  const LiveKitClient = window.LivekitClient;
  if (!LiveKitClient) {
    document.body.insertAdjacentHTML(
      "afterbegin",
      '<div class="fatal-error">LiveKit JS client failed to load. Check your internet connection and reload.</div>',
    );
    return;
  }

  const elements = {
    livekitUrl: document.getElementById("livekitUrl"),
    roomName: document.getElementById("roomName"),
    identity: document.getElementById("identity"),
    token: document.getElementById("token"),
    generateTokenButton: document.getElementById("generateTokenButton"),
    connectButton: document.getElementById("connectButton"),
    disconnectButton: document.getElementById("disconnectButton"),
    micButton: document.getElementById("micButton"),
    resumeAudioButton: document.getElementById("resumeAudioButton"),
    connectionStatus: document.getElementById("connectionStatus"),
    micStatus: document.getElementById("micStatus"),
    remoteAudioStatus: document.getElementById("remoteAudioStatus"),
    activeSpeakers: document.getElementById("activeSpeakers"),
    statusMessage: document.getElementById("statusMessage"),
    eventLog: document.getElementById("eventLog"),
    transcriptFeed: document.getElementById("transcriptFeed"),
    audioContainer: document.getElementById("audioContainer"),
  };

  let room = null;
  let isMicEnabled = false;
  let clientConfig = {
    voiceQualityMode: "balanced",
    audioCaptureOptions: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      sampleRate: 48000,
      channelCount: 1,
    },
  };

  const participantStore = new Map();
  const pendingTracksByParticipantSid = new Map();
  const remoteAudioEntries = new Map();

  function logEvent(message) {
    const item = document.createElement("li");
    item.textContent = `${new Date().toLocaleTimeString()}  ${message}`;
    elements.eventLog.prepend(item);
  }

  function appendTranscript(message) {
    if (!elements.transcriptFeed.dataset.hasMessages) {
      elements.transcriptFeed.textContent = "";
      elements.transcriptFeed.dataset.hasMessages = "true";
    }
    const line = document.createElement("div");
    line.textContent = message;
    elements.transcriptFeed.appendChild(line);
  }

  function setStatus(label, cssClass, message) {
    elements.connectionStatus.textContent = label;
    elements.connectionStatus.className = `pill ${cssClass}`;
    elements.statusMessage.textContent = message;
  }

  function participantSid(participant) {
    return participant && participant.sid ? participant.sid : "";
  }

  function participantLabel(participant) {
    if (!participant) {
      return "unknown-participant";
    }
    return participant.identity || participant.name || participant.sid || "unknown-participant";
  }

  function buildAudioCaptureOptions() {
    const options = clientConfig.audioCaptureOptions || {};
    return {
      echoCancellation: options.echoCancellation !== false,
      noiseSuppression: options.noiseSuppression !== false,
      autoGainControl: options.autoGainControl !== false,
      sampleRate: Number(options.sampleRate) || 48000,
      channelCount: Number(options.channelCount) || 1,
    };
  }

  function buildTrackKey(track, publication, participantSidHint) {
    return publication?.trackSid || publication?.sid || track?.sid || `${participantSidHint || "unknown"}:audio`;
  }

  function updateMicButton() {
    elements.micStatus.textContent = isMicEnabled ? "On" : "Off";
    elements.micButton.textContent = isMicEnabled ? "Mute mic" : "Unmute mic";
    elements.micButton.disabled = !room;
  }

  function updateAudioStatus() {
    const remoteAudioCount = remoteAudioEntries.size;
    elements.remoteAudioStatus.textContent =
      remoteAudioCount > 0 ? `Receiving ${remoteAudioCount} remote audio track(s)` : "Waiting for remote audio";
    const canResume = room && typeof room.startAudio === "function";
    elements.resumeAudioButton.disabled = !canResume;
  }

  function updateButtons() {
    const connected = Boolean(room);
    elements.connectButton.disabled = connected;
    elements.disconnectButton.disabled = !connected;
    updateMicButton();
    updateAudioStatus();
  }

  function clearRemoteAudioElements() {
    for (const entry of remoteAudioEntries.values()) {
      entry.audioElement.remove();
    }
    remoteAudioEntries.clear();
    updateAudioStatus();
  }

  function clearParticipantState() {
    participantStore.clear();
    pendingTracksByParticipantSid.clear();
    clearRemoteAudioElements();
    elements.activeSpeakers.textContent = "None";
  }

  async function attemptAudioPlayback(audioElement, reason) {
    if (typeof audioElement.play !== "function") {
      return;
    }
    try {
      await audioElement.play();
      logEvent(`Remote audio playback started (${reason})`);
    } catch (error) {
      elements.statusMessage.textContent = "Remote audio is ready. If you cannot hear it, click Resume audio.";
      logEvent(`Remote audio playback pending user gesture (${reason}): ${error.message}`);
    }
  }

  async function attachRemoteAudioTrack(track, publication, participant, reason) {
    if (!track || track.kind !== LiveKitClient.Track.Kind.Audio) {
      return;
    }

    const sid = participantSid(participant);
    const label = participantLabel(participant);
    const key = buildTrackKey(track, publication, sid);

    if (remoteAudioEntries.has(key)) {
      reconcileRemoteAudioMetadata(track, publication, participant, `${reason}:existing`);
      return;
    }

    logEvent(`Audio element created for ${label} (${reason})`);
    const audioElement = track.attach();
    audioElement.controls = true;
    audioElement.autoplay = true;
    audioElement.playsInline = true;
    audioElement.dataset.participantIdentity = label;
    audioElement.dataset.participantSid = sid;
    audioElement.dataset.trackKey = key;
    elements.audioContainer.appendChild(audioElement);

    remoteAudioEntries.set(key, {
      audioElement,
      participantIdentity: label,
      participantSid: sid,
      track,
    });

    updateAudioStatus();
    logEvent(`Remote audio stream attached for ${label} (${reason})`);
    await attemptAudioPlayback(audioElement, `${label} / ${reason}`);
  }

  function reconcileRemoteAudioMetadata(track, publication, participant, reason) {
    const sid = participantSid(participant);
    const label = participantLabel(participant);
    const key = buildTrackKey(track, publication, sid);
    const entry = remoteAudioEntries.get(key);

    if (!entry) {
      return false;
    }

    const metadataChanged = entry.participantIdentity !== label || entry.participantSid !== sid;
    entry.participantIdentity = label;
    entry.participantSid = sid;
    entry.audioElement.dataset.participantIdentity = label;
    entry.audioElement.dataset.participantSid = sid;

    if (metadataChanged) {
      logEvent(`Remote audio metadata reconciled for ${label} (${reason})`);
    }

    return true;
  }

  function removeRemoteAudioForTrack(track, publication, participant, reason) {
    const sid = participantSid(participant);
    const label = participantLabel(participant);
    const key = buildTrackKey(track, publication, sid);
    const entry = remoteAudioEntries.get(key);

    if (entry) {
      entry.audioElement.remove();
      remoteAudioEntries.delete(key);
    }

    if (track && typeof track.detach === "function") {
      track.detach().forEach((element) => element.remove());
    }

    updateAudioStatus();
    logEvent(`Remote audio removed for ${label} (${reason})`);
  }

  function removeRemoteAudioForParticipant(participant, reason) {
    const sid = participantSid(participant);
    if (!sid) {
      return;
    }

    for (const [trackKey, entry] of remoteAudioEntries.entries()) {
      if (entry.participantSid !== sid) {
        continue;
      }
      entry.audioElement.remove();
      remoteAudioEntries.delete(trackKey);
    }

    updateAudioStatus();
    logEvent(`Participant audio cleared for ${participantLabel(participant)} (${reason})`);
  }

  function queuePendingTrack(track, publication, participant, reason) {
    const sid = participantSid(participant) || publication?.participantSid || "unknown";
    const key = buildTrackKey(track, publication, sid);

    let queuedTracks = pendingTracksByParticipantSid.get(sid);
    if (!queuedTracks) {
      queuedTracks = new Map();
      pendingTracksByParticipantSid.set(sid, queuedTracks);
    }

    if (queuedTracks.has(key)) {
      return;
    }

    queuedTracks.set(key, {
      publication,
      track,
      participantIdentityHint: participantLabel(participant),
    });
    logEvent(`Pending participant metadata queued for ${participantLabel(participant)} (${reason})`);
  }

  function pendingTrackMatchesParticipant(entry, participant) {
    const sid = participantSid(participant);
    if (!sid) {
      return false;
    }

    if (entry.publication?.participantSid === sid) {
      return true;
    }

    if (!participant?.trackPublications) {
      return false;
    }

    if (entry.publication?.sid && participant.trackPublications.has(entry.publication.sid)) {
      return true;
    }

    for (const participantPublication of participant.trackPublications.values()) {
      if (participantPublication === entry.publication) {
        return true;
      }
      if (participantPublication?.sid && entry.publication?.sid && participantPublication.sid === entry.publication.sid) {
        return true;
      }
      if (
        participantPublication?.trackSid &&
        entry.publication?.trackSid &&
        participantPublication.trackSid === entry.publication.trackSid
      ) {
        return true;
      }
      if (participantPublication?.track && entry.track && participantPublication.track === entry.track) {
        return true;
      }
    }

    return false;
  }

  async function flushPendingTracks(participant, reason) {
    const sid = participantSid(participant);
    if (!sid) {
      return;
    }

    for (const queueSid of [sid, "unknown"]) {
      const queuedTracks = pendingTracksByParticipantSid.get(queueSid);
      if (!queuedTracks || !queuedTracks.size) {
        continue;
      }

      for (const [trackKey, entry] of Array.from(queuedTracks.entries())) {
        if (queueSid !== sid && !pendingTrackMatchesParticipant(entry, participant)) {
          continue;
        }

        queuedTracks.delete(trackKey);
        logEvent(`Pending track reconciled for ${participantLabel(participant)} (${reason})`);
        reconcileRemoteAudioMetadata(entry.track, entry.publication, participant, `${reason}:pending`);
        await attachRemoteAudioTrack(entry.track, entry.publication, participant, `${reason}:pending`);
      }

      if (!queuedTracks.size) {
        pendingTracksByParticipantSid.delete(queueSid);
      }
    }
  }

  async function reconcileParticipantPublications(participant, reason) {
    if (!participant || !participant.trackPublications) {
      return;
    }

    for (const publication of participant.trackPublications.values()) {
      if (publication.kind !== LiveKitClient.Track.Kind.Audio) {
        continue;
      }
      if (publication.track) {
        await attachRemoteAudioTrack(publication.track, publication, participant, `${reason}:snapshot`);
      }
    }
  }

  async function ensureParticipantRecord(participant, reason) {
    const sid = participantSid(participant);
    if (!sid) {
      return null;
    }

    const hadPendingTracks = pendingTracksByParticipantSid.has(sid);
    const existing = participantStore.get(sid);
    const label = participantLabel(participant);

    participantStore.set(sid, {
      sid,
      identity: label,
      participant,
    });

    if (!existing) {
      logEvent(`Participant added: ${label} (${reason})`);
    } else if (hadPendingTracks || reason.startsWith("snapshot") || reason === "reconnected") {
      logEvent(`Participant reconciled: ${label} (${reason})`);
    }

    await flushPendingTracks(participant, reason);
    await reconcileParticipantPublications(participant, reason);
    return participantStore.get(sid);
  }

  async function reconcileRoomSnapshot(currentRoom, reason) {
    const remoteParticipants = Array.from(currentRoom.remoteParticipants.values());
    if (!remoteParticipants.length) {
      logEvent(`Room reconciliation complete: no remote participants (${reason})`);
      return;
    }

    for (const participant of remoteParticipants) {
      await ensureParticipantRecord(participant, `snapshot:${reason}`);
    }
    logEvent(`Room reconciliation complete: ${remoteParticipants.length} remote participant(s) (${reason})`);
  }

  async function handleTrackSubscribed(currentRoom, track, publication, participant) {
    if (track.kind !== LiveKitClient.Track.Kind.Audio) {
      return;
    }
    logEvent(`Track subscribed kind=audio trackSid=${publication?.trackSid || track?.sid || "unknown"}`);

    if (!participant || !participantSid(participant)) {
      logEvent("Audio track subscribed without participant metadata; attaching playback immediately");
      await attachRemoteAudioTrack(track, publication, participant, "track_subscribed_without_participant");
      queuePendingTrack(track, publication, participant, "track_subscribed_without_participant");
      await reconcileRoomSnapshot(currentRoom, "track_subscribed_without_participant");
      return;
    }

    await ensureParticipantRecord(participant, "track_subscribed");
    await attachRemoteAudioTrack(track, publication, participant, "track_subscribed");
  }

  function handleTrackUnsubscribed(track, publication, participant) {
    if (track.kind !== LiveKitClient.Track.Kind.Audio) {
      return;
    }

    removeRemoteAudioForTrack(track, publication, participant, "track_unsubscribed");
  }

  async function handleTrackPublished(currentRoom, publication, participant) {
    if (publication.kind !== LiveKitClient.Track.Kind.Audio) {
      return;
    }

    if (!participant || !participantSid(participant)) {
      logEvent("Audio publication arrived before participant snapshot; reconciling room state");
      await reconcileRoomSnapshot(currentRoom, "track_published_without_participant");
      return;
    }

    await ensureParticipantRecord(participant, "track_published");
  }

  function handleParticipantDisconnected(participant) {
    const sid = participantSid(participant);
    if (sid) {
      participantStore.delete(sid);
      pendingTracksByParticipantSid.delete(sid);
    }
    removeRemoteAudioForParticipant(participant, "participant_disconnected");
    logEvent(`Participant disconnected: ${participantLabel(participant)}`);
  }

  function registerRoomEvents(currentRoom) {
    const { RoomEvent } = LiveKitClient;

    currentRoom.on(RoomEvent.Connected, async () => {
      setStatus("Connected", "connected", `Joined room ${currentRoom.name}.`);
      logEvent(`Connected to room ${currentRoom.name}`);
      await reconcileRoomSnapshot(currentRoom, "connected");
    });

    currentRoom.on(RoomEvent.ConnectionStateChanged, (state) => {
      setStatus(String(state), String(state).toLowerCase(), `Room state changed to ${state}.`);
      logEvent(`Connection state changed to ${state}`);
    });

    currentRoom.on(RoomEvent.Reconnected, async () => {
      logEvent("Room reconnected");
      await reconcileRoomSnapshot(currentRoom, "reconnected");
    });

    currentRoom.on(RoomEvent.Disconnected, () => {
      logEvent("Disconnected from room");
      setStatus("Disconnected", "disconnected", "Not connected.");
      room = null;
      isMicEnabled = false;
      clearParticipantState();
      updateButtons();
    });

    currentRoom.on(RoomEvent.ParticipantConnected, async (participant) => {
      await ensureParticipantRecord(participant, "participant_connected");
    });

    currentRoom.on(RoomEvent.ParticipantDisconnected, (participant) => {
      handleParticipantDisconnected(participant);
    });

    currentRoom.on(RoomEvent.TrackSubscribed, async (track, publication, participant) => {
      await handleTrackSubscribed(currentRoom, track, publication, participant);
    });

    currentRoom.on(RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
      handleTrackUnsubscribed(track, publication, participant);
    });

    if (RoomEvent.TrackPublished) {
      currentRoom.on(RoomEvent.TrackPublished, async (publication, participant) => {
        await handleTrackPublished(currentRoom, publication, participant);
      });
    }

    currentRoom.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      const names = (speakers || []).map((speaker) => speaker.identity).join(", ");
      elements.activeSpeakers.textContent = names || "None";
    });

    if (RoomEvent.AudioPlaybackStatusChanged) {
      currentRoom.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        updateAudioStatus();
        logEvent("Audio playback status changed");
      });
    }

    if (RoomEvent.TranscriptionReceived) {
      currentRoom.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        const lines = Array.isArray(segments)
          ? segments.map((segment) => segment?.text || "").filter(Boolean)
          : [];
        if (!lines.length) {
          return;
        }
        const prefix = participant?.identity ? `${participant.identity}: ` : "";
        appendTranscript(`${prefix}${lines.join(" ")}`);
      });
    }
  }

  async function loadDefaults() {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) {
        throw new Error(`config request failed: ${response.status}`);
      }
      const payload = await response.json();
      clientConfig = {
        voiceQualityMode: payload.voiceQualityMode || "balanced",
        audioCaptureOptions: payload.audioCaptureOptions || clientConfig.audioCaptureOptions,
      };
      elements.livekitUrl.value = payload.livekitUrl || "";
      elements.roomName.value = payload.roomName || "";
      elements.identity.value = payload.suggestedIdentity || "";
      elements.generateTokenButton.disabled = !payload.canGenerateToken;
      const audioCaptureOptions = buildAudioCaptureOptions();
      logEvent(
        `Loaded local UI defaults quality_mode=${clientConfig.voiceQualityMode} capture=${JSON.stringify(audioCaptureOptions)}`,
      );
    } catch (error) {
      logEvent(`Failed to load local defaults: ${error.message}`);
    }
  }

  async function generateToken() {
    const roomName = elements.roomName.value.trim();
    const identity = elements.identity.value.trim();
    if (!roomName || !identity) {
      throw new Error("Room and identity are required before token generation.");
    }

    const response = await fetch("/api/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ roomName, identity }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "token_generation_failed");
    }
    elements.token.value = payload.token || "";
    logEvent(`Generated local token for ${identity}`);
    return payload.token || "";
  }

  async function connect() {
    const wsUrl = elements.livekitUrl.value.trim();
    if (!wsUrl) {
      throw new Error("LiveKit URL is required.");
    }

    let token = elements.token.value.trim();
    if (!token) {
      token = await generateToken();
    }

    const currentRoom = new LiveKitClient.Room();
    room = currentRoom;
    clearParticipantState();
    registerRoomEvents(currentRoom);

    setStatus("Connecting", "connecting", "Connecting to room...");
    await currentRoom.connect(wsUrl, token);
    isMicEnabled = true;
    const audioCaptureOptions = buildAudioCaptureOptions();
    logEvent(`Enabling microphone with capture options ${JSON.stringify(audioCaptureOptions)}`);
    await room.localParticipant.setMicrophoneEnabled(true, audioCaptureOptions);
    updateButtons();

    if (typeof room.startAudio === "function") {
      try {
        await room.startAudio();
        logEvent("Room audio playback activated");
      } catch (error) {
        logEvent(`Audio resume may still require a user gesture: ${error.message}`);
      }
    }

    await reconcileRoomSnapshot(currentRoom, "post_connect");
  }

  async function disconnect() {
    if (!room) {
      return;
    }
    const currentRoom = room;
    room = null;
    isMicEnabled = false;
    clearParticipantState();
    updateButtons();
    await currentRoom.disconnect();
    setStatus("Disconnected", "disconnected", "Not connected.");
  }

  async function toggleMic() {
    if (!room) {
      return;
    }
    isMicEnabled = !isMicEnabled;
    const audioCaptureOptions = buildAudioCaptureOptions();
    if (isMicEnabled) {
      await room.localParticipant.setMicrophoneEnabled(true, audioCaptureOptions);
    } else {
      await room.localParticipant.setMicrophoneEnabled(false);
    }
    updateMicButton();
    logEvent(
      `Microphone ${isMicEnabled ? "enabled" : "muted"}${isMicEnabled ? ` with capture ${JSON.stringify(audioCaptureOptions)}` : ""}`,
    );
  }

  async function resumeAudio() {
    if (!room || typeof room.startAudio !== "function") {
      return;
    }
    await room.startAudio();
    logEvent("Audio playback start requested");
    for (const entry of remoteAudioEntries.values()) {
      await attemptAudioPlayback(entry.audioElement, `resume:${entry.participantIdentity}`);
    }
    logEvent("Audio playback resumed");
  }

  elements.generateTokenButton.addEventListener("click", async () => {
    try {
      await generateToken();
    } catch (error) {
      setStatus("Error", "error", error.message);
      logEvent(`Token generation failed: ${error.message}`);
    }
  });

  elements.connectButton.addEventListener("click", async () => {
    try {
      await connect();
    } catch (error) {
      setStatus("Error", "error", error.message);
      logEvent(`Connection failed: ${error.message}`);
      if (room) {
        await disconnect();
      }
    }
  });

  elements.disconnectButton.addEventListener("click", async () => {
    try {
      await disconnect();
      logEvent("Disconnected by user");
    } catch (error) {
      setStatus("Error", "error", error.message);
    }
  });

  elements.micButton.addEventListener("click", async () => {
    try {
      await toggleMic();
    } catch (error) {
      setStatus("Error", "error", error.message);
      logEvent(`Microphone toggle failed: ${error.message}`);
    }
  });

  elements.resumeAudioButton.addEventListener("click", async () => {
    try {
      await resumeAudio();
    } catch (error) {
      setStatus("Error", "error", error.message);
      logEvent(`Audio resume failed: ${error.message}`);
    }
  });

  setStatus("Disconnected", "disconnected", "Ready.");
  updateButtons();
  loadDefaults();
})();
