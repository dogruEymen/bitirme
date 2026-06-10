import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import {
  Send,
  Bot,
  AlertCircle,
  RotateCcw,
  Loader2,
  Clock3,
} from "lucide-react";
import { ensureOk, getBackendBaseUrl, normalizeUnknownError } from "../api/client";
import { clearStoredUser, getAuthHeaders, getStoredUser } from "../lib/auth";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  status?: "sending" | "success" | "failed";
  error?: string;
}

export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(true);
  const [statusText, setStatusText] = useState("Ready");
  const [isAuthenticated, setIsAuthenticated] = useState(!!getStoredUser());

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inactivityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentAbortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const skipFetchSessionIdRef = useRef<string | null>(null);

  const backendBaseUrl = getBackendBaseUrl();

  useEffect(() => {
    setIsAuthenticated(!!getStoredUser());
  }, []);

  useEffect(() => {
    const state = location.state as { initialPrompt?: string } | null;
    if (state?.initialPrompt) {
      setInput(state.initialPrompt);
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, location.state, navigate]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      currentAbortControllerRef.current?.abort();
      currentAbortControllerRef.current = null;
      setIsTyping(false);
      setStatusText("Ready");
    };
  }, []);

  const fetchMessages = useCallback(async (targetSessionId: string) => {
    setLoadingMessages(true);
    setStatusText("Loading chat...");
    try {
      const response = await fetch(
        `${backendBaseUrl}/chat/sessions/${targetSessionId}/messages`,
        {
          headers: getAuthHeaders(),
        },
      );
      if (response.status === 401) {
        clearStoredUser();
        setIsAuthenticated(false);
        navigate("/auth");
        return;
      }
      await ensureOk(response);
      const data: Message[] = await response.json();
      setMessages(data.map((m) => ({ ...m, status: "success" })));
      setStatusText("Ready");
    } catch (error) {
      console.error("Failed to fetch messages", error);
      setStatusText(normalizeUnknownError(error, "Unable to load chat.").message);
    } finally {
      setLoadingMessages(false);
    }
  }, [backendBaseUrl, navigate]);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/auth");
      return;
    }

    if (!sessionId) {
      navigate("/session/new");
      return;
    }

    if (sessionId === "new") {
      setMessages([]);
      setLoadingMessages(false);
      setStatusText("Ready");
      return;
    }

    if (skipFetchSessionIdRef.current === sessionId) {
      skipFetchSessionIdRef.current = null;
      setLoadingMessages(false);
      setStatusText("Ready");
      return;
    }

    setMessages([]);
    fetchMessages(sessionId);
  }, [fetchMessages, isAuthenticated, navigate, sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
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
    setStatusText("Creating session...");

    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions`, {
        method: "POST",
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        if (response.status === 401) {
          clearStoredUser();
          setIsAuthenticated(false);
          setIsTyping(false);
          clearInactivityTimer();
          navigate("/auth");
          return;
        }
        await ensureOk(response);
      }

      const newSession = await response.json();
      skipFetchSessionIdRef.current = newSession.id;
      await sendMessage(newSession.id, messageText);
      window.dispatchEvent(new Event("sessions-updated"));
      navigate(`/session/${newSession.id}`);
    } catch (error) {
      console.error("Create session failed", error);
      setStatusText(normalizeUnknownError(error, "Unable to create session.").message);
    }
  };

  const resetInactivityTimer = (abortController: AbortController) => {
    clearInactivityTimer();
    inactivityTimerRef.current = setTimeout(() => {
      abortController.abort();
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === "assistant") {
          last.status = "failed";
          last.error = "Response timed out (inactivity).";
        }
        return next;
      });
      setIsTyping(false);
      setStatusText("Response timed out.");
      clearInactivityTimer();
    }, 100000);
  };

  const sendMessage = async (
    targetSessionId: string,
    messageText: string,
    isResend = false,
  ) => {
    const userMsgId = isResend
      ? messages[messages.length - 2]?.id || Date.now().toString()
      : Date.now().toString();
    const assistantMsgId = (Date.now() + 1).toString();

    let nextMessages: Message[];

    if (isResend) {
      nextMessages = messages.filter(
        (msg) => msg.id !== messages[messages.length - 1]?.id,
      );
      const userIndex = nextMessages.findIndex((msg) => msg.id === userMsgId);
      if (userIndex !== -1) {
        nextMessages[userIndex].status = "sending";
      }
    } else {
      nextMessages = [
        ...messages,
        {
          id: userMsgId,
          role: "user",
          content: messageText,
          status: "success",
        },
      ];
    }

    nextMessages.push({
      id: assistantMsgId,
      role: "assistant",
      content: "",
      status: "sending",
    });

    setMessages(nextMessages);
    setIsTyping(true);
    setStatusText("Assistant is typing...");

    const abortController = new AbortController();
    currentAbortControllerRef.current = abortController;
    resetInactivityTimer(abortController);

    try {
      const response = await fetch(
        `${backendBaseUrl}/chat/sessions/${targetSessionId}/message`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({ message: messageText }),
          signal: abortController.signal,
        },
      );

      if (!response.ok) {
        if (response.status === 401) {
          clearStoredUser();
          setIsAuthenticated(false);
          navigate("/auth");
          return;
        }
        await ensureOk(response);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream available");

      const decoder = new TextDecoder();
      let done = false;
      let accumulated = "";

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
            if (last && last.role === "assistant") {
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
        if (last && last.role === "assistant") {
          last.status = "success";
        }
        return next;
      });
      if (currentAbortControllerRef.current === abortController) {
        currentAbortControllerRef.current = null;
      }
      if (!isMountedRef.current) return;
      setIsTyping(false);
      setStatusText("Ready");
    } catch (error: unknown) {
      if (currentAbortControllerRef.current === abortController) {
        currentAbortControllerRef.current = null;
      }
      clearInactivityTimer();
      if (!isMountedRef.current) return;
      setIsTyping(false);
      setStatusText("Response failed.");
      const errorName =
        error instanceof Error ? error.name : "UnknownError";
      const errorMessage =
        normalizeUnknownError(error, "Connection error").message;
      if (errorName !== "AbortError") {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") {
            last.status = "failed";
            last.error = errorMessage || "Connection error";
          }
          return next;
        });
      }
    }
  };

  const startStream = async (messageText: string, isResend = false) => {
    if (!sessionId) return;
    if (sessionId === "new") {
      await createSessionAndSend(messageText);
      return;
    }

    await sendMessage(sessionId, messageText, isResend);
  };

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isTyping) return;
    setInput("");
    startStream(trimmed);
  };

  const handleResend = () => {
    const userMessages = messages.filter((msg) => msg.role === "user");
    if (!userMessages.length) return;
    const lastUser = userMessages[userMessages.length - 1];
    startStream(lastUser.content, true);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const renderMarkdown = (text: string) => {
    if (!text) return null;
    const lines = text.split("\n");
    return lines.map((line, idx) => {
      if (line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
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
        const classes =
          [
            "font-semibold text-[var(--text-primary)] my-3 text-xl leading-snug",
            "font-semibold text-[var(--text-primary)] my-2 text-lg leading-snug",
            "font-semibold text-[var(--text-primary)] my-1.5 text-base leading-snug",
          ][level - 1] ||
          "font-semibold text-[var(--text-primary)] my-1.5 text-base leading-snug";
        return (
          <HeadingTag key={idx} className={classes}>
            {parseInlineMarkdown(content)}
          </HeadingTag>
        );
      }

      return (
        <p
          key={idx}
          className="min-h-[1.5rem] text-[15px] leading-[1.6] my-1 text-[var(--text-secondary)]"
        >
          {parseInlineMarkdown(line)}
        </p>
      );
    });
  };

  const parseInlineMarkdown = (text: string) => {
    const parts: Array<string | JSX.Element> = [];
    const regex =
      /(https?:\/\/[^\s<>()]+[^\s<>().,;:!?])|(\*\*|__)(.*?)\2|(\*|_)(.*?)\4|(`)(.*?)\6/g;
    let match: RegExpExecArray | null;
    let lastIndex = 0;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }

      if (match[1]) {
        parts.push(
          <a
            key={`a-${match.index}`}
            href={match[1]}
            target="_blank"
            rel="noreferrer"
            className="break-words font-medium text-[var(--text-primary)] underline decoration-[var(--text-muted)] underline-offset-4 transition hover:decoration-[var(--text-primary)]"
          >
            {match[1]}
          </a>,
        );
      } else if (match[3]) {
        parts.push(
          <strong
            key={`b-${match.index}`}
            className="font-semibold text-[var(--text-primary)]"
          >
            {match[3]}
          </strong>,
        );
      } else if (match[5]) {
        parts.push(
          <em key={`i-${match.index}`} className="italic">
            {match[5]}
          </em>,
        );
      } else if (match[7]) {
        parts.push(
          <code
            key={`c-${match.index}`}
            className="rounded bg-[var(--surface-elevated)] px-1.5 py-0.5 font-mono text-xs text-[var(--text-primary)] border border-[var(--border)]"
          >
            {match[7]}
          </code>,
        );
      }

      lastIndex = regex.lastIndex;
    }

    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  };

  const splitSources = (text: string) => {
    const match = text.match(/\n?Sources:\s*/i);
    if (!match || typeof match.index !== "number") {
      return { body: text, sources: [] as string[] };
    }
    const body = text.slice(0, match.index).trimEnd();
    const sourcesText = text.slice(match.index + match[0].length).trim();
    const sources = sourcesText
      .split(/\n+/)
      .map((line) => line.replace(/^[-*]\s*/, "").trim())
      .filter(Boolean);
    return { body, sources };
  };

  const statusBadge = useMemo(() => {
    if (isTyping) {
      return (
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-elevated)] px-3 py-1 text-xs font-medium text-[var(--text-primary)]">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Thinking...
        </div>
      );
    }

    return (
      <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
        <Clock3 size={14} />
        {statusText}
      </div>
    );
  }, [isTyping, statusText]);

  return (
    <div className="flex h-full flex-col bg-[var(--canvas)] text-[var(--text-primary)]">
      <div className="flex items-center justify-end border-b border-[var(--border)] bg-[var(--canvas)] px-4 py-3 md:px-6">
        {statusBadge}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        <div className="h-full overflow-y-auto px-4 py-8 md:px-6">
          <div className="mx-auto max-w-[800px] space-y-8">
            {loadingMessages ? (
              <div className="flex h-[60vh] items-center justify-center">
                <div className="flex items-center gap-3 text-sm text-[var(--text-secondary)]">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--text-muted)] border-t-[var(--text-primary)]" />
                  <span>Loading chat history...</span>
                </div>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex min-h-[58vh] flex-col items-center justify-center text-center">
                <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)]">
                  <Bot size={22} />
                </div>
                <h1 className="max-w-2xl text-2xl font-semibold leading-tight tracking-normal text-[var(--text-primary)] md:text-[32px] md:leading-[1.2]">
                  What would you like to research?
                </h1>
                <div className="mt-7 flex max-w-2xl flex-wrap justify-center gap-2">
                  {[
                    "Summarize recent papers",
                    "Compare research clusters",
                    "Find representative methods",
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => setInput(prompt)}
                      className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] px-3 py-2 text-sm text-[var(--text-secondary)] transition hover:border-[var(--text-primary)] hover:text-[var(--text-primary)]"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-8">
                {messages.map((message) => {
                  const isUser = message.role === "user";
                  const isFailed = message.status === "failed";
                  const showThinking =
                    !isUser &&
                    message.status === "sending" &&
                    !message.content.trim();
                  return (
                    <div
                      key={message.id}
                      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[92%] rounded-2xl border px-5 py-4 md:max-w-[82%] ${
                          isUser
                            ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--canvas)]"
                            : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)]"
                        }`}
                      >
                        <div className="mb-3 flex items-center gap-3">
                          <div
                            className={`flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold ${
                              isUser
                                ? "border-black/15 bg-[var(--canvas)] text-[var(--text-primary)]"
                                : "border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--text-primary)]"
                            }`}
                          >
                            {isUser ? (
                              <span>U</span>
                            ) : (
                              <Bot size={16} />
                            )}
                          </div>
                          <div
                            className={`text-xs font-semibold uppercase tracking-[0.05em] ${
                              isUser ? "text-[var(--canvas)]/60" : "text-[var(--text-muted)]"
                            }`}
                          >
                            {isUser ? "You" : "Assistant"}
                          </div>
                          {showThinking && (
                            <div className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface-elevated)] px-2 py-0.5 text-[11px] font-medium normal-case tracking-normal text-[var(--text-primary)]">
                              <Loader2 className="h-3 w-3 animate-spin" />
                              Thinking...
                            </div>
                          )}
                        </div>
                        {isFailed ? (
                          <div className="rounded-lg border border-[var(--danger)] bg-[var(--danger-soft)] p-3 text-xs text-[var(--danger)]">
                            <div className="flex items-center gap-2">
                              <AlertCircle size={14} />
                              <span>
                                {message.error ||
                                  "The response failed. Please try again."}
                              </span>
                            </div>
                          </div>
                        ) : isUser ? (
                          <p className="whitespace-pre-wrap text-[15px] leading-[1.6] text-[var(--canvas)]">
                            {message.content}
                          </p>
                        ) : (
                          <div className="max-w-none text-[15px] leading-[1.6] text-[var(--text-secondary)]">
                            {(() => {
                              const parsed = splitSources(message.content);
                              return (
                                <>
                                  {renderMarkdown(parsed.body)}
                                  {parsed.sources.length ? (
                                    <div className="mt-4 rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-3">
                                      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">Sources</p>
                                      <div className="space-y-2">
                                        {parsed.sources.map((source, index) => (
                                          <div key={`${source}-${index}`} className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs text-[var(--text-secondary)]">
                                            {parseInlineMarkdown(source)}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null}
                                </>
                              );
                            })()}
                          </div>
                        )}
                        {isFailed && (
                          <button
                            type="button"
                            onClick={handleResend}
                            className="mt-4 inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--text-primary)] px-3 py-1.5 text-[11px] font-semibold text-[var(--canvas)] transition hover:opacity-90"
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

      <div className="border-t border-[var(--border)] bg-[var(--canvas)] px-4 py-4 md:px-6">
        <div className="mx-auto max-w-[800px]">
          <div className="flex items-end gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-elevated)] px-3 py-3 transition focus-within:border-[var(--text-primary)]">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about papers, clusters, methods, or summaries..."
              className="max-h-[140px] min-h-10 flex-1 resize-none bg-transparent px-0 py-2 text-[15px] leading-6 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
            />
            <button
              type="button"
              disabled={!input.trim() || isTyping}
              onClick={handleSend}
              className="mb-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--text-primary)] text-[var(--canvas)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:bg-[var(--surface-high)] disabled:text-[var(--text-muted)]"
              aria-label="Send message"
            >
              <Send size={17} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
