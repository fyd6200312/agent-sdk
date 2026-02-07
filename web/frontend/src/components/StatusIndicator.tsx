import React from 'react';
import { Wifi, WifiOff, Loader2, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { ConnectionStatus, AgentStatus } from '../types';

interface StatusIndicatorProps {
  connectionStatus: ConnectionStatus;
  agentStatus: AgentStatus;
  sessionId: string | null;
}

export function StatusIndicator({ connectionStatus, agentStatus, sessionId }: StatusIndicatorProps) {
  const getConnectionIcon = () => {
    switch (connectionStatus) {
      case 'connected':
        return <Wifi className="w-4 h-4 text-green-500" />;
      case 'connecting':
        return <Loader2 className="w-4 h-4 text-yellow-500 animate-spin" />;
      case 'error':
        return <WifiOff className="w-4 h-4 text-red-500" />;
      default:
        return <WifiOff className="w-4 h-4 text-gray-400" />;
    }
  };

  const getAgentStatusBadge = () => {
    switch (agentStatus) {
      case 'thinking':
        return (
          <span className="flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs">
            <Loader2 className="w-3 h-3 animate-spin" />
            Thinking
          </span>
        );
      case 'done':
        return (
          <span className="flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs">
            <CheckCircle className="w-3 h-3" />
            Done
          </span>
        );
      case 'error':
        return (
          <span className="flex items-center gap-1 px-2 py-1 bg-red-100 text-red-700 rounded-full text-xs">
            <XCircle className="w-3 h-3" />
            Error
          </span>
        );
      case 'interrupted':
        return (
          <span className="flex items-center gap-1 px-2 py-1 bg-amber-100 text-amber-700 rounded-full text-xs">
            <AlertCircle className="w-3 h-3" />
            Interrupted
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex items-center gap-4 px-4 py-2 bg-white border-b text-sm">
      <div className="flex items-center gap-2">
        {getConnectionIcon()}
        <span className="text-gray-600 capitalize">{connectionStatus}</span>
      </div>

      {sessionId && (
        <div className="text-gray-400 text-xs font-mono">
          Session: {sessionId.slice(0, 8)}...
        </div>
      )}

      <div className="flex-1" />

      {getAgentStatusBadge()}
    </div>
  );
}
