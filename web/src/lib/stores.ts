import { writable } from 'svelte/store';

function readStoredKey(): string {
	if (typeof localStorage !== 'undefined') {
		return localStorage.getItem('panel_api_key') || '';
	}
	return '';
}

export const panelKey = writable<string>(readStoredKey());
export const requestId = writable<string>('');
export const toastMessage = writable<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

export function showToast(text: string, type: 'success' | 'error' | 'info' = 'info') {
	toastMessage.set({ text, type });
	setTimeout(() => toastMessage.set(null), 3000);
}

export function loadKey() {
	const saved = readStoredKey();
	if (saved) panelKey.set(saved);
}

export function saveKey(key: string) {
	panelKey.set(key);
	if (typeof localStorage !== 'undefined') {
		localStorage.setItem('panel_api_key', key);
	}
}

export function clearKey() {
	panelKey.set('');
	if (typeof localStorage !== 'undefined') {
		localStorage.removeItem('panel_api_key');
	}
}