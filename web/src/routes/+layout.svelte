<script lang="ts">
	export const ssr = false;
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';
	import { panelKey, toastMessage, loadKey, clearKey } from '$lib/stores';
	import Badge from '$lib/components/ui/badge.svelte';
	import { health } from '$lib/api';

	let { children }: { children?: import('svelte').Snippet } = $props();

	onMount(() => { loadKey(); });

	let serverOk = $state(false);
	let version = $state('');
	let mobileOpen = $state(false);

	onMount(async () => {
		try {
			const h = await health();
			serverOk = h.status === 'ok';
			version = h.version;
		} catch { serverOk = false; }
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

	function logout() { clearKey(); goto(base + '/login'); }
	function closeSidebar() { mobileOpen = false; }
</script>

<div class="flex flex-col xl:flex-row h-screen">
<!-- mobile top bar -->
<div class="xl:hidden flex items-center gap-3 px-4 py-3 border-b border-zinc-800 bg-[#121214] shrink-0">
	<button aria-label="Toggle menu" onclick={() => (mobileOpen = !mobileOpen)} class="text-zinc-400 hover:text-zinc-200 p-1">
		<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
		</svg>
	</button>
	<h1 class="text-lg font-bold text-indigo-400">DemumuMind</h1>
	<div class="ml-auto flex items-center gap-2">
		{#if serverOk}
			<span class="w-2 h-2 rounded-full bg-green-500"></span>
		{:else}
			<span class="w-2 h-2 rounded-full bg-red-500"></span>
		{/if}
		{#if $panelKey}
			<button onclick={logout} class="text-xs text-zinc-500 hover:text-zinc-300">Logout</button>
		{:else}
			<a href={base + '/login'} class="text-xs text-indigo-400 hover:text-indigo-300">Login</a>
		{/if}
	</div>
</div>

<!-- sidebar overlay (mobile) + sidebar (desktop) -->
<div class="flex flex-1 overflow-hidden">
<aside
	class="xl:flex xl:flex-col xl:w-56 xl:border-r xl:border-zinc-800 xl:bg-[#121214] xl:shrink-0 xl:static
		fixed inset-y-0 left-0 z-40 w-64 bg-[#121214] border-r border-zinc-800 transform transition-transform duration-200
		{mobileOpen ? 'translate-x-0' : '-translate-x-full'} xl:translate-x-0"
>
	<div class="p-4 border-b border-zinc-800 flex items-center justify-between">
		<div>
			<h1 class="text-lg font-bold text-indigo-400">DemumuMind</h1>
			<p class="text-xs text-zinc-500">Panel v{version || '0.1.0'}</p>
		</div>
		<button aria-label="Close menu" onclick={closeSidebar} class="xl:hidden text-zinc-500 hover:text-zinc-300 p-1">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
			</svg>
		</button>
	</div>
	<nav class="flex-1 p-2 space-y-1">
		{#each nav as item}
			<a
				href={base + item.href}
				onclick={closeSidebar}
				class="block rounded-lg px-3 py-2 text-sm transition-colors {$page.url.pathname === base + item.href ? 'bg-indigo-600/20 text-indigo-300' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'}"
			>{item.label}</a>
		{/each}
	</nav>
	<div class="p-3 border-t border-zinc-800 hidden xl:block">
		<div class="flex items-center gap-2 mb-2">
			{#if serverOk}
				<Badge variant="success">Online</Badge>
			{:else}
				<Badge variant="danger">Offline</Badge>
			{/if}
		</div>
		{#if $panelKey}
			<button onclick={logout} class="text-xs text-zinc-500 hover:text-zinc-300">Logout</button>
		{:else}
			<a href={base + '/login'} class="text-xs text-indigo-400 hover:text-indigo-300">Login</a>
		{/if}
	</div>
</aside>

<!-- overlay backdrop (mobile) -->
{#if mobileOpen}
	<div
		role="button"
		tabindex="-1"
		aria-label="Close menu"
		onclick={closeSidebar}
		onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); closeSidebar(); } }}
		class="xl:hidden fixed inset-0 z-30 bg-black/50"
	></div>
{/if}

<main class="flex-1 overflow-auto p-4 sm:p-6">
	{@render children?.()}
</main>
</div>
</div>

{#if $toastMessage}
	<div class="fixed bottom-4 right-4 z-50 rounded-lg px-4 py-3 text-sm shadow-lg
		{$toastMessage.type === 'success' ? 'bg-green-700 text-white' : $toastMessage.type === 'error' ? 'bg-red-700 text-white' : 'bg-zinc-800 text-zinc-100'}">
		{$toastMessage.text}
	</div>
{/if}