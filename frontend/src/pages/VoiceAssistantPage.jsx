import { CallInterface } from '../components/voice/CallInterface'

export function VoiceAssistantPage({ voice }) {
  return (
    <div className="page-stack voice-page">
      <section className="page-intro">
        <div>
          <p className="eyebrow">VeyaCare voice</p>
          <h1>Talk to the assistant</h1>
          <p className="lede">Ask about clinic availability or appointments. You can review every booking detail before confirming.</p>
        </div>
      </section>
      <CallInterface {...voice} />
    </div>
  )
}
