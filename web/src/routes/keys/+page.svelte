<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import Table from '$lib/components/ui/table.svelte';
	import EmptyState from '$lib/components/ui/empty-state.svelte';
	import { fetchKeys, createKey, deleteKey } from '$lib/api';
	import { showToast } from '$lib/stores';
	import { Key, Plus, Trash2 } from 'lucide-svelte';

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

<div class="flex items-center gap-2 mb-6">
	<Key class="w-5 h-5 text-(--accent)" />
	<h1 class="text-2xl font-bold text-(--text)">API Keys</h1>
</div>

<Card class="mb-6">
	<h2 class="text-sm font-semibold mb-3 text-(--text)">Generate Key</h2>
	<div class="flex flex-col sm:flex-row gap-3 items-end">
		<div class="w-full sm:w-32">
			<label for="key-budget" class="text-xs text-(--text-muted) block mb-1">Monthly budget (USD)</label>
			<Input id="key-budget" type="number" bind:value={budget} class="w-full" />
		</div>
		<Button onclick={add} disabled={busy}><Plus class="w-4 h-4" /> Generate</Button>
	</div>
	{#if newKey}
		<div class="mt-3 p-3 bg-(--accent-soft) border border-(--accent)/30 rounded-lg text-sm">
			<span class="font-bold text-(--accent-hover)">⚠️ Copy this key now:</span>
			<code class="block mt-1 text-(--accent-hover) break-all select-all">{newKey}</code>
		</div>
	{/if}
</Card>

<Card>
	<Table headers={['ID', 'Key hash (prefix)', 'Budget', 'Created', 'Actions']}>
		{#each keys as k}
			<tr class="border-b border-(--border)/50 hover:bg-(--bg-hover) transition-colors">
				<td class="py-2 px-3 text-(--text-muted) text-xs tabular-nums">{k.id.slice(0, 8)}…</td>
				<td class="py-2 px-3"><code class="text-xs text-(--text-muted)">{k.key_hash.slice(0, 12)}…</code></td>
				<td class="py-2 px-3 tabular-nums">${k.monthly_budget.toFixed(2)}</td>
				<td class="py-2 px-3 text-xs text-(--text-faint) tabular-nums">{new Date(k.created_at).toLocaleDateString()}</td>
				<td class="py-2 px-3 text-right">
					<Button variant="ghost" size="sm" onclick={() => remove(k.id)}><Trash2 class="w-3.5 h-3.5" /></Button>
				</td>
			</tr>
		{/each}
	</Table>
	{#if keys.length === 0}
		<EmptyState title="No keys" description="Generate your first API key.">
			{#snippet icon()}<Key class="w-5 h-5" />{/snippet}
		</EmptyState>
	{/if}
</Card>
