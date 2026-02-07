import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { ChatMessage } from './components/ChatMessage';
import { ChatInput } from './components/ChatInput';
import { ApprovalModal } from './components/ApprovalModal';
import { StatusIndicator } from './components/StatusIndicator';
import { MessageType, ChatMessage as ChatMessageType, ApprovalRequest, WSMessage, ToolCall } from './types';
import { Trash2 } from 'lucide-react';

function App() {
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [pendingApproval, setPendingApproval] = useState<ApprovalRequest | null>(null);
  const [currentAssistantMessage, setCurrentAssistantMessage] = useState<string>('');
  const [currentToolCalls, setCurrentToolCalls] = useState<ToolCall[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Helper to flush accumulated assistant message
  const flushAssistantMessage = useCallback(() => {
    setCurrentAssistantMessage((prev) => {
      if (prev.trim()) {
        setMessages((msgs) => [
          ...msgs,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: prev,
            timestamp: new Date(),
          },
        ]);
      }
      return '';
    });
  }, []);

  // Helper to flush tool calls
  const flushToolCalls = useCallback(() => {
    setCurrentToolCalls((prev) => {
      if (prev.length > 0) {
        setMessages((msgs) => [
          ...msgs,
          {
            id: crypto.randomUUID(),
            role: 'tool',
            content: '',
            toolCalls: prev,
            timestamp: new Date(),
          },
        ]);
      }
      return [];
    });
  }, []);

  // Handle history messages from server
  const handleHistory = useCallback((historyMessages: WSMessage[]) => {
    const restoredMessages: ChatMessageType[] = [];

    for (const msg of historyMessages) {
      const { type, data } = msg;
      const timestamp = new Date((msg as any).timestamp || Date.now());

      switch (type) {
        case MessageType.USER_MESSAGE:
          restoredMessages.push({
            id: crypto.randomUUID(),
            role: 'user',
            content: data.content as string,
            timestamp,
          });
          break;

        case MessageType.ASSISTANT_TEXT:
          // 合并连续的 assistant text
          const lastMsg = restoredMessages[restoredMessages.length - 1];
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.content += data.text as string;
          } else {
            restoredMessages.push({
              id: crypto.randomUUID(),
              role: 'assistant',
              content: data.text as string,
              timestamp,
            });
          }
          break;

        case MessageType.THINKING:
          restoredMessages.push({
            id: crypto.randomUUID(),
            role: 'thinking',
            content: data.thinking as string,
            timestamp,
          });
          break;

        case MessageType.TOOL_USE:
          // 查找或创建 tool message
          let toolMsg = restoredMessages[restoredMessages.length - 1];
          if (!toolMsg || toolMsg.role !== 'tool') {
            toolMsg = {
              id: crypto.randomUUID(),
              role: 'tool',
              content: '',
              toolCalls: [],
              timestamp,
            };
            restoredMessages.push(toolMsg);
          }
          toolMsg.toolCalls = toolMsg.toolCalls || [];
          toolMsg.toolCalls.push({
            id: data.tool_use_id as string,
            name: data.tool_name as string,
            input: data.tool_input as Record<string, unknown>,
            status: 'running',
          });
          break;

        case MessageType.TOOL_RESULT:
          // 更新对应的 tool call
          for (let i = restoredMessages.length - 1; i >= 0; i--) {
            const m = restoredMessages[i];
            if (m.role === 'tool' && m.toolCalls) {
              const tool = m.toolCalls.find(t => t.id === data.tool_use_id);
              if (tool) {
                tool.status = data.is_error ? 'error' : 'completed';
                tool.result = data.result as string;
                tool.isError = data.is_error as boolean;
                break;
              }
            }
          }
          break;

        case MessageType.RESULT:
          if (data.cost) {
            restoredMessages.push({
              id: crypto.randomUUID(),
              role: 'system',
              content: `Completed. Cost: $${(data.cost as number).toFixed(6)}`,
              timestamp,
            });
          }
          break;

        case MessageType.ERROR:
          restoredMessages.push({
            id: crypto.randomUUID(),
            role: 'system',
            content: `Error: ${data.message as string}`,
            timestamp,
          });
          break;
      }
    }

    setMessages(restoredMessages);
  }, []);

  // Handle session cleared
  const handleSessionCleared = useCallback(() => {
    setMessages([]);
    setCurrentAssistantMessage('');
    setCurrentToolCalls([]);
    setPendingApproval(null);
  }, []);

  const handleMessage = useCallback((message: WSMessage) => {
    const { type, data } = message;

    switch (type) {
      case MessageType.ASSISTANT_TEXT:
        // Flush tool calls before text
        flushToolCalls();
        // Accumulate streaming text
        setCurrentAssistantMessage((prev) => prev + (data.text as string));
        break;

      case MessageType.THINKING:
        // Flush any pending content
        flushAssistantMessage();
        flushToolCalls();
        // Add thinking message
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'thinking',
            content: data.thinking as string,
            timestamp: new Date(),
          },
        ]);
        break;

      case MessageType.TOOL_USE:
        // Flush any pending assistant message
        flushAssistantMessage();
        // Add to current tool calls
        setCurrentToolCalls((prev) => [
          ...prev,
          {
            id: data.tool_use_id as string,
            name: data.tool_name as string,
            input: data.tool_input as Record<string, unknown>,
            status: 'running',
          },
        ]);
        break;

      case MessageType.TOOL_RESULT:
        // Update the specific tool call with result
        setCurrentToolCalls((prev) => {
          const toolUseId = data.tool_use_id as string;
          return prev.map((tool) =>
            tool.id === toolUseId
              ? {
                  ...tool,
                  status: (data.is_error ? 'error' : 'completed') as ToolCall['status'],
                  result: data.result as string,
                  isError: data.is_error as boolean,
                }
              : tool
          );
        });
        break;

      case MessageType.ERROR:
        flushAssistantMessage();
        flushToolCalls();
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'system',
            content: `Error: ${data.message as string}`,
            timestamp: new Date(),
          },
        ]);
        break;

      case MessageType.RESULT:
        // Flush any remaining content
        flushAssistantMessage();
        flushToolCalls();
        if (data.cost) {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: 'system',
              content: `Completed. Cost: $${(data.cost as number).toFixed(6)}`,
              timestamp: new Date(),
            },
          ]);
        }
        break;
    }
  }, [flushAssistantMessage, flushToolCalls]);

  const handleApprovalRequest = useCallback((request: ApprovalRequest) => {
    // Flush any pending content before showing approval
    flushAssistantMessage();
    flushToolCalls();
    setPendingApproval(request);
  }, [flushAssistantMessage, flushToolCalls]);

  const {
    connectionStatus,
    agentStatus,
    sessionId,
    sendUserMessage,
    sendApprovalResponse,
    interrupt,
    clearSession,
  } = useWebSocket({
    onMessage: handleMessage,
    onApprovalRequest: handleApprovalRequest,
    onHistory: handleHistory,
    onSessionCleared: handleSessionCleared,
  });

  // Handle user sending a message with optional file paths
  const handleSend = (content: string, filePaths?: string[]) => {
    // Build display content
    let displayContent = content;
    if (filePaths && filePaths.length > 0) {
      const pathsStr = filePaths.join(', ');
      displayContent = content ? `${content}\n\n[文件: ${pathsStr}]` : `[文件: ${pathsStr}]`;
    }

    // Flush any pending content before adding user message
    flushAssistantMessage();
    flushToolCalls();

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'user',
        content: displayContent,
        timestamp: new Date(),
      },
    ]);
    sendUserMessage(content, filePaths);
  };

  // Handle approval
  const handleApprove = () => {
    sendApprovalResponse(true);
    setPendingApproval(null);
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'system',
        content: `Approved: ${pendingApproval?.toolName}`,
        timestamp: new Date(),
      },
    ]);
  };

  const handleDeny = (reason?: string) => {
    sendApprovalResponse(false, reason);
    setPendingApproval(null);
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'system',
        content: `Denied: ${pendingApproval?.toolName}${reason ? ` - ${reason}` : ''}`,
        timestamp: new Date(),
      },
    ]);
  };

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentAssistantMessage, currentToolCalls]);

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-800">Agent</h1>
            <p className="text-sm text-gray-500">Interactive AI assistant with tool execution</p>
          </div>
          <button
            onClick={clearSession}
            disabled={agentStatus === 'thinking'}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="清理会话"
          >
            <Trash2 className="w-4 h-4" />
            <span>清理会话</span>
          </button>
        </div>
      </header>

      {/* Status bar */}
      <StatusIndicator
        connectionStatus={connectionStatus}
        agentStatus={agentStatus}
        sessionId={sessionId}
      />

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto">
          {messages.length === 0 && (
            <div className="text-center py-20 text-gray-400">
              <p className="text-lg mb-2">No messages yet</p>
              <p className="text-sm">Start a conversation with the agent</p>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}

          {/* Current tool calls (in progress) */}
          {currentToolCalls.length > 0 && (
            <ChatMessage
              message={{
                id: 'current-tools',
                role: 'tool',
                content: '',
                toolCalls: currentToolCalls,
                timestamp: new Date(),
              }}
            />
          )}

          {/* Streaming assistant message */}
          {currentAssistantMessage && (
            <ChatMessage
              message={{
                id: 'streaming',
                role: 'assistant',
                content: currentAssistantMessage,
                timestamp: new Date(),
              }}
            />
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        onInterrupt={interrupt}
        agentStatus={agentStatus}
        disabled={connectionStatus !== 'connected'}
      />

      {/* Approval Modal */}
      {pendingApproval && (
        <ApprovalModal
          request={pendingApproval}
          onApprove={handleApprove}
          onDeny={handleDeny}
        />
      )}
    </div>
  );
}

export default App;
