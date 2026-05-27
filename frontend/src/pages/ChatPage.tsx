import { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Send, Bot, Sparkles, AlertCircle, RotateCcw, Loader2, Clock3 } from 'lucide-react';
import { getAuthHeaders, getStoredUser } from '../lib/auth';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
  status?: 'sending' | 'success' | 'failed';
  error?: string;
}

export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(true);
  const [statusText, setStatusText] = useState('Ready');
  const [isAuthenticated, setIsAuthenticated] = useState(!!getStoredUser());

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inactivityTimerRef = useRef<NodeJS.Timeout | null>(null);
  const currentAbortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const skipFetchSessionIdRef = useRef<string | null>(null);

  const backendHost = window.location.hostname;
  const backendBaseUrl = `http://${backendHost}:8000`;

  useEffect(() => {
    setIsAuthenticated(!!getStoredUser());
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      currentAbortControllerRef.current?.abort();
      currentAbortControllerRef.current = null;
      setIsTyping(false);
      setStatusText('Ready');
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/auth');
      return;
    }

    if (!sessionId) {
      navigate('/session/new');
      return;
    }

    if (sessionId === 'new') {
      setMessages([]);
      setLoadingMessages(false);
      setStatusText('Ready');
      return;
    }

    if (skipFetchSessionIdRef.current === sessionId) {
      skipFetchSessionIdRef.current = null;
      setLoadingMessages(false);
      setStatusText('Ready');
      return;
    }

    setMessages([]);
    fetchMessages(sessionId);
  }, [sessionId, isAuthenticated]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${Math.min(scrollHeight, 140)}px`;
    }
  }, [input]);

  const clearInactivityTimer = () => {
    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
      inactivityTimerRef.current = null;
    }
  };

  const createSessionAndSend = async (messageText: string) => {
    setStatusText('Creating session...');

    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('Unable to create session');
      }

      const newSession = await response.json();
      skipFetchSessionIdRef.current = newSession.id;
      await sendMessage(newSession.id, messageText);
      window.dispatchEvent(new Event('sessions-updated'));
      navigate(`/session/${newSession.id}`);
    } catch (error) {
      console.error('Create session failed', error);
      setStatusText('Unable to create session');
    }
  };

  const fetchMessages = async (sessionId: string) => {
    setLoadingMessages(true);
    setStatusText('Loading chat...');
    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions/${sessionId}/messages`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data: Message[] = await response.json();
        setMessages(data.map((m) => ({ ...m, status: 'success' })));
        setStatusText('Ready');
      } else {
        throw new Error(`Failed to load ${response.status}`);
      }
    } catch (error) {
      console.error('Failed to fetch messages', error);
      setStatusText('Unable to load chat');
    } finally {
      setLoadingMessages(false);
    }
  };

  const resetInactivityTimer = (abortController: AbortController) => {
    clearInactivityTimer();
    inactivityTimerRef.current = setTimeout(() => {
      abortController.abort();
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') {
          last.status = 'failed';
          last.error = 'Response timed out (inactivity).';
        }
        return next;
      });
      setIsTyping(false);
      setStatusText('Response timed out.');
      clearInactivityTimer();
    }, 30000);
  };

  const sendMessage = async (targetSessionId: string, messageText: string, isResend = false) => {
    const userMsgId = isResend ? messages[messages.length - 2]?.id || Date.now().toString() : Date.now().toString();
    const assistantMsgId = (Date.now() + 1).toString();

    let nextMessages: Message[];

    if (isResend) {
      nextMessages = messages.filter((msg) => msg.id !== messages[messages.length - 1]?.id);
      const userIndex = nextMessages.findIndex((msg) => msg.id === userMsgId);
      if (userIndex !== -1) {
        nextMessages[userIndex].status = 'sending';
      }
    } else {
      nextMessages = [
        ...messages,
        {
          id: userMsgId,
          role: 'user',
          content: messageText,
          status: 'success',
        },
      ];
    }

    nextMessages.push({
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      status: 'sending',
    });

    setMessages(nextMessages);
    setIsTyping(true);
    setStatusText('Assistant is typing...');

    const abortController = new AbortController();
    currentAbortControllerRef.current = abortController;
    resetInactivityTimer(abortController);

    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions/${targetSessionId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ message: messageText }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response stream available');

      const decoder = new TextDecoder();
      let done = false;
      let accumulated = '';

      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;

        if (value) {
          resetInactivityTimer(abortController);
          const chunk = decoder.decode(value, { stream: !done });
          accumulated += chunk;
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last && last.role === 'assistant') {
              last.content = accumulated;
            }
            return next;
          });
        }
      }

      clearInactivityTimer();
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') {
          last.status = 'success';
        }
        return next;
      });
      if (currentAbortControllerRef.current === abortController) {
        currentAbortControllerRef.current = null;
      }
      if (!isMountedRef.current) return;
      setIsTyping(false);
      setStatusText('Ready');
    } catch (error: any) {
      if (currentAbortControllerRef.current === abortController) {
        currentAbortControllerRef.current = null;
      }
      clearInactivityTimer();
      if (!isMountedRef.current) return;
      setIsTyping(false);
      setStatusText('Response failed.');
      if (error.name !== 'AbortError') {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') {
            last.status = 'failed';
            last.error = error.message || 'Connection error';
          }
          return next;
        });
      }
    }
  };

  const startStream = async (messageText: string, isResend = false) => {
    if (!sessionId) return;
    if (sessionId === 'new') {
      await createSessionAndSend(messageText);
      return;
    }

    await sendMessage(sessionId, messageText, isResend);
  };

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isTyping) return;
    setInput('');
    startStream(trimmed);
  };

  const handleResend = () => {
    const userMessages = messages.filter((msg) => msg.role === 'user');
    if (!userMessages.length) return;
    const lastUser = userMessages[userMessages.length - 1];
    startStream(lastUser.content, true);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const renderMarkdown = (text: string) => {
    if (!text) return null;
    const lines = text.split('\n');
    return lines.map((line, idx) => {
      if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
        return (
          <li key={idx} className="ml-4 list-disc text-sm my-1 pl-1">
            {parseInlineMarkdown(line.trim().substring(2))}
          </li>
        );
      }

      const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
      if (headingMatch) {
        const level = headingMatch[1].length;
        const content = headingMatch[2];
        const HeadingTag = `h${level}` as keyof JSX.IntrinsicElements;
        const classes = [
          'font-bold text-slate-900 dark:text-slate-100 my-2 text-lg',
          'font-bold text-slate-900 dark:text-slate-100 my-1.5 text-base',
          'font-bold text-slate-900 dark:text-slate-100 my-1 text-sm',
        ][level - 1] || 'font-bold text-slate-900 dark:text-slate-100 my-1 text-sm';
        return (
          <HeadingTag key={idx} className={classes}>
            {parseInlineMarkdown(content)}
          </HeadingTag>
        );
      }

      return (
        <p key={idx} className="min-h-[1.25rem] text-sm my-1 text-slate-700 dark:text-slate-300">
          {parseInlineMarkdown(line)}
        </p>
      );
    });
  };

  const parseInlineMarkdown = (text: string) => {
    const parts: Array<string | JSX.Element> = [];
    const regex = /(\*\*|__)(.*?)\1|(\*|_)(.*?)\3|(`)(.*?)\5/g;
    let match: RegExpExecArray | null;
    let lastIndex = 0;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }

      if (match[2]) {
        parts.push(
          <strong key={`b-${match.index}`} className="font-bold text-slate-900 dark:text-slate-100">
            {match[2]}
          </strong>
        );
      } else if (match[4]) {
        parts.push(
          <em key={`i-${match.index}`} className="italic">
            {match[4]}
          </em>
        );
      } else if (match[6]) {
        parts.push(
          <code key={`c-${match.index}`} className="bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded font-mono text-xs text-emerald-500 border border-slate-200 dark:border-slate-700">
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

  const statusBadge = useMemo(() => {
    if (isTyping) {
      return (
        <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-200">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Thinking...
        </div>
      );
    }

    return (
      <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
        <Clock3 size={14} />
        {statusText}
      </div>
    );
  }, [isTyping, statusText]);

  return (
    <div className="h-screen flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      <div className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-6 py-4 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3">
            <Sparkles size={22} className="text-emerald-500" />
            <div>
              <h1 className="text-xl font-semibold">Academic Research Assistant</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">Real-time research chat with saved conversation history.</p>
            </div>
          </div>
          <div>{statusBadge}</div>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        <div className="h-full overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-6xl space-y-5">
            {loadingMessages ? (
              <div className="flex h-[60vh] items-center justify-center">
                <p className="text-slate-500 dark:text-slate-400">Loading chat history…</p>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex h-[55vh] flex-col items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/80 dark:bg-slate-900/80 text-center px-6 py-10">
                <Bot size={34} className="text-emerald-500" />
                <h2 className="mt-4 text-lg font-semibold text-slate-900 dark:text-slate-100">Start a new chat</h2>
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 max-w-md">
                  Type your question below and press Enter. The assistant will generate the answer in parts and save the conversation automatically.
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                {messages.map((message) => {
                  const isUser = message.role === 'user';
                  const isFailed = message.status === 'failed';
                  return (
                    <div key={message.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'} px-2`}>
                      <div className={`max-w-[90%] rounded-[32px] p-5 shadow-sm ${
                        isUser
                          ? 'bg-emerald-600 text-white rounded-br-none dark:bg-emerald-500'
                          : 'bg-white text-slate-900 border border-slate-200 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-100 rounded-bl-none'
                      }`}>
                        <div className="flex items-center gap-3 mb-3">
                          <div className={`w-9 h-9 rounded-2xl flex items-center justify-center ${isUser ? 'bg-emerald-700' : 'bg-slate-100 dark:bg-slate-800'}`}>
                            {isUser ? <span className="text-white text-xs font-semibold">U</span> : <Bot size={18} className="text-emerald-500" />}
                          </div>
                          {!isUser && (
                            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                              Assistant
                            </div>
                          )}
                        </div>
                        {isFailed ? (
                          <div className="rounded-2xl bg-rose-50 dark:bg-rose-950/50 border border-rose-100 dark:border-rose-900 p-3 text-xs text-rose-700 dark:text-rose-200">
                            <div className="flex items-center gap-2">
                              <AlertCircle size={14} />
                              <span>{message.error || 'The response failed. Please try again.'}</span>
                            </div>
                          </div>
                        ) : (
                          <div className="prose prose-sm max-w-none text-slate-800 dark:text-slate-100">
                            {renderMarkdown(message.content)}
                          </div>
                        )}
                        {isFailed && (
                          <button
                            type="button"
                            onClick={handleResend}
                            className="mt-4 inline-flex items-center gap-2 rounded-full bg-rose-600 px-3 py-1 text-white text-[11px] font-semibold hover:bg-rose-500 transition"
                          >
                            <RotateCcw size={12} /> Resend
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>

      <div className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-6 py-5">
        <div className="mx-auto max-w-6xl">
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">Your message</label>
          <textarea
            ref={textareaRef}
            rows={3}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your research question, ask about clusters, papers, or summaries..."
            className="w-full min-h-[100px] max-h-[180px] resize-none rounded-3xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-900 shadow-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-emerald-500 dark:focus:ring-emerald-500/20"
          />
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-slate-500 dark:text-slate-400">Press Enter to send, Shift + Enter for a new line.</p>
            <button
              type="button"
              disabled={!input.trim() || isTyping}
              onClick={handleSend}
              className="inline-flex items-center justify-center gap-2 rounded-full bg-emerald-600 px-5 py-3 text-sm font-semibold text-white shadow-md shadow-emerald-500/20 hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50 transition"
            >
              <Send size={16} /> Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
