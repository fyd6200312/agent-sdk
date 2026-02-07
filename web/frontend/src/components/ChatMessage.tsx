import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChatMessage as ChatMessageType, ToolCall } from '../types';
import { User, Bot, Terminal, AlertCircle, Brain, ChevronDown, ChevronRight, Check, Loader2, XCircle } from 'lucide-react';

interface ChatMessageProps {
  message: ChatMessageType;
}

function ToolCallItem({ tool }: { tool: ToolCall }) {
  const [expanded, setExpanded] = useState(true);

  const statusIcon = {
    running: <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />,
    completed: <Check className="w-4 h-4 text-green-500" />,
    error: <XCircle className="w-4 h-4 text-red-500" />,
  }[tool.status];

  return (
    <div className="border border-gray-300 rounded-lg mb-2 overflow-hidden bg-white shadow-sm">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-gray-100 hover:bg-gray-200 transition-colors text-left"
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-gray-600" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-600" />
        )}
        <Terminal className="w-4 h-4 text-amber-600" />
        <span className="flex-1 font-medium text-sm text-gray-800">{tool.name}</span>
        {statusIcon}
      </button>

      {expanded && (
        <div className="p-3 border-t border-gray-200 bg-white">
          {/* Input */}
          <div className="mb-3">
            <div className="text-xs font-semibold text-gray-600 mb-1">Input</div>
            <pre className="text-xs bg-gray-900 text-green-400 p-3 rounded overflow-x-auto whitespace-pre-wrap font-mono">
              {JSON.stringify(tool.input, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {tool.result && (
            <div>
              <div className="text-xs font-semibold text-gray-600 mb-1">
                {tool.isError ? 'Error' : 'Result'}
              </div>
              <pre className={`text-xs p-3 rounded overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto font-mono ${
                tool.isError ? 'bg-red-100 text-red-800 border border-red-300' : 'bg-gray-100 text-gray-800 border border-gray-300'
              }`}>
                {tool.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ThinkingBlock({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="mb-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-left mb-2"
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-purple-600" />
        ) : (
          <ChevronRight className="w-4 h-4 text-purple-600" />
        )}
        <Brain className="w-4 h-4 text-purple-600" />
        <span className="font-medium text-sm text-purple-700">思考过程</span>
      </button>

      {expanded && (
        <div className="pl-6 text-sm text-gray-700 leading-relaxed prose prose-sm max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
                  {children}
                </a>
              ),
              table: ({ children }) => (
                <div className="overflow-x-auto my-4">
                  <table className="min-w-full border-collapse border border-gray-300">
                    {children}
                  </table>
                </div>
              ),
              thead: ({ children }) => (
                <thead className="bg-gray-100">{children}</thead>
              ),
              th: ({ children }) => (
                <th className="border border-gray-300 px-3 py-2 text-left font-semibold text-gray-700">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="border border-gray-300 px-3 py-2 text-gray-700">
                  {children}
                </td>
              ),
              tr: ({ children }) => (
                <tr className="hover:bg-gray-50">{children}</tr>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isTool = message.role === 'tool';
  const isSystem = message.role === 'system';
  const isThinking = message.role === 'thinking';

  // For thinking messages, render as collapsible block
  if (isThinking) {
    return (
      <div className="p-4 bg-gray-50">
        <div className="max-w-4xl mx-auto">
          <ThinkingBlock content={message.content} />
        </div>
      </div>
    );
  }

  // For tool messages with grouped tool calls
  if (isTool && message.toolCalls && message.toolCalls.length > 0) {
    return (
      <div className="p-4 bg-gray-50">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center gap-2 mb-2">
            <Terminal className="w-5 h-5 text-amber-500" />
            <span className="font-medium text-sm text-gray-700">Tool Calls</span>
            <span className="text-xs text-gray-400">({message.toolCalls.length})</span>
          </div>
          {message.toolCalls.map((tool) => (
            <ToolCallItem key={tool.id} tool={tool} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 p-4 ${isUser ? 'bg-white' : 'bg-gray-50'}`}>
      {/* Avatar */}
      <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
        isUser ? 'bg-blue-500' : isTool ? 'bg-amber-500' : isSystem ? 'bg-red-500' : 'bg-purple-500'
      }`}>
        {isUser ? (
          <User className="w-5 h-5 text-white" />
        ) : isTool ? (
          <Terminal className="w-5 h-5 text-white" />
        ) : isSystem ? (
          <AlertCircle className="w-5 h-5 text-white" />
        ) : (
          <Bot className="w-5 h-5 text-white" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm text-gray-700">
            {isUser ? 'You' : isTool ? `Tool: ${message.toolName}` : isSystem ? 'System' : 'Assistant'}
          </span>
          <span className="text-xs text-gray-400">
            {message.timestamp.toLocaleTimeString()}
          </span>
        </div>

        {/* Tool input display (legacy single tool) */}
        {isTool && message.toolInput && !message.toolCalls && (
          <div className="mb-2 p-2 bg-gray-800 rounded-lg text-xs">
            <pre className="text-gray-300 whitespace-pre-wrap">
              {JSON.stringify(message.toolInput, null, 2)}
            </pre>
          </div>
        )}

        {/* Message content */}
        <div className={`text-sm ${isSystem ? 'text-red-600' : 'text-gray-800'} prose prose-sm max-w-none`}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
                  {children}
                </a>
              ),
              table: ({ children }) => (
                <div className="overflow-x-auto my-4">
                  <table className="min-w-full border-collapse border border-gray-300">
                    {children}
                  </table>
                </div>
              ),
              thead: ({ children }) => (
                <thead className="bg-gray-100">{children}</thead>
              ),
              th: ({ children }) => (
                <th className="border border-gray-300 px-3 py-2 text-left font-semibold text-gray-700">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="border border-gray-300 px-3 py-2 text-gray-700">
                  {children}
                </td>
              ),
              tr: ({ children }) => (
                <tr className="hover:bg-gray-50">{children}</tr>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
