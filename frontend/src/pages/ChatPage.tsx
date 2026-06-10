import { useState, useEffect, useRef, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Send,
  Bot,
  AlertCircle,
  RotateCcw,
  Loader2,
  Clock3,
} from "lucide-react";
import { getBackendBaseUrl } from "../api/client";
import { getAuthHeaders, getStoredUser } from "../lib/auth";

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
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      currentAbortControllerRef.current?.abort();
      currentAbortControllerRef.current = null;
      setIsTyping(false);
      setStatusText("Ready");
    };
  }, []);

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
  }, [sessionId, isAuthenticated]);

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
        throw new Error("Unable to create session");
      }

      const newSession = await response.json();
      skipFetchSessionIdRef.current = newSession.id;
      await sendMessage(newSession.id, messageText);
      window.dispatchEvent(new Event("sessions-updated"));
      navigate(`/session/${newSession.id}`);
    } catch (error) {
      console.error("Create session failed", error);
      setStatusText("Unable to create session");
    }
  };

  const fetchMessages = async (sessionId: string) => {
    setLoadingMessages(true);
    setStatusText("Loading chat...");
    try {
      const response = await fetch(
        `${backendBaseUrl}/chat/sessions/${sessionId}/messages`,
        {
          headers: getAuthHeaders(),
        },
      );
      if (response.ok) {
        const data: Message[] = await response.json();
        setMessages(data.map((m) => ({ ...m, status: "success" })));
        setStatusText("Ready");
      } else {
        throw new Error(`Failed to load ${response.status}`);
      }
    } catch (error) {
      console.error("Failed to fetch messages", error);
      setStatusText("Unable to load chat");
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
        throw new Error(`HTTP ${response.status}`);
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
        error instanceof Error ? error.message : "Connection error";
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
            "font-semibold text-white my-3 text-xl leading-snug",
            "font-semibold text-white my-2 text-lg leading-snug",
            "font-semibold text-white my-1.5 text-base leading-snug",
          ][level - 1] ||
          "font-semibold text-white my-1.5 text-base leading-snug";
        return (
          <HeadingTag key={idx} className={classes}>
            {parseInlineMarkdown(content)}
          </HeadingTag>
        );
      }

      return (
        <p
          key={idx}
          className="min-h-[1.5rem] text-[15px] leading-[1.6] my-1 text-[#b4b4b4]"
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
            className="break-words font-medium text-white underline decoration-[#767676] underline-offset-4 transition hover:decoration-white"
          >
            {match[1]}
          </a>,
        );
      } else if (match[3]) {
        parts.push(
          <strong
            key={`b-${match.index}`}
            className="font-semibold text-white"
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
            className="rounded bg-[#171717] px-1.5 py-0.5 font-mono text-xs text-white border border-[#2f2f2f]"
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

  const statusBadge = useMemo(() => {
    if (isTyping) {
      return (
        <div className="inline-flex items-center gap-2 rounded-full border border-[#2f2f2f] bg-[#171717] px-3 py-1 text-xs font-medium text-white">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Thinking...
        </div>
      );
    }

    return (
      <div className="inline-flex items-center gap-2 rounded-full border border-[#2f2f2f] bg-[#0d0d0d] px-3 py-1 text-xs font-medium text-[#b4b4b4]">
        <Clock3 size={14} />
        {statusText}
      </div>
    );
  }, [isTyping, statusText]);

  return (
    <div className="flex h-full flex-col bg-black text-white">
      <div className="flex items-center justify-end border-b border-[#2f2f2f] bg-black px-4 py-3 md:px-6">
        {statusBadge}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        <div className="h-full overflow-y-auto px-4 py-8 md:px-6">
          <div className="mx-auto max-w-[800px] space-y-8">
            {loadingMessages ? (
              <div className="flex h-[60vh] items-center justify-center">
                <div className="flex items-center gap-3 text-sm text-[#b4b4b4]">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#767676] border-t-white" />
                  <span>Loading chat history...</span>
                </div>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex min-h-[58vh] flex-col items-center justify-center text-center">
                <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-full border border-[#2f2f2f] bg-[#0d0d0d] text-[#b4b4b4]">
                  <Bot size={22} />
                </div>
                <h1 className="max-w-2xl text-2xl font-semibold leading-tight tracking-normal text-white md:text-[32px] md:leading-[1.2]">
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
                      className="rounded-lg border border-[#2f2f2f] bg-[#171717] px-3 py-2 text-sm text-[#b4b4b4] transition hover:border-white hover:text-white"
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
                            ? "border-white bg-white text-black"
                            : "border-[#2f2f2f] bg-[#0d0d0d] text-[#b4b4b4]"
                        }`}
                      >
                        <div className="mb-3 flex items-center gap-3">
                          <div
                            className={`flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold ${
                              isUser
                                ? "border-black/15 bg-black text-white"
                                : "border-[#2f2f2f] bg-[#171717] text-white"
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
                              isUser ? "text-black/60" : "text-[#767676]"
                            }`}
                          >
                            {isUser ? "You" : "Assistant"}
                          </div>
                          {showThinking && (
                            <div className="inline-flex items-center gap-1.5 rounded-full border border-[#2f2f2f] bg-[#171717] px-2 py-0.5 text-[11px] font-medium normal-case tracking-normal text-white">
                              <Loader2 className="h-3 w-3 animate-spin" />
                              Thinking...
                            </div>
                          )}
                        </div>
                        {isFailed ? (
                          <div className="rounded-lg border border-[#93000a] bg-[#1f0f0f] p-3 text-xs text-[#ffb4ab]">
                            <div className="flex items-center gap-2">
                              <AlertCircle size={14} />
                              <span>
                                {message.error ||
                                  "The response failed. Please try again."}
                              </span>
                            </div>
                          </div>
                        ) : isUser ? (
                          <p className="whitespace-pre-wrap text-[15px] leading-[1.6] text-black">
                            {message.content}
                          </p>
                        ) : (
                          <div
                            className="max-w-none text-[15px] leading-[1.6] text-[#b4b4b4]"
                          >
                            {renderMarkdown(message.content)}
                          </div>
                        )}
                        {isFailed && (
                          <button
                            type="button"
                            onClick={handleResend}
                            className="mt-4 inline-flex items-center gap-2 rounded-lg border border-[#2f2f2f] bg-white px-3 py-1.5 text-[11px] font-semibold text-black transition hover:bg-[#e2e2e2]"
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

      <div className="border-t border-[#2f2f2f] bg-black px-4 py-4 md:px-6">
        <div className="mx-auto max-w-[800px]">
          <div className="flex items-end gap-3 rounded-2xl border border-[#2f2f2f] bg-[#171717] px-3 py-3 transition focus-within:border-white">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about papers, clusters, methods, or summaries..."
              className="max-h-[140px] min-h-10 flex-1 resize-none bg-transparent px-0 py-2 text-[15px] leading-6 text-white outline-none placeholder:text-[#767676]"
            />
            <button
              type="button"
              disabled={!input.trim() || isTyping}
              onClick={handleSend}
              className="mb-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-black transition hover:bg-[#e2e2e2] disabled:cursor-not-allowed disabled:bg-[#1f1f1f] disabled:text-[#767676]"
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
