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
  jidDecode,
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
        
        // Log sock.user to see exact format
        console.log('🔍 sock.user object:', JSON.stringify(this.sock.user, null, 2));
        console.log('🔍 sock.user.id raw:', this.sock.user?.id);
        
        // CRITICAL: Send presence update like OpenClaw does
        // This may be required for receiving messages
        try {
          await this.sock.sendPresenceUpdate('available');
          console.log('📡 Sent presence update: available');
        } catch (err) {
          console.error('Failed to send presence update:', err);
        }
        
        this.options.onStatus('connected');
      }
    });

    // Save credentials on update
    this.sock.ev.on('creds.update', saveCreds);

    // Handle incoming messages - using jidDecode for robust self-message detection
    this.sock.ev.on('messages.upsert', async (upsert: { messages: any[]; type: string }) => {
      const { messages, type } = upsert;
      
      // LOG EVERYTHING to diagnose
      console.log(`\n🔔 messages.upsert EVENT FIRED!`);
      console.log(`   Type: ${type}`);
      console.log(`   Message count: ${messages?.length || 0}`);
      console.log(`   Raw upsert:`, JSON.stringify(upsert, null, 2).substring(0, 1500));
      
      // Accept ALL types for now to debug - don't filter yet
      // if (type !== 'notify' && type !== 'append') {
      //   console.log(`   ↳ Skipping: type "${type}" not notify/append`);
      //   return;
      // }
      
      // Use jidDecode for robust JID extraction
      const me = jidDecode(this.sock.user?.id)?.user;
      const myJid = me ? `${me}@s.whatsapp.net` : null;
      console.log(`   My decoded JID: ${myJid} (from sock.user.id: ${this.sock.user?.id})`);
      
      for (const msg of messages) {
        const remoteJid = msg.key?.remoteJid;
        if (!remoteJid) {
          console.log(`   ↳ Message has no remoteJid, skipping`);
          continue;
        }
        
        // Skip status updates and broadcasts
        if (remoteJid.endsWith('@status') || remoteJid.endsWith('@broadcast')) {
          console.log(`   ↳ Skipping status/broadcast: ${remoteJid}`);
          continue;
        }
        
        const isMe = Boolean(msg.key?.fromMe);
        const isGroup = remoteJid.endsWith('@g.us');
        
        // Use jidDecode for the remote JID too
        const decodedRemote = jidDecode(remoteJid);
        const decodedRemoteJid = decodedRemote?.user ? `${decodedRemote.user}@s.whatsapp.net` : null;
        
        // Check for BOTH: the special "me" JID AND matching phone number
        const isMessageToSelf = remoteJid === 'me' || (!isGroup && decodedRemoteJid === myJid);
        
        const content = this.extractMessageContent(msg);
        
        // Log EVERY message - including outgoing - for debugging
        console.log(`📨 Message details:`);
        console.log(`   remoteJid: ${remoteJid}`);
        console.log(`   decodedRemoteJid: ${decodedRemoteJid}`);
        console.log(`   myJid: ${myJid}`);
        console.log(`   fromMe: ${isMe}`);
        console.log(`   isGroup: ${isGroup}`);
        console.log(`   isMessageToSelf: ${isMessageToSelf}`);
        console.log(`   type: ${type}`);
        console.log(`   content: ${content ? `"${content.substring(0, 50)}..."` : '(none)'}`);
        
        // For now, DON'T skip outgoing messages - log them all
        if (isMe && !isMessageToSelf) {
          console.log(`   ⚠️ This is an OUTGOING message to someone else (would normally skip)`);
          // continue; // Commented out for debugging
        }
        
        if (!content) {
          console.log(`   ↳ No text content to process`);
          continue;
        }
        
        const sender = isMessageToSelf && myJid ? myJid : remoteJid;
        
        console.log(`✅ Processing: from=${sender}`);
        
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
