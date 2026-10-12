'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api, setToken, streamChat } from '@/lib/api';
import { money } from '@/lib/format';
import type {
  User,
  Product,
  Cart,
  Order,
  Ticket,
  ChatMessage,
  Source,
  Action,
  Step,
  Conversation,
  AIRun,
} from '@/lib/types';
import ProductArt from './product-art';
import ServiceWorkspace from './service-workspace';
import RunInsights from './run-insights';
import AdminProducts from './admin-products';
import ActionPreview from './action-preview';

const labels: Record<string, string> = {
  pending_payment: '待支付',
  paid: '待发货',
  shipped: '运输中',
  completed: '已完成',
  cancelled: '已取消',
  open: '待处理',
  processing: '处理中',
  resolved: '已解决',
  pending: '待确认',
  confirmed: '已执行',
  rejected: '已拒绝',
};
const categories = [
  ['', '全部好物'],
  ['audio', '声音与陪伴'],
  ['workspace', '桌面与效率'],
  ['charging', '连接与充电'],
  ['clothing', '服装'],
];
const emptyCart: Cart = {
  items: [],
  subtotal_cents: 0,
  shipping_cents: 0,
  total_cents: 0,
};
type View =
  'service' | 'shop' | 'cart' | 'orders' | 'tickets' | 'admin' | 'assistant';
type Overview = {
  orders: number;
  revenue_cents: number;
  open_tickets: number;
  ai_runs: number;
};

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState<View>('service');
  const [products, setProducts] = useState<Product[]>([]);
  const [adminProducts, setAdminProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<Cart>(emptyCart);
  const [orders, setOrders] = useState<Order[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [category, setCategory] = useState('');
  const [search, setSearch] = useState('');
  const [loadError, setLoadError] = useState('');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [auth, setAuth] = useState(false);
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState('demo@shop.local');
  const [password, setPassword] = useState('Demo12345!');
  const [name, setName] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [detail, setDetail] = useState<Product | null>(null);
  const [address, setAddress] = useState(
    '上海市 · 演示收货地址（不发生真实配送）',
  );
  const checkoutKey = useRef<string | null>(null);
  const [afterSale, setAfterSale] = useState<Order | null>(null);
  const [reason, setReason] = useState('');
  const [mode, setMode] = useState('demo');
  const [database, setDatabase] = useState('unknown');
  const [handoff, setHandoff] = useState<Ticket | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [runs, setRuns] = useState<AIRun[]>([]);
  const chatEnd = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  const refresh = useCallback(
    async (activeUser: User | null = user) => {
      const catalog = await api<Product[]>('/products');
      setProducts(catalog);
      if (activeUser) {
        const [basket, orderList, ticketList, history] = await Promise.all([
          api<Cart>('/cart'),
          api<Order[]>('/orders'),
          api<Ticket[]>('/tickets'),
          api<Conversation[]>('/conversations'),
        ]);
        setCart(basket);
        setOrders(orderList);
        setTickets(ticketList);
        setConversations(history);
        if (activeUser.role === 'admin') {
          const [stats, adminOrders, adminTickets, records, managedProducts] =
            await Promise.all([
              api<Overview>('/admin/overview'),
              api<Order[]>('/admin/orders'),
              api<Ticket[]>('/admin/tickets'),
              api<AIRun[]>('/admin/ai-runs'),
              api<Product[]>('/admin/products'),
            ]);
          setOverview(stats);
          setOrders(adminOrders);
          setTickets(adminTickets);
          setRuns(records);
          setAdminProducts(managedProducts);
        }
      }
    },
    [user],
  );

  useEffect(() => {
    let disposed = false;
    async function initialize() {
      try {
        const health = await api<{ ai_mode: string; database?: string }>(
          '/health',
        );
        if (!disposed) {
          setMode(health.ai_mode);
          setDatabase(health.database || 'unknown');
        }
        const saved = sessionStorage.getItem('shiwu-token');
        let activeUser: User | null = null;
        if (saved) {
          setToken(saved);
          try {
            activeUser = await api<User>('/auth/me');
          } catch {
            sessionStorage.removeItem('shiwu-token');
            setToken('');
          }
          if (!disposed) setUser(activeUser);
        }
        await refresh(activeUser);
      } catch (e) {
        if (!disposed) setLoadError((e as Error).message);
      } finally {
        if (!disposed) setLoading(false);
      }
    }
    void initialize();
    return () => {
      disposed = true;
      abort.current?.abort();
    };
    // Initial restoration owns its user value; later refreshes run after explicit mutations.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 4500);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (!auth && !detail && !afterSale && !deleteTarget) return;
    const previous = document.activeElement as HTMLElement | null;
    const modal = document.querySelector<HTMLElement>('[role="dialog"]');
    modal?.querySelector<HTMLElement>('input,textarea,button')?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setAuth(false);
        setDetail(null);
        setAfterSale(null);
        setDeleteTarget(null);
      }
      if (event.key === 'Tab' && modal) {
        const elements = Array.from(
          modal.querySelectorAll<HTMLElement>(
            'button:not(:disabled),input,textarea,select,[tabindex="0"]',
          ),
        );
        const first = elements[0],
          last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (previous?.isConnected) previous.focus();
    };
  }, [auth, detail, afterSale, deleteTarget]);

  async function mutate(work: () => Promise<unknown>, success: string) {
    if (busy) return;
    setBusy(true);
    try {
      await work();
      await refresh();
      setNotice(success);
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function requireUser() {
    if (!user) {
      setPasswordError('');
      setAuth(true);
      return false;
    }
    return true;
  }
  async function signIn(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api<{ token: string; user: User }>(
        register ? '/auth/register' : '/auth/login',
        'POST',
        register ? { email, password, name } : { email, password },
      );
      setToken(result.token);
      sessionStorage.setItem('shiwu-token', result.token);
      setUser(result.user);
      setMessages([]);
      setConversationId(null);
      setHandoff(null);
      setView('service');
      setAuth(false);
      await refresh(result.user);
      setNotice(`欢迎，${result.user.name}`);
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    abort.current?.abort();
    setBusy(true);
    try {
      await api('/auth/logout', 'POST');
      setToken('');
      sessionStorage.removeItem('shiwu-token');
      setUser(null);
      setCart(emptyCart);
      setAdminProducts([]);
      setOrders([]);
      setTickets([]);
      setMessages([]);
      setConversations([]);
      setConversationId(null);
      setHandoff(null);
      setView('service');
      await refresh(null);
      setNotice('已退出登录');
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function addCart(p: Product) {
    if (!requireUser()) return;
    const quantity = (cart.items.find((i) => i.id === p.id)?.quantity || 0) + 1;
    void mutate(
      () => api('/cart', 'PUT', { product_id: p.id, quantity }),
      `${p.name} 已加入购物车`,
    );
  }
  async function checkout() {
    if (!requireUser()) return;
    checkoutKey.current ||= crypto.randomUUID();
    await mutate(async () => {
      await api('/orders', 'POST', {
        address,
        request_key: checkoutKey.current,
      });
      checkoutKey.current = null;
      setView('orders');
    }, '订单已创建，库存已预留');
  }
  async function loadConversation(id: string) {
    if (chatBusy) return;
    if (!id) {
      setConversationId(null);
      setMessages([]);
      setHandoff(null);
      return;
    }
    try {
      const history = await api<{
        messages: ChatMessage[];
        handoff: Ticket | null;
      }>(`/conversations/${id}`);
      setConversationId(id);
      setMessages(history.messages);
      setHandoff(history.handoff);
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  async function deleteConversation() {
    if (!deleteTarget || chatBusy || busy) return;
    const id = deleteTarget.id;
    await mutate(async () => {
      await api(`/conversations/${id}`, 'DELETE');
      setConversations((previous) => previous.filter((c) => c.id !== id));
      if (conversationId === id) {
        setConversationId(null);
        setMessages([]);
        setHandoff(null);
        setInput('');
      }
      setDeleteTarget(null);
    }, '会话已删除');
  }
  async function send(text = input) {
    if (!text.trim() || chatBusy || !requireUser()) return;
    setView(user?.role === 'admin' ? 'assistant' : 'service');
    setInput('');
    setChatBusy(true);
    if (handoff && conversationId) {
      try {
        await api(`/conversations/${conversationId}/messages`, 'POST', {
          content: text,
        });
        await loadConversation(conversationId);
        await refresh();
      } catch (e) {
        setInput(text);
        setNotice((e as Error).message);
      } finally {
        setChatBusy(false);
      }
      return;
    }
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text },
      { role: 'assistant', content: '', steps: [], sources: [], actions: [] },
    ]);
    const controller = new AbortController();
    abort.current = controller;
    try {
      await streamChat(
        text,
        conversationId,
        (event) => {
          if (event.event === 'conversation') {
            const data = event.data as { id: string; mode: string };
            setConversationId(data.id);
            setMode(data.mode);
            return;
          }
          if (event.event === 'error') {
            setNotice((event.data as { message: string }).message);
          }
          setMessages((prev) => {
            const next = [...prev];
            const last = { ...next[next.length - 1] };
            if (last.role !== 'assistant') return prev;
            if (event.event === 'token')
              last.content += (event.data as { content: string }).content;
            if (event.event === 'step')
              last.steps = [...(last.steps || []), event.data as Step];
            if (event.event === 'sources')
              last.sources = event.data as Source[];
            if (event.event === 'products')
              last.products = event.data as Product[];
            if (event.event === 'action')
              last.actions = [...(last.actions || []), event.data as Action];
            if (event.event === 'message') Object.assign(last, event.data);
            if (event.event === 'error')
              last.content =
                '本次回答失败。已准备的操作仍需你确认，请稍后重试。';
            next[next.length - 1] = last;
            return next;
          });
        },
        controller.signal,
      );
      await refresh();
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setNotice((e as Error).message);
        setMessages((prev) =>
          prev.map((m, i) =>
            i === prev.length - 1 && m.role === 'assistant'
              ? { ...m, content: m.content || '本次请求未完成，请重试。' }
              : m,
          ),
        );
      }
    } finally {
      setChatBusy(false);
      abort.current = null;
    }
  }
  async function confirm(action: Action, confirmed: boolean) {
    await mutate(
      async () => {
        const result = await api<Action>(
          `/actions/${action.id}/confirm`,
          'POST',
          { confirmed },
        );
        setMessages((prev) =>
          prev.map((m) => ({
            ...m,
            actions: m.actions?.map((a) =>
              a.id === result.id ? { ...a, status: result.status } : a,
            ),
          })),
        );
        if (confirmed && action.kind === 'handoff' && conversationId)
          await loadConversation(conversationId);
      },
      confirmed ? '操作已执行' : '已拒绝，数据没有变更',
    );
  }
  function navigate(target: View) {
    if (target !== 'shop' && target !== 'service' && !requireUser()) return;
    setView(target);
  }

  const visible = products.filter(
    (p) =>
      (!category || p.category === category) &&
      (!search ||
        `${p.id} ${p.name} ${p.description} ${Object.values(p.specs).join(' ')}`
          .toLowerCase()
          .includes(search.toLowerCase())),
  );
  const cartCount = cart.items.reduce((sum, i) => sum + (i.quantity || 0), 0);
  const nav = [
    ['service', user?.role === 'admin' ? '客服工作台' : 'AI 客服'],
    ['shop', '商品浏览'],
    ['orders', user?.role === 'admin' ? '店铺订单' : '我的订单'],
    ['tickets', '售后服务'],
  ] as const;

  const chatPanel = (
    <aside
      className="chat-panel embedded-chat"
      aria-label={user?.role === 'admin' ? 'AI 运营助手' : 'AI 电商客服'}
    >
      <div className="chat-header">
        <div className="assistant-mark">S</div>
        <div>
          <strong>
            {user?.role === 'admin' ? '购物 AI 运营助手' : '购物 AI 客服'}
          </strong>
          <small>
            {mode === 'llm'
              ? 'AI 在线 · 操作需确认'
              : '规则演示 · 可切换 LLM 模式'}
          </small>
        </div>
        <span className="chat-channel">
          {handoff ? '人工服务' : '在线咨询'}
        </span>
      </div>
      <div className="chat-messages">
        {!messages.length && (
          <div className="chat-welcome">
            <span className="eyebrow">HELLO, NICE TO HELP YOU</span>
            <h2>
              {user?.role === 'admin'
                ? '今天要处理什么店铺业务？'
                : '今天有什么需要帮助？'}
            </h2>
            <p>
              {user?.role === 'admin' ? (
                '查询商品，准备上新和库存调整。每次修改都由你确认。'
              ) : (
                <>
                  订单物流、商品政策、售后处理，
                  <br />
                  从咨询到结果，都在这里完成。
                </>
              )}
            </p>
            {(user?.role === 'admin'
              ? [
                  '查询所有商品',
                  '查询已下架商品',
                  '把 P001 的库存改为 50 件',
                  '把 P001 的售价改为 199.00',
                  '下架 P001',
                  '重新上架 P001',
                  '上新一个衣服商品',
                ]
              : [
                  '查询我的订单和物流',
                  '耳机有什么保修政策？',
                  '订单 ORD-DEMO 的耳机左侧无法连接，帮我申请售后',
                  '查询我的售后处理进度',
                ]
            ).map((q) => (
              <button key={q} disabled={chatBusy} onClick={() => void send(q)}>
                {q}
                <span>↗</span>
              </button>
            ))}
          </div>
        )}
        {messages.map((m, index) => (
          <div key={index} className={`chat-message message-${m.role}`}>
            <span className="message-label">
              {m.role === 'user'
                ? '你'
                : m.author === 'human'
                  ? '人工客服'
                  : m.author === 'service'
                    ? '服务通知'
                    : user?.role === 'admin'
                      ? 'AI 运营助手'
                      : 'AI 客服'}
            </span>
            <p>{m.content || '正在处理…'}</p>
            {m.products?.length ? (
              <div className="chat-products">
                {m.products.map((p) => (
                  <button key={p.id} onClick={() => setDetail(p)}>
                    <span>
                      {p.name}
                      {p.active === 0 ? ' · 已下架' : ''}
                    </span>
                    <strong>{money(p.price_cents)}</strong>
                  </button>
                ))}
              </div>
            ) : null}
            {m.actions?.map((a) => (
              <div className="action-card" key={a.id}>
                <span>操作确认 · {labels[a.status] || a.status}</span>
                <strong>{a.summary}</strong>
                {a.preview && (
                  <ActionPreview
                    before={a.preview.before}
                    after={a.preview.after}
                  />
                )}{' '}
                {a.status === 'pending' && (
                  <div>
                    <button
                      className="primary"
                      disabled={busy || chatBusy}
                      onClick={() => void confirm(a, true)}
                    >
                      确认执行
                    </button>
                    <button
                      className="text-button"
                      disabled={busy || chatBusy}
                      onClick={() => void confirm(a, false)}
                    >
                      拒绝
                    </button>
                  </div>
                )}
              </div>
            ))}
            {m.sources?.length ? (
              <details className="sources">
                <summary>参考资料 · {m.sources.length} 条</summary>
                {m.sources.map((s) => (
                  <div key={s.id}>
                    <strong>
                      {s.title} / {s.id}
                    </strong>
                    <p>{s.content}</p>
                  </div>
                ))}
              </details>
            ) : null}
            {m.steps?.length || m.trace?.length ? (
              <details className="trace">
                <summary>查看处理过程</summary>
                {(
                  m.steps ||
                  m.trace?.map((t) => ({
                    node: t.node,
                    status: t.ok === false ? 'error' : 'completed',
                    detail:
                      t.error ||
                      (t.elapsed_ms !== undefined
                        ? `${t.elapsed_ms} ms`
                        : '已完成'),
                  })) ||
                  []
                ).map((s, i) => (
                  <div key={i}>
                    <span>{s.node}</span>
                    <small>
                      {s.status === 'running' ? '执行中' : s.detail}
                    </small>
                  </div>
                ))}
              </details>
            ) : null}
            {m.elapsed_ms !== undefined && (
              <small className="run-meta">
                {m.first_response_ms !== null &&
                m.first_response_ms !== undefined
                  ? `首次响应 ${m.first_response_ms} ms · `
                  : ''}
                总耗时 {m.elapsed_ms} ms · {m.llm_calls} 次模型调用 ·{' '}
                {m.tool_calls} 次工具调用
              </small>
            )}
          </div>
        ))}
        <div ref={chatEnd} />
      </div>
      <form
        className="chat-compose"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <textarea
          aria-label="发送消息给客服"
          placeholder={
            user
              ? handoff
                ? '补充问题，消息将发送给人工客服…'
                : user.role === 'admin'
                  ? '例如：把 P001 的库存改为 50 件…'
                  : '描述你的问题，例如：耳机无法连接，想申请售后…'
              : '登录后开始对话'
          }
          value={input}
          maxLength={2000}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === 'Enter' &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button
          className="primary"
          type="submit"
          disabled={chatBusy || !input.trim()}
          aria-label="发送消息"
        >
          {chatBusy ? '…' : '↑'}
        </button>
      </form>
      <div className="chat-disclaimer">
        {mode === 'demo'
          ? '规则演示用于验证流程，不代表模型能力。'
          : 'AI 可能出错，请核对商品信息与操作内容。'}
      </div>
    </aside>
  );

  return (
    <div
      className={`store ${view === 'service' || view === 'assistant' ? 'service-page' : ''}`}
    >
      <div className="announcement">
        购物 · AI 电商客服<span>本地业务演示 · 支付与物流均为模拟</span>
      </div>
      <header className="site-header">
        <button
          className="brand"
          onClick={() => navigate('service')}
          aria-label="购物客服首页"
        >
          <b>
            购物<span>SHOPPING</span>
          </b>
          <small>客户服务与订单履约</small>
        </button>
        <nav aria-label="主导航">
          {nav.map(([target, title]) => (
            <button
              key={target}
              className={view === target ? 'active' : ''}
              onClick={() => navigate(target)}
            >
              {title}
            </button>
          ))}
          {user?.role === 'admin' && (
            <button
              className={view === 'assistant' ? 'active' : ''}
              onClick={() => navigate('assistant')}
            >
              AI 运营助手
            </button>
          )}
          {user?.role === 'admin' && (
            <button
              className={view === 'admin' ? 'active' : ''}
              onClick={() => navigate('admin')}
            >
              业务管理
            </button>
          )}
        </nav>
        <div className="header-actions">
          <button className="cart-link" onClick={() => navigate('cart')}>
            购物车 <span>{cartCount}</span>
          </button>
          {user ? (
            <button onClick={() => void logout()} disabled={busy || chatBusy}>
              {user.name} · 退出
            </button>
          ) : (
            <button
              onClick={() => {
                setPasswordError('');
                setAuth(true);
              }}
            >
              登录 / 注册
            </button>
          )}
        </div>
      </header>

      <main className="main-wrap">
        {loading ? (
          <div className="empty-state">正在连接客服与业务系统…</div>
        ) : loadError ? (
          <div className="empty-state">
            <h2>暂时无法连接业务服务</h2>
            <p>{loadError}</p>
            <button className="primary" onClick={() => location.reload()}>
              重新连接
            </button>
          </div>
        ) : (
          <>
            {(view === 'service' || view === 'assistant') && (
              <ServiceWorkspace
                aiOperations={view === 'assistant'}
                key={user?.id || 'guest'}
                user={user}
                mode={mode}
                database={database}
                tickets={tickets}
                conversations={conversations}
                conversationId={conversationId}
                chatBusy={chatBusy || busy}
                chat={chatPanel}
                onLogin={() => {
                  setPasswordError('');
                  setAuth(true);
                }}
                onSend={(text) => void send(text)}
                onConversation={loadConversation}
                onDeleteConversation={setDeleteTarget}
                onRefresh={refresh}
                onOrders={() => navigate('orders')}
              />
            )}
            {view === 'shop' && (
              <>
                <section id="catalog" className="catalog">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow">CURATED FOR YOU</span>
                      <h2>
                        日常精选 <small>{products.length} 件好物</small>
                      </h2>
                    </div>
                    <label className="search-field">
                      <span>搜索</span>
                      <input
                        aria-label="搜索商品"
                        placeholder="耳机、键盘、充电板…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                  </div>
                  <div
                    className="category-tabs"
                    role="group"
                    aria-label="商品分类"
                  >
                    {categories.map(([key, title]) => (
                      <button
                        key={key}
                        className={category === key ? 'selected' : ''}
                        onClick={() => setCategory(key)}
                      >
                        {title}
                      </button>
                    ))}
                  </div>
                  {visible.length ? (
                    <div className="product-grid">
                      {visible.map((p) => (
                        <article className="product-card" key={p.id}>
                          <button
                            className="product-image"
                            onClick={() => setDetail(p)}
                            aria-label={`查看${p.name}详情`}
                          >
                            <ProductArt kind={p.image} />
                            <span className="product-code">{p.id}</span>
                          </button>
                          <div className="product-meta">
                            <span className="product-category">
                              {categories.find((c) => c[0] === p.category)?.[1]}
                            </span>
                            <h3>
                              <button onClick={() => setDetail(p)}>
                                {p.name}
                              </button>
                            </h3>
                            <p>{p.description}</p>
                            <div className="product-bottom">
                              <strong>{money(p.price_cents)}</strong>
                              <button
                                className="add-button"
                                disabled={busy || p.stock === 0}
                                onClick={() => addCart(p)}
                                aria-label={`添加${p.name}到购物车`}
                              >
                                {p.stock === 0 ? '售罄' : '＋'}
                              </button>
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">
                      没有找到这件好物，换个关键词试试。
                    </div>
                  )}
                </section>
              </>
            )}

            {view === 'cart' && (
              <section className="workspace">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">YOUR SELECTION</span>
                    <h1>
                      购物车 <small>{cartCount} 件</small>
                    </h1>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => navigate('shop')}
                  >
                    继续挑选 →
                  </button>
                </div>
                {!cart.items.length ? (
                  <div className="empty-state">
                    <h2>留一点空间，给喜欢的东西。</h2>
                    <p>购物车还没有商品。</p>
                    <button
                      className="primary"
                      onClick={() => navigate('shop')}
                    >
                      发现好物
                    </button>
                  </div>
                ) : (
                  <div className="checkout-layout">
                    <div className="line-items">
                      {cart.items.map((p) => (
                        <div className="cart-item" key={p.id}>
                          <div className="cart-art">
                            <ProductArt kind={p.image} />
                          </div>
                          <div>
                            <h3>{p.name}</h3>
                            {p.active === 0 && (
                              <p className="field-error">
                                商品已下架，请移出购物车
                              </p>
                            )}
                            <p>{money(p.price_cents)} / 件</p>
                            <span className="muted">
                              当前可售库存 {p.stock} 件
                            </span>
                          </div>
                          <div className="quantity">
                            <button
                              disabled={
                                busy || p.active === 0 || (p.quantity || 1) <= 1
                              }
                              aria-label={`减少${p.name}数量`}
                              onClick={() =>
                                void mutate(
                                  () =>
                                    api('/cart', 'PUT', {
                                      product_id: p.id,
                                      quantity: (p.quantity || 1) - 1,
                                    }),
                                  '数量已更新',
                                )
                              }
                            >
                              −
                            </button>
                            <span>{p.quantity}</span>
                            <button
                              disabled={
                                busy ||
                                p.active === 0 ||
                                (p.quantity || 0) >= p.stock
                              }
                              aria-label={`增加${p.name}数量`}
                              onClick={() =>
                                void mutate(
                                  () =>
                                    api('/cart', 'PUT', {
                                      product_id: p.id,
                                      quantity: (p.quantity || 1) + 1,
                                    }),
                                  '数量已更新',
                                )
                              }
                            >
                              ＋
                            </button>
                          </div>
                          <button
                            className="text-button"
                            disabled={busy}
                            onClick={() =>
                              void mutate(
                                () => api(`/cart/${p.id}`, 'DELETE'),
                                '商品已移出购物车',
                              )
                            }
                          >
                            移除
                          </button>
                        </div>
                      ))}
                    </div>
                    <aside className="checkout-summary">
                      <h2>订单小计</h2>
                      <div>
                        <span>商品金额</span>
                        <strong>{money(cart.subtotal_cents)}</strong>
                      </div>
                      <div>
                        <span>运费</span>
                        <strong>
                          {cart.shipping_cents
                            ? money(cart.shipping_cents)
                            : '免运费'}
                        </strong>
                      </div>
                      <label>
                        收货信息
                        <textarea
                          value={address}
                          onChange={(e) => {
                            setAddress(e.target.value);
                            checkoutKey.current = null;
                          }}
                          minLength={5}
                          maxLength={200}
                        />
                      </label>
                      <div className="summary-total">
                        <span>合计</span>
                        <strong>{money(cart.total_cents)}</strong>
                      </div>
                      <button
                        className="primary full"
                        disabled={
                          busy ||
                          address.trim().length < 5 ||
                          cart.items.some((p) => p.active === 0)
                        }
                        onClick={() => void checkout()}
                      >
                        {busy ? '正在创建…' : '创建订单 →'}
                      </button>
                      <p className="muted">
                        创建订单后预留库存。支付为模拟操作，不产生扣款。
                      </p>
                    </aside>
                  </div>
                )}
              </section>
            )}

            {view === 'orders' && (
              <section className="workspace">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">ORDER JOURNEY</span>
                    <h1>{user?.role === 'admin' ? '店铺订单' : '我的订单'}</h1>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => setView('service')}
                  >
                    让 AI 客服查单 →
                  </button>
                </div>
                {!orders.length ? (
                  <div className="empty-state">
                    还没有订单，去挑选第一件好物吧。
                  </div>
                ) : (
                  <div className="records">
                    {orders.map((o) => (
                      <article className="record" key={o.id}>
                        <div className="record-top">
                          <span>
                            {o.id}{' '}
                            <small>
                              {new Date(o.created_at).toLocaleDateString(
                                'zh-CN',
                              )}
                            </small>
                          </span>
                          <span className={`status status-${o.status}`}>
                            {labels[o.status]}
                          </span>
                        </div>
                        {o.items.map((i) => (
                          <div className="order-item" key={i.product_id}>
                            <strong>{i.name}</strong>
                            <span>× {i.quantity}</span>
                            <span>{money(i.price_cents * i.quantity)}</span>
                          </div>
                        ))}
                        <div className="order-progress">
                          <span
                            className={
                              o.status !== 'cancelled' ? 'reached' : ''
                            }
                          >
                            创建订单
                          </span>
                          <span
                            className={
                              ['paid', 'shipped', 'completed'].includes(
                                o.status,
                              )
                                ? 'reached'
                                : ''
                            }
                          >
                            模拟支付
                          </span>
                          <span
                            className={
                              ['shipped', 'completed'].includes(o.status)
                                ? 'reached'
                                : ''
                            }
                          >
                            店铺发货
                          </span>
                          <span
                            className={
                              o.status === 'completed' ? 'reached' : ''
                            }
                          >
                            确认收货
                          </span>
                        </div>
                        <div className="order-fulfillment">
                          {o.fulfillment?.map((f) => (
                            <p key={f.id}>
                              <time>
                                {new Date(f.created_at).toLocaleString('zh-CN')}
                              </time>{' '}
                              {f.detail}
                            </p>
                          ))}
                        </div>
                        <p className="muted">{o.address}</p>
                        <div className="record-bottom">
                          <strong>合计 {money(o.total_cents)}</strong>
                          <div>
                            {o.status === 'pending_payment' &&
                              user?.id === o.user_id && (
                                <>
                                  <button
                                    className="text-button"
                                    disabled={busy}
                                    onClick={() =>
                                      void mutate(
                                        () =>
                                          api(`/orders/${o.id}/cancel`, 'POST'),
                                        '订单已取消，库存已释放',
                                      )
                                    }
                                  >
                                    取消订单
                                  </button>
                                  <button
                                    className="primary"
                                    disabled={busy}
                                    onClick={() =>
                                      void mutate(
                                        () =>
                                          api(`/orders/${o.id}/pay`, 'POST'),
                                        '模拟支付成功',
                                      )
                                    }
                                  >
                                    模拟支付
                                  </button>
                                </>
                              )}
                            {o.status === 'shipped' &&
                              user?.id === o.user_id && (
                                <button
                                  className="primary"
                                  disabled={busy}
                                  onClick={() =>
                                    void mutate(
                                      () =>
                                        api(`/orders/${o.id}/receive`, 'POST'),
                                      '已确认收货',
                                    )
                                  }
                                >
                                  确认收货
                                </button>
                              )}
                            {['paid', 'shipped', 'completed'].includes(
                              o.status,
                            ) &&
                              user?.id === o.user_id && (
                                <button
                                  className="secondary"
                                  onClick={() => {
                                    setAfterSale(o);
                                    setReason('');
                                  }}
                                >
                                  申请售后
                                </button>
                              )}
                            {o.status === 'paid' && user?.role === 'admin' && (
                              <button
                                className="primary"
                                disabled={busy}
                                onClick={() =>
                                  void mutate(
                                    () =>
                                      api(`/admin/orders/${o.id}/ship`, 'POST'),
                                    '已模拟发货',
                                  )
                                }
                              >
                                模拟发货
                              </button>
                            )}
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}

            {view === 'tickets' && (
              <section className="workspace">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">WE ARE HERE TO HELP</span>
                    <h1>售后服务</h1>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => setView('service')}
                  >
                    联系 AI 客服 →
                  </button>
                </div>
                {!tickets.length ? (
                  <div className="empty-state">
                    <h2>有问题，我们一起解决。</h2>
                    <p>暂无售后工单，可在订单页申请或让助手帮你创建。</p>
                  </div>
                ) : (
                  <div className="records">
                    {tickets.map((t) => (
                      <article className="record" key={t.id}>
                        <div className="record-top">
                          <span>{t.id}</span>
                          <span className="status">{labels[t.status]}</span>
                        </div>
                        <h3>{t.reason}</h3>
                        <p className="muted">
                          关联订单：{t.order_id || '一般咨询'}
                        </p>
                        <p>
                          {t.resolution ||
                            '等待客服处理，处理进度会显示在这里。'}
                        </p>
                        <div className="ticket-public-events">
                          {t.events?.map((e) => (
                            <p key={e.id}>
                              <time>
                                {new Date(e.created_at).toLocaleString('zh-CN')}
                              </time>{' '}
                              {e.content}
                            </p>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}

            {view === 'admin' && user?.role === 'admin' && (
              <section className="workspace">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">SHOP OPERATIONS</span>
                    <h1>业务管理与运行观测</h1>
                  </div>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      void mutate(() => Promise.resolve(), '店铺数据已刷新')
                    }
                  >
                    刷新数据
                  </button>
                </div>
                <div className="stats-row">
                  {[
                    ['订单数', overview?.orders || 0],
                    ['模拟成交额', money(overview?.revenue_cents || 0)],
                    ['待处理售后', overview?.open_tickets || 0],
                    ['助手调用', overview?.ai_runs || 0],
                  ].map(([title, value]) => (
                    <div key={title}>
                      <span>{title}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
                <AdminProducts
                  products={adminProducts}
                  busy={busy || chatBusy}
                  onSave={mutate}
                  onAI={() => navigate('assistant')}
                />
                <RunInsights runs={runs} />
                <h2>助手运行记录</h2>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>模式</th>
                        <th>状态</th>
                        <th>耗时</th>
                        <th>模型调用</th>
                        <th>工具调用</th>
                        <th>输入 / 输出 Token</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((r) => (
                        <tr key={r.id}>
                          <td>{r.mode === 'llm' ? 'LLM' : '规则演示'}</td>
                          <td>{r.status}</td>
                          <td>{r.elapsed_ms} ms</td>
                          <td>{r.llm_calls}</td>
                          <td>{r.tool_calls}</td>
                          <td>
                            {r.prompt_tokens} / {r.completion_tokens}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!runs.length && (
                    <p className="muted">
                      完成一次助手对话后，这里会出现运行记录。
                    </p>
                  )}
                </div>
              </section>
            )}
          </>
        )}
      </main>
      <footer>
        <span>购物 SHOPPING</span>
        <p>客户咨询、订单履约与售后协作。</p>
        <small>AI 应用开发项目 · 本地模拟业务</small>
      </footer>
      {view !== 'service' && view !== 'assistant' && user?.role !== 'admin' && (
        <button
          className="assistant-launcher"
          onClick={() => setView('service')}
        >
          <span className="assistant-mark">S</span>
          <span>
            AI 客服<small>订单、政策与售后咨询</small>
          </span>
          <b>↗</b>
        </button>
      )}

      {auth && (
        <div className="modal-backdrop" onClick={() => setAuth(false)}>
          <section
            className="modal auth-modal"
            role="dialog"
            aria-modal="true"
            aria-label={register ? '注册账户' : '登录账户'}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              aria-label="关闭登录"
              onClick={() => setAuth(false)}
            >
              ×
            </button>
            <span className="eyebrow">WELCOME TO SHOPPING</span>
            <h2>{register ? '开启你的购物旅程' : '欢迎回来。'}</h2>
            <form onSubmit={(e) => void signIn(e)}>
              {register && (
                <label>
                  昵称
                  <input
                    required
                    value={name}
                    maxLength={30}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="nickname"
                  />
                </label>
              )}
              <label>
                邮箱
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                />
              </label>
              <label>
                密码
                <input
                  id="auth-password"
                  aria-label="密码"
                  type="password"
                  required
                  minLength={register ? 8 : 1}
                  value={password}
                  aria-invalid={!!passwordError}
                  aria-describedby={
                    register || passwordError ? 'password-hint' : undefined
                  }
                  onInvalid={(e) => {
                    e.preventDefault();
                    setPasswordError(
                      e.currentTarget.validity.valueMissing
                        ? '请输入密码'
                        : '密码至少需要 8 位字符',
                    );
                    e.currentTarget.focus();
                  }}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setPasswordError('');
                  }}
                  autoComplete={register ? 'new-password' : 'current-password'}
                />
                {(register || passwordError) && (
                  <span
                    id="password-hint"
                    className={
                      passwordError ? 'field-hint field-error' : 'field-hint'
                    }
                    aria-live="polite"
                  >
                    {passwordError || '至少 8 位字符'}
                  </span>
                )}
              </label>
              <button className="primary full" disabled={busy}>
                {busy ? '请稍候…' : register ? '创建账户' : '登录'}
              </button>
            </form>
            <button
              className="text-button"
              onClick={() => {
                setPasswordError('');
                setRegister(!register);
              }}
            >
              {register ? '已有账户？去登录' : '新朋友？创建账户'}
            </button>
            {!register && (
              <div className="demo-accounts">
                <span>本地演示账户 / 密码 Demo12345!</span>
                <div>
                  <button
                    onClick={() => {
                      setEmail('demo@shop.local');
                      setPassword('Demo12345!');
                      setPasswordError('');
                    }}
                  >
                    买家账户
                  </button>
                  <button
                    onClick={() => {
                      setEmail('admin@shop.local');
                      setPassword('Demo12345!');
                      setPasswordError('');
                    }}
                  >
                    管理员账户
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
      {detail && (
        <div className="modal-backdrop" onClick={() => setDetail(null)}>
          <section
            className="modal product-modal"
            role="dialog"
            aria-modal="true"
            aria-label={detail.name}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              aria-label="关闭商品详情"
              onClick={() => setDetail(null)}
            >
              ×
            </button>
            <div className="detail-art">
              <ProductArt kind={detail.image} />
            </div>
            <div>
              <span className="eyebrow">{detail.id} / SHOPPING COLLECTION</span>
              <h2>{detail.name}</h2>
              <p>{detail.description}</p>
              <dl>
                {Object.entries(detail.specs).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              <strong className="detail-price">
                {money(detail.price_cents)}
              </strong>
              <p className="muted">
                {detail.active === 0 ? '已下架 · ' : ''}库存 {detail.stock} 件 ·
                满 ¥99 免运费
              </p>
              <div className="detail-actions">
                <button
                  className="primary"
                  disabled={busy || !detail.stock || detail.active === 0}
                  onClick={() => addCart(detail)}
                >
                  加入购物车 ＋
                </button>
                <button
                  className="text-button"
                  onClick={() => {
                    setDetail(null);
                    void send(`${detail.name}适合什么场景？`);
                  }}
                >
                  问问助手 →
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
      {afterSale && (
        <div className="modal-backdrop" onClick={() => setAfterSale(null)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="申请售后"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              aria-label="关闭售后申请"
              onClick={() => setAfterSale(null)}
            >
              ×
            </button>
            <h2>告诉我们遇到的问题。</h2>
            <p className="muted">订单 {afterSale.id}</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void mutate(async () => {
                  await api('/tickets', 'POST', {
                    order_id: afterSale.id,
                    reason,
                  });
                  setAfterSale(null);
                  setView('tickets');
                }, '售后工单已创建');
              }}
            >
              <label>
                问题描述
                <textarea
                  required
                  minLength={3}
                  maxLength={1000}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="例如：耳机左侧无法连接，希望更换。"
                />
              </label>
              <button
                className="primary full"
                disabled={busy || reason.trim().length < 3}
              >
                提交售后申请
              </button>
            </form>
          </section>
        </div>
      )}
      {deleteTarget && (
        <div
          className="modal-backdrop"
          onClick={() => {
            if (!busy) setDeleteTarget(null);
          }}
        >
          <section
            className="modal delete-conversation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-conversation-title"
            aria-describedby="delete-conversation-description"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="delete-conversation-title">删除这条会话？</h2>
            <p className="delete-conversation-name">{deleteTarget.title}</p>
            <p id="delete-conversation-description" className="muted">
              删除后，会话将从列表移除，无法继续对话，未确认的操作将作废。关联订单和工单不受影响。
            </p>
            <div className="delete-conversation-actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setDeleteTarget(null)}
              >
                取消
              </button>
              <button
                className="primary"
                disabled={busy || chatBusy}
                onClick={() => void deleteConversation()}
              >
                {busy ? '正在删除…' : '确认删除'}
              </button>
            </div>
          </section>
        </div>
      )}
      {notice && (
        <div className="toast" role="status">
          {notice}
        </div>
      )}
    </div>
  );
}
