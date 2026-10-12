import { test, expect } from '@playwright/test';

for (const role of ['buyer', 'agent', 'operations'] as const) {
  test(`${role} workspace fits the viewport and keeps the composer accessible`, async ({
    page,
  }) => {
    await page.goto('/');
    await page
      .getByRole('button', { name: '登录 / 注册', exact: true })
      .first()
      .click();
    const dialog = page.getByRole('dialog');
    await dialog
      .getByRole('button', {
        name: role === 'buyer' ? '买家账户' : '管理员账户',
        exact: true,
      })
      .click();
    await dialog.getByRole('button', { name: '登录', exact: true }).click();
    await expect(dialog).toBeHidden();
    if (role === 'operations')
      await page
        .getByRole('button', { name: 'AI 运营助手', exact: true })
        .click();
    await expect(page.locator('.service-layout')).toBeVisible();

    for (const viewport of [
      { width: 1920, height: 1080 },
      { width: 1440, height: 900 },
      { width: 1280, height: 720 },
      { width: 1024, height: 768 },
      { width: 960, height: 640 },
      { width: 820, height: 1180 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(viewport);
      const metrics = await page.evaluate(() => ({
        width: document.documentElement.scrollWidth,
        height: document.documentElement.scrollHeight,
      }));
      expect(
        metrics.width,
        `${role}: horizontal overflow at ${viewport.width}`,
      ).toBeLessThanOrEqual(viewport.width);
      if (role !== 'agent' && viewport.width >= 640)
        await expect(page.locator('.chat-welcome')).toHaveCSS(
          'display',
          'grid',
        );
      if (viewport.width >= 960) {
        expect(
          metrics.height,
          `${role}: page overflow at ${viewport.width}`,
        ).toBeLessThanOrEqual(viewport.height);
        const panel = await page.locator('.service-layout').boundingBox();
        expect(panel!.y + panel!.height).toBeLessThanOrEqual(viewport.height);
        if (role !== 'agent') {
          const composer = await page.locator('.chat-compose').boundingBox();
          expect(composer!.y + composer!.height).toBeLessThanOrEqual(
            viewport.height,
          );
          expect(composer!.height).toBeGreaterThan(60);
          const messages = page.locator('.chat-messages');
          await messages.evaluate((el) => {
            el.scrollTop = el.scrollHeight;
          });
          expect(await page.locator('.chat-compose').boundingBox()).toEqual(
            composer,
          );
        }
      }
      if (viewport.width === 1440 || viewport.width === 390)
        await page.screenshot({
          path: `../logs/layout-${role}-${viewport.width}.png`,
          fullPage: true,
          style: '.toast{visibility:hidden}',
        });
    }
  });
}
