import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

async function login(page: Page, admin = false) {
  await page.goto('/');
  await page
    .getByRole('button', { name: '登录 / 注册', exact: true })
    .first()
    .click();
  const dialog = page.getByRole('dialog');
  if (admin)
    await dialog
      .getByRole('button', { name: '管理员账户', exact: true })
      .click();
  await dialog.getByRole('button', { name: '登录', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.locator('.service-heading h1')).toHaveText(
    admin ? '客服工作台' : 'AI 电商客服',
  );
}

test('buyer and human service complete a handoff and return to AI', async ({
  page,
  browser,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await login(page);
  await page
    .locator('.scenario-list')
    .getByRole('button', { name: '查询我的订单和物流' })
    .click();
  await expect(
    page.locator('.chat-message.message-assistant').last(),
  ).toContainText('ORD-DEMO');
  await expect(page.locator('.run-meta').last()).toBeVisible();
  await page.getByRole('button', { name: '转人工', exact: true }).click();
  const reason = '浏览器验证：耳机左侧无法连接，确认换货方案';
  await page.getByLabel('需要人工协助的问题').fill(reason);
  await page.getByRole('button', { name: '确认转人工', exact: true }).click();
  await expect(page.locator('.chat-channel')).toHaveText('人工服务');
  await page.getByLabel('发送消息给客服').fill('我已尝试重置耳机');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await expect(page.locator('.chat-message.message-user').last()).toContainText(
    '我已尝试重置耳机',
  );
  const adminContext = await browser.newContext({
    baseURL: process.env.E2E_URL || 'http://127.0.0.1:3120',
    viewport: { width: 1440, height: 1000 },
  });
  const agent = await adminContext.newPage();
  await login(agent, true);
  await agent
    .locator('.session-list')
    .getByRole('button')
    .filter({ hasText: reason })
    .first()
    .click();
  await expect(agent.locator('.handoff-summary')).toContainText('查询我的订单');
  await expect(agent.locator('.customer-identity')).toContainText('林同学');
  await agent.getByRole('button', { name: '接单处理', exact: true }).click();
  await agent.getByLabel('回复客户').fill('已核实订单，正在确认换货条件');
  await agent.getByRole('button', { name: '发送回复', exact: true }).click();
  await page.getByRole('button', { name: '刷新进度', exact: true }).click();
  await expect(page.locator('.chat-message').last()).toContainText(
    '已核实订单',
  );
  await agent
    .getByLabel('处理结果', { exact: true })
    .fill('已安排模拟换货，问题已解决');
  await agent.getByRole('button', { name: '完成工单', exact: true }).click();
  await page.getByRole('button', { name: '刷新进度', exact: true }).click();
  await expect(page.locator('.chat-channel')).toHaveText('在线咨询');
  await page.getByLabel('发送消息给客服').fill('查询我的售后处理进度');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await expect(
    page.locator('.chat-message.message-assistant').last(),
  ).toContainText('已安排模拟换货');
  expect(errors).toEqual([]);
  await page.screenshot({
    path: '../logs/service-desktop.png',
    fullPage: true,
  });
  await agent.screenshot({ path: '../logs/service-agent.png', fullPage: true });
  await adminContext.close();
});

test('password validation uses an inline message', async ({ page }) => {
  await page.goto('/');
  await page
    .getByRole('button', { name: '登录 / 注册', exact: true })
    .first()
    .click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: '新朋友？创建账户' }).click();
  await dialog.getByLabel('昵称').fill('测试昵称');
  await dialog.getByLabel('密码', { exact: true }).fill('123456');
  await dialog.getByRole('button', { name: '创建账户', exact: true }).click();
  await expect(page.locator('#password-hint')).toHaveText(
    '密码至少需要 8 位字符',
  );
  await expect(dialog.getByLabel('密码', { exact: true })).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  await dialog.getByLabel('密码', { exact: true }).fill('12345678');
  await expect(page.locator('#password-hint')).toHaveText('至少 8 位字符');
});

test('mobile workspace keeps readable conversation and no horizontal overflow', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(page.locator('.chat-welcome h2')).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(
    await page
      .locator('.chat-compose textarea')
      .evaluate((el) => getComputedStyle(el).fontSize),
  ).toBe('15px');
  await page.screenshot({ path: '../logs/service-mobile.png', fullPage: true });
});

test('logout clears the visible customer service context', async ({ page }) => {
  await login(page);
  await expect(page.locator('.customer-identity')).toContainText('林同学');
  await page
    .getByRole('button', { name: '林同学 · 退出', exact: true })
    .click();
  await expect(page.locator('.customer-identity')).toHaveCount(0);
  await expect(page.locator('.context-placeholder')).toContainText(
    '登录后查看服务上下文',
  );
});

test('admin creates and edits products manually, then confirms an AI stock update', async ({
  page,
}) => {
  const id = `PUI${Date.now()}`;
  await login(page, true);
  await page.getByRole('button', { name: '业务管理', exact: true }).click();
  await page.getByRole('button', { name: '新增商品', exact: true }).click();
  await page.getByLabel('商品编号', { exact: true }).fill(id);
  await page.getByLabel('商品名称', { exact: true }).fill('浏览器验证耳机');
  await page.getByLabel('售价（元）', { exact: true }).fill('199.99');
  await page.getByLabel('可售库存', { exact: true }).fill('17');
  await page.getByRole('button', { name: '保存商品', exact: true }).click();
  const row = page
    .locator('.admin-products tbody tr')
    .filter({ hasText: id })
    .first();
  await expect(row).toContainText('199.99');
  await row.getByRole('button', { name: '编辑', exact: true }).click();
  await page
    .getByLabel('商品名称', { exact: true })
    .fill('浏览器验证耳机升级版');
  await page.getByLabel('售价（元）', { exact: true }).fill('198.01');
  await page.getByRole('button', { name: '保存商品', exact: true }).click();
  await expect(row).toContainText('升级版');
  await page.getByRole('button', { name: '使用 AI 管理', exact: true }).click();
  await expect(page.locator('.service-heading h1')).toHaveText('AI 运营助手');
  await page.getByLabel('发送消息给客服').fill(`把 ${id} 的库存改为 27 件`);
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  const card = page.locator('.action-card').last();
  await expect(card.locator('.operation-preview')).toContainText('17');
  await expect(card.locator('.operation-preview')).toContainText('27');
  await card.getByRole('button', { name: '确认执行', exact: true }).click();
  await expect(card).toContainText('已执行');
  await page.getByRole('button', { name: '业务管理', exact: true }).click();
  await expect(row).toContainText('27');
  await page.locator('.product-audit summary').click();
  await expect(
    page.locator('.product-audit article').filter({ hasText: id }).first(),
  ).toContainText('AI 确认操作');
  await page.screenshot({
    path: '../logs/admin-product-management.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'AI 运营助手', exact: true }).click();
  await page.screenshot({
    path: '../logs/admin-ai-operations.png',
    fullPage: true,
  });
});

test('AI product creation waits for confirmation and stale stock previews are blocked', async ({
  page,
}) => {
  const id = `PAI${Date.now()}`;
  await login(page, true);
  await page.getByRole('button', { name: 'AI 运营助手', exact: true }).click();
  await page
    .getByLabel('发送消息给客服')
    .fill(
      `新增商品，编号 ${id}，名称 AI草稿耳机，分类 audio，售价 120.01，库存 8`,
    );
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  const card = page.locator('.action-card').last();
  await expect(card).toContainText(id);
  await expect(card).toContainText('120.01');
  expect((await page.request.get(`/api/products/${id}`)).status()).toBe(404);
  await card.getByRole('button', { name: '确认执行', exact: true }).click();
  await expect(card).toContainText('已执行');
  const product = await (await page.request.get(`/api/products/${id}`)).json();
  expect(product.price_cents).toBe(12001);
  await page.getByLabel('发送消息给客服').fill(`把 ${id} 的库存改为 13 件`);
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await expect(page.locator('.action-card').last()).toContainText('待确认');
  const token = await page.evaluate(() =>
    sessionStorage.getItem('shiwu-token'),
  );
  const changed = await page.request.patch(`/api/admin/products/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { stock: 9 },
  });
  expect(changed.status()).toBe(200);
  await page
    .locator('.action-card')
    .last()
    .getByRole('button', { name: '确认执行', exact: true })
    .click();
  await expect(page.locator('.toast')).toContainText('已变化');
  expect(
    (await (await page.request.get(`/api/products/${id}`)).json()).stock,
  ).toBe(9);
});

test('mobile admin can reach AI and the product editor without overflow', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, true);
  await page.getByRole('button', { name: 'AI 运营助手', exact: true }).click();
  await expect(page.locator('.chat-compose')).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole('button', { name: '业务管理', exact: true }).click();
  await page.getByRole('button', { name: '新增商品', exact: true }).click();
  await expect(page.getByLabel('商品名称', { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: '../logs/admin-mobile.png', fullPage: true });
});

test('listing clothes asks for missing details and remembers them after reload', async ({
  page,
}) => {
  const id = `CLOUI${Date.now()}`;
  await login(page, true);
  await page.getByRole('button', { name: 'AI 运营助手', exact: true }).click();
  await page.getByLabel('发送消息给客服').fill('上新一个衣服商品');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await expect(
    page.locator('.chat-message.message-assistant').last(),
  ).toContainText('请补充');
  await expect(page.locator('.chat-products')).toHaveCount(0);
  await page.getByLabel('发送消息给客服').fill('名称 纯棉T恤，售价 99.00');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await expect(
    page.locator('.chat-message.message-assistant').last(),
  ).toContainText('编号、库存');
  await page.reload();
  await page.getByRole('button', { name: 'AI 运营助手', exact: true }).click();
  await page
    .locator('.session-list')
    .getByRole('button')
    .filter({ hasText: '上新一个衣服商品' })
    .first()
    .click();
  await expect(
    page.locator('.chat-message.message-assistant').last(),
  ).toContainText('纯棉T恤');
  await page.getByLabel('发送消息给客服').fill(`编号 ${id}，库存 20`);
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  const card = page.locator('.action-card').last();
  await expect(card).toContainText('服装');
  await expect(card).toContainText('99.00');
  await expect(card).toContainText('服装示意图');
  expect((await page.request.get(`/api/products/${id}`)).status()).toBe(404);
  await card.getByRole('button', { name: '确认执行', exact: true }).click();
  await expect(card).toContainText('已执行');
  await page.getByRole('button', { name: '商品浏览', exact: true }).click();
  await page.getByRole('button', { name: '服装', exact: true }).click();
  await page.getByLabel('搜索商品').fill(id);
  const product = page.locator('.product-card').filter({ hasText: id });
  await expect(product).toContainText('纯棉T恤');
  await expect(product.locator('.art-shirt')).toBeVisible();
  await page.screenshot({
    path: '../logs/clothing-listing.png',
    fullPage: true,
  });
});

test('complete AI lifecycle and manual relisting preserve buyer purchase boundaries', async ({
  page,
  browser,
}) => {
  const id = `LIFE${Date.now()}`;
  await login(page, true);
  await page.getByRole('button', { name: 'AI 运营助手', exact: true }).click();
  async function command(message: string) {
    await page.getByLabel('发送消息给客服').fill(message);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const card = page.locator('.action-card').last();
    await expect(card).toContainText('待确认');
    await card.getByRole('button', { name: '确认执行', exact: true }).click();
    await expect(card).toContainText('已执行');
  }
  await command(
    `新增商品，编号 ${id}，名称 完整流程测试商品，分类 服装，售价 99.00，库存 5`,
  );
  const buyerContext = await browser.newContext({
    baseURL: process.env.E2E_URL || 'http://127.0.0.1:3120',
  });
  const buyerAuth = await page.request.post('/api/auth/register', {
    data: {
      email: `${id.toLowerCase()}@shop.local`,
      name: '流程买家',
      password: 'Lifecycle12345!',
    },
  });
  expect(buyerAuth.status()).toBe(201);
  const buyerToken = (await buyerAuth.json()).token;
  await buyerContext.addInitScript(
    (token) => sessionStorage.setItem('shiwu-token', token),
    buyerToken,
  );
  const buyer = await buyerContext.newPage();
  await buyer.goto('/');
  await expect(buyer.locator('.service-heading h1')).toHaveText('AI 电商客服');
  await buyer.getByRole('button', { name: '商品浏览', exact: true }).click();
  await buyer.getByLabel('搜索商品').fill(id);
  await buyer
    .getByRole('button', { name: '添加完整流程测试商品到购物车', exact: true })
    .click();
  await expect(buyer.locator('.toast')).toContainText('已加入购物车');
  await command(`把 ${id} 的售价改为 109.99`);
  await command(`把 ${id} 的库存增加 2 件`);
  await command(`下架 ${id}`);
  expect((await page.request.get(`/api/products/${id}`)).status()).toBe(404);
  await page.getByLabel('发送消息给客服').fill(`查询已下架商品 ${id}`);
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await expect(
    page.locator('.chat-message.message-assistant').last(),
  ).toContainText('已下架');
  await buyer.reload();
  await buyer.getByRole('button', { name: '商品浏览', exact: true }).click();
  await buyer.getByLabel('搜索商品').fill(id);
  await expect(buyer.locator('.product-card')).toHaveCount(0);
  await buyer.getByRole('button', { name: /^购物车/ }).click();
  await expect(
    buyer.locator('.cart-item').filter({ hasText: '完整流程测试商品' }),
  ).toContainText('已下架');
  await expect(
    buyer.getByRole('button', { name: '创建订单 →', exact: true }),
  ).toBeDisabled();
  await page.getByRole('button', { name: '业务管理', exact: true }).click();
  await page.getByLabel('查询商品', { exact: true }).fill(id);
  await page.getByLabel('上架状态', { exact: true }).selectOption('unlisted');
  const row = page
    .locator('.admin-products .table-scroll tbody tr')
    .filter({ hasText: id });
  await expect(row).toContainText('已下架');
  await row.getByRole('button', { name: '编辑', exact: true }).click();
  await page.getByLabel('售价（元）', { exact: true }).fill('129.99');
  await page.getByLabel('可售库存', { exact: true }).fill('11');
  await page.getByRole('button', { name: '保存商品', exact: true }).click();
  await expect(row).toContainText('129.99');
  await expect(row).toContainText('已下架');
  await page.screenshot({
    path: '../logs/product-lifecycle-unlisted.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'AI 运营助手', exact: true }).click();
  await command(`重新上架 ${id}`);
  await page.screenshot({
    path: '../logs/product-lifecycle-ai.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: '业务管理', exact: true }).click();
  await page.getByLabel('查询商品', { exact: true }).fill(id);
  await page.getByLabel('上架状态', { exact: true }).selectOption('listed');
  await row.getByRole('button', { name: '下架', exact: true }).click();
  await page.getByRole('button', { name: '确认下架', exact: true }).click();
  await expect(row).toHaveCount(0);
  await page.getByLabel('上架状态', { exact: true }).selectOption('unlisted');
  await row.getByRole('button', { name: '上架', exact: true }).click();
  await page.getByRole('button', { name: '确认上架', exact: true }).click();
  await expect(row).toHaveCount(0);
  await buyer.reload();
  await buyer.getByRole('button', { name: /^购物车/ }).click();
  await expect(
    buyer.getByRole('button', { name: '创建订单 →', exact: true }),
  ).toBeEnabled();
  await buyer.getByRole('button', { name: '创建订单 →', exact: true }).click();
  await expect(
    buyer.locator('.record').filter({ hasText: '完整流程测试商品' }),
  ).toContainText('¥129.99');
  await buyerContext.close();
});
