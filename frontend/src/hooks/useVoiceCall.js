import { useCallback, useRef, useState } from 'react'
import { SmallWebRtcClient } from '../voice/smallWebRtcClient'
import { addCallRecord } from '../utils/callHistory'
import { isValidIndianMobile, redactPhoneText } from '../utils/patientLookup'

const NOOP = () => {}

function sanitizeData(value, key = '') {
  if (/phone/i.test(key)) return '[hidden]'
  if (typeof value === 'string') return redactPhoneText(value)
  if (Array.isArray(value)) return value.map((item) => sanitizeData(item))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([entryKey, entryValue]) => [
      entryKey,
      sanitizeData(entryValue, entryKey),
    ]))
  }
  return value
}

function friendlyCallError(err) {
  const name = err?.name || ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return 'Microphone permission denied. Allow microphone access in the browser, then start the call again.'
  }
  if (name === 'NotFoundError') {
    return 'No microphone was found on this device.'
  }
  return err?.message || 'Could not start the voice call.'
}
function formatDataMessage(raw) {
  if (typeof raw !== 'string') return null
  if (raw.startsWith('ping')) return null
  try {
    const parsed = JSON.parse(raw)
    if (parsed.type === 'signalling') return null
    if (parsed.type === 'veyacare_booking_succeeded' && isValidIndianMobile(parsed.phone_number)) {
      return { type: 'booking_succeeded', phoneNumber: parsed.phone_number }
    }
    if (typeof parsed.text === 'string' && parsed.text.trim()) {
      return { speaker: 'Receptionist', text: redactPhoneText(parsed.text) }
    }
    return { speaker: 'System', text: JSON.stringify(sanitizeData(parsed)) }
  } catch {
    return { speaker: 'System', text: redactPhoneText(raw) }
  }
}

export function useVoiceCall(displayName = '', onBookingSucceeded = NOOP, refreshAppointments = NOOP) {
  const clientRef = useRef(null)
  const startedAtRef = useRef(null)
  const activeRef = useRef(false)
  const [status, setStatus] = useState('idle')
  const [muted, setMuted] = useState(false)
  const [startedAt, setStartedAt] = useState(null)
  const [transcript, setTranscript] = useState([])
  const [error, setError] = useState('')
  const [remoteStream, setRemoteStream] = useState(null)
  const [localStream, setLocalStream] = useState(null)

  const appendLine = useCallback((speaker, text) => {
    setTranscript((current) => [
      ...current,
      { id: crypto.randomUUID(), speaker, text, at: new Date().toISOString() },
    ])
  }, [])

  const startCall = useCallback(async () => {
    if (activeRef.current) return
    activeRef.current = true
    setError('')
    setTranscript([])
    setStartedAt(null)
    setMuted(false)
    setStatus('connecting')
    appendLine('System', 'Requesting microphone and creating a WebRTC offer…')

    const client = new SmallWebRtcClient({
      displayName,
      onStatus: (next) => {
        setStatus(next)
        if (next === 'connected') {
          const now = Date.now()
          startedAtRef.current = now
          setStartedAt(now)
          appendLine(
            'System',
            'Voice connection established. Speak with the medical receptionist.',
          )
        }
      },
      onRemoteTrack: (track) => {
        if (track.kind === 'audio') {
          const stream = new MediaStream([track])
          setRemoteStream(stream)
        }
      },
      onLocalStream: setLocalStream,
      onDataMessage: (raw) => {
        const parsed = formatDataMessage(raw)
        if (parsed?.type === 'booking_succeeded') {
          onBookingSucceeded(parsed.phoneNumber)
          refreshAppointments()
          return
        }
        if (parsed) appendLine(parsed.speaker, parsed.text)
      },
      onError: (err) => {
        const message = friendlyCallError(err)
        setError(message)
        appendLine('System', message)
      },
    })

    clientRef.current = client
    try {
      await client.connect()
    } catch (err) {
      activeRef.current = false
      setStatus('failed')
      const message = friendlyCallError(err)
      setError(message)
      appendLine('System', message)
      client.disconnect({ silent: true })
      clientRef.current = null
      addCallRecord({
        status: 'failed',
        durationSeconds: 0,
        note: message,
      })
    }
  }, [appendLine, displayName, onBookingSucceeded, refreshAppointments])

  const endCall = useCallback(() => {
    if (!activeRef.current && !clientRef.current) return
    const elapsed = startedAtRef.current
      ? Math.round((Date.now() - startedAtRef.current) / 1000)
      : 0
    const startedAtIso = startedAtRef.current
      ? new Date(startedAtRef.current).toISOString()
      : new Date().toISOString()
    clientRef.current?.disconnect({ silent: true })
    clientRef.current = null
    activeRef.current = false
    setRemoteStream(null)
    setLocalStream(null)
    setMuted(false)
    setStartedAt(null)
    setStatus('ended')
    addCallRecord({
      startedAt: startedAtIso,
      status: 'ended',
      durationSeconds: elapsed,
      note: 'Call ended from dashboard',
    })
    appendLine('System', 'Call ended.')
  }, [appendLine])

  const toggleMute = useCallback(() => {
    const next = !muted
    clientRef.current?.setMuted(next)
    setMuted(next)
    appendLine('System', next ? 'Microphone muted.' : 'Microphone unmuted.')
  }, [appendLine, muted])

  return {
    status,
    muted,
    startedAt,
    transcript,
    error,
    remoteStream,
    localStream,
    startCall,
    endCall,
    toggleMute,
  }
}
