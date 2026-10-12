# 购物 SHOPPING · AI 电商客服工作台

以 AI 客服为主入口，连接客户档案、订单履约与售后工单。买家咨询与人工客服工作台共享服务上下文，商品选购为辅助业务。

技术栈：**Next.js / React / TypeScript + FastAPI / Pydantic + LangGraph + MySQL 8.0+ / SQLAlchemy Core / PyMySQL**。RAG 保留中文多粒度 BM25 基线；不声称已实现向量或混合检索。
**支付、物流和商品数据均为演示，不连接支付机构。** 默认规则模式不需要 API Key；配置后可使用真实 LLM。

## 功能

| 业务 | 已实现 |
| --- | --- |
| 用户 | 邮箱注册、密码哈希、登录会话、退出、买家与管理员权限 |
| 商品 | 分类、搜索、详情；管理员新增与编辑名称、描述、规格、价格、库存、补货日期与本地示意图；操作记录 |
| 购物车 | 数量调整、移除、服务端金额和运费计算 |
| 订单 | 事务预留库存、请求幂等、模拟支付、取消释放库存、管理员模拟发货、确认收货 |
| 客户服务 / CRM | 客户订单、咨询、工单档案；对话关联工单、24 小时演示处理时限、接单负责人及处理记录 |
| 人工协作 | 携带对话与工具摘要转人工，客户补充问题、客服回复、结单后恢复 AI；接管期间停止 AI 处理 |
| 订单履约 | 模拟发货、运输/送达节点、库存与补货日期查询；不连接商业 ERP 或物流供应商 |
| 售后 | 关联订单及会话创建工单、避免重复未完成工单、管理员接单及解决 |
| AI | LangGraph 工具循环、多轮上下文、真实 SSE、资料来源、写操作确认；管理员 AI 上新、编辑及库存调整 |
| 观察与评测 | 首次文本响应、总耗时、工具耗时、Token、按模式统计 p50/p95；检索对比、业务流程回归报告 |

## 本地启动

环境：Python 3.12+、Node.js 22+、MySQL 8.0.16+（InnoDB / utf8mb4）。项目内现有 `.env` 不会被自动改写。

先在自己的 MySQL 实例创建 `shiwu` 数据库和仅对该库有权限的应用账户，在 `backend/.env` 配置 `DATABASE_URL`。示例连接：`mysql+pymysql://shiwu:shiwu_local@127.0.0.1:3306/shiwu?charset=utf8mb4`；密码中的特殊字符需要 URL 编码。Docker 完整启动见下方 Docker 小节。

旧 `DATABASE_PATH` 仅保留为迁移源说明，应用现在读取 `DATABASE_URL`。

后端（PowerShell）：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 尚无 .env 时再执行下面这一行；已有文件请保留。
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动时幂等初始化目标 MySQL 数据库的表、索引和 schema 版本记录。演示数据包含 6 件商品、13 篇说明、1 笔已发货订单。

前端（另一个终端）：

```powershell
cd frontend
npm ci
npm run dev
```

访问 <http://localhost:3000>，接口文档 <http://127.0.0.1:8000/docs>。
首页默认进入 AI 客服工作区；管理员登录后进入工单工作台。
前端通过 Next.js `/api` 代理访问后端；换端口时设置 `BACKEND_URL`，无需向浏览器暴露容器 DNS。

依赖已安装后也可执行根目录 `start.py` 或双击 `启动项目.bat`。
脚本仅管理它自己创建的两个进程，日志写到 `logs/`，按回车停止。

```powershell
.\backend\.venv\Scripts\python.exe start.py --backend-port 8100 --frontend-port 3100
```

| 演示账户 | 邮箱 | 密码 |
| --- | --- | --- |
| 买家 | demo@shop.local | Demo12345! |
| 管理员 | admin@shop.local | Demo12345! |

登录令牌保存在浏览器当前标签页的 sessionStorage。可用两个标签页分别演示买家与管理端。
`SEED_DEMO=false` 可关闭默认账户和数据创建；此时需自行初始化商品及管理员。

## 使用真实模型

在 `backend/.env` 中配置：

```ini
AI_MODE=llm
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

重启后端。页面会显示当前实际模式；`demo` 是规则流程演示，不应计入模型能力评测。
真实模式使用异步 HTTP 与模型原生 SSE，支持增量工具参数、Token 用量、有限重试与总超时。
供应商必须支持 Chat Completions、工具调用及流式响应；不同模型需单独验证。

可以依次尝试：

1. “推荐一款适合通勤的耳机。”
2. “把 P001 加入购物车。” → 查看确认卡 → 确认后购物车变化。
3. 在购物车创建订单并模拟支付。
4. “查一下我的订单。” → “这单现在是什么状态？”
5. “订单 ORD-DEMO 的耳机左侧无法连接，帮我申请售后。”
6. 点击“转人工”，填写问题及关联订单；对话与已查资料会附在工单摘要中。
7. 在另一标签页登录管理员，在客服工作台接单、回复，填写处理结果并完成工单。
8. 买家点击“刷新进度”，看到人工回复和完成结果；继续询问“查询我的售后处理进度”。

## 管理员 AI 运营与商品管理

登录管理员后，在顶部进入「AI 运营助手」；「客服工作台」继续用于处理买家工单。「业务管理 → 商品管理」可新增、编辑、上下架商品，按编号/名称/规格及上下架状态筛选，并查看最近 50 条操作记录。

规则模式可尝试：

- `查询所有商品` / `查询已下架商品` / `查询 P001 的库存和价格`
- `下架 P001` / `重新上架 P001`
- `把 P001 的库存改为 50 件` / `把 P001 的库存增加 10 件`
- `把 P001 的售价改为 199.00`
- `把 P001 的补货日期改为 2026-11-15`
- `新增商品，编号 P007，名称 蓝牙耳机，分类 audio，售价 199.00，库存 20`

可以先说“上新一个衣服商品”，再回复“名称 纯棉T恤，售价 99.00”，最后回复“编号 CLO001，库存 20”。未完成草稿保存到当前会话，刷新后选择该会话可继续；“取消上新”会清除未完成草稿。

新增商品须提供编号、名称、分类、售价、库存。分类为 audio / workspace / charging / clothing（服装）；未提供描述和规格时留空，插图为本地示意图，服装使用衣服插图。规则模式识别上新、上架、新增或添加商品，并支持在同一会话按字段分次补齐信息；不支持任意表达；LLM 模式通过相同的 schema 与业务校验生成操作。

AI 操作展示新增内容或修改前后值，确认前不写商品。确认时重新校验管理员角色、操作归属、有效期及商品快照；期间商品或可售库存发生变化则返回冲突，需重新生成预览。确认重放只执行一次。成功的商品写入、操作状态、结果与审计记录同事务提交；拒绝和失败不产生商品修改记录。

库存为当前可售数量，不含已预留库存；价格使用整数分，历史订单保留成交快照。商品规格和描述不自动成为政策知识库文档。新增商品保存或确认后直接上架；已有商品支持下架与重新上架。下架仅改变可售状态，不删除商品、库存和历史订单；买家目录不展示，已加入购物车的商品不能结算，已有订单继续支付/履约或取消。管理员可在下架期间编辑，重新上架后使用最新资料。没有图片上传、采购入库、审批流或批量导入。

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe evaluation/run.py
.\.venv\Scripts\python.exe evaluation/service_run.py
# 可选：使用配置的密钥，产生少量模型调用费用；只使用临时库和虚构数据。
.\.venv\Scripts\python.exe scripts/smoke_llm.py
cd ..\frontend
npm run build
# 已启动本地测试服务时：
npx playwright install chromium
$env:E2E_URL="http://127.0.0.1:3000"
npm run test:e2e
```

单元回归默认使用隔离 SQLite 数据库，不连接用户数据。使用专用 MySQL 测试账户设置 `MYSQL_TEST_URL` 后，同一套业务测试会创建随机 `shiwu_test_*` 数据库，结束时只移除本次创建的库；账户须具备建库权限。**不要指向生产账户。**

测试覆盖库存竞争、事务回滚、请求幂等、订单/会话隔离、确认重放、确认过期、人工接管/回复/恢复、履约节点、SSE、模型协议及售后闭环。业务流程报告 `backend/evaluation/service-report.json` 是规则模式契约回归，不是 LLM 准确率。浏览器测试会创建虚构商品、工单，注册虚构买家并修改本次创建的商品，应使用演示环境。
检索评测为 29 条人工样例，包含口语改写和无答案查询。详见 `backend/evaluation/report.json` 与 `docs/验证记录.md`。
这个小数据集不是独立测试集，也不代表真实客服准确率；没有证据表明已提高整体模型回答准确率。

## 架构

```mermaid
flowchart LR
    UI[Next.js AI客服 / 人工工作台 / 商品] --> API[FastAPI / 身份与权限]
    API --> DB[(MySQL / InnoDB)]
    API --> CRM[客户档案 / 工单 / 人工接管]
    CRM --> DB
    API --> OMS[订单 / 库存 / 模拟履约]
    OMS --> DB
    API --> G[LangGraph prepare → assistant ⇄ tools]
    G --> R[多粒度 BM25 检索]
    G --> L[兼容 API / 原生 SSE]
    G --> T[受用户权限约束的业务工具]
    T --> P[待确认操作]
    P --> C[用户确认 / 再次校验 / 幂等执行]
    C --> DB
    G --> S[SSE 节点事件与回答]
    S --> UI
```

持久会话保存在数据库，模型输入取最近 16 条用户/助手消息。不是跨进程 LangGraph checkpoint 恢复。
每次运行最多 3 轮工具请求、每轮最多 6 个工具；写操作统一生成待确认记录，模型不能调用支付、发货或退款。

主要代码：

```text
backend/app/
  main.py                 应用创建、生命周期、健康检查与路由注册
  routers/auth.py         注册、登录、会话鉴权与退出
  routers/shop.py         商品查询、购物车与订单接口
  routers/customer_service.py  工单、转人工与会话接口
  routers/chat.py         AI 对话、SSE 与操作确认接口
  routers/admin.py        商品管理、客户档案与人工处理接口
  db.py / seed.py          SQLAlchemy表结构、连接池与幂等演示数据
  service.py               客户档案、会话历史、人工交接、工单记录与履约
  catalog.py               商品写入、快照冲突检查与事务审计
  security.py              密码、会话、鉴权
  commerce.py              购物车、交易事务、状态转换、售后
  chat.py                  会话持久化、SSE、运行记录
  agents/graph.py          有界工具循环与实际节点事件
  agents/tool_agent.py     schema 校验、用户范围、操作确认
  agents/llm_client.py     异步模型流与工具参数拼接
  knowledge_base/retriever.py  中文单字/双字 BM25
frontend/app/
  page.tsx                客服入口、对话流与辅助电商业务
  service-workspace.tsx   买家咨询、人工工作台、管理员 AI 与客户上下文
  admin-products.tsx       商品编辑与操作记录
  action-preview.tsx       字段修改前后预览
  run-insights.tsx        分模式运行观测
  product-art.tsx         本地 SVG 商品插画
  globals.css             响应式布局
frontend/lib/api.ts       API 客户端与 SSE 解码
```

## Docker

```powershell
docker compose up --build
```

默认规则模式；MySQL 8.4 数据通过 `mysql-data` 命名卷保存。MySQL 仅映射到宿主机 `127.0.0.1:3307`，后端通过容器内地址连接。默认密码仅用于本地演示；修改 `MYSQL_PASSWORD` 时同步配置包含编码密码的 `DATABASE_URL`。使用 LLM 时在根目录 `.env` 配置对应变量或通过 shell 环境传入。
前端生成 standalone 输出，代理目标在 Docker 构建时设为 `http://backend:8000`。
旧版 Vercel 临时文件系统部署配置已移除，因为本版本依赖持久 MySQL 和长连接。

## 简历与后续方向

详见 `docs/重构方向与简历.md`，面试准备见 `docs/面试问答.md`。
这是本地学习项目：未接真实支付、配送、退款、生产用户或分布式库存；暂未实现未支付订单自动超时回收、登录限流及跨实例任务恢复。
本次业务与技术取舍、MySQL 事务说明、演示路线及后续优先级见 [AI 应用开发说明](docs/AI应用开发说明.md)。

实现参考：[LangGraph 流式接口](https://docs.langchain.com/oss/python/langgraph/streaming)、[FastAPI 流式响应](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)、[Next.js 代理重写](https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites)。

MIT

## 旧 SQLite 数据迁移

先创建一个空的 MySQL 目标库，配置 `DATABASE_URL`。不要先启动默认演示种子，否则目标非空。然后执行：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts/migrate_sqlite.py --source ./data/shop.db
```

源 SQLite 以只读方式打开，原文件不删除。目标非空则拒绝；复制过程在单个 MySQL 事务内执行，并逐表检查行数。结构初始化的 DDL 与数据事务分开，失败时可能留下空表，数据插入会回滚。迁移测试验证原文件字节保持不变、数据行数一致及重复迁移被拒绝。
