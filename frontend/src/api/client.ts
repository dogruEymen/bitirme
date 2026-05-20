import type {ChatResponse} from './../types/chat-response.ts'

export default async function fetchDataWithTimeout(url: string, timeout = 10000){
	const controller = new AbortController();
	const timer = setTimeout(() => {
		controller.abort();
	}, timeout);

	try{
		const res = await fetch(url, {
			signal: controller.signal
		});

		if(!res.ok){
			throw new Error("HTTP " + res.status);
		}		

		return await res.json();
	}
	// }catch(error){
	// 	if(error.name === 'AbortError'){
	// 		console.log("Request timed out !");
	// 	}else{
	// 		console.log("Error: ", error);
	// 	}
	// }
	finally{
		clearTimeout(timer);
	}
}

export async function postMessage(
	url: string, 
	message: string
): Promise<ChatResponse>{
	const router_prompt = `
	You are an expert routing system.

	Your task is to decide whether the user query needs retrieval.

	Use RAG if:
	- the question references documents
	- asks for sources
	- asks about PDFs
	- asks for research papers
	- asks for citations
	- asks about uploaded files
	- requires factual grounding

	Use LLM if:
	- casual conversation
	- coding help
	- brainstorming
	- general knowledge
	- explanations
	- writing tasks

	Return ONLY:
	RAG
	or
	LLM

	Question:
	${message}`

	const router_response = await sendMessage(url, router_prompt);

	let data: ChatResponse;
	console.log(router_response.modelResponse?.trim());
	if(router_response.modelResponse?.trim() === 'RAG'){
		
		const retrievedContext = "";
		const ragPrompt = `Based on the following context:\n${retrievedContext}\n\nUser question: ${message}`;

		data = await sendMessage(url, ragPrompt);

	}else{
		data = await sendMessage(url, message);
	}

	return data;
}

async function sendMessage(url: string, message: string): Promise<ChatResponse> {
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
