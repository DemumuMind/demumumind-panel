<script lang="ts">
	export const ssr = false;
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { panelKey, toastMessage, loadKey, clearKey, saveKey } from '$lib/stores';
	import Badge from '$lib/components/ui/badge.svelte';
	import { health } from '$lib/api';

	onMount(() => {
		loadKey();
	});

	let serverOk = $state(false);
	let version = $state('');

	onMount(async () => {
		try {
			const h = await health();
			serverOk = h.status === 'ok';
			version = h.version;
		} catch {
			serverOk = false;
		}
	});

	const nav = [
		{ label: 'Dashboard', href: '/' },
		{ label: 'Providers', href: '/providers' },
		{ label: 'Models', href: '/models' },
		{ label: 'Keys', href: '/keys' },
		{ label: 'Playground', href: '/playground' },
		{ label: 'Usage', href: '/usage' },
		{ label: 'Plugins', href: '/plugins' },
		{ label: 'MCP', href: '/mcp' }
	];

	function logout() {
		clearKey();
		goto('/login');
	}
</script>

<div class="flex h-screen">
	<aside class="w-56 border-r border-zinc-800 bg-[#121214] flex flex-col shrink-0">
		<div class="p-4 border-b border-zinc-800">
			<h1 class="text-lg font-bold text-indigo-400">DemumuMind</h1>
			<p class="text-xs text-zinc-500">Panel v{version || '0.1.0'}</p>
		</div>
		<nav class="flex-1 p-2 space-y-1">
			{#each nav as item}
				<a
					href={item.href}
					class="block rounded-lg px-3 py-2 text-sm transition-colors {$page.url.pathname === item.href ? 'bg-indigo-600/20 text-indigo-300' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'}"
					>{item.label}</a
				>
			{/each}
		</nav>
		<div class="p-3 border-t border-zinc-800">
			<div class="flex items-center gap-2 mb-2">
				{#if serverOk}
					<Badge variant="success">Online</Badge>
				{:else}
					<Badge variant="danger">Offline</Badge>
				{/if}
			</div>
			{#if $panelKey}
				<button onclick={logout} class="text-xs text-zinc-500 hover:text-zinc-300">Logout</button>
			{/if}
		</div>
	</aside>
	<main class="flex-1 overflow-auto p-6">
		<slot />
	</main>
</div>

{#if $toastMessage}
	<div class="fixed bottom-4 right-4 z-50 rounded-lg px-4 py-3 text-sm shadow-lg
		{$toastMessage.type === 'success' ? 'bg-green-700 text-white' : $toastMessage.type === 'error' ? 'bg-red-700 text-white' : 'bg-zinc-800 text-zinc-100'}">
		{$toastMessage.text}
	</div>
{/if}