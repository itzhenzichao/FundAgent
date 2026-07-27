# 基金持仓行业分析

查询基金持仓股票的行业分布，分析基金声称方向与实际持仓的偏离度，支持自选基金管理、净值回撤分析和 AI 智能问答。

## 功能

- **基金搜索** — 输入基金代码，查询基金基本信息（名称、类型、规模、经理等）
- **持仓行业分析** — 获取基金最新持仓股票，将每只股票归入对应行业分类，汇总行业占比分布，对比基金声称的投资方向与实际持仓的偏离度
- **持仓股票分类** — 每只持仓股票标注所属行业板块（如电子、医药、新能源等），一目了然看出基金扎堆在哪些行业
- **净值走势与回撤** — 展示基金净值历史曲线，自动计算最大回撤幅度和回撤修复周期，红绿分段标注涨跌区间
- **近15日收益** — 逐日展示最近15个交易日的日收益率，涨红跌绿（符合 A 股习惯），支持倒序排列
- **自选基金管理** — 添加/移除自选基金列表，一键切换查看关注的基金
- **AI 智能问答** — 悬浮球式聊天界面，支持快捷话术（打分、持仓分析、回撤评估、风险提示），基金代码自动注入实时数据，基于郑希投资方法知识库回答

## 技术栈

- 后端：Python 3.13 + FastAPI + SQLite + AkShare + efinance + zhipuai SDK
- 前端：React 19 + TypeScript + Ant Design + ECharts + Vite + react-markdown

## 启动

### 后端
D:\Python313 是本地安装的 Python 3.13 目录。

```bash
# 安装依赖（首次）
D:\Python313\python.exe -m pip install -r backend/requirements.txt

# 启动服务
cd backend
D:\Python313\python.exe -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

后端启动后访问 http://localhost:8000/docs 可查看 API 文档。

### 前端

```bash
# 安装依赖（首次）
cd frontend
npm install

# 启动开发服务器
npm run dev
```

前端启动后访问 http://localhost:5173 ，API 请求通过 Vite 代理转发到后端 8000 端口。

## 行业数据更新

行业分类数据存储在本地 SQLite，不依赖实时 API 调用（避免限流）。

建议**每月更新一次**：

```bash
cd backend
D:\Python313\python.exe -X utf8 build_industry_cache.py
```

脚本会遍历全部 A 股（约5500只），用 efinance 获取每只股票的行业分类，写入 SQLite 数据库。预计耗时25分钟。

## AI 基金助手

### 架构

| 层 | 组件 | 说明 |
|---|---|---|
| 前端 | ChatBubble 组件 | 全局悬浮球 + 右侧抽屉式聊天界面 |
| 前端 | chatApi.ts | SSE 流式通信（fetch + ReadableStream） |
| 后端 | chat_service.py | ChatService 类，调用中转 API + 数据注入 |
| 后端 | SSE 接口 | sse-starlette EventSourceResponse |
| LLM | 智谱 GLM-5.1 | 通过中转服务（OpenAI 兼容格式）调用 |

### 核心机制

1. **SSE 流式传输**：后端逐 token 输出，前端实时渲染，用户无需等待完整回复
2. **基金数据自动注入**：当用户消息包含6位基金代码时，后端自动并发获取该基金的实时数据（基本信息、持仓行业、近15日收益、净值回撤），注入到发给 AI 的上下文中，确保 AI 用真实数据回答
3. **知识库约束**：system prompt 加载郑希投资方法（method.md）和评分体系（scorecard.md），限制 AI 只回答基金/股票话题
4. **聊天历史持久化**：SQLite 存储对话记录，关闭页面后重新打开可恢复历史

### 配置

中转 API 配置在 `backend/app/chat_service.py` 中：

```python
API_KEY = "your_api_key_here"       # 替换为你的 API key
BASE_URL = "https://ai-gateway.xxxx.cn/v1"  # 中转服务地址
MODEL = "glm-5.1"                   # 可选: glm-5.1, glm-5.2, deepseek-v4-pro, deepseek-v4-flash
```

### 前端快捷按钮

聊天输入框上方有4个快捷按钮，点击后自动填入模板话术，用户只需将 `$基金代码$` 替换为实际代码即可发送：

- **打分** — 郑希框架六维度评分
- **持仓分析** — 持仓结构和偏离度分析
- **回撤评估** — 最大回撤和净值走势
- **风险提示** — 集中度、周期、流动性风险

### API 接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/chat/send` | POST | SSE 流式聊天（请求体: session_id + message） |
| `/api/chat/history` | GET | 获取会话历史 |
| `/api/chat/clear` | DELETE | 清除会话记录 |

### 性能说明

- 基金数据注入：4线程并发获取，约0.5秒
- LLM API 响应：取决于中转网络延迟，约4-6秒
- 总体首次响应时间：约5-7秒（缓存命中后约5秒）

## 贡献

欢迎一起完善，实现小而美的工具。无论是新增功能、优化体验、修复问题还是补充知识库，都欢迎提交 Issue 或 PR。

## 免责声明

本工具仅提供数据分析和信息展示，不构成任何投资建议。投资有风险，入市需谨慎。
