import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageType, WSMessage, ConnectionStatus, AgentStatus, ApprovalRequest } from '../types';

const SESSION_ID_KEY = 'claude_agent_session_id';

interface UseWebSocketOptions {
  onMessage?: (message: WSMessage) => void;
  onApprovalRequest?: (request: ApprovalRequest) => void;
  onHistory?: (messages: WSMessage[]) => void;
  onSessionCleared?: () => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [agentStatus, setAgentStatus] = useState<AgentStatus>('idle');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnectionStatus('connecting');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // 从 localStorage 获取 session_id
    const savedSessionId = localStorage.getItem(SESSION_ID_KEY);
    const wsUrl = savedSessionId
      ? `${protocol}//${window.location.host}/ws?session_id=${savedSessionId}`
      : `${protocol}//${window.location.host}/ws`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus('connected');
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onclose = () => {
      setConnectionStatus('disconnected');
      setAgentStatus('idle');
      // Auto reconnect after 3 seconds
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = () => {
      setConnectionStatus('error');
    };

    ws.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data);
        handleMessage(message);
      } catch (e) {
        console.error('Failed to parse message:', e);
      }
    };
  }, []);

  const handleMessage = useCallback((message: WSMessage) => {
    const { type, data } = message;

    switch (type) {
      case MessageType.STATUS:
        if (data.session_id) {
          const newSessionId = data.session_id as string;
          setSessionId(newSessionId);
          // 保存到 localStorage
          localStorage.setItem(SESSION_ID_KEY, newSessionId);
        }
        if (data.status === 'session_cleared') {
          options.onSessionCleared?.();
        } else if (data.status === 'thinking') {
          setAgentStatus('thinking');
        } else if (data.status === 'done') {
          setAgentStatus('done');
          setTimeout(() => setAgentStatus('idle'), 500);
        } else if (data.status === 'error') {
          setAgentStatus('error');
        } else if (data.status === 'interrupted') {
          setAgentStatus('interrupted');
          setTimeout(() => setAgentStatus('idle'), 500);
        }
        break;

      case MessageType.HISTORY:
        options.onHistory?.(data.messages as WSMessage[]);
        break;

      case MessageType.APPROVAL_REQUEST:
        options.onApprovalRequest?.({
          toolName: data.tool_name as string,
          toolInput: data.tool_input as Record<string, unknown>,
        });
        break;

      default:
        options.onMessage?.(message);
    }
  }, [options]);

  const sendMessage = useCallback((type: MessageType, data: Record<string, unknown> = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, data }));
    }
  }, []);

  const sendUserMessage = useCallback((content: string, filePaths?: string[]) => {
    sendMessage(MessageType.USER_MESSAGE, { content, file_paths: filePaths });
  }, [sendMessage]);

  const sendApprovalResponse = useCallback((approved: boolean, reason?: string) => {
    sendMessage(MessageType.APPROVAL_RESPONSE, { approved, reason });
  }, [sendMessage]);

  const interrupt = useCallback(() => {
    sendMessage(MessageType.INTERRUPT);
  }, [sendMessage]);

  const clearSession = useCallback(() => {
    sendMessage(MessageType.CLEAR_SESSION);
  }, [sendMessage]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    wsRef.current?.close();
  }, []);

  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    connectionStatus,
    agentStatus,
    sessionId,
    sendUserMessage,
    sendApprovalResponse,
    interrupt,
    clearSession,
    reconnect: connect,
  };
}
