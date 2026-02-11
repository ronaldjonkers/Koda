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
  downloadMediaMessage,
} from '@whiskeysockets/baileys';

import { Boom } from '@hapi/boom';
import qrcode from 'qrcode-terminal';
import pino from 'pino';
import * as fs from 'fs';
import * as path from 'path';

const VERSION = '0.1.0';

// Suppress noisy Baileys session logs - patch all console methods and stdout
const shouldSuppress = (args: any[]): boolean => {
  const str = args.map(a => typeof a === 'string' ? a : JSON.stringify(a)).join(' ');
  return str.includes('Closing session') ||
    str.includes('SessionEntry') ||
    str.includes('_chains') ||
    str.includes('registrationId') ||
    str.includes('currentRatchet') ||
    str.includes('ephemeralKeyPair') ||
    str.includes('chainKey') ||
    str.includes('messageKeys') ||
    str.includes('privKey') ||
    str.includes('pubKey') ||
    str.includes('<Buffer');
};

const originalLog = console.log;
const originalDebug = console.debug;
const originalInfo = console.info;
const originalWarn = console.warn;

console.log = (...args: any[]) => { if (!shouldSuppress(args)) originalLog.apply(console, args); };
console.debug = (...args: any[]) => { if (!shouldSuppress(args)) originalDebug.apply(console, args); };
console.info = (...args: any[]) => { if (!shouldSuppress(args)) originalInfo.apply(console, args); };
console.warn = (...args: any[]) => { if (!shouldSuppress(args)) originalWarn.apply(console, args); };

export interface InboundMessage {
  id: string;
  sender: string;
  content: string;
  timestamp: number;
  isGroup: boolean;
  hasMedia?: boolean;
  mediaType?: string;
  mediaPath?: string;
  mediaFilename?: string;
  mediaMimetype?: string;
}

export interface WhatsAppClientOptions {
  authDir: string;
  onMessage: (msg: InboundMessage) => void;
  onQR: (qr: string) => void;
  onStatus: (status: string) => void;
  downloadDir?: string;
}

export class WhatsAppClient {
  private sock: any = null;
  private options: WhatsAppClientOptions;
  private reconnecting = false;
  private sentMessageIds: Set<string> = new Set(); // Track sent messages to prevent loops
  private downloadDir: string;

  constructor(options: WhatsAppClientOptions) {
    this.options = options;
    this.downloadDir = options.downloadDir || path.join(process.cwd(), 'downloads');
    this.ensureDownloadDir();
  }

  private ensureDownloadDir(): void {
    if (!fs.existsSync(this.downloadDir)) {
      fs.mkdirSync(this.downloadDir, { recursive: true });
    }
  }

  async connect(): Promise<void> {
    // Create a completely silent logger to suppress Baileys internal logs
    const logger = pino({ level: 'silent', enabled: false });
    const { state, saveCreds } = await useMultiFileAuthState(this.options.authDir);
    const { version } = await fetchLatestBaileysVersion();

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
      // Suppress session logging
      getMessage: async () => undefined,
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
        
        // Send presence update (required for receiving messages)
        try {
          await this.sock.sendPresenceUpdate('available');
        } catch (err) {
          // Ignore presence errors
        }
        
        this.options.onStatus('connected');
      }
    });

    // Save credentials on update
    this.sock.ev.on('creds.update', saveCreds);

    // Handle incoming messages
    this.sock.ev.on('messages.upsert', async (upsert: { messages: any[]; type: string }) => {
      const { messages, type } = upsert;
      
      // Only process notify (real-time) and append (history sync)
      if (type !== 'notify' && type !== 'append') {
        return;
      }
      
      // Use jidDecode for robust JID extraction
      const me = jidDecode(this.sock.user?.id)?.user;
      const myJid = me ? `${me}@s.whatsapp.net` : null;
      
      for (const msg of messages) {
        const remoteJid = msg.key?.remoteJid;
        const messageId = msg.key?.id;
        if (!remoteJid) continue;
        
        // Skip messages we sent ourselves (prevents infinite loops)
        if (messageId && this.sentMessageIds.has(messageId)) {
          this.sentMessageIds.delete(messageId); // Clean up
          continue;
        }
        
        // Skip status updates and broadcasts
        if (remoteJid.endsWith('@status') || remoteJid.endsWith('@broadcast')) {
          continue;
        }
        
        const isMe = Boolean(msg.key?.fromMe);
        const isGroup = remoteJid.endsWith('@g.us');
        
        // Use jidDecode for the remote JID too
        const decodedRemote = jidDecode(remoteJid);
        const decodedRemoteJid = decodedRemote?.user ? `${decodedRemote.user}@s.whatsapp.net` : null;
        
        // Check for self-chat: special "me" JID or matching phone number
        const isMessageToSelf = remoteJid === 'me' || (!isGroup && decodedRemoteJid === myJid);
        
        // Skip outgoing messages to others (but allow self-chat)
        if (isMe && !isMessageToSelf) {
          continue;
        }
        
        // Extract content and handle media
        const content = this.extractMessageContent(msg);
        const mediaInfo = await this.extractMediaInfo(msg);
        
        const sender = isMessageToSelf && myJid ? myJid : remoteJid;
        
        this.options.onMessage({
          id: msg.key.id || '',
          sender,
          content: content || mediaInfo.caption || '[Media]',
          timestamp: msg.messageTimestamp as number,
          isGroup,
          hasMedia: mediaInfo.hasMedia,
          mediaType: mediaInfo.mediaType,
          mediaPath: mediaInfo.mediaPath,
          mediaFilename: mediaInfo.filename,
          mediaMimetype: mediaInfo.mimetype,
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
      return message.imageMessage.caption;
    }

    // Video with caption
    if (message.videoMessage?.caption) {
      return message.videoMessage.caption;
    }

    // Document with caption
    if (message.documentMessage?.caption) {
      return message.documentMessage.caption;
    }

    return null;
  }

  private async extractMediaInfo(msg: any): Promise<{
    hasMedia: boolean;
    mediaType?: string;
    caption?: string;
    filename?: string;
    mimetype?: string;
    mediaPath?: string;
  }> {
    const message = msg.message;
    if (!message) return { hasMedia: false };

    let mediaMsg: any = null;
    let mediaType = '';

    // Check for different media types
    if (message.imageMessage) {
      mediaMsg = message.imageMessage;
      mediaType = 'image';
    } else if (message.videoMessage) {
      mediaMsg = message.videoMessage;
      mediaType = 'video';
    } else if (message.documentMessage) {
      mediaMsg = message.documentMessage;
      mediaType = 'document';
    } else if (message.audioMessage) {
      mediaMsg = message.audioMessage;
      mediaType = 'audio';
    } else if (message.stickerMessage) {
      mediaMsg = message.stickerMessage;
      mediaType = 'sticker';
    }

    if (!mediaMsg) return { hasMedia: false };

    try {
      // Download the media
      const buffer = await downloadMediaMessage(
        msg,
        'buffer',
        {},
        {
          logger: pino({ level: 'silent' }),
          reuploadRequest: this.sock.updateMediaMessage,
        }
      );

      if (!buffer) {
        return { hasMedia: true, mediaType, caption: mediaMsg.caption };
      }

      // Generate filename
      const timestamp = Date.now();
      const extension = this.getExtensionFromMimetype(mediaMsg.mimetype, mediaType);
      const filename = mediaMsg.fileName || `${mediaType}_${timestamp}${extension}`;
      const filepath = path.join(this.downloadDir, filename);

      // Save to disk
      fs.writeFileSync(filepath, buffer);

      return {
        hasMedia: true,
        mediaType,
        caption: mediaMsg.caption,
        filename,
        mimetype: mediaMsg.mimetype,
        mediaPath: filepath,
      };
    } catch (error) {
      console.error('Error downloading media:', error);
      return { hasMedia: true, mediaType, caption: mediaMsg.caption };
    }
  }

  private getExtensionFromMimetype(mimetype: string, mediaType: string): string {
    const mimeToExt: { [key: string]: string } = {
      'image/jpeg': '.jpg',
      'image/png': '.png',
      'image/webp': '.webp',
      'image/gif': '.gif',
      'video/mp4': '.mp4',
      'video/ogg': '.ogg',
      'audio/ogg': '.ogg',
      'audio/mp4': '.m4a',
      'audio/mpeg': '.mp3',
      'application/pdf': '.pdf',
      'text/plain': '.txt',
      'application/msword': '.doc',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    };

    if (mimetype && mimeToExt[mimetype]) {
      return mimeToExt[mimetype];
    }

    // Default extensions by media type
    const defaultExt: { [key: string]: string } = {
      image: '.jpg',
      video: '.mp4',
      audio: '.ogg',
      document: '.bin',
      sticker: '.webp',
    };

    return defaultExt[mediaType] || '.bin';
  }

  async sendMessage(to: string, text: string): Promise<void> {
    if (!this.sock) {
      throw new Error('Not connected');
    }

    const result = await this.sock.sendMessage(to, { text });
    
    // Track the message ID to prevent processing it as incoming
    if (result?.key?.id) {
      this.sentMessageIds.add(result.key.id);
      // Clean up old IDs after 60 seconds to prevent memory leak
      setTimeout(() => this.sentMessageIds.delete(result.key.id), 60000);
    }
  }

  async sendTypingIndicator(to: string, isTyping: boolean): Promise<void> {
    if (!this.sock) {
      return;
    }

    try {
      // Send typing state: 'composing' = typing, 'paused' = stopped typing
      const state = isTyping ? 'composing' : 'paused';
      await this.sock.sendPresenceUpdate(state, to);
      
      // If typing, also set online presence
      if (isTyping) {
        await this.sock.sendPresenceUpdate('available');
      }
    } catch (err) {
      // Ignore typing errors - they're not critical
      console.debug('Typing indicator error (non-critical):', err);
    }
  }

  async sendImage(to: string, imageData: Buffer, caption?: string): Promise<void> {
    if (!this.sock) {
      throw new Error('Not connected');
    }

    const result = await this.sock.sendMessage(to, {
      image: imageData,
      caption: caption || undefined,
    });
    
    // Track the message ID to prevent processing it as incoming
    if (result?.key?.id) {
      this.sentMessageIds.add(result.key.id);
      setTimeout(() => this.sentMessageIds.delete(result.key.id), 60000);
    }
  }

  async sendFile(to: string, fileData: Buffer, filename: string, caption?: string): Promise<void> {
    if (!this.sock) {
      throw new Error('Not connected');
    }

    // Determine mimetype from filename
    const mimetype = this.getMimetypeFromFilename(filename);

    const result = await this.sock.sendMessage(to, {
      document: fileData,
      mimetype: mimetype,
      fileName: filename,
      caption: caption || undefined,
    });
    
    // Track the message ID to prevent processing it as incoming
    if (result?.key?.id) {
      this.sentMessageIds.add(result.key.id);
      setTimeout(() => this.sentMessageIds.delete(result.key.id), 60000);
    }
  }

  async sendVideo(to: string, videoData: Buffer, caption?: string): Promise<void> {
    if (!this.sock) {
      throw new Error('Not connected');
    }

    const result = await this.sock.sendMessage(to, {
      video: videoData,
      caption: caption || undefined,
    });
    
    // Track the message ID to prevent processing it as incoming
    if (result?.key?.id) {
      this.sentMessageIds.add(result.key.id);
      setTimeout(() => this.sentMessageIds.delete(result.key.id), 60000);
    }
  }

  private getMimetypeFromFilename(filename: string): string {
    const extToMime: { [key: string]: string } = {
      '.jpg': 'image/jpeg',
      '.jpeg': 'image/jpeg',
      '.png': 'image/png',
      '.gif': 'image/gif',
      '.webp': 'image/webp',
      '.pdf': 'application/pdf',
      '.doc': 'application/msword',
      '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      '.txt': 'text/plain',
      '.mp4': 'video/mp4',
      '.mp3': 'audio/mpeg',
      '.ogg': 'audio/ogg',
      '.m4a': 'audio/mp4',
    };

    const ext = path.extname(filename).toLowerCase();
    return extToMime[ext] || 'application/octet-stream';
  }

  async disconnect(): Promise<void> {
    if (this.sock) {
      this.sock.end(undefined);
      this.sock = null;
    }
  }
}
