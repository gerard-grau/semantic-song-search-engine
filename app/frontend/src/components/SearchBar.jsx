import { useState } from 'react'

export default function SearchBar({ onSearch, onReset, isLoading }) {
  const [query, setQuery] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const q = query.trim()
    if (q) {
      onSearch(q)
      setQuery('')
    }
  }

  function handleReset() {
    setQuery('')
    onReset()
  }

  return (
    <form className="search-bar" onSubmit={handleSubmit}>
      <input
        type="text"
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="Escriu una cerca (ex: cançons tristes, amor, rock català)..."
        disabled={isLoading}
      />
      <button type="submit" className="btn-search" disabled={isLoading || !query.trim()}>
        {isLoading ? 'Cercant...' : 'Cercar'}
      </button>
      <button type="button" className="btn-reset" onClick={handleReset} disabled={isLoading}>
        Reset
      </button>
    </form>
  )
}
