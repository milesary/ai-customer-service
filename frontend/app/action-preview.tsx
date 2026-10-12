import { money } from '@/lib/format';

const labels: Record<string, string> = {
  id: '商品编号',
  name: '商品名称',
  active: '上架状态',
  category: '分类',
  description: '商品描述',
  price_cents: '售价',
  stock: '可售库存',
  restock_at: '补货日期',
  specs: '规格',
  image: '商品示意图',
};
function display(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '未填写';
  if (key === 'price_cents') return money(Number(value));
  if (key === 'active') return Number(value) === 1 ? '已上架' : '已下架';
  if (key === 'category')
    return (
      (
        {
          audio: '声音与陪伴',
          workspace: '桌面与效率',
          charging: '连接与充电',
          clothing: '服装',
        } as Record<string, string>
      )[String(value)] || String(value)
    );
  if (key === 'image')
    return (
      (
        {
          headphones: '耳机',
          keyboard: '键盘',
          charger: '充电板',
          speaker: '音箱',
          mouse: '鼠标',
          hub: '扩展坞',
          shirt: '服装',
        } as Record<string, string>
      )[String(value)] + '示意图'
    );
  if (typeof value === 'object')
    return (
      Object.entries(value as Record<string, string>)
        .map(([k, v]) => `${k}：${v}`)
        .join('；') || '未填写'
    );
  return String(value);
}
export default function ActionPreview({
  before,
  after,
}: {
  before: Record<string, unknown> | null;
  after: Record<string, unknown>;
}) {
  const keys = Object.keys(labels).filter(
    (k) =>
      k in after &&
      (!before || JSON.stringify(before[k]) !== JSON.stringify(after[k])),
  );
  return (
    <div className="operation-preview">
      <table>
        <thead>
          <tr>
            <th>字段</th>
            {before && <th>修改前</th>}
            <th>{before ? '修改后' : '新增内容'}</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k}>
              <th>{labels[k]}</th>
              {before && <td>{display(k, before[k])}</td>}
              <td>{display(k, after[k])}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!keys.length && <p>字段值未变化</p>}
    </div>
  );
}
