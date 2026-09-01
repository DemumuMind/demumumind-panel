<script lang="ts">
	export const ssr = false;
	import '../app.css';
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';
	import { panelKey, toastMessage, loadKey, clearKey } from '$lib/stores';
	import Badge from '$lib/components/ui/badge.svelte';
	import { health } from '$lib/api';
	import {
		LayoutDashboard,
		Bot,
		Boxes,
		Key,
		Play,
		BarChart3,
		Puzzle,
		Cable,
		Image,
		LogOut,
		Menu,
		X
	} from 'lucide-svelte';

	let { children }: { children?: import('svelte').Snippet } = $props();

	onMount(() => {
		loadKey();
		const key = get(panelKey);
		const isLoginPage = window.location.pathname.replace(/\/+$/, '') === (base + '/login').replace(/\/+$/, '');
		if (!key && !isLoginPage) {
			goto(base + '/login');
		}
	});

	afterNavigate(() => {
		const key = get(panelKey);
		const isLoginPage = get(page).url.pathname.replace(/\/+$/, '') === (base + '/login').replace(/\/+$/, '');
		if (!key && !isLoginPage) {
			goto(base + '/login');
		}
	});

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
		{ label: 'Dashboard', href: '/', icon: LayoutDashboard },
		{ label: 'Providers', href: '/providers', icon: Bot },
		{ label: 'Models', href: '/models', icon: Boxes },
		{ label: 'Keys', href: '/keys', icon: Key },
		{ label: 'Playground', href: '/playground', icon: Play },
		{ label: 'Usage', href: '/usage', icon: BarChart3 },
		{ label: 'Images', href: '/images', icon: Image },
		{ label: 'Plugins', href: '/plugins', icon: Puzzle },
		{ label: 'MCP', href: '/mcp', icon: Cable }
	];

	function logout() { clearKey(); goto(base + '/login'); }
	function closeSidebar() { mobileOpen = false; }

	function isActive(href: string) {
		return get(page).url.pathname.replace(/\/+$/, '') === (base + href).replace(/\/+$/, '');
	}
</script>

<div class="flex flex-col xl:flex-row h-screen bg-(--bg)">
	<!-- mobile top bar -->
	<div class="xl:hidden flex items-center gap-3 px-4 py-3 border-b border-(--border) bg-(--bg-card) shrink-0">
		<button aria-label="Toggle menu" onclick={() => (mobileOpen = !mobileOpen)} class="text-(--text-muted) hover:text-(--text) p-1">
			<Menu class="w-5 h-5" />
		</button>
		<div class="flex items-center gap-2">
			<div class="w-2 h-2 rounded-full bg-(--accent)"></div>
			<h1 class="text-lg font-bold bg-gradient-to-r from-(--accent) to-(--accent-2) bg-clip-text text-transparent">DemumuMind</h1>
		</div>
		<div class="ml-auto flex items-center gap-2">
			{#if serverOk}
				<span class="w-2 h-2 rounded-full bg-(--success)"></span>
			{:else}
				<span class="w-2 h-2 rounded-full bg-(--danger)"></span>
			{/if}
			{#if $panelKey}
				<button onclick={logout} class="text-(--text-faint) hover:text-(--text-muted) p-1">
					<LogOut class="w-4 h-4" />
				</button>
			{:else}
				<a href={base + '/login'} class="text-xs text-(--accent-hover) hover:text-(--accent)">Login</a>
			{/if}
		</div>
	</div>

	<div class="flex flex-1 overflow-hidden">
		<!-- sidebar overlay (mobile) + sidebar (desktop) -->
		<aside
			class="xl:flex xl:flex-col xl:w-56 xl:border-r xl:border-(--border) xl:bg-(--bg-card) xl:shrink-0 xl:static
				fixed inset-y-0 left-0 z-40 w-64 bg-(--bg-card) border-r border-(--border) transform transition-transform duration-200
				{mobileOpen ? 'translate-x-0' : '-translate-x-full'} xl:translate-x-0"
		>
			<div class="p-4 border-b border-(--border) flex items-center justify-between">
				<div class="flex items-center gap-2">
					<div class="w-8 h-8 rounded-lg bg-gradient-to-br from-(--accent) to-(--accent-2) flex items-center justify-center text-white font-bold text-sm">D</div>
					<div>
						<h1 class="text-base font-bold bg-gradient-to-r from-(--accent) to-(--accent-2) bg-clip-text text-transparent">DemumuMind</h1>
						<p class="text-xs text-(--text-faint)">Panel v{version || '0.2.0'}</p>
					</div>
				</div>
				<button aria-label="Close menu" onclick={closeSidebar} class="xl:hidden text-(--text-muted) hover:text-(--text) p-1">
					<X class="w-4 h-4" />
				</button>
			</div>
			<nav class="flex-1 p-2 space-y-0.5">
				{#each nav as item}
					<a
						href={base + item.href}
						onclick={closeSidebar}
						class="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-all duration-150
							{isActive(item.href)
								? 'bg-(--accent-soft) text-(--accent-hover) font-medium'
								: 'text-(--text-muted) hover:text-(--text) hover:bg-(--bg-hover)'}"
					>
						<svelte:component this={item.icon} class="w-4 h-4 shrink-0" />
						{item.label}
					</a>
				{/each}
			</nav>
			<div class="p-3 border-t border-(--border) hidden xl:block">
				<div class="rounded-lg bg-(--bg-elevated) border border-(--border) p-3">
					<div class="flex items-center gap-2 mb-2">
						{#if serverOk}
							<span class="w-2 h-2 rounded-full bg-(--success)"></span>
							<span class="text-xs text-(--success)">Online</span>
						{:else}
							<span class="w-2 h-2 rounded-full bg-(--danger)"></span>
							<span class="text-xs text-(--danger)">Offline</span>
						{/if}
					</div>
					{#if $panelKey}
						<button onclick={logout} class="flex items-center gap-2 text-xs text-(--text-faint) hover:text-(--text-muted) w-full">
							<LogOut class="w-3.5 h-3.5" />
							Logout
						</button>
					{:else}
						<a href={base + '/login'} class="flex items-center gap-2 text-xs text-(--accent-hover) hover:text-(--accent) w-full">
							Login
						</a>
					{/if}
				</div>
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
				class="xl:hidden fixed inset-0 z-30 bg-black/60"
			></div>
		{/if}

		<main class="flex-1 overflow-auto p-4 sm:p-6">
			{@render children?.()}
		</main>
	</div>
</div>

{#if $toastMessage}
	<div class="fixed bottom-4 right-4 z-50 rounded-lg px-4 py-3 text-sm shadow-(--shadow-lift)
		{$toastMessage.type === 'success' ? 'bg-emerald-700 text-white' : $toastMessage.type === 'error' ? 'bg-red-700 text-white' : 'bg-(--bg-elevated) border border-(--border) text-(--text)'}">
		{$toastMessage.text}
	</div>
{/if}