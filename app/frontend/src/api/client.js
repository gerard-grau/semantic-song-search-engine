import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 120000 })

export async function fetchAllSongs() {
  const { data } = await api.get('/songs')
  return data
}

export async function filterSongs(query, songIds = null) {
  const { data } = await api.post('/filter', {
    query,
    song_ids: songIds,
  })
  return data
}

export async function fetchSongDetail(songId) {
  const { data } = await api.get(`/songs/${songId}`)
  return data
}

export async function fetchNeighbors(songId, options = {}) {
  const {
    n = 20,
    songIds = null,
    previousSongId = null,
    bridgeSongIds = [],
    bridgeCount = 5,
    previousPositions = [],
  } = options
  const { data } = await api.post('/neighbors', {
    song_id: songId,
    n,
    song_ids: songIds,
    previous_song_id: previousSongId,
    bridge_song_ids: bridgeSongIds,
    bridge_count: bridgeCount,
    previous_positions: previousPositions,
  })
  return data
}
