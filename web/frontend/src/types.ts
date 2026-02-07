/**
 * WebSocket message types matching backend.
 */
export enum MessageType {
  // Client -> Server
  USER_MESSAGE = 'user_message',
  APPROVAL_RESPONSE = 'approval_response',
  INTERRUPT = 'interrupt',
  CLEAR_SESSION = 'clear_session',

  // Server -> Client
  ASSISTANT_TEXT = 'assistant_text',
  THINKING = 'thinking',  // Extended thinking block
  TOOL_USE = 'tool_use',
  TOOL_RESULT = 'tool_result',
  APPROVAL_REQUEST = 'approval_request',
  RESULT = 'result',
  ERROR = 'error',
  STATUS = 'status',
  HISTORY = 'history',
}

export interface WSMessage {
  type: MessageType;
  data: Record<string, unknown>;
}

export interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
  status: 'running' | 'completed' | 'error';
  result?: string;
  isError?: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool' | 'system' | 'thinking';
  content: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  toolCalls?: ToolCall[];  // For grouped tool calls
  timestamp: Date;
}

export interface ApprovalRequest {
  toolName: string;
  toolInput: Record<string, unknown>;
}

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';
export type AgentStatus = 'idle' | 'thinking' | 'done' | 'error' | 'interrupted';
