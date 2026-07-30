# 基金持仓行业分析

查询基金持仓股票的行业分布，分析基金声称方向与实际持仓的偏离度，支持自选基金管理、持仓跟踪和 AI 智能问答。

## 功能

- **基金搜索** — 输入基金代码，查询基本信息（名称、类型、最新净值），支持纯债基金
- **持仓行业分析** — 持仓股票归入行业分类，汇总占比分布，对比声称方向与实际持仓的偏离度
- **债券持仓** — 查看基金债券持仓明细，纯债基金同样适用
- **净值走势与回撤** — 净值历史曲线 + 最大回撤，红绿分段标注涨跌区间
- **近15日收益** — 逐日收益率，涨红跌绿（A 股习惯）
- **自选基金管理** — 添加/移除自选，持仓跟踪（余额、收益、收益率），净值更新自动重算
- **AI 智能问答** — 悬浮球聊天，快捷话术，基金代码自动注入实时数据，郑希投资方法知识库

## 技术栈

- 后端：Python 3.13 + FastAPI + SQLite + AkShare + efinance + OpenAI SDK
- 前端：React 19 + TypeScript + Ant Design + ECharts + Vite + react-markdown

## 启动

### 配置 AI 密钥

```bash
cd backend/app
cp config.example.py config.py
```

编辑 `config.py`，填入你的 API Key：

```python
API_KEY = "your-api-key-here"
BASE_URL = "https://your-api-gateway-url/v1"
MODEL = "glm-5.1"
```

> `config.py` 已在 .gitignore 中，不会被提交到仓库。

### 后端

```bash
# 安装依赖（首次）
pip install -r backend/requirements.txt

# 启动服务
cd backend
python -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动后访问 http://localhost:8000/docs 查看 API 文档。

### 前端

```bash
cd frontend
npm install
npm run dev
```

启动后访问 http://localhost:5173 ，API 请求通过 Vite 代理转发到后端 8000 端口。

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

1. **SSE 流式传输**：后端逐 token 输出，前端实时渲染
2. **基金数据自动注入**：消息包含6位基金代码时，后端自动并发获取实时数据注入上下文
3. **知识库约束**：system prompt 加载郑希投资方法，限制 AI 只回答基金/股票话题
4. **聊天历史持久化**：SQLite 存储对话记录，关闭页面后可恢复

### 快捷按钮

聊天输入框上方有4个快捷按钮，点击后自动填入模板话术，用户只需将 `$基金代码$` 替换为实际代码即可发送：

- **打分** — 郑希框架六维度评分
- **持仓分析** — 持仓结构和偏离度分析
- **回撤评估** — 最大回撤和净值走势
- **风险提示** — 集中度、周期、流动性风险

## 致谢

AI 基金助手的知识库（投资方法 method.md、评分体系 scorecard.md）来自 [zhengxi-views](https://github.com/lyra81604/zhengxi-views) 项目的郑希观点库 Skill，感谢原作者的开放共享。

## 贡献

欢迎一起完善，实现小而美的工具。无论是新增功能、优化体验、修复问题还是补充知识库，都欢迎提交 Issue 或 PR。

## 免责声明

本工具仅提供数据分析和信息展示，不构成任何投资建议。投资有风险，入市需谨慎。
