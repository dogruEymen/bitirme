import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles } from 'lucide-react';
import type { ChatMessage } from '../lib/types';

const sampleMessages: ChatMessage[] = [
  {
    id: '1',
    role: 'assistant',
    content: 'Welcome to AcademicAI Chat! I can help you explore academic paper clusters, find relevant research, and answer questions about the latest publications. What would you like to know?',
    created_at: new Date(Date.now() - 60000).toISOString(),
  },
];

const botResponses = [
  'Based on the latest cluster analysis, Natural Language Processing continues to dominate with 342 papers this quarter, showing a 15% increase in publications focused on large language model scaling laws and efficient inference techniques.',
  'The Computer Vision cluster has seen significant growth in foundation model research. Papers on Vision Transformers and segment-anything architectures represent the highest-impact contributions this period.',
  'Our analysis reveals a strong convergence between Multi-Modal Learning and Generative Models clusters, with cross-referenced papers increasing by 28%. This suggests an emerging research frontier at their intersection.',
  'The Reinforcement Learning cluster shows promising developments in offline RL methods, particularly for safety-critical applications. Reward modeling for alignment remains the most cited subtopic.',
  'Medical AI publications demonstrate the highest real-world impact score among all clusters. Drug discovery with deep learning and privacy-preserving federated approaches lead in clinical translation potential.',
  'Quantum Computing remains the smallest but fastest-growing cluster at 89 papers. Quantum error correction with surface codes represents a critical milestone achievement this quarter.',
  'Sustainability-focused AI research has doubled its publication rate compared to last year. Climate modeling and smart grid optimization papers show the strongest interdisciplinary connections.',
  'The Explainable AI cluster is increasingly intersecting with AI Ethics & Governance. Papers on fairness auditing and algorithmic accountability are driving new regulatory frameworks.',
];

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(sampleMessages);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const responseIndex = useRef(0);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSend = () => {
    if (!input.trim()) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    setTimeout(() => {
      const botMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: botResponses[responseIndex.current % botResponses.length],
        created_at: new Date().toISOString(),
      };
      responseIndex.current += 1;
      setIsTyping(false);
      setMessages((prev) => [...prev, botMsg]);
    }, 1500 + Math.random() * 1000);
  };

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      {/* Header */}
      <header className="h-14 bg-white border-b border-slate-200 flex items-center px-6 shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-emerald-500" />
          <h1 className="text-sm font-semibold text-slate-800">Academic Research Assistant</h1>
        </div>
        <span className="ml-3 px-2 py-0.5 bg-emerald-50 text-emerald-600 text-xs font-medium rounded-full">
          Online
        </span>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center shrink-0 mt-1">
                  <Bot size={16} className="text-white" />
                </div>
              )}
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-slate-800 text-white rounded-br-md'
                    : 'bg-white border border-slate-200 text-slate-700 rounded-bl-md shadow-sm'
                }`}
              >
                {msg.content}
              </div>
              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-lg bg-slate-700 flex items-center justify-center shrink-0 mt-1">
                  <User size={16} className="text-slate-300" />
                </div>
              )}
            </div>
          ))}

          {/* Typing indicator */}
          {isTyping && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center shrink-0 mt-1">
                <Bot size={16} className="text-white" />
              </div>
              <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
                <div className="flex items-center gap-1">
                  <span className="text-xs text-slate-500 mr-2">Thinking</span>
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
        <div className="max-w-3xl mx-auto flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Ask about academic clusters, papers, or trends..."
            className="flex-1 h-10 px-4 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-400 transition-all"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="h-10 px-4 bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-300 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
          >
            <Send size={14} />
            <span className="hidden sm:inline">Send</span>
          </button>
        </div>
      </div>
    </div>
  );
}
