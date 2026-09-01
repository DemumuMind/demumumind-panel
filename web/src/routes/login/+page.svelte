<script lang="ts">
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';
	import { saveKey } from '$lib/stores';
	import Input from '$lib/components/ui/input.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Card from '$lib/components/ui/card.svelte';
	import { login } from '$lib/api';
	import { Lock } from 'lucide-svelte';

	let key = $state('');
	let error = $state('');

	async function handleLogin() {
		error = '';
		try {
			await login(key);
			saveKey(key);
			goto(base || '/');
		} catch (e: any) {
			error = e.message || 'Login failed';
		}
	}
</script>

<div class="flex items-center justify-center min-h-full p-4 bg-(--bg)">
	<Card class="w-full max-w-md mx-4 sm:w-96">
		<div class="flex flex-col items-center text-center mb-6">
			<div class="w-12 h-12 rounded-xl bg-gradient-to-br from-(--accent) to-(--accent-2) flex items-center justify-center text-white mb-3">
				<Lock class="w-6 h-6" />
			</div>
			<h1 class="text-xl font-bold bg-gradient-to-r from-(--accent) to-(--accent-2) bg-clip-text text-transparent">DemumuMind</h1>
			<p class="text-sm text-(--text-faint) mt-1">Enter your Panel API Key</p>
		</div>
		{#if error}
			<div class="mb-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-3 py-2">{error}</div>
		{/if}
		<form onsubmit={(e) => { e.preventDefault(); handleLogin(); }}>
			<Input
				type="password"
				placeholder="PANEL_API_KEY"
				bind:value={key}
				class="mb-3"
			/>
			<Button type="submit" disabled={!key} class="w-full">Login</Button>
		</form>
	</Card>
</div>
