'use client';
import { useState } from 'react';
import type { AIRun } from '@/lib/types';

function percentile(values: number[], p: number) {
  if (!values.length) return '—';
  const sorted = [...values].sort((a, b) => a - b);
  return `${sorted[Math.max(0, Math.ceil(sorted.length * p) - 1)]} ms`;
}

export default function RunInsights({ runs }: { runs: AIRun[] }) {
  const [mode, setMode] = useState('llm');
  const filtered = runs.filter((r) => r.mode === mode);
  const complete = filtered.filter((r) => r.status === 'completed');
  const first = complete.flatMap((r) =>
    r.first_response_ms === null || r.first_response_ms === undefined
      ? []
      : [r.first_response_ms],
  );
  return (
    <section className="run-insights">
      <div className="insights-heading">
        <div>
          <h2>客服运行观测</h2>
          <p>最近 100 次运行中的实测数据，规则演示与模型调用分别统计。</p>
        </div>
        <select
          aria-label="观测模式"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="llm">LLM 模式</option>
          <option value="demo">规则演示</option>
        </select>
      </div>
      <div className="insights-grid">
        {[
          ['运行次数', filtered.length],
          ['执行完成', `${complete.length} / ${filtered.length}`],
          ['首次响应 p50', percentile(first, 0.5)],
          [
            '总耗时 p95',
            percentile(
              complete.map((r) => r.elapsed_ms),
              0.95,
            ),
          ],
          ['工具调用', filtered.reduce((n, r) => n + r.tool_calls, 0)],
          [
            'Token 用量',
            filtered.reduce(
              (n, r) => n + r.prompt_tokens + r.completion_tokens,
              0,
            ),
          ],
        ].map(([name, value]) => (
          <div key={name}>
            <span>{name}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <p className="muted">
        执行完成表示流程未报错，业务任务是否完成需通过评测单独验证。首次响应统计回答文本首次到达的时间。
      </p>
      {!filtered.length && (
        <p className="insights-empty">暂无此模式的运行数据。</p>
      )}
      {filtered.length > 0 && (
        <details className="run-traces">
          <summary>查看最近一次工具执行记录</summary>
          <p>
            {filtered[0].id} ·{' '}
            {new Date(filtered[0].created_at).toLocaleString('zh-CN')}
          </p>
          <pre>{JSON.stringify(JSON.parse(filtered[0].trace), null, 2)}</pre>
        </details>
      )}
    </section>
  );
}
