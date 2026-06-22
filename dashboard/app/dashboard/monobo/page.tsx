'use client';

import { useState } from 'react';
import { AppHeader } from '@/components/AppHeader';
import { ExternalLink, RefreshCw, Maximize2, AlertCircle } from 'lucide-react';

const MANUS_URL = process.env.NEXT_PUBLIC_MANUS_APP_URL
  || 'https://monobackof-qxpbyjhx.manus.space/';

export default function MonoBoEmbedPage() {
  const [iframeKey, setIframeKey] = useState(0);
  const [loading, setLoading] = useState(true);

  const reload = () => {
    setLoading(true);
    setIframeKey(k => k + 1);
  };

  const openInNewTab = () => {
    window.open(MANUS_URL, '_blank', 'noopener,noreferrer');
  };

  const goFullscreen = () => {
    const iframe = document.getElementById('manus-iframe') as HTMLIFrameElement;
    if (iframe?.requestFullscreen) iframe.requestFullscreen();
  };

  return (
    <>
      <AppHeader breadcrumbs={['MONOPO (Manus 連携)']} />

      {/* Iframe toolbar */}
      <div className="bg-white border-b border-gray-200 px-6 py-2 flex items-center gap-2">
        <div className="flex items-center gap-2 text-sm text-gray-600 flex-1 min-w-0">
          <div className="w-2 h-2 rounded-full bg-green-500 shrink-0" />
          <span className="truncate font-mono text-xs">{MANUS_URL}</span>
        </div>
        <button
          onClick={reload}
          className="flex items-center gap-1 px-3 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
          title="再読み込み"
        >
          <RefreshCw className="w-3 h-3" />
          再読み込み
        </button>
        <button
          onClick={goFullscreen}
          className="flex items-center gap-1 px-3 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
          title="全画面"
        >
          <Maximize2 className="w-3 h-3" />
          全画面
        </button>
        <button
          onClick={openInNewTab}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700"
          title="新しいタブで開く"
        >
          <ExternalLink className="w-3 h-3" />
          新しいタブで開く
        </button>
      </div>

      {/* Iframe container */}
      <div className="flex-1 relative bg-gray-100">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10 bg-white/80">
            <div className="flex items-center gap-2 text-gray-500">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span className="text-sm">MONOPO (Manus) を読み込み中…</span>
            </div>
          </div>
        )}
        <iframe
          id="manus-iframe"
          key={iframeKey}
          src={MANUS_URL}
          className="absolute inset-0 w-full h-full border-0"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
          allow="clipboard-read; clipboard-write"
          onLoad={() => setLoading(false)}
        />
      </div>
    </>
  );
}
