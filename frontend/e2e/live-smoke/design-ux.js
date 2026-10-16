import { expect } from '@playwright/test';
import { chooseDropdown, dropdownValues } from './dropdowns.js';
import { contrastRatio } from '../../src/utils/contrast.js';

const check = expect.configure({ timeout: 6_000 });
const COVERS = ['hyrule', 'vigil', 'sunlit', 'snowquill', 'verdant', 'harvest'];
const PIXEL = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=', 'base64');

// Inspect rendered colors, including translucent ancestor surfaces and every
// gradient stop. Nothing here reads account state or evaluates app source.
async function contrastPairs(locator, { property = 'color', focus = false, adjacent = false } = {}) {
  return locator.evaluate((element, options) => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d');
    const rgba = value => {
      context.clearRect(0, 0, 1, 1);
      context.fillStyle = value;
      context.fillRect(0, 0, 1, 1);
      return [...context.getImageData(0, 0, 1, 1).data].map((value, index) => index === 3 ? value / 255 : value);
    };
    const blend = (color, background) => color.slice(0, 3).map((value, index) => Math.round(value * color[3] + background[index] * (1 - color[3])));
    const hex = color => '#' + color.map(value => value.toString(16).padStart(2, '0')).join('');
    const ancestors = [];
    for (let node = element; node; node = node.parentElement) ancestors.unshift(node);
    let surfaces = [[255, 255, 255]];
    let outside = surfaces;
    for (const node of ancestors) {
      if (node === element) outside = [...surfaces];
      const style = getComputedStyle(node);
      surfaces = surfaces.map(background => blend(rgba(style.backgroundColor), background));
      const stops = style.backgroundImage.match(/(?:rgba?|color|oklab|oklch|lab|lch|hsla?)\([^)]+\)/g);
      if (style.backgroundImage !== 'none' && !stops) throw new Error('DESIGN_CONTRAST_SURFACE');
      if (stops) surfaces = surfaces.flatMap(background => stops.map(stop => blend(rgba(stop), background)));
    }
    const style = getComputedStyle(element);
    const foreground = rgba(options.focus
      ? style.boxShadow === 'none' ? style.outlineColor : style.getPropertyValue('--tw-ring-color')
      : style[options.property]);
    if (options.adjacent) surfaces.push(...outside);
    return surfaces.map(background => ({ foreground: hex(blend(foreground, background)), background: hex(background) }));
  }, { property, focus, adjacent });
}

async function readable(locator, minimum, options) {
  // Cover tokens change immediately, but transition-colors interpolates the
  // painted foreground/surface independently. Check the settled UI after the
  // actual finite paint transitions finish, including inherited surfaces.
  // Do not wait for a favorable contrast value: a bad stable palette must fail
  // the unchanged threshold once its transitions have completed.
  await check.poll(() => locator.evaluate(element => {
    for (let node = element; node; node = node.parentElement) {
      for (const animation of node.getAnimations()) {
        const property = animation.transitionProperty;
        if (typeof property === 'string'
          && /color$|^box-shadow$|^fill$|^stroke$|^--tw-gradient-(?:from|via|to)$/.test(property)
          && !['finished', 'idle'].includes(animation.playState)) return false;
      }
    }
    return true;
  }), { message: 'DESIGN_COLOR_SETTLEMENT', intervals: [16, 32, 64] }).toBe(true);
  for (const pair of await contrastPairs(locator, options)) {
    check(contrastRatio(pair.foreground, pair.background), 'DESIGN_CONTROL_CONTRAST').toBeGreaterThanOrEqual(minimum);
  }
}

async function fitsPhone(locator) {
  const bounds = await locator.boundingBox();
  check(Boolean(bounds), 'DESIGN_MOBILE').toBe(true);
  check(bounds.x, 'DESIGN_MOBILE').toBeGreaterThanOrEqual(-0.5);
  check(bounds.x + bounds.width, 'DESIGN_MOBILE').toBeLessThanOrEqual(320.5);
}

async function chooseFile(page, button, file) {
  const chooser = page.waitForEvent('filechooser', { timeout: 6_000 });
  await button.click({ timeout: 6_000 });
  await (await chooser).setFiles(file, { timeout: 6_000 });
}

// Call only on a fresh anonymous page protected by the existing RequestGate.
// The production default visits the real deployed route. The optional path is
// for the isolated offline fixture; it never changes or mocks API responses.
// All form saves, pins, failures and file choices below are synthetic gallery
// state, not domain uploads, rewards, account changes or service-worker actions.
export async function assertDesignUx(page, baseUrl, { designPath = '/__design' } = {}) {
  const started = Date.now();
  const viewport = page.viewportSize();
  const wasReduced = await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches);
  const target = new URL(designPath, baseUrl);
  check(target.origin, 'DESIGN_ORIGIN').toBe(new URL(baseUrl).origin);
  try {
    await page.setViewportSize({ width: 320, height: 740 });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto(target.href, { waitUntil: 'domcontentloaded', timeout: 15_000 });
    const settings = page.getByRole('complementary', { name: 'Design preview settings', exact: true });
    await check(settings).toBeVisible();
    const spinner = page.getByRole('button', { name: 'Saving…', exact: true }).locator('svg');
    await check(settings.getByText(/^Device motion preference: standard\./)).toBeVisible();
    await check(spinner).toHaveCSS('animation-name', 'spin');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await check(settings.getByText(/^Device motion preference: reduced\./)).toBeVisible();
    await check(spinner).toHaveCSS('animation-name', 'none');
    // The explicit preview control also works independently of the OS setting.
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await check(spinner).toHaveCSS('animation-name', 'spin');
    await settings.getByRole('checkbox', { name: 'Preview reduced motion', exact: true }).check();
    await check(spinner).toHaveCSS('animation-name', 'none');
    await settings.getByRole('checkbox', { name: 'Preview reduced motion', exact: true }).uncheck();
    await check(spinner).toHaveCSS('animation-name', 'spin');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await check(spinner).toHaveCSS('animation-name', 'none');

    await settings.getByRole('checkbox', { name: 'Long content', exact: true }).check();
    await settings.getByRole('checkbox', { name: 'Larger text', exact: true }).check();
    await chooseDropdown(settings.getByRole('combobox', { name: 'Example role', exact: true }), 'parent');
    await page.evaluate(() => document.fonts.ready);
    const cover = settings.getByRole('combobox', { name: 'Color theme', exact: true });
    check(await dropdownValues(cover), 'DESIGN_THEMES').toEqual(COVERS);
    await check(settings.getByText('Long content', { exact: true })).toHaveCSS('font-size', '20px');
    const palette = () => page.evaluate(() => ['--color-ink-page', '--color-ink-primary', '--color-control-border', '--color-sheikah-teal-deep']
      .map(token => getComputedStyle(document.documentElement).getPropertyValue(token)).join('|'));
    const renderedPalettes = new Set();
    for (const theme of COVERS) {
      const previousPalette = await palette();
      await chooseDropdown(cover, theme);
      await check(cover).toHaveJSProperty('value', theme);
      if (renderedPalettes.size) await check.poll(palette).not.toBe(previousPalette);
      renderedPalettes.add(await palette());
      check(await page.evaluate(() => document.documentElement.scrollWidth), 'DESIGN_MOBILE').toBeLessThanOrEqual(320);
      for (const name of ['Color theme', 'Activity name', 'Due date example']) {
        const control = page.getByLabel(name, { exact: true });
        await fitsPhone(control);
        check((await control.boundingBox()).height, 'DESIGN_TOUCH_TARGET').toBeGreaterThanOrEqual(44);
        await readable(control, 4.5);
        await readable(control, 3, { property: 'borderTopColor', adjacent: true });
        await control.focus();
        check(await control.evaluate(element => {
          const style = getComputedStyle(element);
          return style.boxShadow !== 'none' || (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2);
        }), 'DESIGN_FOCUS_VISIBLE').toBe(true);
        await readable(control, 3, { focus: true, adjacent: true });
      }
      for (const name of ['Primary action', 'Confirm action', 'Secondary action', 'Destructive action', 'Ghost action']) {
        const button = page.getByRole('button', { name, exact: true });
        await fitsPhone(button);
        await readable(button, 4.5);
      }
    }
    check(renderedPalettes.size, 'DESIGN_THEMES').toBe(COVERS.length);

    const opener = page.getByRole('button', { name: 'Open example form', exact: true });
    await opener.click();
    const dialog = page.getByRole('dialog', { name: 'Edit activity', exact: true });
    await fitsPhone(dialog);
    check(await dialog.evaluate(element => getComputedStyle(element).transform), 'DESIGN_REDUCED_MOTION').toBe('none');
    const name = dialog.getByRole('textbox', { name: 'Activity name', exact: true });
    // The shared dialog initially focuses its first control (Close). Verify
    // containment and keyboard access rather than requiring input autofocus.
    check(await dialog.evaluate(element => element.contains(document.activeElement)), 'DESIGN_DIALOG_FOCUS').toBe(true);
    await dialog.getByRole('button', { name: 'Close', exact: true }).focus();
    await page.keyboard.press('Tab');
    await check(name).toBeFocused();
    await check(name).toHaveCSS('font-size', '22px');
    await dialog.getByRole('button', { name: 'Save example', exact: true }).click();
    await check(name).toHaveAttribute('aria-invalid', 'true');
    await check(dialog.getByRole('alert')).toHaveText('Enter an activity name.');
    await name.fill('Local design check');
    await page.keyboard.press('Escape');
    const confirmation = page.getByRole('alertdialog');
    await check(confirmation).toBeVisible();
    await fitsPhone(confirmation);
    await check(confirmation.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    check(await confirmation.evaluate(element => element.contains(document.activeElement)), 'DESIGN_DIALOG_FOCUS').toBe(true);
    await confirmation.getByRole('button', { name: 'Cancel', exact: true }).click();
    await check(name).toHaveValue('Local design check');
    await dialog.getByRole('button', { name: 'Save example', exact: true }).click();
    await check(dialog).toHaveCount(0);
    await check(opener).toBeFocused();

    const task = page.getByRole('region', { name: 'Task folio', exact: true });
    const taskOpener = task.getByRole('button', { name: 'View Run 2 miles this week', exact: true });
    await taskOpener.focus();
    await page.keyboard.press('Enter');
    const detail = page.getByRole('dialog', { name: 'Run 2 miles this week', exact: true });
    await check(detail).toBeVisible();
    await fitsPhone(detail);
    await check(detail.getByRole('heading', { name: 'What counts', exact: true })).toBeVisible();
    await detail.getByRole('button', { name: 'Unpin', exact: true }).click();
    await check(detail.getByRole('progressbar', { name: 'Run 2 miles this week progress', exact: true })).toHaveAttribute('aria-valuenow', '1.25');
    await page.keyboard.press('Escape');
    await check(detail).toHaveCount(0);
    await check(taskOpener).toBeFocused();

    const attachments = page.getByRole('region', { name: 'Attachments', exact: true });
    const picker = attachments.getByLabel('Example photo', { exact: true });
    await check(picker).toHaveAttribute('accept', 'image/*');
    await check(attachments.getByText('Local image preview only. This example never uploads the file.', { exact: true })).toBeVisible();
    const first = { name: 'local-check-only.png', mimeType: 'image/png', buffer: PIXEL };
    await chooseFile(page, attachments.getByRole('button', { name: 'Choose example photo', exact: true }), first);
    await check(attachments.getByText(first.name, { exact: true })).toBeVisible();
    await check(attachments.getByRole('img', { name: 'Example photo preview', exact: true })).toBeVisible();
    await attachments.getByRole('button', { name: 'Preview upload failure', exact: true }).click();
    await check(attachments.getByRole('alert')).toContainText('selected file is still available');
    await check(picker).toHaveAttribute('aria-invalid', 'true');
    check(await picker.evaluate(element => element.getAttribute('aria-describedby').split(' ').some(id => document.getElementById(id)?.getAttribute('role') === 'alert')), 'DESIGN_ATTACHMENT_ERROR_LABEL').toBe(true);
    await check(attachments.getByText(first.name, { exact: true })).toBeVisible();
    const replacement = { ...first, name: 'local-replacement-only.png' };
    await chooseFile(page, attachments.getByRole('button', { name: 'Replace example photo', exact: true }), replacement);
    await check(attachments.getByText(replacement.name, { exact: true })).toBeVisible();
    await check(attachments.getByText(first.name, { exact: true })).toHaveCount(0);
    await check(attachments.getByRole('alert')).toHaveCount(0);
    await chooseFile(page, attachments.getByRole('button', { name: 'Replace example photo', exact: true }), {
      name: 'local-preview-failure.png', mimeType: 'image/png', buffer: Buffer.from('not an image'),
    });
    await check(attachments.getByText('Preview unavailable. The selected file is still attached.', { exact: true })).toBeVisible();
    await attachments.getByRole('button', { name: 'Remove example photo', exact: true }).click();
    await check(attachments.getByText('No file selected', { exact: true })).toBeVisible();
    await check(attachments.getByRole('button', { name: 'Replace example photo', exact: true })).toHaveCount(0);
    await chooseFile(page, attachments.getByRole('button', { name: 'Choose example photo', exact: true }), first);
    await check(attachments.getByRole('img', { name: 'Example photo preview', exact: true })).toBeVisible();
    await attachments.getByRole('button', { name: 'Remove example photo', exact: true }).click();
    check(await page.evaluate(() => document.documentElement.scrollWidth), 'DESIGN_MOBILE').toBeLessThanOrEqual(320);
    check(Date.now() - started, 'DESIGN_RUNTIME').toBeLessThan(45_000);
    return { designMobile: true, themes: true, controlContrast: true, dialogKeyboard: true, attachments: true, motion: true };
  } finally {
    if (viewport) await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: wasReduced ? 'reduce' : 'no-preference' });
  }
}
