import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

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
