import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles, AlertCircle, RotateCcw, Plus, MessageSquare } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
  status?: 'sending' | 'success' | 'failed';
  error?: string;
}

interface ChatSession {
  id: string;
  title: string;
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const inactivityTimerRef = useRef<NodeJS.Timeout | null>(null);

  const backendHost = window.location.hostname;
  const backendBaseUrl = `http://${backendHost}:8000`;

  // Auto-scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // Load chat sessions on component mount
  useEffect(() => {
    fetchSessions();
    return () => {
      clearInactivityTimer();
    };
  }, []);

  // Auto-resize textarea height
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${Math.min(scrollHeight, 120)}px`; // Limits to ~5 lines
    }
  }, [input]);

  const clearInactivityTimer = () => {
    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
      inactivityTimerRef.current = null;
    }
  };

  const fetchSessions = async (selectLatest = true) => {
    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions`);
      if (response.ok) {
        const data: ChatSession[] = await response.json();
        setSessions(data);
        if (data.length > 0 && selectLatest) {
          handleSelectSession(data[0].id);
        } else if (data.length === 0) {
          // Auto create a session if none exist
          handleCreateSession();
        }
      }
    } catch (e) {
      console.error("Failed to fetch sessions", e);
    } finally {
      setLoadingSessions(false);
    }
  };

  const handleCreateSession = async () => {
    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions`, { method: 'POST' });
      if (response.ok) {
        const newSession: ChatSession = await response.json();
        setSessions(prev => [newSession, ...prev]);
        handleSelectSession(newSession.id);
      }
    } catch (e) {
      console.error("Failed to create session", e);
    }
  };

  const handleSelectSession = async (sessionId: string) => {
    // Abort any ongoing stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    clearInactivityTimer();
    setIsTyping(false);
    setActiveSessionId(sessionId);
    
    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions/${sessionId}/messages`);
      if (response.ok) {
        const data: Message[] = await response.json();
        setMessages(data.map(m => ({ ...m, status: 'success' })));
      }
    } catch (e) {
      console.error("Failed to fetch messages for session", e);
    }
  };

  const startStream = async (messageText: string, isResend = false) => {
    if (!activeSessionId) return;

    clearInactivityTimer();

    const userMsgId = isResend ? messages[messages.length - 2]?.id || Date.now().toString() : Date.now().toString();
    const assistantMsgId = (Date.now() + 1).toString();

    // 1. Prepare messages list
    let updatedMessages: Message[];
    if (isResend) {
      // Remove the failed assistant message and reuse user message
      updatedMessages = messages.filter(m => m.id !== messages[messages.length - 1].id);
      const userMsgIndex = updatedMessages.findIndex(m => m.id === userMsgId);
      if (userMsgIndex !== -1) {
        updatedMessages[userMsgIndex].status = 'sending';
      }
    } else {
      const userMsg: Message = {
        id: userMsgId,
        role: 'user',
        content: messageText,
        status: 'success'
      };
      updatedMessages = [...messages, userMsg];
    }

    // Add empty assistant response card
    const assistantMsg: Message = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      status: 'sending'
    };

    setMessages([...updatedMessages, assistantMsg]);
    setIsTyping(true);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    // Helper to start the inactivity timer
    const resetInactivityTimer = () => {
      clearInactivityTimer();
      inactivityTimerRef.current = setTimeout(() => {
        // Inactivity timeout triggered!
        abortController.abort();
        setMessages(prev => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') {
            last.status = 'failed';
            last.error = 'Response timed out (inactivity).';
          }
          return next;
        });
        setIsTyping(false);
        clearInactivityTimer();
      }, 30000); // 30 seconds inactivity timeout
    };

    try {
      resetInactivityTimer(); // Start initial timer

      const response = await fetch(`${backendBaseUrl}/chat/sessions/${activeSessionId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
        signal: abortController.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("Null response body reader");

      const decoder = new TextDecoder();
      let done = false;
      let accumulated = '';

      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;

        if (value) {
          resetInactivityTimer(); // Refresh inactivity timer on every new chunk!
          const chunk = decoder.decode(value, { stream: !done });
          accumulated += chunk;

          setMessages(prev => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last && last.role === 'assistant') {
              last.content = accumulated;
            }
            return next;
          });
        }
      }

      // Completed successfully
      clearInactivityTimer();
      setMessages(prev => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') {
          last.status = 'success';
        }
        return next;
      });
      setIsTyping(false);
      
      // Update sidebar session title if it was the first message
      if (messages.length === 0) {
        fetchSessions(false);
      }

    } catch (e: any) {
      clearInactivityTimer();
      setIsTyping(false);
      if (e.name !== 'AbortError') {
        setMessages(prev => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') {
            last.status = 'failed';
            last.error = e.message || 'Failed to connect to the backend.';
          }
          return next;
        });
      }
    }
  };

  const handleSend = () => {
    const text = input.trim();
    if (!text || isTyping) return;
    setInput('');
    startStream(text);
  };

  const handleResend = () => {
    // Find the last user message
    const userMessages = messages.filter(m => m.role === 'user');
    if (userMessages.length === 0) return;
    const lastUserText = userMessages[userMessages.length - 1].content;
    startStream(lastUserText, true);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Basic Markdown Renderer
  const renderMarkdown = (text: string) => {
    if (!text) return null;
    const lines = text.split('\n');
    return lines.map((line, idx) => {
      // Bullets
      if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
        return (
          <li key={idx} className="ml-4 list-disc text-sm my-1 pl-1">
            {parseInlineMarkdown(line.trim().substring(2))}
          </li>
        );
      }
      // Headings
      if (line.startsWith('#')) {
        const match = line.match(/^(#{1,6})\s+(.*)$/);
        if (match) {
          const level = match[1].length;
          const content = match[2];
          const HeadingTag = `h${level}` as keyof JSX.IntrinsicElements;
          const classes = [
            'font-bold text-slate-800 my-2 text-lg',
            'font-bold text-slate-800 my-1.5 text-base',
            'font-bold text-slate-800 my-1 text-sm'
          ][level - 1] || 'font-bold text-slate-800 my-1 text-sm';
          return (
            <HeadingTag key={idx} className={classes}>
              {parseInlineMarkdown(content)}
            </HeadingTag>
          );
        }
      }
      // Normal Line
      return (
        <p key={idx} className="min-h-[1.25rem] text-sm my-1 text-slate-700">
          {parseInlineMarkdown(line)}
        </p>
      );
    });
  };

  const parseInlineMarkdown = (text: string) => {
    const parts = [];
    const regex = /(\*\*|__)(.*?)\1|(\*|_)(.*?)\3|(`)(.*?)\5/g;
    let match;
    let lastIndex = 0;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }

      if (match[2]) {
        // Bold
        parts.push(<strong key={match.index} className="font-bold text-slate-900">{match[2]}</strong>);
      } else if (match[4]) {
        // Italic
        parts.push(<em key={match.index} className="italic">{match[4]}</em>);
      } else if (match[6]) {
        // Inline Code
        parts.push(
          <code key={match.index} className="bg-slate-100 px-1 py-0.5 rounded font-mono text-xs text-rose-600 border border-slate-200">
            {match[6]}
          </code>
        );
      }
      lastIndex = regex.lastIndex;
    }

    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  };

  return (
    <div className="h-screen flex bg-slate-50 overflow-hidden">
      {/* Session History Sidebar */}
      <aside className="w-64 bg-white border-r border-slate-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between shrink-0">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Chat History</h2>
          <button
            onClick={handleCreateSession}
            className="p-1 hover:bg-slate-100 rounded-lg text-slate-600 hover:text-emerald-600 transition-colors"
            title="Start New Chat"
          >
            <Plus size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loadingSessions ? (
            <div className="flex items-center justify-center p-8">
              <div className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : sessions.length === 0 ? (
            <p className="text-xs text-slate-400 text-center p-4">No recent chats</p>
          ) : (
            sessions.map(s => {
              const isActive = s.id === activeSessionId;
              return (
                <button
                  key={s.id}
                  onClick={() => handleSelectSession(s.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-xs font-medium flex items-center gap-2.5 transition-colors ${
                    isActive
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <MessageSquare size={14} className={isActive ? 'text-emerald-500' : 'text-slate-400'} />
                  <span className="truncate flex-1">{s.title}</span>
                </button>
              );
            })
          )}
        </div>
      </aside>

      {/* Main Messaging Interface */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0 z-10">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-emerald-500 animate-pulse" />
            <h1 className="text-sm font-semibold text-slate-800">Academic Research Assistant</h1>
          </div>
          <span className="px-2 py-0.5 bg-emerald-50 text-emerald-600 text-xs font-medium rounded-full">
            Online
          </span>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.length === 0 ? (
              <div className="text-center py-20">
                <div className="w-12 h-12 bg-emerald-50 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Bot size={24} className="text-emerald-500" />
                </div>
                <h3 className="text-sm font-semibold text-slate-800">Start a new conversation</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 leading-relaxed">
                  Ask about academic research topics, paper clusters, publication trends, or ask to summarize abstract content.
                </p>
              </div>
            ) : (
              messages.map((msg) => {
                const isUser = msg.role === 'user';
                const isFailed = msg.status === 'failed';
                return (
                  <div
                    key={msg.id}
                    className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isUser && (
                      <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center shrink-0 mt-1 shadow-sm">
                        <Bot size={16} className="text-white" />
                      </div>
                    )}
                    <div className="max-w-[75%] flex flex-col gap-1">
                      <div
                        className={`rounded-2xl px-4 py-3 text-sm leading-relaxed border ${
                          isUser
                            ? 'bg-slate-800 text-white border-slate-800 rounded-br-md shadow-sm'
                            : isFailed
                            ? 'bg-rose-50 border-rose-200 text-rose-800 rounded-bl-md'
                            : 'bg-white border-slate-200 text-slate-700 rounded-bl-md shadow-sm'
                        }`}
                      >
                        {isFailed ? (
                          <div className="flex items-center gap-2">
                            <AlertCircle size={16} className="text-rose-500 shrink-0" />
                            <span>{msg.error || 'Connection timed out.'}</span>
                          </div>
                        ) : (
                          renderMarkdown(msg.content)
                        )}
                      </div>
                      {isFailed && (
                        <button
                          onClick={handleResend}
                          className="self-start mt-1 flex items-center gap-1 text-[11px] font-medium text-emerald-600 hover:text-emerald-700 transition-colors"
                        >
                          <RotateCcw size={10} />
                          <span>Resend Message</span>
                        </button>
                      )}
                    </div>
                    {isUser && (
                      <div className="w-8 h-8 rounded-lg bg-slate-700 flex items-center justify-center shrink-0 mt-1 shadow-sm">
                        <User size={16} className="text-slate-300" />
                      </div>
                    )}
                  </div>
                );
              })
            )}

            {/* Typing indicator */}
            {isTyping && messages[messages.length - 1]?.content === '' && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center shrink-0 mt-1 shadow-sm">
                  <Bot size={16} className="text-white" />
                </div>
                <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-slate-500 mr-1.5">Thinking</span>
                    <div className="flex gap-1">
                      <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="bg-white border-t border-slate-200 px-4 py-3 shrink-0">
          <div className="max-w-3xl mx-auto flex gap-2 items-end">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about academic clusters, papers, or trends..."
              className="flex-1 min-h-[40px] max-h-[120px] px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-400 transition-all resize-none leading-relaxed"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isTyping}
              className="h-10 px-4 bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-200 disabled:text-slate-400 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2 shrink-0 shadow-sm shadow-emerald-500/10 cursor-pointer disabled:cursor-not-allowed"
            >
              <Send size={14} />
              <span className="hidden sm:inline">Send</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
