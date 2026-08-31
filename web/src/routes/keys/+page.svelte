<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import { fetchKeys, createKey, deleteKey } from '$lib/api';
	import { showToast } from '$lib/stores';

	let keys = $state<any[]>([]);
	let budget = $state('0');
	let newKey = $state('');
	let busy = $state(false);

	async function load() {
		try {
			const data = await fetchKeys(100, 0);
			keys = data.items;
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}

	onMount(load);

	async function add() {
		busy = true;
		try {
			const r = await createKey({ monthly_budget: parseFloat(budget) || 0, model_mapping: {} });
			newKey = r.api_key;
			showToast('Key created! Copy it now — it will not be shown again.', 'success');
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			busy = false;
		}
	}

	async function remove(id: string) {
		try {
			await deleteKey(id);
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}
</script>

<h1 class="text-2xl font-bold mb-6">API Keys</h1>

<Card class="mb-6">
	<h2 class="text-sm font-semibold mb-3">Generate Key</h2>
	<div class="flex gap-3 items-end">
		<div>
			<label class="text-xs text-zinc-500 block mb-1">Monthly budget (USD)</label>
			<Input type="number" bind:value={budget} class="w-32" />
		</div>
		<Button onclick={add} disabled={busy}>Generate</Button>
	</div>
	{#if newKey}
		<div class="mt-3 p-3 bg-indigo-900/30 border border-indigo-700 rounded-lg text-sm">
			<span class="font-bold text-indigo-300">⚠️ Copy this key now:</span>
			<code class="block mt-1 text-indigo-200 break-all select-all">{newKey}</code>
		</div>
	{/if}
</Card>

<Card>
	<table class="w-full text-sm">
		<thead>
			<tr class="text-left text-zinc-400 border-b border-zinc-800">
				<th class="py-2">ID</th>
				<th>Key hash (prefix)</th>
				<th>Budget</th>
				<th>Created</th>
				<th class="text-right">Actions</th>
			</tr>
		</thead>
		<tbody>
			{#each keys as k}
				<tr class="border-b border-zinc-800/50">
					<td class="py-2 text-zinc-400 text-xs">{k.id.slice(0, 8)}…</td>
					<td><code class="text-xs">{k.key_hash.slice(0, 12)}…</code></td>
					<td>${k.monthly_budget.toFixed(2)}</td>
					<td class="text-xs text-zinc-400">{new Date(k.created_at).toLocaleDateString()}</td>
					<td class="text-right">
						<button onclick={() => remove(k.id)} class="text-xs text-red-400 hover:text-red-300">Revoke</button>
					</td>
				</tr>
			{/each}
			{#if keys.length === 0}
				<tr><td colspan="5" class="py-4 text-center text-zinc-500">No keys</td></tr>
			{/if}
		</tbody>
	</table>
</Card>