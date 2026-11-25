import { patchWebRtcIce, postWebRtcOffer } from '../api/client'

const AUDIO_TRANSCEIVER_INDEX = 0

function candidatePayload(candidate) {
  const raw = candidate.candidate || ''
  const sdp = raw.startsWith('candidate:') ? raw.slice('candidate:'.length) : raw
  if (!sdp) return null
  return {
    candidate: sdp,
    sdp_mid: candidate.sdpMid ?? '',
    sdp_mline_index: candidate.sdpMLineIndex ?? 0,
  }
}

export class SmallWebRtcClient {
  constructor({ onStatus, onRemoteTrack, onLocalStream, onDataMessage, onError, displayName = '' } = {}) {
    this.onStatus = onStatus
    this.onRemoteTrack = onRemoteTrack
    this.onLocalStream = onLocalStream
    this.onDataMessage = onDataMessage
    this.onError = onError
    this.displayName = displayName
    this.pc = null
    this.dc = null
    this.pcId = null
    this.localStream = null
    this.keepAlive = null
    this.candidateQueue = []
    this.canSendIce = false
    this.flushTimer = null
    this.muted = false
    this.closed = false
  }

  async connect() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('This browser cannot access a microphone for a voice call.')
    }

    this.closed = false
    this.onStatus?.('connecting')
    this.pc = new RTCPeerConnection({
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
    })

    this.pc.addTransceiver('audio', { direction: 'sendrecv' })
    this.pc.addTransceiver('video', { direction: 'sendrecv' })

    this.pc.onicecandidate = (event) => {
      if (event.candidate) this.queueIceCandidate(event.candidate)
    }

    this.pc.onconnectionstatechange = () => {
      const state = this.pc?.connectionState
      if (state === 'connected') this.onStatus?.('connected')
      if (state === 'disconnected') this.onStatus?.('disconnected')
      if (state === 'failed') {
        this.onStatus?.('failed')
        this.onError?.(new Error('WebRTC connection failed.'))
      }
      if (state === 'closed' && !this.closed) this.onStatus?.('ended')
    }

    this.pc.ontrack = (event) => {
      this.onRemoteTrack?.(event.track, event.streams[0])
    }

    this.dc = this.pc.createDataChannel('chat', { ordered: true })
    this.dc.onopen = () => {
      this.keepAlive = window.setInterval(() => {
        if (this.dc?.readyState === 'open') {
          this.dc.send(`ping: ${Date.now()}`)
        }
      }, 1000)
    }
    this.dc.onmessage = (event) => {
      if (this.handleDataChannelMessage(event.data)) return
      this.onDataMessage?.(event.data)
    }

    this.localStream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false,
    })
    this.onLocalStream?.(this.localStream)
    const audioTrack = this.localStream.getAudioTracks()[0]
    const audioSender = this.pc.getTransceivers()[AUDIO_TRANSCEIVER_INDEX]?.sender
    if (audioTrack && audioSender) {
      await audioSender.replaceTrack(audioTrack)
    }

    const offer = await this.pc.createOffer()
    await this.pc.setLocalDescription(offer)
    await this.exchangeOffer(false)
  }

  handleDataChannelMessage(raw) {
    if (typeof raw !== 'string' || raw.startsWith('ping')) return false
    try {
      const parsed = JSON.parse(raw)
      if (parsed?.type === 'signalling' && parsed.message?.type === 'renegotiate') {
        this.renegotiate().catch((err) => {
          this.onError?.(err)
        })
        return true
      }
    } catch {
      return false
    }
    return false
  }

  async exchangeOffer(restartPc) {
    const offerBody = {
      sdp: this.pc.localDescription.sdp,
      type: this.pc.localDescription.type,
      restart_pc: restartPc,
      request_data: { display_name: this.displayName },
    }
    if (this.pcId) offerBody.pc_id = this.pcId

    const answer = await postWebRtcOffer(offerBody)
    if (!answer?.sdp || !answer?.type || !answer?.pc_id) {
      throw new Error('The voice server did not return a WebRTC answer.')
    }

    this.pcId = answer.pc_id
    await this.pc.setRemoteDescription({
      sdp: answer.sdp,
      type: answer.type,
    })

    this.canSendIce = true
    await this.flushIceCandidates()
  }

  async renegotiate() {
    if (!this.pc || this.closed) return
    this.canSendIce = false
    const offer = await this.pc.createOffer()
    await this.pc.setLocalDescription(offer)
    await this.exchangeOffer(false)
  }

  queueIceCandidate(candidate) {
    this.candidateQueue.push(candidate)
    if (!this.flushTimer) {
      this.flushTimer = window.setTimeout(() => {
        this.flushTimer = null
        this.flushIceCandidates().catch((err) => this.onError?.(err))
      }, 200)
    }
  }

  async flushIceCandidates() {
    if (!this.canSendIce || !this.pcId || this.candidateQueue.length === 0) {
      return
    }

    const candidates = this.candidateQueue.splice(0, this.candidateQueue.length)
    const payload = candidates.map(candidatePayload).filter(Boolean)
    if (payload.length === 0) return

    await patchWebRtcIce({
      pc_id: this.pcId,
      candidates: payload,
    })
  }

  setMuted(muted) {
    this.muted = muted
    this.localStream?.getAudioTracks().forEach((track) => {
      track.enabled = !muted
    })
    this.sendSignalling({
      type: 'trackStatus',
      receiver_index: AUDIO_TRANSCEIVER_INDEX,
      enabled: !muted,
    })
  }

  sendSignalling(message) {
    if (this.dc?.readyState !== 'open') return
    this.dc.send(
      JSON.stringify({
        type: 'signalling',
        message,
      }),
    )
  }

  disconnect({ silent = false } = {}) {
    this.closed = true
    if (this.keepAlive) {
      clearInterval(this.keepAlive)
      this.keepAlive = null
    }
    if (this.flushTimer) {
      clearTimeout(this.flushTimer)
      this.flushTimer = null
    }
    this.dc?.close()
    this.localStream?.getTracks().forEach((track) => track.stop())
    this.pc?.getSenders().forEach((sender) => sender.track?.stop())
    this.pc?.close()
    this.pc = null
    this.dc = null
    this.pcId = null
    this.localStream = null
    this.onLocalStream?.(null)
    this.candidateQueue = []
    this.canSendIce = false
    if (!silent) this.onStatus?.('ended')
  }
}
