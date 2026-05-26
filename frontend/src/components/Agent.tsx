import './../App.css'
import {useState, useRef, useEffect} from 'react'
import MessageCard from './MessageCard'
import type {MessageCardProps} from './../types/message.ts'
import type {ChatResponse} from './../types/chat-response.ts'
import {postMessage} from './../api/client.ts'

const createMessageId = () => crypto.randomUUID();

export default function Agent(){
	const [messages, setMessages] = useState<MessageCardProps[]>([]);
	const [input, setInput] = useState("");
	const [isWaiting, setIsWaiting] = useState(false);
	const messagesEndRef = useRef<HTMLDivElement>(null);

	const sendMessage = async () => {
		const messageText = input.trim();
		if(messageText.length === 0 || isWaiting) return;

		const userMessage: MessageCardProps = {
			id: createMessageId(),
			text: messageText,
			sender: 'user',
			timestamp: new Date(),
		};

		setMessages(prev => [...prev, userMessage]);

		setInput("");
		setIsWaiting(true);

		try {
			const response: ChatResponse = await postMessage("http://127.0.0.1:8000/chat", messageText);
			const agentMessage: MessageCardProps = {
				id: createMessageId(),
				text: response.modelResponse,
				sender: 'agent',
				timestamp: new Date(),
			};

			setMessages(prev => [...prev, agentMessage]);
		} finally {
			setIsWaiting(false);
		}
	}

	useEffect(() => {
		messagesEndRef.current?.scrollIntoView({behavior: 'smooth'});
	}, [messages]);

	return(
	<>
		<h3 className="border-2 border-gray-100">AI Agent with RAG System</h3>
		
		<div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[50vw] h-[85vh] bg-white shadow-lg rounded-lg flex flex-col p-4">
		  <div className="flex-1 overflow-y-auto flex flex-col">		  
		  {messages.map( (msg) => (
			<MessageCard key={msg.id} {...msg}/>
		  ))}
		  <div ref={messagesEndRef} />
		  </div>

		  <div className="flex gap-2">
		  <input 
		    type="text"
		    value={input}
		    placeholder="Your message..."
		    className="h-[40px] w-4/5 px-10 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-800"
		    onChange={(e) => setInput(e.target.value)}
		  />
		  <button 
		  className="px-4 py-2 w-1/5 bg-white text-black border-2 border-blue-200 rounded-lg hover:bg-blue-500 hover:text-white transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
		  onClick={() => sendMessage()}
		  disabled={isWaiting}
		  >
		  {isWaiting ? 'waiting' : 'commit'}
		  </button>
		  </div>
		</div>
	</>
	);
}

