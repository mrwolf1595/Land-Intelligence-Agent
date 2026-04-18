/**
 * WhatsApp Web JS Bridge
 * - Connects to WhatsApp Web (free)
 * - Monitors specified groups
 * - Forwards new messages to Python pipeline via HTTP
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const axios = require('axios');
const fs = require('fs');

require('dotenv').config();

const PYTHON_BRIDGE_PORT = process.env.PYTHON_BRIDGE_PORT || 3002;
const PYTHON_BRIDGE_URL = process.env.PYTHON_BRIDGE_URL || `http://localhost:${PYTHON_BRIDGE_PORT}/message`;
const WA_BRIDGE_PORT = process.env.WA_BRIDGE_PORT || 3001;
const MONITORED_GROUPS = (process.env.WA_MONITORED_GROUPS || '').split(',').map(g => g.trim());
const BROKER_NUMBER = process.env.BROKER_WHATSAPP || '';

const app = express();
app.use(express.json());

let waClient = null;

function initializeWhatsApp() {
    console.log('🔄 Initializing WhatsApp Client...');
    
    // On Linux: use system Chromium to avoid bundled-browser issues.
    // Falls back gracefully if not found (Windows / Mac).
    const LINUX_CHROME_PATHS = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
    ];
    const { execSync } = require('child_process');
    let executablePath;
    for (const p of LINUX_CHROME_PATHS) {
        try { execSync(`test -x ${p}`); executablePath = p; break; } catch {}
    }

    try {
        const puppeteerConfig = {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',   // critical on Linux: prevents /dev/shm OOM crash
                '--disable-gpu',
                '--disable-extensions',
                '--disable-background-networking',
                '--no-first-run',
                '--no-zygote',
            ],
        };
        if (executablePath) {
            puppeteerConfig.executablePath = executablePath;
            console.log(`🌐 Using system Chromium: ${executablePath}`);
        }

        const client = new Client({
            authStrategy: new LocalAuth({ dataPath: '.wwebjs_auth' }),
            puppeteer: puppeteerConfig,
        });

    client.on('qr', (qr) => {
        console.log('\n📱 Scan this QR code with your WhatsApp:');
        qrcode.generate(qr, { small: true });
    });

    client.on('ready', () => {
        console.log('✅ WhatsApp connected successfully');
        waClient = client;
    });

    client.on('auth_failure', () => {
        console.error('❌ WhatsApp auth failed — cleaning auth data and restarting...');
        try {
            fs.rmSync('.wwebjs_auth', { recursive: true, force: true });
        } catch (err) {}
        setTimeout(initializeWhatsApp, 3000); // Reconnect loop
    });

    client.on('disconnected', (reason) => {
        console.log('⚠️ WhatsApp disconnected. Reason:', reason);
        waClient = null;
        client.destroy();
        setTimeout(initializeWhatsApp, 5000);
    });

    client.on('message', async (msg) => {
        try {
            // Only group messages
            if (!msg.from.endsWith('@g.us')) return;

            const chat = await msg.getChat();
            const groupName = chat.name;

            // Target groups only
            if (!MONITORED_GROUPS.some(g => groupName.includes(g))) return;

            if (msg.fromMe) return;

            const contact = await msg.getContact();
            const senderPhone = contact.number || 'unknown';
            const senderName = contact.pushname || contact.name || senderPhone;

            const payload = {
                message_id: msg.id._serialized,
                group_name: groupName,
                sender_phone: senderPhone,    
                sender_name: senderName,
                raw_text: msg.body,
                timestamp: new Date(msg.timestamp * 1000).toISOString(),
                has_media: msg.hasMedia,
            };

            console.log(`[${groupName}] ${senderName}: ${msg.body.slice(0, 80)}...`);

            // Retry up to 3 times with 2-second backoff so transient bridge
            // startup delays (bridge isn't ready yet) don't lose messages.
            let sent = false;
            for (let attempt = 1; attempt <= 3; attempt++) {
                try {
                    await axios.post(PYTHON_BRIDGE_URL, payload, { timeout: 15000 });
                    sent = true;
                    break;
                } catch (retryErr) {
                    if (attempt < 3) {
                        await new Promise(r => setTimeout(r, 2000 * attempt));
                    } else {
                        throw retryErr;
                    }
                }
            }

        } catch (e) {
            console.error('Message processing error:', e.message);
        }
    });

        client.initialize();
    } catch (e) {
        console.error('❌ WhatsApp client error:', e.message);
        console.log('ℹ️ Deferring WhatsApp connection. Manual session activation required.');
    }
}

// HTTP API: Python -> WhatsApp
app.post('/send', async (req, res) => {
    const { to, message } = req.body;
    if (!waClient) return res.status(503).json({ error: 'WhatsApp not ready' });
    
    try {
        const chatId = to.replace(/\D/g, '') + '@c.us';
        await waClient.sendMessage(chatId, message);
        res.json({ success: true });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.get('/status', (req, res) => {
    res.json({ connected: !!waClient, groups: MONITORED_GROUPS });
});

app.listen(WA_BRIDGE_PORT, () => console.log(`🌉 WhatsApp Node bridge API running on port ${WA_BRIDGE_PORT}`));

initializeWhatsApp();
