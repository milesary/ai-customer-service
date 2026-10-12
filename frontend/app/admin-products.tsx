'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Product, ProductEvent } from '@/lib/types';
import ActionPreview from './action-preview';

type Draft = {
  id: string;
  name: string;
  category: string;
  description: string;
  price: string;
  stock: string;
  restock_at: string;
  image: string;
  specs: string;
};
const blank: Draft = {
  id: '',
  name: '',
  category: 'audio',
  description: '',
  price: '',
  stock: '0',
  restock_at: '',
  image: 'headphones',
  specs: '',
};
export default function AdminProducts({
  products,
  busy,
  onSave,
  onAI,
}: {
  products: Product[];
  busy: boolean;
  onSave: (work: () => Promise<unknown>, success: string) => Promise<void>;
  onAI: () => void;
}) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState(false);
  const [original, setOriginal] = useState<Product | null>(null);
  const [error, setError] = useState('');
  const [events, setEvents] = useState<ProductEvent[]>([]);
  const [eventError, setEventError] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [listing, setListing] = useState<Product | null>(null);
  const visible = products.filter(
    (p) =>
      (status === 'all' || p.active === (status === 'listed' ? 1 : 0)) &&
      `${p.id} ${p.name} ${p.description} ${Object.values(p.specs).join(' ')}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  useEffect(() => {
    let disposed = false;
    void api<ProductEvent[]>('/admin/product-events')
      .then((rows) => {
        if (!disposed) {
          setEvents(rows);
          setEventError('');
        }
      })
      .catch((e) => {
        if (!disposed) setEventError(e.message);
      });
    return () => {
      disposed = true;
    };
  }, [products]);
  function edit(p: Product) {
    setOriginal(p);
    setEditing(true);
    setError('');
    setDraft({
      id: p.id,
      name: p.name,
      category: p.category,
      description: p.description,
      price: (p.price_cents / 100).toFixed(2),
      stock: String(p.stock),
      restock_at: p.restock_at || '',
      image: p.image,
      specs: Object.entries(p.specs)
        .map(([k, v]) => `${k}：${v}`)
        .join('\n'),
    });
  }
  function field(key: keyof Draft, value: string) {
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
    setError('');
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft) return;
    if (!/^\d+(\.\d{1,2})?$/.test(draft.price)) {
      setError('售价填写正数，最多两位小数');
      return;
    }
    const specs: Record<string, string> = Object.create(null);
    for (const row of draft.specs.split('\n').filter((r) => r.trim())) {
      const match = row.match(/^([^：:]+)[：:](.*)$/);
      if (!match) {
        setError('规格请每行填写“名称：值”');
        return;
      }
      specs[match[1].trim()] = match[2].trim();
    }
    const priceParts = draft.price.split('.');
    const body = {
      name: draft.name.trim(),
      category: draft.category,
      description: draft.description.trim(),
      price_cents:
        Number(priceParts[0]) * 100 +
        Number((priceParts[1] || '').padEnd(2, '0')),
      stock: Number(draft.stock),
      restock_at: draft.restock_at || null,
      image: draft.image,
      specs,
    };
    const changes = Object.fromEntries(
      Object.entries(body).filter(
        ([k, v]) =>
          JSON.stringify(v) !==
          JSON.stringify(original?.[k as keyof Product] ?? null),
      ),
    );
    if (editing && !Object.keys(changes).length) {
      setError('商品资料未修改');
      return;
    }
    await onSave(
      async () => {
        await api(
          editing ? `/admin/products/${draft.id}` : '/admin/products',
          editing ? 'PATCH' : 'POST',
          editing ? changes : { id: draft.id.toUpperCase(), ...body },
        );
        setDraft(null);
      },
      editing ? '商品已更新' : '商品已新增',
    );
  }
  return (
    <section className="admin-products">
      <div className="product-management-heading">
        <div>
          <h2>商品管理</h2>
          <p>维护商品资料与可售库存，历史订单保留成交时的价格。</p>
        </div>
        <div>
          <button className="secondary" disabled={busy} onClick={onAI}>
            使用 AI 管理
          </button>
          <button
            className="primary"
            disabled={busy}
            onClick={() => {
              setEditing(false);
              setError('');
              setDraft({ ...blank });
            }}
          >
            新增商品
          </button>
        </div>
      </div>
      {draft && (
        <form className="product-editor" onSubmit={(e) => void submit(e)}>
          <h3>{editing ? `编辑商品 ${draft.id}` : '新增商品'}</h3>
          <div className="product-form-grid">
            <label>
              商品编号
              <input
                required
                disabled={editing || busy}
                pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,39}"
                maxLength={40}
                value={draft.id}
                onChange={(e) => field('id', e.target.value)}
                placeholder="例如 P007"
              />
            </label>
            <label>
              商品名称
              <input
                required
                maxLength={120}
                value={draft.name}
                onChange={(e) => field('name', e.target.value)}
              />
            </label>
            <label>
              商品分类
              <select
                value={draft.category}
                onChange={(e) => {
                  field('category', e.target.value);
                  if (e.target.value === 'clothing') field('image', 'shirt');
                }}
              >
                <option value="audio">声音与陪伴</option>
                <option value="workspace">桌面与效率</option>
                <option value="charging">连接与充电</option>
                <option value="clothing">服装</option>
              </select>
            </label>
            <label>
              售价（元）
              <input
                required
                type="number"
                min="0.01"
                max="1000000"
                step="0.01"
                value={draft.price}
                onChange={(e) => field('price', e.target.value)}
              />
            </label>
            <label>
              可售库存
              <input
                required
                type="number"
                min="0"
                max="100000"
                step="1"
                value={draft.stock}
                onChange={(e) => field('stock', e.target.value)}
              />
            </label>
            <label>
              预计补货日期
              <input
                type="date"
                value={draft.restock_at}
                onChange={(e) => field('restock_at', e.target.value)}
              />
            </label>
            <label>
              商品示意图
              <select
                value={draft.image}
                onChange={(e) => field('image', e.target.value)}
              >
                {[
                  ['headphones', '耳机'],
                  ['keyboard', '键盘'],
                  ['charger', '充电板'],
                  ['speaker', '音箱'],
                  ['mouse', '鼠标'],
                  ['hub', '扩展坞'],
                  ['shirt', '服装'],
                ].map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label className="product-wide">
              商品描述
              <textarea
                maxLength={2000}
                value={draft.description}
                onChange={(e) => field('description', e.target.value)}
              />
            </label>
            <label className="product-wide">
              商品规格
              <textarea
                value={draft.specs}
                maxLength={11000}
                onChange={(e) => field('specs', e.target.value)}
                placeholder={'每行一项，例如：\n连接方式：蓝牙\n颜色：深绿'}
              />
            </label>
          </div>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <p className="muted">
            {editing
              ? '保存资料保持当前上下架状态。'
              : '新增商品保存后即上架。'}
            可售库存不含订单已预留的数量。图片为本地示意图。
          </p>
          <div className="product-editor-actions">
            <button className="primary" disabled={busy}>
              保存商品
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => setDraft(null)}
            >
              取消
            </button>
          </div>
        </form>
      )}
      <div className="product-filters">
        <label>
          查询商品
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="编号、名称或规格"
          />
        </label>
        <label>
          上架状态
          <select
            aria-label="上架状态"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">全部商品</option>
            <option value="listed">已上架</option>
            <option value="unlisted">已下架</option>
          </select>
        </label>
        <span>{visible.length} 件商品</span>
      </div>
      {listing && (
        <div className="listing-confirm" role="region" aria-label="上下架确认">
          <h3>
            {listing.active ? '下架' : '上架'} {listing.id} · {listing.name}
          </h3>
          <p>
            {listing.active
              ? '下架后停止展示和新购买，购物车中的商品不能结算。已创建订单继续履约。'
              : '上架后恢复商品展示和购买，库存为 0 时显示售罄。'}
          </p>
          <div>
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                void onSave(
                  async () => {
                    await api(`/admin/products/${listing.id}/listing`, 'PUT', {
                      active: !listing.active,
                    });
                    setListing(null);
                  },
                  listing.active ? '商品已下架' : '商品已上架',
                )
              }
            >
              {listing.active ? '确认下架' : '确认上架'}
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => setListing(null)}
            >
              取消
            </button>
          </div>
        </div>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>商品</th>
              <th>状态</th>
              <th>售价</th>
              <th>可售库存</th>
              <th>补货日期</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.id} · {p.name}
                </td>
                <td>{p.active ? '已上架' : '已下架'}</td>
                <td>¥{(p.price_cents / 100).toFixed(2)}</td>
                <td>{p.stock}</td>
                <td>{p.restock_at || '未设置'}</td>
                <td>
                  <div className="product-row-actions">
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() => edit(p)}
                    >
                      编辑
                    </button>
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() => setListing(p)}
                    >
                      {p.active ? '下架' : '上架'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!visible.length && <p className="muted">没有匹配商品</p>}
      </div>
      <details className="product-audit">
        <summary>商品操作记录 · 最近 50 条</summary>
        {eventError && <p role="alert">{eventError}</p>}
        {events.map((event) => (
          <article key={event.id}>
            <strong>
              {event.product_id} ·{' '}
              {(
                {
                  create: '新增',
                  update: '修改',
                  list: '上架',
                  unlist: '下架',
                } as Record<string, string>
              )[event.kind] || event.kind}{' '}
              · {event.actor_name}
            </strong>
            <p>
              {new Date(event.created_at).toLocaleString('zh-CN')} ·{' '}
              {event.action_id ? 'AI 确认操作' : '手动操作'}
            </p>
            <ActionPreview
              before={event.before_data}
              after={event.after_data}
            />
          </article>
        ))}
        {!events.length && !eventError && <p>暂无操作记录</p>}
      </details>
    </section>
  );
}
