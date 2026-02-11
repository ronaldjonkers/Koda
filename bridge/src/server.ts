/**
 * WebSocket server for Python-Node.js bridge communication.
 */

import { WebSocketServer, WebSocket } from 'ws';
import { WhatsAppClient, InboundMessage } from './whatsapp.js';
import * as fs from 'fs';
import * as path from 'path';

interface SendCommand {
  type: 'send';
  to: string;
  text: string;
}

interface TypingCommand {
  type: 'typing';
  to: string;
  isTyping: boolean;
}

interface ImageCommand {
  type: 'image';
  to: string;
  imageData: string; // base64 encoded
  caption?: string;
}

interface FileCommand {
  type: 'file';
  to: string;
  fileData: string; // base64 encoded
  filename: string;
  caption?: string;
}

interface VideoCommand {
  type: 'video';
  to: string;
  videoData: string; // base64 encoded
  caption?: string;
}

interface BridgeMessage {
  type: 'message' | 'status' | 'qr' | 'error' | 'file';
  [key: string]: unknown;
}

interface FileMessage extends BridgeMessage {
  type: 'file';
  id: string;
  sender: string;
  content: string;
  timestamp: number;
  isGroup: boolean;
  hasMedia: boolean;
  mediaType?: string;
  mediaPath?: string;
  mediaFilename?: string;
  mediaMimetype?: string;
}

export class BridgeServer {
  private wss: WebSocketServer | null = null;
  private wa: WhatsAppClient | null = null;
  private clients: Set<WebSocket> = new Set();
  private downloadDir: string;

  constructor(private port: number, private authDir: string) {
    this.downloadDir = path.join(process.cwd(), 'downloads');
  }

  async start(): Promise<void> {
    // Create WebSocket server
    this.wss = new WebSocketServer({ port: this.port });
    console.log(`🌉 Bridge server listening on ws://localhost:${this.port}`);

    // Initialize WhatsApp client with download support
    this.wa = new WhatsAppClient({
      authDir: this.authDir,
      downloadDir: this.downloadDir,
      onMessage: (msg) => this.handleIncomingMessage(msg),
      onQR: (qr) => this.broadcast({ type: 'qr', qr }),
      onStatus: (status) => this.broadcast({ type: 'status', status }),
    });

    // Handle WebSocket connections
    this.wss.on('connection', (ws) => {
      console.log('🔗 Python client connected');
      this.clients.add(ws);

      ws.on('message', async (data) => {
        try {
          const cmd = JSON.parse(data.toString()) as SendCommand | TypingCommand | ImageCommand | FileCommand | VideoCommand;
          await this.handleCommand(cmd);
          ws.send(JSON.stringify({ type: 'sent', success: true }));
        } catch (error) {
          console.error('Error handling command:', error);
          ws.send(JSON.stringify({ type: 'error', error: String(error) }));
        }
      });

      ws.on('close', () => {
        console.log('🔌 Python client disconnected');
        this.clients.delete(ws);
      });

      ws.on('error', (error) => {
        console.error('WebSocket error:', error);
        this.clients.delete(ws);
      });
    });

    // Connect to WhatsApp
    await this.wa.connect();
  }

  private handleIncomingMessage(msg: InboundMessage): void {
    // If message has media, read the file and send as base64
    if (msg.hasMedia && msg.mediaPath) {
      try {
        const fileData = fs.readFileSync(msg.mediaPath);
        const base64Data = fileData.toString('base64');
        
        const fileMsg: FileMessage = {
          type: 'file',
          id: msg.id,
          sender: msg.sender,
          content: msg.content,
          timestamp: msg.timestamp,
          isGroup: msg.isGroup,
          hasMedia: true,
          mediaType: msg.mediaType,
          mediaData: base64Data,
          mediaFilename: msg.mediaFilename,
          mediaMimetype: msg.mediaMimetype,
          mediaPath: msg.mediaPath,
        };
        
        this.broadcast(fileMsg);
        return;
      } catch (error) {
        console.error('Error reading media file:', error);
        // Fall through to regular message
      }
    }
    
    // Regular text message
    this.broadcast({
      type: 'message',
      ...msg
    });
  }

  private async handleCommand(cmd: SendCommand | TypingCommand | ImageCommand | FileCommand | VideoCommand): Promise<void> {
    if (!this.wa) return;
    
    if (cmd.type === 'send') {
      await this.wa.sendMessage(cmd.to, cmd.text);
    } else if (cmd.type === 'typing') {
      await this.wa.sendTypingIndicator(cmd.to, cmd.isTyping);
    } else if (cmd.type === 'image') {
      const imageBuffer = Buffer.from(cmd.imageData, 'base64');
      await this.wa.sendImage(cmd.to, imageBuffer, cmd.caption);
    } else if (cmd.type === 'file') {
      const fileBuffer = Buffer.from(cmd.fileData, 'base64');
      await this.wa.sendFile(cmd.to, fileBuffer, cmd.filename, cmd.caption);
    } else if (cmd.type === 'video') {
      const videoBuffer = Buffer.from(cmd.videoData, 'base64');
      await this.wa.sendVideo(cmd.to, videoBuffer, cmd.caption);
    }
  }

  private broadcast(msg: BridgeMessage | FileMessage): void {
    const data = JSON.stringify(msg);
    for (const client of this.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    }
  }

  async stop(): Promise<void> {
    // Close all client connections
    for (const client of this.clients) {
      client.close();
    }
    this.clients.clear();

    // Close WebSocket server
    if (this.wss) {
      this.wss.close();
      this.wss = null;
    }

    // Disconnect WhatsApp
    if (this.wa) {
      await this.wa.disconnect();
      this.wa = null;
    }
  }
}
