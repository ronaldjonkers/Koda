/**
 * WhatsApp client wrapper using Baileys.
 * Based on OpenClaw's working implementation.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} from '@whiskeysockets/baileys';

import { Boom } from '@hapi/boom';
import qrcode from 'qrcode-terminal';
import pino from 'pino';

const VERSION = '0.1.0';

export interface InboundMessage {
  id: string;
  sender: string;
  content: string;
  timestamp: number;
  isGroup: boolean;
}

export interface WhatsAppClientOptions {
  authDir: string;
  onMessage: (msg: InboundMessage) => void;
  onQR: (qr: string) => void;
  onStatus: (status: string) => void;
}

export class WhatsAppClient {
  private sock: any = null;
  private options: WhatsAppClientOptions;
  private reconnecting = false;

  constructor(options: WhatsAppClientOptions) {
    this.options = options;
  }

  async connect(): Promise<void> {
    const logger = pino({ level: 'silent' });
    const { state, saveCreds } = await useMultiFileAuthState(this.options.authDir);
    const { version } = await fetchLatestBaileysVersion();

    console.log(`Using Baileys version: ${version.join('.')}`);

    // Create socket following OpenClaw's pattern
    this.sock = makeWASocket({
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      version,
      logger,
      printQRInTerminal: false,
      browser: ['koda', 'cli', VERSION],
      syncFullHistory: false,
      markOnlineOnConnect: false,
    });

    // Handle WebSocket errors
    if (this.sock.ws && typeof this.sock.ws.on === 'function') {
      this.sock.ws.on('error', (err: Error) => {
        console.error('WebSocket error:', err.message);
      });
    }

    // Handle connection updates
    this.sock.ev.on('connection.update', async (update: any) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        // Display QR code in terminal
        console.log('\n📱 Scan this QR code with WhatsApp (Linked Devices):\n');
        qrcode.generate(qr, { small: true });
        this.options.onQR(qr);
      }

      if (connection === 'close') {
        const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

        console.log(`Connection closed. Status: ${statusCode}, Will reconnect: ${shouldReconnect}`);
        this.options.onStatus('disconnected');

        if (shouldReconnect && !this.reconnecting) {
          this.reconnecting = true;
          console.log('Reconnecting in 5 seconds...');
          setTimeout(() => {
            this.reconnecting = false;
            this.connect();
          }, 5000);
        }
      } else if (connection === 'open') {
        console.log('✅ Connected to WhatsApp');
        
        // CRITICAL: Send presence update like OpenClaw does
        // This may be required for receiving messages
        try {
          await this.sock.sendPresenceUpdate('available');
          console.log('� Sent presence update: available');
        } catch (err) {
          console.error('Failed to send presence update:', err);
        }
        
        this.options.onStatus('connected');
      }
    });

    // Save credentials on update
    this.sock.ev.on('creds.update', saveCreds);

    // Handle incoming messages - using exact Baileys pattern for self-messages
    this.sock.ev.on('messages.upsert', async (upsert: { messages: any[]; type: string }) => {
      const { messages, type } = upsert;
      
      // CRITICAL: Type 'append' is often used for self-messages
      // WhatsApp treats self-messages as sync actions, not regular incoming messages
      if (type !== 'notify' && type !== 'append') {
        return;
      }
      
      for (const msg of messages) {
        const jid = msg.key?.remoteJid;
        if (!jid) continue;
        
        // Skip status updates and broadcasts
        if (jid.endsWith('@status') || jid.endsWith('@broadcast')) {
          continue;
        }
        
        const isMe = Boolean(msg.key?.fromMe);
        const isGroup = jid.endsWith('@g.us');
        
        // Determine if this is the 'Message Yourself' chat
        // In this chat, the JID equals your own number
        // sock.user.id format: "31614254251:123@s.whatsapp.net" -> extract "31614254251"
        const myNumber = this.sock.user?.id?.split(':')[0];
        const myJid = myNumber ? `${myNumber}@s.whatsapp.net` : null;
        const isMessageToSelf = !isGroup && jid === myJid;
        
        // Log for debugging
        console.log(`📨 Message: jid=${jid}, myJid=${myJid}, fromMe=${isMe}, isMessageToSelf=${isMessageToSelf}, type=${type}`);
        
        if (isMe && !isMessageToSelf) {
          // This is a message YOU sent to SOMEONE ELSE
          // Skip to prevent loops
          console.log(`   ↳ Skipping: outbound message to others`);
          continue;
        }
        
        // If we get here, it's either:
        // - A message FROM someone else (isMe=false)
        // - A message you sent TO YOURSELF (isMe=true && isMessageToSelf=true)
        
        const content = this.extractMessageContent(msg);
        if (!content) {
          console.log(`   ↳ Skipping: no text content`);
          continue;
        }
        
        const sender = isMessageToSelf && myJid ? myJid : jid;
        
        console.log(`✅ Processing: from=${sender}, content="${content.substring(0, 50)}${content.length > 50 ? '...' : ''}"`);
        
        this.options.onMessage({
          id: msg.key.id || '',
          sender,
          content,
          timestamp: msg.messageTimestamp as number,
          isGroup,
        });
      }
    });
  }

  private extractMessageContent(msg: any): string | null {
    const message = msg.message;
    if (!message) return null;

    // Text message
    if (message.conversation) {
      return message.conversation;
    }

    // Extended text (reply, link preview)
    if (message.extendedTextMessage?.text) {
      return message.extendedTextMessage.text;
    }

    // Image with caption
    if (message.imageMessage?.caption) {
      return `[Image] ${message.imageMessage.caption}`;
    }

    // Video with caption
    if (message.videoMessage?.caption) {
      return `[Video] ${message.videoMessage.caption}`;
    }

    // Document with caption
    if (message.documentMessage?.caption) {
      return `[Document] ${message.documentMessage.caption}`;
    }

    // Voice/Audio message
    if (message.audioMessage) {
      return `[Voice Message]`;
    }

    return null;
  }

  async sendMessage(to: string, text: string): Promise<void> {
    if (!this.sock) {
      throw new Error('Not connected');
    }

    await this.sock.sendMessage(to, { text });
  }

  async disconnect(): Promise<void> {
    if (this.sock) {
      this.sock.end(undefined);
      this.sock = null;
    }
  }
}
