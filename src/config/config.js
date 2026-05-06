import { localizeDocument } from '../vendor/i18n.mjs';

localizeDocument();

const params = new URLSearchParams(location.search);
const storageId = params.get('storageId');

const OPTIONS = [
  { id: 'show-hidden',     key: `vfs-toolkit-local-show-hidden-${storageId}` },
  { id: 'follow-symlinks', key: `vfs-toolkit-local-follow-symlinks-${storageId}` },
];

const savedNotice = document.getElementById('saved-notice');
let hideTimer;

const defaults = Object.fromEntries(OPTIONS.map(o => [o.key, false]));
const stored = await browser.storage.local.get(defaults);

for (const { id, key } of OPTIONS) {
  const checkbox = document.getElementById(id);
  checkbox.checked = stored[key];
  checkbox.addEventListener('change', async () => {
    await browser.storage.local.set({ [key]: checkbox.checked });
    savedNotice.classList.add('visible');
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => savedNotice.classList.remove('visible'), 1500);
  });
}
