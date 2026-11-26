import { test, expect } from '@playwright/test';

test('diagnostic: filter button computed backgrounds', async ({ page }) => {
  await page.goto('/');
  
  // Click "All" to activate it
  await page.getByRole('button', { name: 'All', exact: true }).click();
  
  const buttons = ['All', 'Active', 'Completed'];
  for (const name of buttons) {
    const btn = page.getByRole('button', { name, exact: true });
    const bg = await btn.evaluate((el) => getComputedStyle(el).backgroundColor);
    const bgColor = await btn.evaluate((el) => el.style.backgroundColor);
    console.log(`${name} button - computed: ${bg}, inline: ${JSON.stringify(bgColor)}`);
  }
});
