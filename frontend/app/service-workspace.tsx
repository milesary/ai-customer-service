'use client';

import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '@/lib/api';
import { money } from '@/lib/format';
import type {
  User,
  Ticket,
  CustomerContext,
  Conversation,
  ChatMessage,
} from '@/lib/types';

const status: Record<string, string> = {
  open: '待接单',
  processing: '处理中',
  resolved: '已完成',
  pending_payment: '待支付',
  paid: '待发货',
  shipped: '已发货',
  completed: '已收货',
  cancelled: '已取消',
};
const date = (value: string) =>
  new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

type Props = {
  aiOperations?: boolean;
  user: User | null;
  mode: string;
  database: string;
  tickets: Ticket[];
  conversations: Conversation[];
  conversationId: string | null;
  chatBusy: boolean;
  chat: ReactNode;
  onLogin: () => void;
  onSend: (text: string) => void;
  onConversation: (id: string) => Promise<void>;
  onDeleteConversation: (conversation: Conversation) => void;
  onRefresh: () => Promise<void>;
  onOrders: () => void;
};

export default function ServiceWorkspace(p: Props) {
  const admin = p.user?.role === 'admin';
  const operating = admin && p.aiOperations;
  const [customers, setCustomers] = useState<User[]>([]);
  const [customerId, setCustomerId] = useState('');
  const [context, setContext] = useState<CustomerContext | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [humanMessages, setHumanMessages] = useState<ChatMessage[]>([]);
  const [reply, setReply] = useState('');
  const [resolution, setResolution] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('active');
  const [handoffReason, setHandoffReason] = useState('');
  const [handoffOrder, setHandoffOrder] = useState('');
  const [showHandoff, setShowHandoff] = useState(false);
  const [deliveryNote, setDeliveryNote] = useState('');
  const selected = p.tickets.find((t) => t.id === selectedId);
  const active = context?.tickets.find(
    (t) =>
      t.conversation_id === p.conversationId &&
      t.category === 'handoff' &&
      t.status !== 'resolved',
  );
  const queue = p.tickets.filter(
    (t) => filter === 'all' || t.status !== 'resolved',
  );

  useEffect(() => {
    let disposed = false;
    if (admin)
      void api<User[]>('/admin/customers')
        .then((list) => {
          if (!disposed) setCustomers(list);
        })
        .catch((e) => {
          if (!disposed) setError(e.message);
        });
    return () => {
      disposed = true;
    };
  }, [admin, p.user?.id, p.tickets]);

  const refreshContext = useCallback(async () => {
    if (!p.user) return;
    const id = admin ? customerId : p.user.id;
    if (!id) return;
    const data = await api<CustomerContext>(
      admin ? `/admin/customers/${id}` : '/service/context',
    );
    setContext(data);
  }, [admin, customerId, p.user]);

  useEffect(() => {
    let disposed = false;
    const id = admin ? customerId : p.user?.id;
    if (id)
      void api<CustomerContext>(
        admin ? `/admin/customers/${id}` : '/service/context',
      )
        .then((data) => {
          if (!disposed) setContext(data);
        })
        .catch((e) => {
          if (!disposed) setError(e.message);
        });
    return () => {
      disposed = true;
    };
  }, [admin, customerId, p.user?.id, p.tickets, p.conversations]);

  useEffect(() => {
    let disposed = false;
    if (selected?.conversation_id)
      void api<{ messages: ChatMessage[] }>(
        `/admin/conversations/${selected.conversation_id}`,
      )
        .then((data) => {
          if (!disposed) setHumanMessages(data.messages);
        })
        .catch((e) => {
          if (!disposed) setError(e.message);
        });
    return () => {
      disposed = true;
    };
  }, [selected?.conversation_id, p.tickets]);

  async function work(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await action();
      await p.onRefresh();
      await refreshContext();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function select(ticket: Ticket) {
    setSelectedId(ticket.id);
    setCustomerId(ticket.user_id);
    setContext(null);
    setHumanMessages([]);
    setReply('');
    setResolution('');
  }

  return (
    <section className="service-shell">
      <div className="service-heading">
        <div>
          <span className="service-kicker">SHOPPING SERVICE</span>
          <h1>
            {operating ? 'AI 运营助手' : admin ? '客服工作台' : 'AI 电商客服'}
          </h1>
          <p>
            {operating
              ? '查询商品、上新与上下架、调价和改库存，确认后执行并留存记录。'
              : admin
                ? '接管客户咨询，关联订单与售后，记录每一步处理。'
                : '查订单、解答政策、协助售后。业务操作由你确认。'}
          </p>
        </div>
        <div className="service-mode">
          <span className="mode-dot" />
          {p.mode === 'llm' ? '模型服务' : '规则演示'}
          <span className="database-tag">
            {p.database === 'mysql'
              ? 'MySQL'
              : p.database === 'sqlite-test'
                ? '测试数据库'
                : '数据库待确认'}
          </span>
        </div>
      </div>
      <div className="service-layout">
        <aside className="service-sidebar">
          <div className="sidebar-title">
            <h2>{admin && !operating ? '工单队列' : '我的会话'}</h2>
            {admin && !operating ? (
              <select
                aria-label="筛选工单"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="active">待处理</option>
                <option value="all">全部</option>
              </select>
            ) : (
              <button
                disabled={p.chatBusy}
                className="text-button"
                onClick={() => void p.onConversation('')}
              >
                ＋ 新建
              </button>
            )}
          </div>
          {!p.user ? (
            <div className="sidebar-empty">
              <p>登录后保存会话，并查询你的订单和售后。</p>
              <button className="primary full" onClick={p.onLogin}>
                登录 / 注册
              </button>
            </div>
          ) : admin && !operating ? (
            <>
              <div className="queue-count">
                {queue.length} 个{filter === 'all' ? '工单' : '待处理工单'}
              </div>
              <div className="session-list">
                {queue.map((t) => (
                  <button
                    className={`session-row ${selectedId === t.id ? 'selected' : ''}`}
                    key={t.id}
                    onClick={() => select(t)}
                  >
                    <span className="session-title">{t.reason}</span>
                    <span className="session-meta">
                      <span>
                        {t.category === 'handoff' ? '人工接管' : '售后服务'}
                      </span>
                      <span>{status[t.status]}</span>
                    </span>
                    <small>{t.id}</small>
                  </button>
                ))}
              </div>
              {!queue.length && (
                <p className="sidebar-empty">
                  暂无待处理工单。可在买家标签页申请售后或转人工。
                </p>
              )}
              <label className="customer-selector">
                客户档案
                <select
                  value={customerId}
                  onChange={(e) => {
                    setCustomerId(e.target.value);
                    setContext(null);
                    setSelectedId('');
                    setHumanMessages([]);
                  }}
                >
                  <option value="">选择客户</option>
                  {customers.map((c) => (
                    <option value={c.id} key={c.id}>
                      {c.name} · {c.email}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : (
            <>
              <div className="session-list">
                {p.conversations.map((c) => (
                  <div className="session-entry" key={c.id}>
                    <button
                      disabled={p.chatBusy || busy}
                      className={`session-row ${p.conversationId === c.id ? 'selected' : ''}`}
                      onClick={() => void p.onConversation(c.id)}
                    >
                      <span className="session-title" title={c.title}>
                        {c.title}
                      </span>
                      <span className="session-meta">查看对话记录</span>
                    </button>
                    <button
                      className="session-delete"
                      aria-label={`删除会话：${c.title}`}
                      disabled={
                        p.chatBusy ||
                        busy ||
                        (c.id === p.conversationId && !!active)
                      }
                      onClick={() => p.onDeleteConversation(c)}
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
              {!p.conversations.length && (
                <p className="sidebar-empty">开始一次咨询，这里会保存会话。</p>
              )}
              <div className="scenario-list">
                <h3>{operating ? '店铺运营' : '常见咨询'}</h3>
                {(operating
                  ? [
                      '查询所有商品',
                      '查询已下架商品',
                      '把 P001 的库存改为 50 件',
                      '把 P001 的售价改为 199.00',
                      '下架 P001',
                      '重新上架 P001',
                    ]
                  : [
                      '查询我的订单和物流',
                      '耳机还有库存吗，什么时候补货？',
                      '退货需要满足什么条件？',
                      '查询我的售后处理进度',
                    ]
                ).map((q) => (
                  <button
                    key={q}
                    disabled={p.chatBusy || !!active}
                    onClick={() => p.onSend(q)}
                  >
                    {q}
                    <span>→</span>
                  </button>
                ))}
              </div>
            </>
          )}
          <div className="sidebar-foot">商品、支付和物流为本地模拟数据。</div>
        </aside>

        <div className="service-main">
          {error && (
            <div className="service-error" role="alert">
              {error}
              <button aria-label="关闭错误提示" onClick={() => setError('')}>
                ×
              </button>
            </div>
          )}
          {operating ? (
            p.chat
          ) : admin ? (
            <>
              <div className="case-heading">
                <div>
                  <h2>{selected ? selected.id : '选择一项客户服务'}</h2>
                  <p>
                    {selected
                      ? `${status[selected.status]} · ${selected.owner_name || '尚未分配客服'}`
                      : '从左侧队列接单，查看客户上下文并回复。'}
                  </p>
                </div>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void work(async () => {})}
                >
                  刷新
                </button>
              </div>
              {selected ? (
                <>
                  <div className="case-body">
                    <h3>{selected.reason}</h3>
                    <div className="case-facts">
                      <span>关联订单：{selected.order_id || '一般咨询'}</span>
                      <span>
                        处理时限：
                        {selected.due_at ? date(selected.due_at) : '未设置'}
                      </span>
                    </div>
                    <details className="handoff-summary" open>
                      <summary>交接摘要</summary>
                      <p>{selected.summary}</p>
                    </details>
                    {selected.conversation_id && (
                      <div className="human-thread">
                        {humanMessages.map((m, i) => (
                          <div
                            key={i}
                            className={`human-message message-${m.role}`}
                          >
                            <span className="message-label">
                              {m.role === 'user'
                                ? '客户'
                                : m.author === 'human'
                                  ? '人工客服'
                                  : m.author === 'service'
                                    ? '服务通知'
                                    : 'AI 客服'}
                            </span>
                            <p>{m.content}</p>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="case-events">
                      <h3>处理记录</h3>
                      {selected.events.map((e) => (
                        <div key={e.id}>
                          <time>{date(e.created_at)}</time>
                          <p>{e.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="case-actions">
                    {selected.status === 'open' ? (
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() =>
                          void work(() =>
                            api(`/admin/tickets/${selected.id}`, 'PUT', {
                              status: 'processing',
                              resolution: '',
                            }),
                          )
                        }
                      >
                        接单处理
                      </button>
                    ) : selected.status === 'resolved' ? (
                      <div className="resolved-note">
                        处理结果：{selected.resolution}
                      </div>
                    ) : (
                      <>
                        <form
                          className="human-compose"
                          onSubmit={(e) => {
                            e.preventDefault();
                            void work(async () => {
                              await api(
                                `/admin/tickets/${selected.id}/reply`,
                                'POST',
                                { content: reply },
                              );
                              setReply('');
                            });
                          }}
                        >
                          <label>
                            回复客户
                            <textarea
                              value={reply}
                              maxLength={2000}
                              onChange={(e) => setReply(e.target.value)}
                              placeholder="回复将同步到客户会话和工单记录"
                            />
                          </label>
                          <button
                            className="primary"
                            disabled={
                              busy ||
                              !reply.trim() ||
                              selected.owner_id !== p.user?.id
                            }
                          >
                            发送回复
                          </button>
                        </form>
                        <form
                          className="resolve-form"
                          onSubmit={(e) => {
                            e.preventDefault();
                            void work(() =>
                              api(`/admin/tickets/${selected.id}`, 'PUT', {
                                status: 'resolved',
                                resolution,
                              }),
                            );
                          }}
                        >
                          <label>
                            处理结果
                            <input
                              value={resolution}
                              maxLength={1000}
                              onChange={(e) => setResolution(e.target.value)}
                              placeholder="填写具体结果后完成工单"
                            />
                          </label>
                          <button
                            className="secondary"
                            disabled={
                              busy ||
                              !resolution.trim() ||
                              selected.owner_id !== p.user?.id
                            }
                          >
                            完成工单
                          </button>
                        </form>
                      </>
                    )}
                  </div>
                </>
              ) : (
                <div className="service-empty">
                  <span className="assistant-mark">S</span>
                  <h2>让客户的问题有结果。</h2>
                  <p>对话、订单、政策与处理记录，在同一个工作区关联。</p>
                  <p className="muted">
                    在另一标签页登录买家，完成一次咨询或转人工，即可演示协作流程。
                  </p>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="service-chat-tools">
                <span>
                  {active ? `人工处理中 · ${active.id}` : '当前由 AI 客服处理'}
                </span>
                <div>
                  {p.conversationId && (
                    <button
                      className="text-button"
                      disabled={p.chatBusy || busy}
                      onClick={() =>
                        void work(() => p.onConversation(p.conversationId!))
                      }
                    >
                      刷新进度
                    </button>
                  )}
                  <button
                    className="text-button"
                    disabled={
                      !p.conversationId || p.chatBusy || busy || !!active
                    }
                    onClick={() => setShowHandoff(!showHandoff)}
                  >
                    转人工
                  </button>
                </div>
              </div>
              {showHandoff && !active && (
                <form
                  className="handoff-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void work(async () => {
                      await api(
                        `/conversations/${p.conversationId}/handoff`,
                        'POST',
                        {
                          reason: handoffReason,
                          order_id: handoffOrder || null,
                        },
                      );
                      setShowHandoff(false);
                      await p.onConversation(p.conversationId!);
                    });
                  }}
                >
                  <label>
                    需要人工协助的问题
                    <input
                      required
                      minLength={3}
                      maxLength={1000}
                      value={handoffReason}
                      onChange={(e) => setHandoffReason(e.target.value)}
                      placeholder="例如：耳机故障，想确认换货方案"
                    />
                  </label>
                  <label>
                    关联订单
                    <select
                      value={handoffOrder}
                      onChange={(e) => setHandoffOrder(e.target.value)}
                    >
                      <option value="">一般咨询</option>
                      {context?.orders.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.id} · {status[o.status]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="muted">
                    将附上当前对话与处理摘要，工单完成前由人工客服接管。
                  </p>
                  <div>
                    <button
                      className="primary"
                      disabled={busy || handoffReason.trim().length < 3}
                    >
                      确认转人工
                    </button>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => setShowHandoff(false)}
                    >
                      取消
                    </button>
                  </div>
                </form>
              )}
              {p.chat}
            </>
          )}
        </div>

        <aside className="customer-context">
          <div className="sidebar-title">
            <h2>
              {operating ? '运营说明' : admin ? '客户档案' : '服务上下文'}
            </h2>
            <span className="context-label">
              {operating ? '商品管理' : 'CRM'}
            </span>
          </div>
          {operating ? (
            <div className="context-placeholder">
              <h3>每一步修改，由你确认</h3>
              <p>
                AI
                先准备草稿，展示新增内容或修改前后值。确认成功后，商品浏览与库存同步更新。
              </p>
              <h3>规则模式示例</h3>
              <p>把 P001 的库存改为 50 件</p>
              <p>把 P001 的售价改为 199.00</p>
              <p>下架 P001 / 重新上架 P001</p>
              <p>查询已下架商品</p>
              <p>
                新增商品，编号 P007，名称 蓝牙耳机，分类 audio，售价
                199.00，库存 20
              </p>
              <p>
                分类可用
                audio、workspace、charging、clothing（服装）。可先说“上新一个衣服商品”，再补充编号、名称、售价和库存；自由表达需要
                LLM 模式。
              </p>
            </div>
          ) : context ? (
            <>
              <div className="customer-identity">
                <span className="customer-avatar">
                  {context.customer.name.slice(0, 1)}
                </span>
                <div>
                  <strong>{context.customer.name}</strong>
                  <p>{context.customer.email}</p>
                </div>
              </div>
              <div className="customer-stats">
                <div>
                  <strong>{context.orders.length}</strong>
                  <span>历史订单</span>
                </div>
                <div>
                  <strong>
                    {
                      context.tickets.filter((t) => t.status !== 'resolved')
                        .length
                    }
                  </strong>
                  <span>待处理工单</span>
                </div>
              </div>
              <div className="context-section">
                <div className="context-title">
                  <h3>订单与履约</h3>
                  <span className="context-label">模拟业务</span>
                </div>
                {context.orders.length ? (
                  context.orders.map((o) => (
                    <details
                      className="context-order"
                      key={o.id}
                      open={context.orders.length === 1}
                    >
                      <summary>
                        <span>{o.id}</span>
                        <span>{status[o.status]}</span>
                      </summary>
                      <p>{o.items.map((i) => i.name).join('、')}</p>
                      <strong>{money(o.total_cents)}</strong>
                      <div className="fulfillment-timeline">
                        {o.fulfillment.length ? (
                          o.fulfillment.map((e) => (
                            <div key={e.id}>
                              <time>{date(e.created_at)}</time>
                              <p>{e.detail}</p>
                            </div>
                          ))
                        ) : (
                          <p className="muted">尚无配送节点</p>
                        )}
                      </div>
                      {admin && o.status === 'paid' && (
                        <button
                          disabled={busy}
                          className="secondary full"
                          onClick={() =>
                            void work(() =>
                              api(`/admin/orders/${o.id}/ship`, 'POST'),
                            )
                          }
                        >
                          模拟发货
                        </button>
                      )}
                      {admin &&
                        o.status === 'shipped' &&
                        o.fulfillment.at(-1)?.stage !== 'delivered' && (
                          <form
                            className="delivery-form"
                            onSubmit={(e) => {
                              e.preventDefault();
                              void work(async () => {
                                await api(
                                  `/admin/orders/${o.id}/fulfillment`,
                                  'POST',
                                  { stage: 'delivered', detail: deliveryNote },
                                );
                                setDeliveryNote('');
                              });
                            }}
                          >
                            <label>
                              配送节点说明
                              <input
                                value={deliveryNote}
                                maxLength={300}
                                onChange={(e) =>
                                  setDeliveryNote(e.target.value)
                                }
                                placeholder="例如：模拟包裹已送达收货点"
                              />
                            </label>
                            <button
                              disabled={busy || deliveryNote.trim().length < 3}
                              className="secondary full"
                            >
                              标记模拟送达
                            </button>
                          </form>
                        )}
                      {!admin && (
                        <button
                          disabled={p.chatBusy || !!active}
                          className="text-button"
                          onClick={() =>
                            p.onSend(`查询订单 ${o.id} 的物流和当前状态`)
                          }
                        >
                          让 AI 查询 →
                        </button>
                      )}
                    </details>
                  ))
                ) : (
                  <p className="muted">暂无订单</p>
                )}
              </div>
              <div className="context-section">
                <h3>售后与工单</h3>
                {context.tickets.length ? (
                  context.tickets.map((t) => (
                    <div className="context-ticket" key={t.id}>
                      <div>
                        <strong>{t.id}</strong>
                        <span>{status[t.status]}</span>
                      </div>
                      <p>{t.reason}</p>
                      {t.resolution && (
                        <p className="resolution-text">{t.resolution}</p>
                      )}
                      {t.events.at(-1) && (
                        <p className="muted">
                          最新：{t.events.at(-1)?.content}
                        </p>
                      )}
                      {admin && (
                        <button
                          className="text-button"
                          onClick={() => select(t)}
                        >
                          查看处理 →
                        </button>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="muted">暂无工单</p>
                )}
              </div>
              {!admin && (
                <button className="secondary full" onClick={p.onOrders}>
                  查看我的订单
                </button>
              )}
            </>
          ) : (
            <div className="context-placeholder">
              <h3>
                {admin
                  ? '选择客户或工单'
                  : p.user
                    ? '客户资料暂未加载'
                    : '登录后查看服务上下文'}
              </h3>
              <p>订单、物流、历史工单会关联到当前客户。</p>
            </div>
          )}
          <div className="context-boundary">
            <strong>{operating ? '库存与价格' : '服务范围'}</strong>
            <p>
              {operating
                ? '库存表示当前可售数量，不包含订单已预留的数量。修改售价不影响历史订单。下架商品仍可编辑和重新上架；既有订单继续履约。若商品在确认前已变化，请重新生成预览。'
                : '订单查询依据登录身份。AI 可提议业务操作，支付、退款与发货由业务流程处理。'}
            </p>
          </div>
        </aside>
      </div>
    </section>
  );
}
