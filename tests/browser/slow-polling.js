async page => {
  await page.route('**/api/v1/tasks?*',async route=>{await page.waitForTimeout(3500); await route.continue();});
  try {
    await page.reload();
    await page.locator('tr[data-task-id]').first().waitFor({timeout:10000});
    return {slowPollingVisible:true};
  } finally {await page.unroute('**/api/v1/tasks?*');}
}
