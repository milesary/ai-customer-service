import { test, expect } from '@playwright/test';

for (const admin of [false, true]) {
  test(`${admin ? 'operations' : 'buyer'} can cancel deletion and delete the current conversation`, async ({
    page,
  }) => {
    await page.goto('/');
    await page
      .getByRole('button', { name: '登录 / 注册', exact: true })
      .first()
      .click();
    const login = page.getByRole('dialog');
    await login
      .getByRole('button', {
        name: admin ? '管理员账户' : '买家账户',
        exact: true,
      })
      .click();
    await login.getByRole('button', { name: '登录', exact: true }).click();
    await expect(login).toBeHidden();
    if (admin)
      await page
        .getByRole('button', { name: 'AI 运营助手', exact: true })
        .click();
    const title = `删除功能验证 ${Date.now()}`;
    await page.getByLabel('发送消息给客服').fill(title);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const entry = page.locator('.session-entry').filter({ hasText: title });
    await expect(entry).toBeVisible();
    await expect(entry).toHaveCSS('display', 'flex');
    const remove = entry.getByRole('button', {
      name: `删除会话：${title}`,
      exact: true,
    });
    await expect(remove).toBeEnabled();
    await remove.click();
    const confirmation = page.getByRole('dialog', { name: '删除这条会话？' });
    await expect(confirmation).toContainText(title);
    await confirmation
      .getByRole('button', { name: '取消', exact: true })
      .click();
    await expect(entry).toBeVisible();
    await remove.click();
    await confirmation
      .getByRole('button', { name: '确认删除', exact: true })
      .click();
    await expect(confirmation).toBeHidden();
    await expect(entry).toHaveCount(0);
    await expect(page.locator('.chat-welcome')).toBeVisible();
    await page.reload();
    if (admin)
      await page
        .getByRole('button', { name: 'AI 运营助手', exact: true })
        .click();
    await expect(page.locator('.service-layout')).toBeVisible();
    await expect(entry).toHaveCount(0);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}
