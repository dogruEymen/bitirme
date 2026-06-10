import type {ChatResponse} from './../types/chat-response.ts'

export interface ApiError {
	status: number | null;
	message: string;
	code: 'auth' | 'network' | 'http' | 'unknown';
	detail?: unknown;
}

export function getBackendBaseUrl(): string {
	const hostname = window.location.hostname;
	const backendHost = hostname === 'localhost' || hostname === '::1' ? '127.0.0.1' : hostname;
	return `http://${backendHost}:8000`;
}

export async function parseApiError(response: Response): Promise<ApiError> {
	let detail: unknown = null;
	try {
		detail = await response.json();
	} catch {
		detail = null;
	}

	const detailMessage =
		typeof detail === 'object' && detail && 'detail' in detail
			? String((detail as { detail: unknown }).detail)
			: null;

	return {
		status: response.status,
		message: detailMessage || `Backend returned HTTP ${response.status}`,
		code: response.status === 401 ? 'auth' : 'http',
		detail,
	};
}

export function normalizeUnknownError(error: unknown, fallback = 'Backend is unavailable.'): ApiError {
	if (typeof error === 'object' && error && 'status' in error && 'message' in error) {
		return error as ApiError;
	}

	if (error instanceof Error) {
		return {
			status: null,
			message: error.message || fallback,
			code: error.name === 'AbortError' ? 'unknown' : 'network',
		};
	}

	return {
		status: null,
		message: fallback,
		code: 'unknown',
	};
}

export async function ensureOk(response: Response): Promise<Response> {
	if (!response.ok) {
		throw await parseApiError(response);
	}
	return response;
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
