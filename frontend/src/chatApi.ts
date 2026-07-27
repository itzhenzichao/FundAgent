export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export async function fetchChatHistory(sessionId: string): Promise<ChatMessage[]> {
  const res = await fetch(`/api/chat/history?session_id=${encodeURIComponent(sessionId)}`)
  return res.json()
}

export async function clearChatSession(sessionId: string): Promise<void> {
  await fetch(`/api/chat/clear?session_id=${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}

export function streamChat(
  sessionId: string,
  message: string,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController()

  fetch('/api/chat/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal: controller.signal,
  }).then(res => {
    if (!res.ok) throw new Error(`Chat request failed: ${res.status}`)
    const reader = res.body?.getReader()
    if (!reader) throw new Error('No response body')
    const decoder = new TextDecoder()
    let buffer = ''
    let finished = false

    const read: () => Promise<void> = () => {
      if (finished) return Promise.resolve()
      return reader!.read().then(({ done, value }) => {
        if (done) { finished = true; onDone(); return }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data:')) {
            const jsonStr = line.slice(5).trim()
            if (!jsonStr) continue
            try {
              const data = JSON.parse(jsonStr)
              if (data.done) { finished = true; onDone(); return }
              if (data.token) onToken(data.token)
            } catch { /* skip */ }
          }
        }
        return read()
      })
    }
    return read()
  }).catch(err => {
    if (err.name !== 'AbortError') onError(err)
  })

  return controller
}
