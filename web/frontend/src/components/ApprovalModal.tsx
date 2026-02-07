import React, { useState } from 'react';
import { AlertTriangle, Check, X, ChevronDown, ChevronUp } from 'lucide-react';
import { ApprovalRequest } from '../types';

interface ApprovalModalProps {
  request: ApprovalRequest;
  onApprove: () => void;
  onDeny: (reason?: string) => void;
}

export function ApprovalModal({ request, onApprove, onDeny }: ApprovalModalProps) {
  const [showDetails, setShowDetails] = useState(true);
  const [denyReason, setDenyReason] = useState('');
  const [showDenyInput, setShowDenyInput] = useState(false);

  const handleDeny = () => {
    if (showDenyInput && denyReason.trim()) {
      onDeny(denyReason.trim());
    } else if (!showDenyInput) {
      setShowDenyInput(true);
    } else {
      onDeny();
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full max-h-[80vh] overflow-hidden">
        {/* Header */}
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-100 rounded-full">
              <AlertTriangle className="w-6 h-6 text-amber-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Tool Approval Required</h2>
              <p className="text-sm text-gray-600">The agent wants to use a tool</p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[50vh]">
          <div className="mb-4">
            <div className="text-sm font-medium text-gray-500 mb-1">Tool Name</div>
            <div className="text-lg font-mono bg-gray-100 px-3 py-2 rounded-lg">
              {request.toolName}
            </div>
          </div>

          <div>
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="flex items-center gap-2 text-sm font-medium text-gray-500 mb-2 hover:text-gray-700"
            >
              {showDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              Tool Input
            </button>
            {showDetails && (
              <pre className="bg-gray-800 text-gray-100 p-4 rounded-lg text-sm overflow-x-auto">
                {JSON.stringify(request.toolInput, null, 2)}
              </pre>
            )}
          </div>

          {showDenyInput && (
            <div className="mt-4">
              <label className="text-sm font-medium text-gray-500 mb-1 block">
                Reason for denial (optional)
              </label>
              <input
                type="text"
                value={denyReason}
                onChange={(e) => setDenyReason(e.target.value)}
                placeholder="Enter reason..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                autoFocus
              />
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="border-t bg-gray-50 px-6 py-4 flex gap-3 justify-end">
          <button
            onClick={handleDeny}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <X className="w-4 h-4" />
            {showDenyInput ? 'Confirm Deny' : 'Deny'}
          </button>
          <button
            onClick={onApprove}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-green-500 text-white hover:bg-green-600 transition-colors"
          >
            <Check className="w-4 h-4" />
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
