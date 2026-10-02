async page => {
  await page.getByRole('tab',{name:'新建任务',exact:true}).click();
  await page.locator('#f_name').fill('<img src=x onerror=alert(1)>');
  await page.locator('#f_profile').selectOption('a_plus_b');
  await page.locator('#f_username').fill('tester');
  await page.locator('#f_password').fill('test-only');
  await page.locator('#f_mode').selectOption('concurrent');
  await page.locator('#f_workers').fill('2');
  await page.locator('#f_strategies').selectOption(['random']);
  await page.locator('#f_caseCount').fill('40');
  const createdResponse=page.waitForResponse(r=>r.url().endsWith('/api/v1/tasks')&&r.request().method()==='POST');
  await page.locator('#submitBtn').click();
  const response=await createdResponse;
  if(response.status()!==202) throw new Error('create failed');
  const {task_id}=await response.json();
  const row=page.locator(`tr[data-task-id="${task_id}"]`);
  await row.waitFor();
  if(await row.locator('img').count()) throw new Error('task name executed as markup');
  if(!await row.getByRole('button',{name:'删除',exact:true}).isDisabled()) throw new Error('active delete enabled');
  await row.getByRole('button',{name:'取消',exact:true}).click();
  await row.getByText('CANCEL_REQUESTED',{exact:true}).waitFor();
  await row.getByText('CANCELLED',{exact:true}).waitFor({timeout:15000});
  await row.getByRole('button',{name:'<img src=x onerror=alert(1)>',exact:true}).click();
  await page.locator('#modalBody').getByText('状态 CANCELLED · 进度 100%',{exact:true}).waitFor();
  if(await page.locator('#modalBody img').count()) throw new Error('unsafe detail');
  const cases=page.locator('#modalBody details[data-case-id]');
  if(await cases.count()!==40) throw new Error('missing case history');
  await cases.first().locator('summary').first().click();
  if(!(await cases.first().locator('pre').first().textContent()).includes('#include')) throw new Error('source missing');
  for(const format of ['HTML','JSON']) {
    const popupPromise=page.waitForEvent('popup');
    await page.getByRole('link',{name:'查看 '+format+' 报告',exact:true}).click();
    const popup=await popupPromise;
    await popup.waitForLoadState();
    if(!(await popup.locator('body').textContent()).includes(format==='HTML'?'OJ 测试报告':'report_id')) throw new Error('report not loaded');
    await popup.close();
  }
  await page.bringToFront();
  await page.keyboard.press('Escape');
  await page.reload();
  await page.locator(`tr[data-task-id="${task_id}"]`).getByText('CANCELLED',{exact:true}).waitFor();
  return {task_id,state:'CANCELLED',source:true,reports:['html','json'],safeName:true,refreshHistory:true};
}
