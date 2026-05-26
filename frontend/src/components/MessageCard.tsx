import './../App.css'
import type {MessageCardProps} from './../types/message.ts'

export default function MessageCard(props: MessageCardProps){
	const isUser = props.sender === 'user';

	return(
		<div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-2`}>
			<div className={`
				max-w-[70%] 
				px-4 
				py-2 
				rounded-2xl 
				${isUser 
					? 'bg-blue-500 text-white rounded-br-none' 
					: 'bg-gray-200 text-black rounded-bl-none'
				}
				shadow-sm
			`}>
				<p className="text-sm">{props.text}</p>
				{props.timestamp && (
					<span className="text-xs opacity-70 mt-1 block">
						{props.timestamp.toLocaleTimeString()}
					</span>
				)}
			</div>
		</div>
	);
}
