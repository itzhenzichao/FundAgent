import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorBgBase: '#0f172a',
          colorBgContainer: '#1e293b',
          colorBgElevated: '#1e293b',
          colorBgLayout: '#0f172a',
          colorPrimary: '#1677ff',
          colorBorder: 'rgba(255,255,255,0.08)',
          colorBorderSecondary: 'rgba(255,255,255,0.06)',
          borderRadius: 8,
        },
        components: {
          Table: {
            headerBg: 'rgba(255,255,255,0.04)',
            rowHoverBg: 'rgba(255,255,255,0.06)',
          },
          Collapse: {
            contentBg: '#1e293b',
            headerBg: 'rgba(255,255,255,0.03)',
          },
          Card: {
            colorBgContainer: '#1e293b',
          },
          Modal: {
            contentBg: '#1e293b',
            headerBg: '#1e293b',
          },
          Drawer: {
            colorBgElevated: '#1e293b',
          },
          Input: {
            colorBgContainer: '#0f172a',
          },
          Segmented: {
            itemActiveBg: 'rgba(255,255,255,0.08)',
          },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </StrictMode>,
)
