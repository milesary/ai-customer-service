# 开发指南

环境与启动见 [README](README.md)。Python 3.12+，Node.js 22+；默认规则模式无需模型密钥。

## 提交前

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe evaluation/run.py
.\.venv\Scripts\python.exe evaluation/service_run.py
cd ..\frontend
npm run build
```

真实模型验证脚本 `backend/scripts/smoke_llm.py` 会调用配置的供应商并产生少量费用，请按需要手动运行。
不要提交密钥、真实用户会话、运行数据库或付款数据。样例必须是虚构或经过授权脱敏的数据。

## 改动约束

- 新工具须定义 Pydantic 参数模型，并通过服务端用户身份约束数据范围。
- AI 写操作须进入待确认流程，禁止增加模型可直接执行的支付、退款或管理员工具。
- 库存、订单、购物车的一致性须保留在事务内。新增状态转换应补对应失败与重试测试。
- 检索算法在相同语料及标注上对比，保留失败样例；不要仅通过更新样例来宣称提升。
- 前端请求经 `/api` 代理；自定义后端地址使用服务端 `BACKEND_URL`。
- 新部署方式必须提供持久数据库。使用 MySQL 8.0.16+ / InnoDB；默认单测用隔离 SQLite，MySQL 语义须用专用 MYSQL_TEST_URL 验证。

建议分支前缀 `codex/`，提交消息使用 `feat:`、`fix:`、`refactor:`、`docs:` 或 `test:`。
