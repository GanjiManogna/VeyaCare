import { useEffect, useRef } from 'react'
import { formatDuration } from '../../utils/callHistory'

const STATUS_LABEL = {
  idle: 'Ready',
  connecting: 'Connecting',
  connected: 'In call',
  disconnected: 'Disconnected',
  failed: 'Needs attention',
  ended: 'Ended',
}

function callMessage({ status, muted, error }) {
  if (error && /denied|permission/i.test(error)) {
    return 'Microphone access was denied. Allow the microphone for this site, then start the call again.'
  }
  if (status === 'failed') {
    return error || 'The voice line did not connect. You can try again.'
  }
  if (status === 'connecting') {
    return 'Asking for your microphone and opening the voice line.'
  }
  if (status === 'connected' && muted) {
    return 'You are connected. Your microphone is muted, so the receptionist cannot hear you.'
  }
  if (status === 'connected') {
    return 'You are connected. Speak naturally when you are ready.'
  }
  if (status === 'disconnected') {
    return 'The voice line dropped. End the call, then start again if you still need help.'
  }
  if (status === 'ended') {
    return 'The call has ended. Start another whenever you are ready.'
  }
  return 'When you are ready, start a call with the VeyaCare receptionist.'
}

function Waveform({ stream, active, role }) {
  const barsRef = useRef(null)

  useEffect(() => {
    const bars = barsRef.current?.querySelectorAll('span')
    if (!bars?.length) return undefined

    const rest = () => {
      bars.forEach((bar) => {
        bar.style.transform = 'scaleY(0.18)'
      })
      barsRef.current?.closest('.audio-monitor')?.classList.remove('speaking')
      const label = barsRef.current?.parentElement?.querySelector('.audio-state')
      if (label) label.textContent = !active ? 'Waiting for live audio' : 'Quiet'
    }

    if (!active || !stream) {
      rest()
      return undefined
    }

    const audio = new AudioContext()
    const source = audio.createMediaStreamSource(stream)
    const analyser = audio.createAnalyser()
    analyser.fftSize = 64
    source.connect(analyser)
    const data = new Uint8Array(analyser.frequencyBinCount)
    const waveform = new Uint8Array(analyser.fftSize)
    let frame = 0

    const tick = () => {
      analyser.getByteFrequencyData(data)
      analyser.getByteTimeDomainData(waveform)
      const volume = waveform.reduce((sum, value) => sum + Math.abs(value - 128), 0) / waveform.length
      const speaking = volume > 7
      barsRef.current?.closest('.audio-monitor')?.classList.toggle('speaking', speaking)
      const label = barsRef.current?.parentElement?.querySelector('.audio-state')
      if (label) label.textContent = speaking ? (role === 'caller' ? 'Speaking' : 'Receptionist speaking') : 'Listening'
      const size = Math.floor(data.length / bars.length) || 1
      bars.forEach((bar, index) => {
        let sum = 0
        for (let offset = 0; offset < size; offset += 1) {
          sum += data[index * size + offset] || 0
        }
        const level = Math.max(0.18, Math.min(1, sum / size / 170))
        bar.style.transform = `scaleY(${level})`
      })
      frame = window.requestAnimationFrame(tick)
    }

    audio.resume().then(tick).catch(rest)

    return () => {
      window.cancelAnimationFrame(frame)
      source.disconnect()
      audio.close().catch(() => {})
    }
  }, [active, role, stream])

  return (
    <div
      ref={barsRef}
      className={`waveform ${active ? 'live' : ''}`}
      aria-hidden="true"
    >
      <span />
      <span />
      <span />
      <span />
      <span />
    </div>
  )
}

export function CallInterface({
  status,
  muted,
  startedAt,
  transcript,
  error,
  remoteStream,
  localStream,
  onStart,
  onEnd,
  onMute,
}) {
  const audioRef = useRef(null)
  const liveCall = Boolean(startedAt) && status === 'connected'
  const elapsedRef = useRef(null)

  useEffect(() => {
    if (!liveCall) {
      if (elapsedRef.current) elapsedRef.current.textContent = formatDuration(0)
      return undefined
    }
    const tick = () => {
      const seconds = Math.floor((Date.now() - startedAt) / 1000)
      if (elapsedRef.current) elapsedRef.current.textContent = formatDuration(seconds)
    }
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [liveCall, startedAt])

  useEffect(() => {
    if (audioRef.current && remoteStream) {
      audioRef.current.srcObject = remoteStream
      audioRef.current.play().catch(() => {})
    }
  }, [remoteStream])

  const live = status === 'connecting' || status === 'connected'
  const permissionDenied = Boolean(error && /denied|permission/i.test(error))

  return (
    <section className="reception">
      <div className="reception-copy">
        <p className="eyebrow">Signature</p>
        <h2>AI Medical Receptionist</h2>
        <p>
          Book, move, or cancel a visit by speaking with VeyaCare. The line
          shows as connected only after the browser voice connection is up.
        </p>
        <p className={`call-state ${permissionDenied || status === 'failed' ? 'warn' : ''}`}>
          {callMessage({ status, muted, error })}
        </p>
      </div>

      <div className="handset">
        <div className="handset-top">
          <div>
            <p className="eyebrow">VeyaCare</p>
            <strong>Reception</strong>
          </div>
          <span className={`chip ${status}`}>{STATUS_LABEL[status] || status}</span>
        </div>
        <div className={`voice-stage ${status}`}>
          <button
            className="voice-mic"
            onClick={status === 'connected' ? onMute : onStart}
            disabled={status === 'connecting'}
            aria-label={status === 'connected' ? (muted ? 'Unmute microphone' : 'Mute microphone') : 'Start voice call'}
            title={status === 'connected' ? (muted ? 'Unmute microphone' : 'Mute microphone') : 'Start voice call'}
          >
            <MicrophoneIcon />
          </button>
          <span className="voice-stage-label" role="status">
            {status === 'connected' ? (muted ? 'Microphone muted' : 'Connected · speak naturally') : status === 'connecting' ? 'Opening secure voice line…' : 'Tap to speak with reception'}
          </span>
        </div>
        <div className="audio-monitors">
          <div className="audio-monitor caller-monitor">
            <span>Caller microphone · <span className="audio-state">{muted ? 'Muted' : 'Waiting for live audio'}</span></span>
            <Waveform stream={localStream} active={status === 'connected' && !muted} role="caller" />
          </div>
          <div className="audio-monitor assistant-monitor">
            <span>Receptionist audio · <span className="audio-state">Waiting for live audio</span></span>
            <Waveform stream={remoteStream} active={status === 'connected'} role="assistant" />
          </div>
        </div>
        <p className="timer" ref={elapsedRef} aria-live="polite">
          {formatDuration(0)}
        </p>
        <p className="phone-caption">
          {status === 'connected'
            ? 'Both meters follow live microphone and receptionist audio.'
            : muted
              ? 'Microphone muted'
              : 'Waiting for a live voice line'}
        </p>
        <audio ref={audioRef} autoPlay playsInline />
        <div className="call-actions">
          <button className="ghost" onClick={onMute} disabled={status !== 'connected'}>
            {muted ? 'Unmute' : 'Mute'}
          </button>
          <button className="danger" onClick={onEnd} disabled={!live}>
            End call
          </button>
        </div>
        {error ? <p className="banner error call-error" role="alert">{error}</p> : null}
        <details className="transcript">
          <summary>Show live transcript and call events</summary>
          <div className="transcript-body">
            {transcript.length === 0 ? (
              <p className="muted">No call activity yet.</p>
            ) : (
              transcript.map((line) => (
                <div key={line.id} className={`transcript-line ${line.speaker.toLowerCase()}`}>
                  <strong>{line.speaker}</strong>
                  <span>{line.text}</span>
                </div>
              ))
            )}
          </div>
        </details>
      </div>
    </section>
  )
}

function MicrophoneIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="3" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3m-4 0h8" />
    </svg>
  )
}
