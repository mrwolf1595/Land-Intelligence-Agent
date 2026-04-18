/**
 * Patches whatsapp-web.js Client.inject() to retry on
 * "Execution context was destroyed" — a race condition where
 * WhatsApp Web navigates during initialization.
 *
 * Run automatically via postinstall (package.json).
 */
const fs = require('fs');
const path = require('path');

const clientPath = path.join(
    __dirname, '..', 'node_modules', 'whatsapp-web.js', 'src', 'Client.js'
);

if (!fs.existsSync(clientPath)) {
    console.log('[patch-whatsapp] Client.js not found — skipping');
    process.exit(0);
}

let code = fs.readFileSync(clientPath, 'utf8');

const OLD = `        if (isCometOrAbove) {
            await this.pupPage.evaluate(ExposeAuthStore);
        } else {
            await this.pupPage.evaluate(ExposeLegacyAuthStore, moduleRaid.toString());
        }`;

const NEW = `        const _evalWithRetry = async (fn, ...args) => {
            for (let i = 3; i--;) {
                try { return await this.pupPage.evaluate(fn, ...args); }
                catch (e) {
                    if (!i || !String(e).includes('context was destroyed')) throw e;
                    await new Promise(r => setTimeout(r, 1500));
                }
            }
        };
        if (isCometOrAbove) {
            await _evalWithRetry(ExposeAuthStore);
        } else {
            await _evalWithRetry(ExposeLegacyAuthStore, moduleRaid.toString());
        }`;

if (code.includes('_evalWithRetry')) {
    console.log('[patch-whatsapp] Already patched — skipping');
    process.exit(0);
}

if (!code.includes(OLD)) {
    console.log('[patch-whatsapp] Pattern not found — whatsapp-web.js may have been updated');
    process.exit(0);
}

fs.writeFileSync(clientPath, code.replace(OLD, NEW), 'utf8');
console.log('[patch-whatsapp] ✅ Client.inject retry patch applied');
