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

    // Handle incoming messages - PROCESS ALL EVENTS
    this.sock.ev.on('messages.upsert', async ({ messages, type }: { messages: any[]; type: string }) => {
      console.log(`\n📨 ===== NEW MESSAGE EVENT =====`);
      console.log(`Type: ${type}, Count: ${messages.length}`);
      
      // Get my own phone number for self-message detection
      const myJid = this.sock.user?.id;
      const myPhone = myJid ? myJid.split('@')[0] : null;
      console.log(`My JID: ${myJid}`);
      console.log(`My Phone: ${myPhone}`);
      
      for (const msg of messages) {
        console.log(`\n--- Message ${msg.key.id} ---`);
        console.log(`remoteJid: ${msg.key.remoteJid}`);
        console.log(`fromMe: ${msg.key.fromMe}`);
        console.log(`participant: ${msg.key.participant || 'none'}`);
        
        const sender = msg.key.remoteJid || 'unknown';
        const senderPhone = sender.split('@')[0];
        
        // Skip status updates
        if (sender === 'status@broadcast') {
          console.log(`Skipping: status broadcast`);
          continue;
        }
        
        // CRITICAL FIX: Check for self-messages
        // Self-messages can appear in multiple ways:
        // 1. fromMe=true and remoteJid is your own number (Yourself chat)
        // 2. fromMe=true in a personal chat
        const isSelfMessage = (
          msg.key.fromMe && 
          (senderPhone === myPhone || sender === myJid)
        );
        
        console.log(`senderPhone: ${senderPhone}, myPhone: ${myPhone}`);
        console.log(`Is self-message: ${isSelfMessage}`);
        
        const content = this.extractMessageContent(msg);
        if (!content) {
          console.log(`Skipping: no content`);
          continue;
        }
        
        console.log(`Content: "${content.substring(0, 100)}..."`);
        
        const isGroup = sender.endsWith('@g.us');
        
        // ALWAYS forward messages - let Python decide what to do
        // For self-messages, use the phone number directly
        let finalSender = sender;
        if (isSelfMessage && myPhone) {
          finalSender = `${myPhone}@s.whatsapp.net`;
          console.log(`🔄 Self-message detected! Using sender: ${finalSender}`);
        }
        
        console.log(`✅ Forwarding to Python: ${finalSender}`);
        
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
