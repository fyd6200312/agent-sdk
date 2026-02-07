import React, { useState, useRef, useEffect } from 'react';
import { Send, Square, Paperclip, X } from 'lucide-react';
import { AgentStatus } from '../types';

interface ChatInputProps {
  onSend: (message: string, filePaths?: string[]) => void;
  onInterrupt: () => void;
  agentStatus: AgentStatus;
  disabled?: boolean;
}

export function ChatInput({ onSend, onInterrupt, agentStatus, disabled }: ChatInputProps) {
  const [input, setInput] = useState('');
  const [filePaths, setFilePaths] = useState<string[]>([]);
  const [showPathInput, setShowPathInput] = useState(false);
  const [pathInput, setPathInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pathInputRef = useRef<HTMLInputElement>(null);
  const isThinking = agentStatus === 'thinking';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if ((input.trim() || filePaths.length > 0) && !disabled) {
      onSend(input.trim(), filePaths.length > 0 ? filePaths : undefined);
      setInput('');
      setFilePaths([]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleAddPath = () => {
    if (pathInput.trim()) {
      setFilePaths((prev) => [...prev, pathInput.trim()]);
      setPathInput('');
      setShowPathInput(false);
    }
  };

  const handlePathKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddPath();
    } else if (e.key === 'Escape') {
      setShowPathInput(false);
      setPathInput('');
    }
  };

  const removePath = (index: number) => {
    setFilePaths((prev) => prev.filter((_, i) => i !== index));
  };

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  // Focus path input when shown
  useEffect(() => {
    if (showPathInput && pathInputRef.current) {
      pathInputRef.current.focus();
    }
  }, [showPathInput]);

  return (
    <form onSubmit={handleSubmit} className="border-t bg-white p-4">
      <div className="max-w-4xl mx-auto">
        {/* File paths preview */}
        {filePaths.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {filePaths.map((path, index) => (
              <div
                key={index}
                className="flex items-center gap-2 px-3 py-2 bg-gray-100 rounded-lg text-sm"
              >
                <Paperclip className="w-4 h-4 text-gray-500" />
                <span className="max-w-[300px] truncate font-mono text-xs">{path}</span>
                <button
                  type="button"
                  onClick={() => removePath(index)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Path input */}
        {showPathInput && (
          <div className="flex gap-2 mb-3">
            <input
              ref={pathInputRef}
              type="text"
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              onKeyDown={handlePathKeyDown}
              placeholder="粘贴文件路径，如 /Users/xxx/data.xlsx"
              className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:border-blue-500 focus:outline-none font-mono"
            />
            <button
              type="button"
              onClick={handleAddPath}
              className="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600"
            >
              添加
            </button>
            <button
              type="button"
              onClick={() => { setShowPathInput(false); setPathInput(''); }}
              className="px-4 py-2 text-sm bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
            >
              取消
            </button>
          </div>
        )}

        <div className="flex items-end gap-2">
          {/* Add file path button */}
          <button
            type="button"
            onClick={() => setShowPathInput(true)}
            disabled={disabled || isThinking || showPathInput}
            className="flex-shrink-0 p-3 rounded-lg text-gray-500 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title="添加文件路径"
          >
            <Paperclip className="w-5 h-5" />
          </button>

          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isThinking ? '输入消息可中断并追加...' : 'Type a message...'}
              disabled={disabled}
              rows={1}
              className={`w-full resize-none rounded-lg border px-4 py-3 pr-12 text-sm focus:outline-none focus:ring-1 disabled:bg-gray-100 disabled:cursor-not-allowed ${
                isThinking
                  ? 'border-orange-300 focus:border-orange-500 focus:ring-orange-500 bg-orange-50'
                  : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500'
              }`}
            />
          </div>

          {isThinking ? (
            <div className="flex gap-1">
              {/* 有输入时显示发送按钮 */}
              {(input.trim() || filePaths.length > 0) && (
                <button
                  type="submit"
                  className="flex-shrink-0 p-3 rounded-lg bg-orange-500 text-white hover:bg-orange-600 transition-colors"
                  title="中断并发送"
                >
                  <Send className="w-5 h-5" />
                </button>
              )}
              {/* 停止按钮 */}
              <button
                type="button"
                onClick={onInterrupt}
                className="flex-shrink-0 p-3 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-colors"
                title="停止"
              >
                <Square className="w-5 h-5" />
              </button>
            </div>
          ) : (
            <button
              type="submit"
              disabled={(!input.trim() && filePaths.length === 0) || disabled}
              className="flex-shrink-0 p-3 rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
              title="Send"
            >
              <Send className="w-5 h-5" />
            </button>
          )}
        </div>

        <div className="text-xs text-gray-400 text-center mt-2">
          Press Enter to send, Shift+Enter for new line
        </div>
      </div>
    </form>
  );
}
