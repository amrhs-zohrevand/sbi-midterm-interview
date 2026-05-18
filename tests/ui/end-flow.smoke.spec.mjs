import { test, expect } from '@playwright/test';


async function expectCompletionDefaults(page) {
  await expect(
    page.getByRole('textbox', { name: 'Confirm or update your email address:' })
  ).toHaveValue('miros@example.com');
  await expect(
    page.getByRole('checkbox', { name: 'Email me a transcript of this interview' })
  ).toBeChecked();
  await expect(
    page.getByText('Rate each statement from 1 to 7 (1 = not at all, 7 = extremely).')
  ).toHaveCount(1);
}


test('manual finish flow prepopulates email and transcript opt-in', async ({ page }) => {
  await page.goto(
    '/?name=Miros&recipient_email=miros@example.com&interview_config=midterm_interview'
  );

  await page.getByRole('button', { name: 'Finish interview' }).click();

  await expect(page.getByRole('heading', { name: 'Finish Interview' })).toBeVisible();
  await expectCompletionDefaults(page);
});


test('end-of-interview flow works in the browser', async ({ page }) => {
  await page.goto(
    '/?name=Miros&recipient_email=miros@example.com&interview_config=midterm_interview'
  );

  await expect(
    page.getByText(
      'Hello! This is a smoke test interview. Please tell me in one sentence how the experience went.'
    )
  ).toBeVisible();

  const chatInput = page.getByTestId('stChatInputTextArea');
  await chatInput.fill('It helped me reflect on my internship.');
  await chatInput.press('Enter');

  await expect(page.getByRole('heading', { name: 'Before You Go' })).toBeVisible();
  await expect(
    page.getByText(
      'The conversation has ended. You can finish here and leave a bit of quick feedback without leaving this page.'
    )
  ).toBeVisible();
  await expectCompletionDefaults(page);
  await page
    .getByRole('radiogroup', { name: 'Compared with a human interviewer, this AI felt more helpful.' })
    .getByText('6', { exact: true })
    .click();
  await page
    .getByRole('radiogroup', { name: 'How connected did you feel to the interviewer?' })
    .getByText('5', { exact: true })
    .click();
  await page
    .getByRole('radiogroup', { name: 'The interviewer understood what I was thinking and feeling.' })
    .getByText('6', { exact: true })
    .click();
  await page
    .getByRole('radiogroup', { name: 'The interaction made me feel validated.' })
    .getByText('4', { exact: true })
    .click();

  await page
    .getByRole('textbox', { name: 'Anything we should improve?' })
    .fill('The inline ending feels much more natural now.');
  await page.getByRole('button', { name: 'Save and Finish' }).click();

  await expect(page.getByText('Your interview has been saved.')).toBeVisible();
  await expect(
    page.getByText(
      'Smoke test mode is enabled: no external model, email, or remote database calls were made.'
    )
  ).toBeVisible();
  await expect(
    page.getByText('Your quick in-app feedback was saved too. Thank you.')
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Open the full follow-up survey' })
  ).toBeVisible();
});


test('mixed-content close code stays in the interview until a later code-only close', async ({ page }) => {
  await page.goto(
    '/?name=Miros&recipient_email=miros@example.com&interview_config=industry_org_survey'
  );

  await expect(
    page.getByText(
      'Hello! This is a smoke test interview. Please tell me in one sentence how the experience went.'
    )
  ).toBeVisible();

  const chatInput = page.getByTestId('stChatInputTextArea');
  await chatInput.fill('Trigger mixed close');
  await chatInput.press('Enter');

  await expect(
    page.getByText('Tell me more about the boundary you draw there.')
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Before You Go' })).toHaveCount(0);

  await chatInput.fill('The boundary is mostly about confidentiality.');
  await chatInput.press('Enter');

  await expect(page.getByRole('heading', { name: 'Before You Go' })).toBeVisible();
  await expectCompletionDefaults(page);
});
