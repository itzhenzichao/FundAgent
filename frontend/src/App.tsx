import { useState, useEffect } from 'react'
import { Input, Card, Descriptions, Table, Tag, Alert, Spin, Typography, Tabs, Button, message, Segmented, Collapse, Modal, Form, InputNumber } from 'antd'
import ChatBubble from './ChatBubble'
import { SearchOutlined, StarOutlined, StarFilled, DeleteOutlined, WalletOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { searchFund, getFundIndustry, addWatchlist, removeWatchlist, getWatchlist, getFundNav, getFundReturns, getBondHoldings, updatePosition } from './api'
import type { FundInfo, FundIndustryResult, Holding, WatchlistItem, NavData, ReturnsData, BondHoldingData } from './api'
import './App.css'

const PERIOD_OPTIONS = [
  { label: '近1月', value: '1m' },
  { label: '近3月', value: '3m' },
  { label: '近6月', value: '6m' },
  { label: '近1年', value: '1y' },
  { label: '近3年', value: '3y' },
]

function App() {
  const [activeTab, setActiveTab] = useState('search')
  const [fundCode, setFundCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [fundInfo, setFundInfo] = useState<FundInfo | null>(null)
  const [industryResult, setIndustryResult] = useState<FundIndustryResult | null>(null)
  const [truncated, setTruncated] = useState(false)
  const [totalCount, setTotalCount] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])
  const [isInWatchlist, setIsInWatchlist] = useState(false)
  const [navPeriod, setNavPeriod] = useState('1y')
  const [navData, setNavData] = useState<NavData | null>(null)
  const [returnsData, setReturnsData] = useState<ReturnsData | null>(null)
  const [bondData, setBondData] = useState<BondHoldingData | null>(null)
  const [watchlistFilter, setWatchlistFilter] = useState<string>('全部')
  const [positionModalOpen, setPositionModalOpen] = useState(false)
  const [positionFund, setPositionFund] = useState<WatchlistItem | null>(null)
  const [positionForm] = Form.useForm()
  const [watchlistLoading, setWatchlistLoading] = useState(false)
  const [toggleWatchlistLoading, setToggleWatchlistLoading] = useState(false)
  const [removingCode, setRemovingCode] = useState<string | null>(null)
  const [positionSaving, setPositionSaving] = useState(false)
  const [navLoading, setNavLoading] = useState(false)

  const loadWatchlist = async () => {
    setWatchlistLoading(true)
    try {
      const list = await getWatchlist()
      setWatchlist(list)
    } catch {} finally {
      setWatchlistLoading(false)
    }
  }

  const loadNavData = async (code: string, period: string) => {
    setNavLoading(true)
    try {
      const data = await getFundNav(code, period)
      setNavData(data)
    } catch {
      setNavData(null)
    } finally {
      setNavLoading(false)
    }
  }

  const loadReturnsData = async (code: string) => {
    try {
      const data = await getFundReturns(code)
      setReturnsData(data)
    } catch {
      setReturnsData(null)
    }
  }

  const loadBondData = async (code: string) => {
    try {
      const data = await getBondHoldings(code)
      setBondData(data)
    } catch {
      setBondData(null)
    }
  }

  useEffect(() => { loadWatchlist() }, [])

  useEffect(() => {
    if (fundInfo) loadNavData(fundInfo.code, navPeriod)
  }, [navPeriod])

  const handleSearch = async (code?: string) => {
    const searchCode = code || fundCode.trim()
    if (!searchCode) return
    setLoading(true)
    setError(null)
    setFundInfo(null)
    setIndustryResult(null)
    setNavData(null)
    setReturnsData(null)
    setBondData(null)

    if (!code) setFundCode(searchCode)

    try {
      const info = await searchFund(searchCode)
      setFundInfo(info)

      setIsInWatchlist(watchlist.some(w => w.code === searchCode))
      setActiveTab('search')

      loadNavData(searchCode, navPeriod)
      loadReturnsData(searchCode)
      loadBondData(searchCode)

      // 行业分析独立调用，不影响主搜索流程
      getFundIndustry(searchCode, undefined, info.name).then(industry => {
        setIndustryResult(industry)
        setTruncated(industry.truncated)
        setTotalCount(industry.total_count)
      }).catch(() => {
        setIndustryResult(null)
      })
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || '查询失败')
    } finally {
      setLoading(false)
    }
  }

  const handleToggleWatchlist = async () => {
    if (!fundInfo) return
    setToggleWatchlistLoading(true)
    try {
      if (isInWatchlist) {
        await removeWatchlist(fundInfo.code)
        message.success('已从自选移除')
      } else {
        await addWatchlist(fundInfo.code, fundInfo.name)
        message.success('已添加到自选')
      }
      setIsInWatchlist(!isInWatchlist)
      loadWatchlist()
    } catch {
      message.error('操作失败')
    } finally {
      setToggleWatchlistLoading(false)
    }
  }

  const handleRemoveFromWatchlist = async (code: string) => {
    setRemovingCode(code)
    try {
      await removeWatchlist(code)
      message.success('已从自选移除')
      loadWatchlist()
      if (fundInfo && fundInfo.code === code) setIsInWatchlist(false)
    } catch {
      message.error('操作失败')
    } finally {
      setRemovingCode(null)
    }
  }

  const handleOpenPosition = (record: WatchlistItem) => {
    setPositionFund(record)
    positionForm.setFieldsValue({
      position_amount: record.is_holding && record.balance !== null ? record.balance : undefined,
      profit: record.is_holding && record.profit !== null ? record.profit : undefined,
    })
    setPositionModalOpen(true)
  }

  const handleSavePosition = async () => {
    if (!positionFund) return
    setPositionSaving(true)
    try {
      const values = await positionForm.validateFields()
      await updatePosition(positionFund.code, values.position_amount || 0, values.profit || 0)
      message.success('持仓已更新')
      setPositionModalOpen(false)
      loadWatchlist()
    } catch {
      message.error('更新失败')
    } finally {
      setPositionSaving(false)
    }
  }

  // 净值趋势图：绿色=最大回撤区间，红色=其他所有区间（含修复段）
  const navChartOption = navData ? (() => {
    const dates = navData.nav_data.map(d => d.date)
    const navValues = navData.nav_data.map(d => d.nav)
    const drawdownValues = navData.drawdown_data.map(d => d.drawdown)

    // 找最大回撤区间起止索引
    const minDDValue = Math.min(...drawdownValues)
    const minDDIndex = drawdownValues.indexOf(minDDValue)
    const maxDDStartIndex = (() => {
      for (let i = minDDIndex; i >= 0; i--) {
        if (drawdownValues[i] >= 0) return i + 1
      }
      return 0
    })()
    const maxDDEndIndex = (() => {
      for (let i = minDDIndex; i < drawdownValues.length; i++) {
        if (drawdownValues[i] >= 0) return i - 1
      }
      return drawdownValues.length - 1
    })()

    // 每个series用完整长度数组，非本段的数据用null，保证对齐
    // 红色前段：0 ~ maxDDStartIndex - 1（不含回撤起点）
    const redBefore = navValues.map((v, i) =>
      i < maxDDStartIndex ? v : null
    )

    // 绿色段：maxDDStartIndex - 1（衔接点）~ maxDDEndIndex + 1（衔接点）
    const greenDD = navValues.map((v, i) => {
      if (i === maxDDStartIndex - 1) return v // 前衔接点
      if (i === maxDDEndIndex + 1) return v // 后衔接点
      if (i >= maxDDStartIndex && i <= maxDDEndIndex) return v
      return null
    })

    // 红色后段：maxDDEndIndex + 1 ~ end（从后衔接点开始）
    const redAfter = navValues.map((v, i) =>
      i >= maxDDEndIndex + 1 ? v : null
    )

    return {
      tooltip: { trigger: 'axis', formatter: (params: any) => {
        const p = params.find((x: any) => x.value != null)
        if (!p) return ''
        const idx = p.dataIndex
        const dd = drawdownValues[idx] ?? 0
        const state = idx >= maxDDStartIndex && idx <= maxDDEndIndex ? '最大回撤区间' : '正常'
        return `${dates[idx]}<br/>净值: ${p.value}<br/>回撤: ${dd}%<br/>状态: ${state}`
      }},
      grid: { left: 60, right: 30, top: 30, bottom: 40 },
      legend: { data: ['净值', '最大回撤区间'], top: 0 },
      xAxis: { type: 'category', data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
      yAxis: { type: 'value', name: '净值', scale: true },
      animation: false,
      series: [
        {
          name: '净值',
          type: 'line',
          data: redBefore,
          smooth: true,
          lineStyle: { width: 2, color: '#ff4d4f' },
          itemStyle: { color: '#ff4d4f' },
          symbol: 'none',
          connectNulls: false,
        },
        {
          name: '最大回撤区间',
          type: 'line',
          data: greenDD,
          smooth: true,
          lineStyle: { width: 2.5, color: '#2e7d32' },
          itemStyle: { color: '#2e7d32' },
          symbol: 'none',
          connectNulls: true,
          markArea: {
            silent: true,
            data: [[
              { xAxis: dates[maxDDStartIndex], itemStyle: { color: 'rgba(46,125,50,0.15)' } },
              { xAxis: dates[maxDDEndIndex] },
            ]],
          },
        },
        {
          name: '净值',
          type: 'line',
          data: redAfter,
          smooth: true,
          lineStyle: { width: 2, color: '#ff4d4f' },
          itemStyle: { color: '#ff4d4f' },
          symbol: 'none',
          connectNulls: false,
        },
      ],
    }
  })() : null

  const industryPieOption = industryResult ? {
    tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
    legend: { orient: 'vertical', left: 'left', type: 'scroll' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
      label: { show: true, formatter: '{b}\n{c}%' },
      data: industryResult.industry_distribution.map(item => ({
        name: item.industry,
        value: Math.round(item.total_ratio * 100) / 100,
      })),
    }],
  } : null

  const holdingsColumns = [
    { title: '股票代码', dataIndex: 'stock_code', key: 'stock_code' },
    { title: '股票名称', dataIndex: 'stock_name', key: 'stock_name' },
    {
      title: '持仓占比', dataIndex: 'holding_ratio', key: 'holding_ratio',
      render: (v: number | null) => v ? `${v}%` : '-',
    },
    {
      title: '所属行业', key: 'industry',
      render: (_: any, record: Holding) => {
        if (!industryResult) return '-'
        const matched = industryResult.industry_distribution.find(ind =>
          ind.stocks.some(s => s.stock_code === record.stock_code)
        )
        if (matched) return <Tag color="blue">{matched.industry}</Tag>
        return <Tag color="orange">未匹配</Tag>
      },
    },
  ]

  const allHoldings: Holding[] = industryResult
    ? [...industryResult.industry_distribution.flatMap(ind => ind.stocks.map(s => ({ ...s, quarter: industryResult.quarter }))),
       ...industryResult.unmatched_stocks.map(s => ({ ...s, quarter: industryResult.quarter }))]
    : []

  const bondHoldingsColumns = [
    { title: '债券代码', dataIndex: 'bond_code', key: 'bond_code' },
    { title: '债券名称', dataIndex: 'bond_name', key: 'bond_name' },
    {
      title: '占净值比例', dataIndex: 'holding_ratio', key: 'holding_ratio',
      render: (v: number | null) => v ? `${v}%` : '-',
    },
    {
      title: '持仓市值(万)', dataIndex: 'holding_value', key: 'holding_value',
      render: (v: number | null) => v ? `${v}` : '-',
    },
  ]

  const watchlistColumns = [
    { title: '基金代码', dataIndex: 'code', key: 'code' },
    { title: '基金名称', dataIndex: 'name', key: 'name' },
    {
      title: '状态', key: 'is_holding',
      render: (_: any, record: WatchlistItem) =>
        record.is_holding ? <Tag color="green">持有</Tag> : null,
    },
    {
      title: '当前余额', key: 'balance',
      render: (_: any, record: WatchlistItem) =>
        record.is_holding && record.balance !== null ? record.balance.toLocaleString() : '-',
    },
    {
      title: '收益', key: 'profit',
      render: (_: any, record: WatchlistItem) => {
        if (!record.is_holding || record.profit === null) return '-'
        const v = record.profit
        return <span style={{ color: v >= 0 ? '#cf1322' : '#3f8600', fontWeight: 600 }}>{v >= 0 ? '+' : ''}{v.toLocaleString()}</span>
      },
    },
    {
      title: '收益率', key: 'profit_rate',
      render: (_: any, record: WatchlistItem) => {
        if (!record.is_holding || record.profit_rate === null) return '-'
        const v = record.profit_rate
        return <span style={{ color: v >= 0 ? '#cf1322' : '#3f8600', fontWeight: 600 }}>{v >= 0 ? '+' : ''}{v}%</span>
      },
    },
    {
      title: '更新时间', dataIndex: 'updated_at', key: 'updated_at',
      render: (v: string) => v?.slice(0, 16).replace('T', ' ') || '-',
    },
    {
      title: '操作', key: 'action',
      render: (_: any, record: WatchlistItem) => (
        <>
          <Button type="link" size="small" onClick={() => handleSearch(record.code)}>查看</Button>
          <Button type="link" size="small" icon={<WalletOutlined />} onClick={() => handleOpenPosition(record)}>持仓</Button>
          <Button type="link" size="small" danger loading={removingCode === record.code} onClick={() => handleRemoveFromWatchlist(record.code)}>
            {removingCode !== record.code && <><DeleteOutlined /> 移除</>}
          </Button>
        </>
      ),
    },
  ]

  const returnsColumns = [
    { title: '日期', dataIndex: 'date', key: 'date' },
    { title: '净值', dataIndex: 'nav', key: 'nav', render: (v: number) => v.toFixed(4) },
    {
      title: '日收益率', dataIndex: 'daily_return', key: 'daily_return',
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#3f8600' }}>
          {v >= 0 ? `+${v}%` : `${v}%`}
        </span>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: 24 }}>
      <Typography.Title level={2}>基金持仓行业分析</Typography.Title>

      <Collapse
        defaultActiveKey={['disclaimer']}
        style={{ marginBottom: 24 }}
        items={[{
          key: 'disclaimer',
          label: '免责声明',
          children: (
            <Alert
              message="本工具仅提供数据分析和信息展示，不构成任何投资建议。投资有风险，入市需谨慎。过往业绩不代表未来表现。"
              type="warning"
              showIcon
            />
          ),
        }]}
      />

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        {
          key: 'search',
          label: '查询',
          children: (
            <>
              <Input.Search
                placeholder="输入基金代码，如 003293"
                enterButton={<><SearchOutlined /> 查询</>}
                size="large"
                value={fundCode}
                onChange={e => setFundCode(e.target.value)}
                onSearch={() => handleSearch()}
                loading={loading}
                style={{ marginBottom: 24 }}
              />

              {error && <Alert message={error} type="error" style={{ marginBottom: 24 }} />}
              {loading && <Spin size="large" style={{ display: 'block', margin: '40px auto' }} />}

              {fundInfo && (
                <Collapse
                  defaultActiveKey={['info']}
                  style={{ marginBottom: 24 }}
                  items={[{
                    key: 'info',
                    label: `${fundInfo.name} (${fundInfo.code})`,
                    extra: (
                      <Button
                        type="text"
                        icon={isInWatchlist ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
                        onClick={handleToggleWatchlist}
                        loading={toggleWatchlistLoading}
                      >
                        {isInWatchlist ? '已自选' : '加自选'}
                      </Button>
                    ),
                    children: (
                      <Descriptions column={2}>
                        <Descriptions.Item label="基金类型">{fundInfo.type}</Descriptions.Item>
                        <Descriptions.Item label="最新净值">
                          {fundInfo.latest_nav ?? '-'} ({fundInfo.latest_date ?? '-'})
                        </Descriptions.Item>
                      </Descriptions>
                    ),
                  }]}
                />
              )}

              {returnsData && (
                <Collapse
                  defaultActiveKey={['returns']}
                  style={{ marginBottom: 24 }}
                  items={[{
                    key: 'returns',
                    label: '近15个交易日收益',
                    children: (
                      <Table
                        columns={returnsColumns}
                        dataSource={[...returnsData.returns].reverse()}
                        rowKey="date"
                        pagination={false}
                        size="small"
                      />
                    ),
                  }]}
                />
              )}

              {navData && fundInfo && (
                <Collapse
                  defaultActiveKey={['nav']}
                  style={{ marginBottom: 24 }}
                  items={[{
                    key: 'nav',
                    label: '净值走势 & 回撤分析',
                    extra: <Segmented options={PERIOD_OPTIONS} value={navPeriod} onChange={v => setNavPeriod(v as string)} disabled={navLoading} />,
                    children: (
                      <>
                        {navLoading && <Spin size="large" style={{ display: 'block', margin: '20px auto' }} />}
                        {!navLoading && (
                          <>
                            <Typography.Text type="secondary" style={{ marginBottom: 8 }}>
                              区间最大回撤: <Typography.Text type="danger">{navData.max_drawdown}%</Typography.Text>
                            </Typography.Text>
                            {navChartOption && <ReactECharts option={navChartOption} style={{ height: 300 }} />}
                          </>
                        )}
                      </>
                    ),
                  }]}
                />
              )}

              {industryResult && industryResult.deviation && (
                <Collapse
                  defaultActiveKey={['deviation']}
                  style={{ marginBottom: 24 }}
                  items={[{
                    key: 'deviation',
                    label: industryResult.deviation.is_deviant ? '偏离提示' : '合规检查',
                    children: (
                      <Alert
                        message={industryResult.deviation.is_deviant
                          ? `该基金声称方向为"${industryResult.deviation.claimed_industry}"，但实际持仓占比仅 ${industryResult.deviation.claimed_ratio}%，低于 80% 合规底线`
                          : `该基金声称方向为"${industryResult.deviation.claimed_industry}"，实际持仓占比 ${industryResult.deviation.claimed_ratio}%，满足 80% 合规要求`}
                        type={industryResult.deviation.is_deviant ? 'error' : 'success'}
                        showIcon
                      />
                    ),
                  }]}
                />
              )}

              {industryResult && (
                <Collapse
                  defaultActiveKey={['industry', 'holdings']}
                  style={{ marginBottom: 24 }}
                  items={[
                    {
                      key: 'industry',
                      label: '行业分布',
                      children: (
                        industryPieOption ? <ReactECharts option={industryPieOption} style={{ height: 400 }} /> : null
                      ),
                    },
                    {
                      key: 'holdings',
                      label: `持仓股票 (${industryResult.quarter})`,
                      children: (
                        <>
                          {truncated && (
                            <Alert
                              message={`该季度共有 ${totalCount} 只持仓股票，当前仅显示前 20 只`}
                              type="info"
                              showIcon
                              style={{ marginBottom: 12 }}
                            />
                          )}
                          <Table
                            columns={holdingsColumns}
                            dataSource={allHoldings}
                            rowKey="stock_code"
                            pagination={false}
                            size="small"
                          />
                        </>
                      ),
                    },
                  ]}
                />
              )}

              {bondData && bondData.bond_holdings.length > 0 && (
                <Collapse
                  defaultActiveKey={['bonds']}
                  style={{ marginBottom: 24 }}
                  items={[{
                    key: 'bonds',
                    label: `债券持仓 (${bondData.quarter})`,
                    children: (
                      <>
                        {bondData.truncated && (
                          <Alert
                            message={`该季度共有 ${bondData.total_count} 只债券持仓，当前仅显示前 20 只`}
                            type="info"
                            showIcon
                            style={{ marginBottom: 12 }}
                          />
                        )}
                        <Table
                          columns={bondHoldingsColumns}
                          dataSource={bondData.bond_holdings}
                          rowKey="bond_code"
                          pagination={false}
                          size="small"
                        />
                      </>
                    ),
                  }]}
                />
              )}
            </>
          ),
        },
        {
          key: 'watchlist',
          label: '自选',
          children: (
            <>
              <Segmented
                options={['全部', '持有']}
                value={watchlistFilter}
                onChange={v => setWatchlistFilter(v as string)}
                style={{ marginBottom: 16 }}
              />
              <Card title="自选基金列表">
                {watchlistLoading && watchlist.length === 0 ? (
                  <Spin size="large" style={{ display: 'block', margin: '40px auto' }} />
                ) : watchlist.length === 0 ? (
                  <Typography.Text type="secondary">暂无自选基金，查询基金后点击"加自选"添加</Typography.Text>
                ) : (
                  <Table
                    columns={watchlistColumns}
                    dataSource={watchlistFilter === '持有' ? watchlist.filter(w => w.is_holding) : watchlist}
                    rowKey="code"
                    pagination={false}
                    size="small"
                    loading={watchlistLoading}
                  />
                )}
              </Card>
            </>
          ),
        },
      ]} />
      <ChatBubble />

      <Modal
        title={positionFund ? `持仓设置 - ${positionFund.name}` : '持仓设置'}
        open={positionModalOpen}
        onOk={handleSavePosition}
        confirmLoading={positionSaving}
        onCancel={() => setPositionModalOpen(false)}
        okText="保存"
      >
        <Form form={positionForm} layout="vertical">
          <Form.Item name="position_amount" label="当前余额（元）" rules={[{ required: true, message: '请输入当前余额' }]}>
            <InputNumber style={{ width: '100%' }} min={0} precision={2} placeholder="输入当前余额" />
          </Form.Item>
          <Form.Item name="profit" label="持有收益（元）" rules={[{ required: true, message: '请输入持有收益' }]}>
            <InputNumber style={{ width: '100%' }} precision={2} placeholder="亏损输入负数" />
          </Form.Item>
          <Typography.Text type="secondary">
            系统会根据基金净值变化自动更新余额和收益。余额和收益都输入0可清除持仓。
          </Typography.Text>
        </Form>
      </Modal>
    </div>
  )
}

export default App
