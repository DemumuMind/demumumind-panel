<script lang="ts">
	import { goto } from '$app/navigation';
	import { saveKey } from '$lib/stores';
	import Input from '$lib/components/ui/input.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Card from '$lib/components/ui/card.svelte';
	import { login } from '$lib/api';

	let key = $state('');
	let error = $state('');

	async function handleLogin() {
		error = '';
		try {
			await login(key);
			saveKey(key);
			goto('/');
		} catch (e: any) {
			error = e.message || 'Login failed';
		}
	}
</script>

<div class="flex items-center justify-center min-h-full p-4">
	<Card class="w-full max-w-md mx-4 sm:w-96">
		<h1 class="text-xl font-bold mb-2">DemumuMind</h1>
		<p class="text-sm text-zinc-400 mb-4">Enter your Panel API Key</p>
		{#if error}
			<div class="mb-3 text-sm text-red-400">{error}</div>
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