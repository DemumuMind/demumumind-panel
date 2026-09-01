import { PUBLIC_API_URL } from '$env/static/public';
import { panelKey } from '$lib/stores';
import { get } from 'svelte/store';

const BASE = PUBLIC_API_URL || '';

async function request(path: string, opts: RequestInit = {}): Promise<Response> {
	const key = get(panelKey);
	const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) };
	if (key) {
		headers['Authorization'] = `Bearer ${key}`;
	}
	if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
		headers['Content-Type'] = 'application/json';
	}
	return fetch(`${BASE}${path}`, { ...opts, headers });
}

export async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
	const res = await request(path, { signal });
	if (!res.ok) {
		const err = await res.json().catch(() => ({ error: res.statusText }));
		throw new Error(err.error || res.statusText);
	}
	return res.json();
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
	const res = await request(path, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({ error: res.statusText }));
		throw new Error(err.error || res.statusText);
	}
	return res.json();
}

export async function del<T>(path: string): Promise<T> {
	const res = await request(path, { method: 'DELETE' });
	if (!res.ok) {
		const err = await res.json().catch(() => ({ error: res.statusText }));
		throw new Error(err.error || res.statusText);
	}
	return res.json();
}

export async function health(): Promise<{ status: string; version: string; checks: Record<string, string> }> {
	return getJSON('/health');
}

export async function login(key: string): Promise<void> {
	await postJSON('/v1/auth/login', { panel_api_key: key });
}

export async function fetchProviders(limit = 100, offset = 0) {
	return getJSON<{ items: any[]; total: number }>(`/v1/admin/providers?limit=${limit}&offset=${offset}`);
}

export async function createProvider(data: any) {
	return postJSON('/v1/admin/providers', data);
}

export async function deleteProvider(id: string) {
	return del(`/v1/admin/providers/${id}`);
}

export async function testProvider(id: string): Promise<{ ok: boolean; models: string[]; message?: string }> {
	return postJSON(`/v1/admin/providers/${id}/test`, {});
}

export async function discoverProvider(id: string, test = false) {
	return postJSON<any>(`/v1/admin/providers/${id}/discover${test ? '?test=1' : ''}`, {});
}

export async function testProviderModel(id: string, internalModel: string) {
	return postJSON<any>(`/v1/admin/providers/${id}/models/${encodeURIComponent(internalModel)}/test`, {});
}

export async function fetchProviderKeys(id: string) {
	return getJSON<any[]>(`/v1/admin/providers/${id}/keys`);
}

export async function addProviderKey(id: string, apiKey: string) {
	return postJSON<any>(`/v1/admin/providers/${id}/keys`, { api_key: apiKey });
}

export async function deleteProviderKey(providerId: string, keyId: string) {
	return del(`/v1/admin/providers/${providerId}/keys/${keyId}`);
}

export async function runCleanup() {
	return postJSON<any>('/v1/admin/cleanup', {});
}

export async function fetchModels(limit = 100, offset = 0) {
	return getJSON<{ items: any[]; total: number }>(`/v1/admin/models?limit=${limit}&offset=${offset}`);
}

export async function createModel(data: any) {
	return postJSON('/v1/admin/models', data);
}

export async function deleteModel(id: string) {
	return del(`/v1/admin/models/${id}`);
}

export async function fetchKeys(limit = 100, offset = 0) {
	return getJSON<{ items: any[]; total: number }>(`/v1/admin/keys?limit=${limit}&offset=${offset}`);
}

export async function createKey(data: any) {
	return postJSON<{ id: string; api_key: string }>('/v1/admin/keys', data);
}

export async function deleteKey(id: string) {
	return del(`/v1/admin/keys/${id}`);
}

export async function seed() {
	return postJSON('/v1/admin/seed', {});
}

export async function chatCompletions(body: any) {
	return postJSON<any>('/v1/chat/completions', body);
}

export async function* streamChat(
	body: any
): AsyncGenerator<{ content?: string; reasoning?: string }> {
	const key = get(panelKey);
	const headers: Record<string, string> = { 'Content-Type': 'application/json' };
	if (key) headers['Authorization'] = `Bearer ${key}`;
	const res = await fetch(`${BASE}/v1/chat/completions`, {
		method: 'POST',
		headers,
		body: JSON.stringify({ ...body, stream: true })
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({ error: res.statusText }));
		throw new Error(err.error || res.statusText);
	}
	if (!res.body) throw new Error('no response stream');
	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	while (true) {
		const { done, value } = await reader.read();
		if (done) break;
		buffer += decoder.decode(value, { stream: true });
		const lines = buffer.split('\n');
		buffer = lines.pop() || '';
		for (const line of lines) {
			const trimmed = line.trim();
			if (!trimmed.startsWith('data:')) continue;
			const data = trimmed.slice(5).trim();
			if (data === '[DONE]') return;
			try {
				const parsed = JSON.parse(data);
				const delta = parsed.choices?.[0]?.delta || {};
				const out: { content?: string; reasoning?: string } = {};
				if (typeof delta.content === 'string' && delta.content) out.content = delta.content;
				if (typeof delta.reasoning_content === 'string' && delta.reasoning_content)
					out.reasoning = delta.reasoning_content;
				if (out.content !== undefined || out.reasoning !== undefined) yield out;
			} catch {
				// skip malformed/keepalive lines
			}
		}
	}
}

export async function fetchUsage(limit = 100, offset = 0) {
	return getJSON<{ items: any[]; total: number }>(`/v1/usage?limit=${limit}&offset=${offset}`);
}

export async function fetchPlugins() {
	return getJSON<any[]>('/v1/admin/plugins');
}

export async function uploadPlugin(name: string, signature: string, file: File) {
	const form = new FormData();
	form.append('payload', file);
	const res = await request(`/v1/admin/plugins/upload`, {
		method: 'POST',
		headers: { 'X-Plugin-Name': name, 'X-Plugin-Signature': signature },
		body: form
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({ error: res.statusText }));
		throw new Error(err.error || res.statusText);
	}
	return res.json();
}