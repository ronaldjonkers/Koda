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
        this.options.onStatus('connected');
      }
    });

    // Save credentials on update
    this.sock.ev.on('creds.update', saveCreds);

    // DEBUG: Log ALL events to diagnose self-message issue
    const eventsToMonitor = [
      'messages.upsert',
      'messages.update', 
      'messages.delete',
      'message-receipt.update',
      'messages.reaction',
      'presence.update',
      'chats.update',
      'chats.upsert',
      'contacts.update',
      'contacts.upsert',
    ];
    
    for (const eventName of eventsToMonitor) {
      if (eventName !== 'messages.upsert') { // we handle this separately
        this.sock.ev.on(eventName, (data: any) => {
          console.log(`\n🔔 EVENT: ${eventName}`);
          console.log(`Data: ${JSON.stringify(data, null, 2).substring(0, 500)}`);
        });
      }
    }

    // Handle incoming messages - following OpenClaw's pattern exactly
    this.sock.ev.on('messages.upsert', async (upsert: { messages: any[]; type: string }) => {
      const { messages, type } = upsert;
      
      console.log(`\n📨 ===== NEW MESSAGE EVENT =====`);
      console.log(`Type: ${type}, Count: ${messages.length}`);
      
      // OpenClaw pattern: Only process "notify" (real-time) and "append" (history sync) events
      // Skip other types like "prepend" which are not real messages
      if (type !== 'notify' && type !== 'append') {
        console.log(`Skipping: type "${type}" is not notify/append`);
        console.log(`===== END MESSAGE EVENT =====\n`);
        return;
      }
      
      // Get my own phone number for self-message detection
      // JID format can be: "31614254251:123@s.whatsapp.net" (with device) or "31614254251@s.whatsapp.net"
      const myJid = this.sock.user?.id;
      const myPhone = myJid ? myJid.split('@')[0].split(':')[0] : null;
      console.log(`My JID: ${myJid}`);
      console.log(`My Phone (extracted): ${myPhone}`);
      
      if (!myPhone) {
        console.log(`WARNING: Could not extract my phone number from JID`);
      }
      
      for (const msg of messages) {
        console.log(`\n--- Message ${msg.key?.id || 'unknown'} ---`);
        console.log(`Full key:`, JSON.stringify(msg.key));
        
        const remoteJid = msg.key?.remoteJid;
        if (!remoteJid) {
          console.log(`Skipping: no remoteJid`);
          continue;
        }
        
        console.log(`remoteJid: ${remoteJid}`);
        console.log(`fromMe: ${msg.key.fromMe}`);
        console.log(`participant: ${msg.key.participant || 'none'}`);
        
        // Skip status updates and broadcasts
        if (remoteJid.endsWith('@status') || remoteJid.endsWith('@broadcast')) {
          console.log(`Skipping: status/broadcast`);
          continue;
        }
        
        // Extract phone from remoteJid (also handle device suffix like "123:456@s.whatsapp.net")
        const senderPhone = remoteJid.split('@')[0].split(':')[0];
        const isGroup = remoteJid.endsWith('@g.us');
        
        // Check if this is a self-chat (messaging yourself)
        // In WhatsApp, when you message yourself:
        // - remoteJid = your own phone number (e.g., "31614254251@s.whatsapp.net")
        // - fromMe can be true OR false depending on the message
        const isSelfChat = !isGroup && myPhone && senderPhone === myPhone;
        
        console.log(`senderPhone: ${senderPhone}, myPhone: ${myPhone}`);
        console.log(`Is self-chat: ${isSelfChat}, isGroup: ${isGroup}, fromMe: ${msg.key.fromMe}`);
        
        // OpenClaw pattern: Skip outbound DMs (fromMe=true) UNLESS it's a self-chat
        // This ensures we only process:
        // 1. Messages FROM others (fromMe=false) 
        // 2. Messages in self-chat (isSelfChat=true, regardless of fromMe)
        if (msg.key.fromMe && !isSelfChat) {
          console.log(`Skipping: outbound message to others (fromMe=true, not self-chat)`);
          continue;
        }
        
        const content = this.extractMessageContent(msg);
        if (!content) {
          console.log(`Skipping: no extractable content`);
          console.log(`Message object:`, JSON.stringify(msg.message || {}, null, 2).substring(0, 500));
          continue;
        }
        
        console.log(`Content: "${content.substring(0, 100)}${content.length > 100 ? '...' : ''}"`);
        
        // Determine the sender for the message
        // For self-chat, use the phone number directly
        let finalSender = remoteJid;
        if (isSelfChat && myPhone) {
          finalSender = `${myPhone}@s.whatsapp.net`;
          console.log(`🔄 Self-chat message detected! Using sender: ${finalSender}`);
        }
        
        console.log(`✅ Forwarding to Python bridge: ${finalSender}`);
        
        this.options.onMessage({
          id: msg.key.id || '',
          sender: finalSender,
          content,
          timestamp: msg.messageTimestamp as number,
          isGroup,
        });
      }
      console.log(`===== END MESSAGE EVENT =====\n`);
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
