import type {ChatResponse} from './../types/chat-response.ts'

export function getBackendBaseUrl(): string {
	const hostname = window.location.hostname;
	const backendHost = hostname === 'localhost' || hostname === '::1' ? '127.0.0.1' : hostname;
	return `http://${backendHost}:8000`;
}

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
