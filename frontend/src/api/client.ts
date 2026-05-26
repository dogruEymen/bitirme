import type {ChatResponse} from './../types/chat-response.ts'

export async function postMessage(
	url: string, 
	message: string
): Promise<ChatResponse>{
	const response = await fetch(url, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ message })
	});
	
	if (!response.ok) {
		throw new Error(`HTTP ${response.status}`);
	}
	
	return response.json();
}
