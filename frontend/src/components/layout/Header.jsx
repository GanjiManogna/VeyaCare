import { useState } from 'react'
import { useApp } from '../../hooks/useApp'
import { useBackendStatus } from '../../hooks/useBackendStatus'

export function Header() {
  const status = useBackendStatus()
  const { displayName, setDisplayName } = useApp()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(displayName)
  const [nameError, setNameError] = useState('')

  function saveName(event) {
    event.preventDefault()
    if (!name.trim()) { setNameError('Name cannot be blank.'); return }
    setDisplayName(name)
    setNameError('')
    setEditing(false)
  }

  return (
    <header className="topbar">
      <div className="wordmark">
        <span className="brand-mark" aria-hidden="true">
          V
        </span>
        <div>
          <strong>VeyaCare</strong>
          <p>Your care, in good hands.</p>
        </div>
      </div>
      <div
        className={`connection ${status.connected ? 'online' : 'offline'}`}
        role="status"
      >
        <span className="pulse" />
        <div>
          <strong>
            {status.loading ? 'Checking' : status.connected ? 'Connected' : 'Offline'}
          </strong>
          <p>{status.message}</p>
        </div>
      </div>
      <div className="profile-area">
        <span className="profile-avatar" aria-hidden="true">{displayName.slice(0, 1).toUpperCase()}</span>
        <div className="profile-copy"><strong>{displayName}</strong><span>Personal profile</span></div>
        <button className="ghost profile-edit" onClick={() => { setName(displayName); setNameError(''); setEditing((value) => !value) }} aria-expanded={editing}>Edit</button>
        {editing ? (
          <form className="profile-popover" onSubmit={saveName}>
            <label>Your display name<input autoFocus required value={name} onChange={(event) => { setName(event.target.value); setNameError('') }} /></label>
            {nameError ? <p className="banner error" role="alert">{nameError}</p> : null}
            <div><button type="button" className="ghost" onClick={() => setEditing(false)}>Cancel</button><button className="primary">Save</button></div>
          </form>
        ) : null}
      </div>
    </header>
  )
}
