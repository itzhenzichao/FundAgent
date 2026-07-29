import { useState, useRef, useEffect } from 'react'
import { Button, Input, Typography, Space, Drawer, Tooltip, message } from 'antd'
import { MessageOutlined, DeleteOutlined, SendOutlined, PlusOutlined, StarOutlined, LineChartOutlined, FundOutlined, AlertOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import { v4 as uuidv4 } from 'uuid'
import { streamChat, fetchChatHistory, clearChatSession } from './chatApi'

interface DisplayMessage {
  role: 'user' | 'assistant'
  content: string
}

const QUICK_PROMPTS = [
  { label: '打分', icon: <StarOutlined />, text: '请用郑希框架给 $基金代码$ 打分，评估景气方向、ROE弹性、全球视野、流动性、集中度与周期拼接、业绩回撤印证六个维度' },
  { label: '持仓分析', icon: <FundOutlined />, text: '请分析 $基金代码$ 的持仓结构和行业分布，是否偏离其声称的投资方向' },
  { label: '回撤评估', icon: <LineChartOutlined />, text: '请评估 $基金代码$ 的最大回撤和净值走势，分析回撤的原因和修复情况' },
  { label: '风险提示', icon: <AlertOutlined />, text: '请分析 $基金代码$ 的主要风险点，包括集中度风险、行业周期风险、流动性风险等' },
]

const FUND_PLACEHOLDER = '$基金代码$'

export default function ChatBubble() {
  const [open, setOpen] = useState(false)
  const [sessionId, setSessionId] = useState(() => localStorage.getItem('jj_chat_session') || uuidv4())
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  // 用 ref 存流式内容，避免 onDone 嵌套 setState 导致重复渲染
  const streamingRef = useRef('')
  const [streamingContent, setStreamingContent] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<any>(null)

  useEffect(() => { localStorage.setItem('jj_chat_session', sessionId) }, [sessionId])

  useEffect(() => {
    if (open) {
      fetchChatHistory(sessionId).then(history => {
        setMessages(history.map(m => ({ role: m.role, content: m.content })))
      }).catch(() => {})
    }
  }, [open, sessionId])

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, streamingContent])

  const handleSend = () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setLoading(true)
    streamingRef.current = ''
    setStreamingContent('')

    // 立即添加用户消息到列表
    setMessages(prev => [...prev, { role: 'user', content: text }])

    streamChat(
      sessionId,
      text,
      (token) => {
        streamingRef.current += token
        setStreamingContent(streamingRef.current)
      },
      () => {
        // 流结束：先固化到 messages，再清空 streamingContent，避免同一渲染周期双重显示
        const content = streamingRef.current
        streamingRef.current = ''
        setMessages(prev => [...prev, { role: 'assistant', content }])
        setStreamingContent('')
        setLoading(false)
      },
      () => {
        streamingRef.current = ''
        setMessages(prev => [...prev, { role: 'assistant', content: '抱歉，回复出错，请重试。' }])
        setStreamingContent('')
        setLoading(false)
      },
    )
  }

  const handleNewChat = () => {
    setSessionId(uuidv4())
    setMessages([])
    streamingRef.current = ''
    setStreamingContent('')
  }

  const handleClear = async () => {
    await clearChatSession(sessionId)
    setMessages([])
    streamingRef.current = ''
    setStreamingContent('')
    message.success('对话已清除')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const handleQuickPrompt = (text: string) => {
    setInput(text)
    setTimeout(() => { if (inputRef.current) inputRef.current.focus() }, 100)
  }

  // 合并显示：已固化的 messages + 正在流式的 streamingContent
  const displayMessages: DisplayMessage[] = streamingContent
    ? [...messages, { role: 'assistant', content: streamingContent }]
    : messages

  return (
    <>
      <div
        style={{
          position: 'fixed', bottom: 32, right: 32,
          width: 56, height: 56, borderRadius: '50%',
          backgroundColor: '#1677ff', color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          zIndex: 1000, fontSize: 24,
        }}
        onClick={() => setOpen(true)}
        onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.1)'}
        onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
      >
        <MessageOutlined />
      </div>

      <Drawer
        title={
          <Space>
            <span>AI 基金助手</span>
            <Tooltip title="新对话"><Button size="small" icon={<PlusOutlined />} onClick={handleNewChat} /></Tooltip>
            <Tooltip title="清除对话"><Button size="small" icon={<DeleteOutlined />} onClick={handleClear} /></Tooltip>
          </Space>
        }
        placement="right"
        width={420}
        open={open}
        onClose={() => {
          if (loading && abortRef.current) abortRef.current.abort()
          setOpen(false)
        }}
        styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', height: 'calc(100% - 55px)' } }}
      >
        <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
          {displayMessages.length === 0 && (
            <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center', marginTop: 40 }}>
              输入基金或股票相关问题开始对话
            </Typography.Text>
          )}
          {displayMessages.map((msg, i) => (
            <div key={i} style={{ marginBottom: 12, display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '85%', padding: '8px 12px', borderRadius: 8,
                backgroundColor: msg.role === 'user' ? '#1677ff' : '#f5f5f5',
                color: msg.role === 'user' ? '#fff' : '#000',
                lineHeight: 1.6, wordBreak: 'break-word',
              }}>
                {msg.role === 'assistant'
                  ? <div className="chat-markdown"><ReactMarkdown>{msg.content || '...'}</ReactMarkdown></div>
                  : msg.content
                }
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div style={{ padding: 12, borderTop: '1px solid #f0f0f0' }}>
          <div style={{ marginBottom: 8 }}>
            <Space size={6}>
              {QUICK_PROMPTS.map(q => (
                <Button key={q.label} size="small" icon={q.icon} onClick={() => handleQuickPrompt(q.text)} disabled={loading}>
                  {q.label}
                </Button>
              ))}
            </Space>
          </div>
          <Space.Compact style={{ width: '100%' }}>
            <Input.TextArea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`输入基金或股票相关问题，或点击上方快捷按钮（将「${FUND_PLACEHOLDER}」替换为实际基金代码）`}
              autoSize={{ minRows: 1, maxRows: 3 }}
              disabled={loading}
              style={{ borderRadius: '8px 0 0 8px' }}
            />
            <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading} style={{ height: 'auto', borderRadius: '0 8px 8px 0' }} />
          </Space.Compact>
        </div>
      </Drawer>
    </>
  )
}
